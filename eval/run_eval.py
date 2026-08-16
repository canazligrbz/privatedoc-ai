"""
DOĞRULUK DEĞERLENDİRME ARACI
============================

eval/testset.yaml içindeki soruları çalıştırır ve ölçer:

  * Ret Doğruluğu (Refusal Accuracy) — belgede olmayan soruyu reddetti mi?
  * Yanlış Ret Oranı (False Refusal) — cevaplanabilir soruyu boşuna reddetti mi?
  * Kaynak İsabeti (Citation Precision) — doğru belgeye atıf verdi mi?
  * Anahtar Kelime Kapsaması — beklenen bilgiyi içeriyor mu?
  * Yasaklı İfade İhlali — tuzağa düştü mü?
  * Gecikme (p50 / p95)

Parametre taraması (grid search) ile en iyi ayarları bulmak için:
    python eval/run_eval.py --sweep

Tekil çalıştırma:
    python eval/run_eval.py
    python eval/run_eval.py --out eval/sonuc.json
"""

from __future__ import annotations

import argparse
import itertools
import json
import statistics
import sys
import time
from pathlib import Path
from typing import Any, Dict, List

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import yaml  # noqa: E402

from src.airgap import enforce_airgap  # noqa: E402
from src.config import load_config  # noqa: E402

CFG = load_config()
enforce_airgap(
    allowed_hosts=CFG.get_path("security.allowed_hosts", []),
    block_network=bool(CFG.get_path("security.block_outbound_network", True)),
)

from src.rag_engine import RAGEngine  # noqa: E402


def normalize(s: str) -> str:
    return (s or "").lower().replace("i̇", "i").replace("İ", "i")


# LLM erişilemediğinde motorun kullanıcıya döndürdüğü hata metninin izleri.
# Bu bir "yanlış cevap" değil, ALTYAPI KESİNTİSİDİR; ölçüme karıştırılmamalıdır.
_OUTAGE_MARKERS = (
    "yerel llm sunucusuna ulaşılamadı",
    "llm isteği başarısız",
    "winerror 10061",
    "connection refused",
    "llm erişilemez",
)


def looks_like_outage(row: Dict[str, Any]) -> bool:
    metin = normalize(" ".join([
        row.get("answer") or "",
        row.get("raw_answer") or "",
        " ".join(row.get("issues") or []),
    ]))
    return any(m in metin for m in _OUTAGE_MARKERS)


class EvalAborted(RuntimeError):
    """Ölçüm geçersiz; sonuç üretilmemelidir."""


def evaluate_case(engine: RAGEngine, case: Dict[str, Any]) -> Dict[str, Any]:
    t0 = time.time()
    res = engine.answer(case["question"])
    elapsed = time.time() - t0

    ctype = case.get("type", "answerable")
    answer_n = normalize(res.answer)
    cited_files = normalize(" ".join(s.source_file for s in res.sources))

    out: Dict[str, Any] = {
        "question": case["question"],
        "type": ctype,
        "refused": res.refused,
        "top_similarity": round(res.top_similarity, 3),
        "elapsed_s": round(elapsed, 2),
        "answer": res.answer[:400],
        "raw_answer": (res.raw_answer or "")[:400],
        # Kaynak METNİ de kaydedilir: "hangi tablo satırı geldi?" sorusu
        # yalnızca konum bilgisiyle (Sayfa 7, satır 17) cevaplanamıyor.
        "sources": [
            f"{s.source_file} ({s.locator}) → "
            f"{' '.join((s.text or '').split())[:95]}"
            for s in res.sources
        ],
        "passed": True,
        "issues": [],
    }

    if ctype == "must_refuse":
        if not res.refused:
            out["passed"] = False
            out["issues"].append("HALÜSİNASYON RİSKİ: reddetmesi gerekirken yanıt üretti")
        return out

    # Tuzak sorular: reddetmek KABUL EDİLEBİLİR bir davranıştır.
    # Asıl ölçtüğümüz şey, kullanıcının yanlış varsayımını ONAYLAYIP
    # onaylamadığıdır. Reddetmek yanlış bilgi vermekten iyidir.
    if ctype == "trap" and res.refused:
        out["issues"].append("(tuzak soru reddedildi — kabul edilebilir)")
        return out

    # Cevaplanabilir sorular
    if res.refused:
        out["passed"] = False
        out["issues"].append(
            f"YANLIŞ RET → {res.refusal_reason or 'gerekçe kaydedilmedi'}")
        return out

    # Hepsi bulunmalı
    for kw in case.get("expect_keywords", []) or []:
        if normalize(kw) not in answer_n:
            out["passed"] = False
            out["issues"].append(f"eksik anahtar kelime: '{kw}'")

    # Herhangi biri yeterli — aynı bilginin birden çok geçerli yazımı olduğunda.
    # Örnek: "yüzbinde üç" ile "0,00003" aynı oranı ifade eder; modelin
    # hangisini seçtiği doğruluk değil biçim meselesidir.
    alts = case.get("expect_any", []) or []
    if alts and not any(normalize(a) in answer_n for a in alts):
        out["passed"] = False
        out["issues"].append(
            f"şu ifadelerden hiçbiri yok: {', '.join(repr(a) for a in alts)}")

    exp_src = case.get("expect_source")
    if exp_src and normalize(exp_src) not in cited_files:
        out["passed"] = False
        out["issues"].append(f"beklenen kaynak atfı yok: '{exp_src}'")

    for kw in case.get("forbid_keywords", []) or []:
        if normalize(kw) in answer_n:
            out["passed"] = False
            out["issues"].append(f"YASAKLI İFADE ÜRETİLDİ (tuzağa düştü): '{kw}'")

    if not res.sources:
        out["passed"] = False
        out["issues"].append("hiç kaynak gösterilmedi")

    return out


