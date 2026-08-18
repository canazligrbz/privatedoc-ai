"""
KURULUM DOĞRULAMA VE AIR-GAP DENETİMİ
=====================================

Air-gap makinede, ilk kurulumdan sonra ve her sürüm güncellemesinde çalıştırın.
Devreye alma (kabul) testi olarak kayıt altına alınabilir.

    python scripts/verify_offline.py
    python scripts/verify_offline.py --json > kabul_testi.json
"""

from __future__ import annotations

import argparse
import json
import platform
import shutil
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.airgap import enforce_airgap, selftest  # noqa: E402
from src.config import load_config  # noqa: E402

CFG = load_config()
enforce_airgap(
    allowed_hosts=CFG.get_path("security.allowed_hosts", []),
    block_network=bool(CFG.get_path("security.block_outbound_network", True)),
)

OK, FAIL, WARN = "✔", "✖", "!"
results = []


def check(name: str, fn):
    t0 = time.time()
    try:
        ok, detail = fn()
    except Exception as exc:
        ok, detail = False, f"{type(exc).__name__}: {exc}"
    sym = OK if ok is True else (WARN if ok == "warn" else FAIL)
    dur = time.time() - t0
    print(f" {sym}  {name:<42} {detail}  ({dur:.1f}s)")
    results.append({"check": name, "ok": ok, "detail": str(detail), "seconds": round(dur, 2)})
    return ok


# ----------------------------------------------------------------- testler

def t_python():
    v = sys.version_info
    ok = (v.major, v.minor) >= (3, 10)
    return ok, f"Python {v.major}.{v.minor}.{v.micro} ({platform.machine()})"


def t_venv():
    """Sanal ortam aktif mi? En sık yapılan hata: activate etmeden çalıştırmak."""
    project = Path(__file__).resolve().parent.parent
    venv_dir = project / ".venv"
    running_in = Path(sys.prefix).resolve()

    if not venv_dir.exists():
        return "warn", f"proje .venv klasoru yok - sistem Python: {running_in}"

    try:
        inside = running_in == venv_dir.resolve()
    except Exception:
        inside = False

    if inside:
        return True, f".venv aktif ({running_in})"

    activate = venv_dir / ("Scripts/activate" if platform.system() == "Windows"
                           else "bin/activate")
    return False, (f"SANAL ORTAM AKTİF DEĞİL — sistem Python'u kullanılıyor ({running_in}).\n"
                   f"      Paketler .venv içinde kurulu olduğu için 'eksik' görünecektir.\n"
                   f"      Şunu çalıştırıp tekrar deneyin:  {activate}")


def t_packages():
    missing = []
    for mod in ["fastapi", "uvicorn", "multipart", "yaml", "pypdf", "docx",
                "chromadb", "sentence_transformers", "torch", "httpx",
                "langchain_text_splitters"]:
        try:
            __import__(mod)
        except ImportError:
            missing.append(mod)
    return (not missing), ("tümü kurulu" if not missing else f"eksik: {', '.join(missing)}")


def t_airgap():
    r = selftest()
    if r["external_blocked"] is True:
        return True, "harici bağlantı bloklandı, localhost açık"
    if r["external_blocked"] == "network_unreachable":
        return "warn", "ağ zaten erişilemez (fiziksel izolasyon) — süreç koruması doğrulanamadı"
    return False, "UYARI: harici bağlantı ENGELLENMEDİ"


def t_machine_isolation():
    """
    MAKİNE DÜZEYİNDE YALITIM — süreç içi korumanın KAPSAMADIĞI alan.

    airgap.py yalnızca bu Python sürecinin socket'ini yamalar. LLM'i çalıştıran
    Ollama AYRI BİR SÜREÇTİR: belgeler ona localhost üzerinden ulaşır, ancak
    kendi dış bağlantılarını (sürüm denetimi vb.) süreç içi koruma engelleyemez.

    Bu kontrol, makinenin hâlâ bir ağa bağlı olup olmadığını varsayılan ağ
    geçidine bakarak söyler. Amaç kurulumu reddetmek değil, kapsam boşluğunu
    GÖRÜNÜR kılmaktır: uyarı varsa yalıtım işletim sistemi düzeyinde
    tamamlanmamış demektir.
    """
    import subprocess

    try:
        if platform.system() == "Windows":
            # "route print 0.0.0.0" varsayılan rota tablosunu verir; 0.0.0.0 ile
            # başlayan bir satır varsa makinenin çıkışı vardır.
            out = subprocess.run(["route", "print", "0.0.0.0"],
                                 capture_output=True, text=True, timeout=15).stdout
            gecit_var = any(l.strip().startswith("0.0.0.0")
                            for l in out.splitlines())
        else:
            out = subprocess.run(["ip", "route", "show", "default"],
                                 capture_output=True, text=True, timeout=15).stdout
            gecit_var = bool(out.strip())
    except Exception as exc:
        return "warn", f"ağ durumu belirlenemedi ({type(exc).__name__}) — elle doğrulayın"

    if gecit_var:
        return "warn", ("makine hâlâ bir ağa bağlı; Ollama süreci koruma "
                        "kapsamı DIŞINDA — ağ arayüzünü kapatın (§9 Aşama 4)")
    return True, "varsayılan ağ geçidi yok, makine yalıtılmış"


def t_embedding():
    from src.embedder import embed_query, model_info
    v = embed_query("sözleşme feshi için kaç gün önceden bildirim yapılır")
    return len(v) > 0, f"{model_info()['path']} → {len(v)} boyut"


def t_vectordb():
    from src import vectorstore
    s = vectorstore.stats(CFG)
    if s.get("error"):
        return False, s["error"]
    if s["chunks"] == 0:
        return "warn", "koleksiyon boş — 'python -m src.ingest' çalıştırın"
    return True, f"{s['documents']} belge / {s['chunks']} parça"


def t_llm():
    from src.llm_client import LocalLLM
    h = LocalLLM(CFG).health()
    if not h["online"]:
        return False, h["message"]
    if not h["model_available"]:
        return False, h["message"]
    return True, f"{CFG.get_path('llm.model')} hazır"


def t_llm_generation():
    from src.llm_client import LocalLLM
    t0 = time.time()
    out = LocalLLM(CFG).chat(
        system="Yalnızca istenen kelimeyi yaz.",
        user="Sadece şu kelimeyi yaz: HAZIR",
    )
    dur = time.time() - t0
    return ("HAZIR" in out.upper()), f"yanıt: {out.strip()[:40]!r} ({dur:.1f} sn)"


def t_rag_refusal():
    """Guardrail testi: belgelerde kesinlikle olmayan bir soru reddedilmeli."""
    from src.rag_engine import RAGEngine
    eng = RAGEngine(CFG)
    if eng.collection.count() == 0:
        return "warn", "indeks boş, test atlandı"
    res = eng.answer("Jüpiter gezegeninin yüzey sıcaklığı Kelvin cinsinden kaçtır?")
    return res.refused, ("doğru şekilde reddedildi" if res.refused
                         else f"REDDETMEDİ (risk!): {res.answer[:80]}")


def t_disk():
    total, used, free = shutil.disk_usage(Path(__file__).resolve().parent.parent)
    gb = free / 1e9
    if gb >= 15:
        return True, f"{gb:.1f} GB boş alan"
    if gb >= 8:
        return "warn", (f"{gb:.1f} GB boş alan — indeksleme için yeterli ama dar. "
                        "15 GB önerilir.")
    return False, (f"{gb:.1f} GB boş alan — YETERSİZ. Windows sayfa dosyası (pagefile) "
                   "büyüyemediği için model yüklemesi başarısız olabilir. En az 15 GB açın "
                   "veya OLLAMA_MODELS ile model klasörünü başka sürücüye taşıyın.")


def _total_ram_gb() -> float:
    """Ek bağımlılık olmadan toplam fiziksel RAM (GB)."""
    if platform.system() == "Windows":
        import ctypes

        class MEMORYSTATUSEX(ctypes.Structure):
            _fields_ = [("dwLength", ctypes.c_ulong),
                        ("dwMemoryLoad", ctypes.c_ulong),
                        ("ullTotalPhys", ctypes.c_ulonglong),
                        ("ullAvailPhys", ctypes.c_ulonglong),
                        ("ullTotalPageFile", ctypes.c_ulonglong),
                        ("ullAvailPageFile", ctypes.c_ulonglong),
                        ("ullTotalVirtual", ctypes.c_ulonglong),
                        ("ullAvailVirtual", ctypes.c_ulonglong),
                        ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]

        stat = MEMORYSTATUSEX()
        stat.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
        ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat))
        return stat.ullTotalPhys / 1e9
    try:
        import os as _os
        return _os.sysconf("SC_PAGE_SIZE") * _os.sysconf("SC_PHYS_PAGES") / 1e9
    except Exception:
        return 0.0