def summarize(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    must_refuse = [r for r in rows if r["type"] == "must_refuse"]
    # Tuzak sorular "yanlış ret" istatistiğine girmez: onlarda reddetmek
    # kabul edilebilir bir sonuçtur.
    answerable = [r for r in rows if r["type"] not in ("must_refuse", "trap")]
    lat = sorted(r["elapsed_s"] for r in rows) or [0]

    def pct(part: List, whole: List) -> float:
        return round(100.0 * len(part) / len(whole), 1) if whole else 0.0

    return {
        "toplam_soru": len(rows),
        "genel_basari_%": pct([r for r in rows if r["passed"]], rows),
        "ret_dogrulugu_%": pct([r for r in must_refuse if r["refused"]], must_refuse),
        "yanlis_ret_%": pct([r for r in answerable if r["refused"]], answerable),
        "kaynakli_yanit_%": pct([r for r in answerable if r["sources"]], answerable),
        "gecikme_p50_s": round(statistics.median(lat), 2),
        "gecikme_p95_s": round(lat[max(0, int(len(lat) * 0.95) - 1)], 2),
    }


def run_once(engine: RAGEngine, cases: List[Dict], verbose: bool = True) -> Dict[str, Any]:
    rows = []
    ardisik_kesinti = 0
    for i, case in enumerate(cases, 1):
        r = evaluate_case(engine, case)

        # ALTYAPI KESİNTİSİ ÖLÇÜM DEĞİLDİR.
        # Ollama kapalıyken koşu, cevaplanabilir soruların hepsini "yanlış ret"
        # sayar ama must_refuse sorularını GEÇMİŞ gösterir (hata metni beklenen
        # bilgiyi içermediği için "reddetti" sanılır). Sonuç: "%31 başarı,
        # %100 ret doğruluğu" gibi makul görünen ama tamamen anlamsız bir rapor.
        # Gerçek bir koşuda tam olarak bu oldu; sayı rapora girebilirdi.
        if looks_like_outage(r):
            ardisik_kesinti += 1
            if ardisik_kesinti >= 3:
                raise EvalAborted(
                    f"{i}. soruda LLM'e üst üste {ardisik_kesinti} kez ulaşılamadı. "
                    "Ölçüm geçersiz olacağı için durduruldu."
                )
        else:
            ardisik_kesinti = 0

        rows.append(r)
        if verbose:
            mark = "✔" if r["passed"] else "✖"
            print(f" {mark} [{i:>2}/{len(cases)}] {case['question'][:64]}")
            for issue in r["issues"]:
                print(f"       ↳ {issue}")
            # Başarısız durumlarda YANITI ve KAYNAKLARI göster.
            # Bunlar olmadan "eksik anahtar kelime" uyarısı tek başına
            # sorunun getirmede mi üretimde mi olduğunu söylemez.
            if not r["passed"]:
                ans = " ".join((r["answer"] or "").split())
                print(f"       │ yanıt: {ans[:200] or '(boş)'}")
                if r.get("raw_answer"):
                    raw = " ".join(r["raw_answer"].split())
                    print(f"       │ MODELİN HAM ÇIKTISI: {raw[:220]}")
                for s in r["sources"][:4]:
                    print(f"       │ kaynak: {s}")
    return {"rows": rows, "summary": summarize(rows)}


def sweep(engine: RAGEngine, cases: List[Dict]) -> List[Dict[str, Any]]:
    """Parametre taraması: en iyi chunk/top_k/eşik kombinasyonunu bulur.
    NOT: chunk_size değişimi yeniden indeksleme gerektirir; burada yalnızca
    arama-zamanı parametreleri taranır."""
    grid = {
        "final_k": [3, 5, 8],
        "min_similarity": [0.30, 0.35, 0.45],
        "mmr_enabled": [True, False],
    }
    out = []
    keys = list(grid)
    for combo in itertools.product(*(grid[k] for k in keys)):
        params = dict(zip(keys, combo))
        CFG["retrieval"].update(params)
        print(f"\n=== {params} ===")
        res = run_once(engine, cases, verbose=False)
        row = {**params, **res["summary"]}
        print(json.dumps(row, ensure_ascii=False))
        out.append(row)
    out.sort(key=lambda r: (r["genel_basari_%"], -r["yanlis_ret_%"]), reverse=True)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--testset", default="eval/testset_depo.yaml")
    ap.add_argument("--out", default=None)
    ap.add_argument("--sweep", action="store_true")
    ap.add_argument("--holdout", action="store_true",
                    help="Ayrılmış seti çalıştırmak için açık onay")
    args = ap.parse_args()

    path = Path(args.testset)
    if not path.is_absolute():
        path = Path(__file__).resolve().parent.parent / path
    cases = yaml.safe_load(path.read_text(encoding="utf-8")) or []
    if not cases:
        print(f"Test seti boş: {path}")
        return 1

    # ------------------------------------------------------- AYRILMIŞ SET KİLİDİ
    # Ayrılmış setin değeri, geliştirme sırasında HİÇ GÖRÜLMEMİŞ olmasından
    # gelir. Bir kez bakılıp sonuçlarına göre ayar yapıldığında set "yanar"
    # ve artık genelleme ölçmez. Bu disiplini hafızaya bırakmak yerine
    # mekanik hale getiriyoruz: açık onay olmadan çalışmaz.
    if "holdout" in path.name.lower() and not args.holdout:
        print("=" * 62)
        print("  AYRILMIŞ TEST SETİ — KİLİTLİ")
        print("=" * 62)
        print(f"  {path.name}, geliştirme sırasında çalıştırılmamalıdır.")
        print("  Sonuçlarına bakıp parametre ayarlanırsa set genelleme")
        print("  ölçme özelliğini kaybeder.")
        print("\n  Geliştirme ölçümü için:")
        print("      python eval/run_eval.py --testset eval/testset_depo.yaml")
        print("\n  Geliştirme gerçekten bittiyse, tek seferlik nihai ölçüm:")
        print(f"      python eval/run_eval.py --testset {args.testset} --holdout")
        return 1

    if args.holdout and args.sweep:
        print("Ayrılmış set üzerinde parametre taraması yapılamaz: "
              "tarama, sete bakarak ayar yapmak demektir.")
        return 1

    engine = RAGEngine(CFG)
    if engine.collection.count() == 0:
        print("İndeks boş. Önce 'python -m src.ingest' çalıştırın.")
        return 1

    # ---------------------------------------------------------------- ÖN KONTROL
    # 29 soruyu çalıştırıp sonunda "LLM kapalıymış" demek yerine, en baştan
    # tek istekle anlaşılır. Kesintili bir koşu yalnızca zaman kaybettirmez,
    # inandırıcı görünen YANLIŞ BİR SKOR üretir.
    from src.llm_client import LocalLLM  # noqa: E402
    saglik = LocalLLM(CFG).health()
    if not saglik["online"] or not saglik["model_available"]:
        print("=" * 62)
        print("  ÖLÇÜM BAŞLATILMADI — LLM hazır değil")
        print("=" * 62)
        print(f"  {saglik['message']}")
        print("\n  Yapılacaklar:")
        print("    1) Ollama'yı başlatın:   ollama serve")
        print(f"    2) Modeli doğrulayın :   ollama list   "
              f"({CFG.get_path('llm.model')} görünmeli)")
        print("    3) Tam kontrol       :   python scripts/verify_offline.py")
        return 1

    print(f"\n{len(cases)} test sorusu çalıştırılıyor...\n")

    try:
        if args.sweep:
            table = sweep(engine, cases)
            print("\n\n=== EN İYİ 5 KOMBİNASYON ===")
            for row in table[:5]:
                print(json.dumps(row, ensure_ascii=False))
            payload: Any = table
        else:
            result = run_once(engine, cases)
            print("\n" + "=" * 62)
            for k, v in result["summary"].items():
                print(f"  {k:<22}: {v}")
            print("=" * 62)
            payload = result
    except EvalAborted as exc:
        print("\n" + "=" * 62)
        print("  ÖLÇÜM İPTAL EDİLDİ — SONUÇ ÜRETİLMEDİ")
        print("=" * 62)
        print(f"  {exc}")
        print("\n  Ollama koşu sırasında durmuş olabilir. Başlatıp tekrar deneyin:")
        print("    ollama serve")
        return 1

    if args.out:
        Path(args.out).write_text(json.dumps(payload, ensure_ascii=False, indent=2),
                                  encoding="utf-8")
        print(f"\nRapor yazıldı: {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