def _available_ram_gb() -> float:
    if platform.system() == "Windows":
        import ctypes

        class MEMORYSTATUSEX(ctypes.Structure):
            _fields_ = [("dwLength", ctypes.c_ulong),
                        ("dwMemoryLoad", ctypes.c_ulong),
                        ("ullTotalPhys", ctypes.c_ulonglong),
                        ("ullAvailPhys", ctypes.c_ulonglong),
                        ("ullTotalPageFile", ctypes.c_ulonglong),
                        ("ullAvailPageFile", ctypes.c_ulonglong),
                        ("ullTotalVirtual", ctypes.c_ulonglong),
                        ("ullAvailVirtual", ctypes.c_ulonglong),
                        ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]

        stat = MEMORYSTATUSEX()
        stat.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
        ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat))
        return stat.ullAvailPhys / 1e9
    try:
        for line in open("/proc/meminfo"):
            if line.startswith("MemAvailable"):
                return int(line.split()[1]) / 1e6
    except Exception:
        pass
    return 0.0


# Model başına kabaca gereken RAM (ağırlık + KV cache + uygulama payı), GB
_MODEL_RAM_NEED = {"3b": 4.0, "7b": 8.0, "8b": 9.0, "9b": 10.0, "14b": 14.0, "32b": 26.0}


def t_ram():
    total = _total_ram_gb()
    avail = _available_ram_gb()
    model = str(CFG.get_path("llm.model", "")).lower()
    need = next((v for k, v in _MODEL_RAM_NEED.items() if k in model), 8.0)
    ctx = int(CFG.get_path("llm.num_ctx", 8192))
    need += (ctx / 8192) * 1.0  # KV cache payı

    msg = f"toplam {total:.1f} GB / boş {avail:.1f} GB — model ihtiyacı ~{need:.1f} GB"
    if avail >= need:
        return True, msg
    if total >= need:
        return "warn", (msg + " | Fiziksel RAM yeterli ama şu an dolu. "
                        "Diğer uygulamaları kapatıp tekrar deneyin.")
    return False, (msg + f" | YETERSİZ. config.yaml → llm.num_ctx=4096 yapın veya "
                   "daha küçük modele geçin: ollama pull qwen2.5:3b-instruct-q4_K_M")


def t_models_dir():
    p = CFG.resolve("embedding.model_path")
    if p.exists():
        n = len(list(p.rglob("*")))
        return True, f"{p.name} ({n} dosya)"
    return False, f"bulunamadı: {p}"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    print("\n" + "=" * 76)
    print("  BELGE ASİSTANI — KURULUM DOĞRULAMA RAPORU")
    print("  " + time.strftime("%d.%m.%Y %H:%M:%S"))
    print("=" * 76)

    check("Python sürümü", t_python)
    check("Sanal ortam (.venv)", t_venv)
    check("Python paketleri", t_packages)
    check("Disk alanı", t_disk)
    check("RAM", t_ram)
    check("Air-gap koruması (süreç içi)", t_airgap)
    check("Makine yalıtımı (süreç DIŞI)", t_machine_isolation)
    check("Embedding modeli dosyaları", t_models_dir)
    check("Embedding üretimi", t_embedding)
    check("Vektör veri tabanı", t_vectordb)
    check("LLM servisi", t_llm)
    check("LLM metin üretimi", t_llm_generation)
    check("Halüsinasyon guardrail (ret testi)", t_rag_refusal)

    failed = [r for r in results if r["ok"] is False]
    warned = [r for r in results if r["ok"] == "warn"]

    print("=" * 76)
    print(f"  Başarılı: {len(results) - len(failed) - len(warned)} | "
          f"Uyarı: {len(warned)} | Başarısız: {len(failed)}")
    print("=" * 76 + "\n")

    if args.json:
        print(json.dumps({"results": results,
                          "failed": len(failed),
                          "warned": len(warned)}, ensure_ascii=False, indent=2))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
