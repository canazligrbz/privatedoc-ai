"""
RAG MOTORU
==========

Akış:
    soru
      -> (ops.) takip sorusunu bağımsızlaştır
      -> embed_query
      -> ChromaDB top_k aday getir
      -> benzerlik eşiği (min_similarity) filtresi          [GUARDRAIL 1]
      -> MMR çeşitlendirme + belge başına parça sınırı
      -> (ops.) cross-encoder reranker
      -> final_k parça ile strict prompt kur
      -> yerel LLM (temperature=0) ile akışlı üretim
      -> atıf doğrulama: [K#] var mı, numaralar geçerli mi   [GUARDRAIL 2 & 3]
      -> kaynak listesi üret + denetim günlüğüne yaz

Kritik nokta: eşik altında hiç parça yoksa LLM HİÇ ÇAĞRILMAZ. Model,
uydurma yapma fırsatı bulamadan standart ret mesajı döner.
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field

from typing import Any, Dict, Generator, List, Optional, Tuple

import numpy as np

from . import vectorstore
from .config import Config, load_config
from .embedder import embed_query
from .llm_client import LLMUnavailable, LocalLLM
from .prompts import (
    QUERY_REWRITE_PROMPT,
    REFUSAL,
    SYSTEM_PROMPT,
    build_user_prompt,
    citation_index,
    citation_label,
)

CITATION_RE = re.compile(r"\[K\s*(\d{1,2})\]")


# ============================================================ veri yapıları

@dataclass
class Source:
    n: int
    source_file: str
    locator: str
    section: str
    similarity: float
    text: str
    cited: bool = False
    coverage: float = 0.0        # sorunun kelimelerinin bu parçada geçme oranı
    below_threshold: bool = False  # eşiği geçemedi, yalnızca teşhis için gösteriliyor

    def label(self) -> str:
        loc = f" — {self.locator}" if self.locator else ""
        sec = f" ({self.section})" if self.section else ""
        return f"[K{self.n}] {self.source_file}{loc}{sec}"


@dataclass
class RAGResult:
    question: str
    answer: str
    sources: List[Source] = field(default_factory=list)
    refused: bool = False
    refusal_reason: str = ""
    top_similarity: float = 0.0
    low_confidence: bool = False
    elapsed_s: float = 0.0
    retrieved: int = 0
    used: int = 0
    # Guardrail devreye girdiğinde modelin HAM çıktısı burada saklanır.
    # Olmadan "neden reddedildi?" sorusu cevaplanamıyor: ekranda yalnızca
    # standart ret metni görünüyor, modelin ne yazdığı kayboluyor.
    raw_answer: str = ""
    # Reddedilen yanıtlarda bile "ne bulundu" görünsün diye, kaynaklar
    # SİLİNMEZ. Teşhis için kritik: parça hiç gelmedi mi, yoksa geldi de
    # model mi kullanamadı?
    sources_are_candidates: bool = False


# ============================================================ yardımcılar

def _mmr_select(query_vec: np.ndarray,
                candidates: List[Dict[str, Any]],
                k: int,
                lambda_mult: float,
                rel_key: str = "final_score") -> List[Dict[str, Any]]:
    """
    Maximal Marginal Relevance: hem soruya yakın hem birbirinden farklı
    parçaları seçer. Aynı paragrafın 5 kopyasının bağlamı doldurmasını önler.

    ÖNEMLİ: "soruya yakınlık" ölçütü olarak kosinüs benzerliği DEĞİL, varsa
    hibrit birleşik skor (rel_key) kullanılır. Aksi hâlde MMR adımı, BM25'in
    ve kelime kapsamının katkısını sessizce çöpe atar — anlamsal olarak
    birbirine çok benzeyen sözleşme sayfalarında bu, doğru parçanın elenmesi
    demektir. Bu hata gerçek bir testte yakalandı.
    """
    if not candidates:
        return []
    vecs = []
    usable = []
    for c in candidates:
        emb = c.get("embedding")
        if emb is None:
            continue
        vecs.append(np.asarray(emb, dtype=np.float32))
        usable.append(c)
    if len(usable) < 2:
        return candidates[:k]

    mat = np.vstack(vecs)
    mat = mat / (np.linalg.norm(mat, axis=1, keepdims=True) + 1e-9)
    q = np.asarray(query_vec, dtype=np.float32)
    q = q / (np.linalg.norm(q) + 1e-9)

    # Alaka skoru: hibrit skor varsa onu 0-1 aralığına ölçekle, yoksa kosinüs
    rel = np.array([float(c.get(rel_key, np.nan)) for c in usable], dtype=np.float32)
    if np.isnan(rel).any():
        sim_to_query = mat @ q
    else:
        lo, hi = float(rel.min()), float(rel.max())
        sim_to_query = ((rel - lo) / (hi - lo)) if hi > lo else np.ones_like(rel)

    selected: List[int] = []
    remaining = list(range(len(usable)))

    while remaining and len(selected) < k:
        if not selected:
            best = int(max(remaining, key=lambda i: sim_to_query[i]))
        else:
            sel_mat = mat[selected]
            best, best_score = remaining[0], -1e9
            for i in remaining:
                redundancy = float(np.max(sel_mat @ mat[i]))
                score = lambda_mult * float(sim_to_query[i]) - (1 - lambda_mult) * redundancy
                if score > best_score:
                    best, best_score = i, score
        selected.append(best)
        remaining.remove(best)

    return [usable[i] for i in selected]


def _cap_per_document(chunks: List[Dict[str, Any]], max_per_doc: int,
                      need: int = 0) -> List[Dict[str, Any]]:
    """
    Tek bir belgenin bağlamı domine etmesini engeller.

    ANCAK bağlamı aç bırakmaz: sınır uygulandıktan sonra elde `need` kadar
    parça kalmadıysa, elenenler sıralamadaki yerleriyle geri doldurulur.
    Aksi hâlde TEK belgeli bir arşivde sınır, tüm bağlamı 3 parçaya
    kilitliyordu ve tablo sorularında doğru satır asla modele ulaşmıyordu.
    """
    counts: Dict[str, int] = {}
    out: List[Dict[str, Any]] = []
    overflow: List[Dict[str, Any]] = []

    for c in chunks:
        key = (c.get("metadata") or {}).get("source_path", "?")
        if counts.get(key, 0) >= max_per_doc:
            overflow.append(c)
            continue
        counts[key] = counts.get(key, 0) + 1
        out.append(c)

    if need and len(out) < need:
        out.extend(overflow[: need - len(out)])
    return out


# ============================================================ motor

class RAGEngine:
    def __init__(self, cfg: Optional[Config] = None):
        self.cfg = cfg or load_config()
        self.llm = LocalLLM(self.cfg)
        self._collection = None
        self._reranker = None
        self._bm25 = None            # BM25 indeksi (tembel kurulur)
        self._bm25_ids: List[str] = []
        self._bm25_count = -1        # hangi parça sayısıyla kuruldu

    # -------------------------------------------------- altyapı

    @property
    def collection(self):
        if self._collection is None:
            self._collection = vectorstore.get_collection(cfg=self.cfg)
        return self._collection

    def refresh(self) -> None:
        """İndeks güncellendikten sonra çağrılır."""
        self._collection = None
        self._bm25 = None
        self._bm25_ids = []
        self._bm25_count = -1

    def _get_bm25(self):
        """
        BM25 indeksini bellekte kurar. Koleksiyondaki parça sayısı değişirse
        otomatik yeniden kurulur (yeni belge eklendiğinde).
        """
        if not self.cfg.get_path("retrieval.hybrid_enabled", True):
            return None
        try:
            count = self.collection.count()
        except Exception:
            return None
        if count == 0:
            return None
        if self._bm25 is not None and self._bm25_count == count:
            return self._bm25

        rows = vectorstore.fetch_all(self.collection)
        if not rows:
            return None
        from .bm25 import BM25
        self._bm25 = BM25([r["text"] for r in rows])
        self._bm25_ids = [r["id"] for r in rows]
        self._bm25_count = count
        return self._bm25

    def health(self) -> Dict[str, Any]:
        info = self.llm.health()
        try:
            info["chunks"] = self.collection.count()
        except Exception:
            info["chunks"] = 0
        return info

    def _get_reranker(self):
        if not self.cfg.get_path("reranker.enabled", False):
            return None
        if self._reranker is not None:
            return self._reranker
        path = self.cfg.resolve("reranker.model_path")
        if not path.exists():
            return None
        from sentence_transformers import CrossEncoder
        self._reranker = CrossEncoder(str(path), device="cpu", local_files_only=True)
        return self._reranker

    # -------------------------------------------------- getirme

    def _bm25_candidates(self, question: str, top_k: int,
                         allowed_files: Optional[List[str]]) -> List[Dict[str, Any]]:
        """BM25 kelime aramasından aday parçalar."""
        bm25 = self._get_bm25()
        if bm25 is None:
            return []
        hits = bm25.top_n(question, top_k * 2)   # filtre sonrası azalabilir
        if not hits:
            return []

        ids, scores = [], {}
        for idx, score in hits:
            if idx >= len(self._bm25_ids):
                continue
            _id = self._bm25_ids[idx]
            ids.append(_id)
            scores[_id] = score

        rows = vectorstore.get_by_ids(self.collection, ids)
        by_id = {r["id"]: r for r in rows}

        out: List[Dict[str, Any]] = []
        for _id in ids:                       # BM25 sırasını koru
            row = by_id.get(_id)
            if row is None:
                continue
            meta = row.get("metadata") or {}
            if allowed_files and meta.get("source_file") not in allowed_files:
                continue
            row["bm25_score"] = scores.get(_id, 0.0)
            row["similarity"] = 0.0           # dense skoru sonra doldurulur
            row["distance"] = 1.0
            out.append(row)
            if len(out) >= top_k:
                break
        return out

    def retrieve(self, question: str,
                 source_filter: Optional[List[str]] = None
                 ) -> Tuple[List[Dict[str, Any]], float, int]:
        """
        HİBRİT GETİRME: vektör araması + BM25 kelime araması, RRF ile birleşik.

        -> (seçilen parçalar, en yüksek kosinüs benzerliği, taranan aday sayısı)
        """
        from .bm25 import keyword_coverage, rrf_fuse

        r = self.cfg.get_path("retrieval", {}) or {}
        top_k = int(r.get("top_k", 20))
        final_k = int(r.get("final_k", 5))
        min_sim = float(r.get("min_similarity", 0.35))
        min_cov = float(r.get("min_keyword_coverage", 0.5))
        hybrid = bool(r.get("hybrid_enabled", True))

        qvec = embed_query(question)

        where = None
        if source_filter:
            where = ({"source_file": {"$in": list(source_filter)}}
                     if len(source_filter) > 1
                     else {"source_file": source_filter[0]})

        # --- 1) Vektör (anlamsal) adaylar
        dense = vectorstore.query(self.collection, qvec, top_k=top_k, where=where)

        # --- 2) BM25 (kelime) adaylar
        sparse = self._bm25_candidates(question, top_k, source_filter) if hybrid else []

        pool: Dict[str, Dict[str, Any]] = {}
        for c in dense:
            pool[c["id"]] = c
        for c in sparse:
            if c["id"] in pool:
                pool[c["id"]]["bm25_score"] = c.get("bm25_score", 0.0)
            else:
                pool[c["id"]] = c

        retrieved = len(pool)
        if not pool:
            return [], 0.0, 0

        top_sim = max((c.get("similarity", 0.0) for c in pool.values()), default=0.0)

        # --- 3) Sıraları RRF ile birleştir
        if sparse:
            fused = rrf_fuse(
                [[c["id"] for c in dense], [c["id"] for c in sparse]],
                k=int(r.get("rrf_k", 60)),
                weights=[float(r.get("dense_weight", 1.0)),
                         float(r.get("bm25_weight", 1.0))],
            )
        else:
            fused = {c["id"]: 1.0 / (60 + i) for i, c in enumerate(dense, start=1)}

        for _id, score in fused.items():
            if _id in pool:
                pool[_id]["fusion_score"] = score

        # --- 4) GUARDRAIL 1: alaka eşiği
        # Bir parça ya anlamca yeterince yakın olmalı, ya da sorunun
        # kelimelerinin yeterli bir kısmını içermeli. İkinci koşul, özel isim
        # içeren sorularda ("ADL-2024/117 ... sözleşmesi") yanlış ret'i engeller.
        kept: List[Dict[str, Any]] = []
        for c in pool.values():
            cov = keyword_coverage(question, c.get("text", ""))
            c["keyword_coverage"] = cov
            if c.get("similarity", 0.0) >= min_sim or cov >= min_cov:
                kept.append(c)

        if not kept:
            return [], top_sim, retrieved

        # --- 4b) Kelime kapsamı yükseltmesi
        # Saf RRF yalnızca SIRALARA bakar; "sorunun kelimelerinin %92'si bu
        # parçada geçiyor" ile "%8'i geçiyor" arasındaki uçurumu yansıtmaz.
        # Özel isim içeren sorularda belirleyici olan tam bu farktır, bu yüzden
        # birleşik skoru kapsamla ölçekliyoruz.
        boost = float(r.get("coverage_boost", 1.0))
        for c in kept:
            c["final_score"] = (c.get("fusion_score", 0.0)
                                * (1.0 + boost * c.get("keyword_coverage", 0.0)))
        kept.sort(key=lambda c: c.get("final_score", 0.0), reverse=True)

        # --- 5) Çeşitlilik (yalnızca embedding'i olan adaylarda anlamlı)
        # MMR, alaka ölçütü olarak birleşik skoru kullanır (rel_key), kosinüsü
        # değil; böylece BM25 katkısı bu adımda kaybolmaz.
        if bool(r.get("mmr_enabled", True)) and len(kept) > final_k:
            with_emb = [c for c in kept if c.get("embedding") is not None]
            if len(with_emb) > final_k:
                selected = _mmr_select(np.asarray(qvec), with_emb,
                                       k=min(final_k * 2, len(with_emb)),
                                       lambda_mult=float(r.get("mmr_lambda", 0.6)),
                                       rel_key="final_score")
                sel_ids = {c["id"] for c in selected}
                # MMR seçimini koru, kalanları sıralamadaki yerleriyle ekle
                kept = selected + [c for c in kept if c["id"] not in sel_ids]

        kept = _cap_per_document(kept, int(r.get("max_chunks_per_document", 3)),
                                 need=final_k)

        # --- 6) Yeniden sıralama (cross-encoder) — açıksa
        reranker = self._get_reranker()
        if reranker is not None and kept:
            pairs = [(question, c["text"]) for c in kept]
            scores = reranker.predict(
                pairs, batch_size=int(self.cfg.get_path("reranker.batch_size", 4)))
            for c, s in zip(kept, scores):
                c["rerank_score"] = float(s)
            kept.sort(key=lambda c: c.get("rerank_score", 0.0), reverse=True)
            final_k = int(self.cfg.get_path("reranker.top_n", final_k))

        return kept[:final_k], top_sim, retrieved

    def nearest_candidates(self, question: str,
                           source_filter: Optional[List[str]] = None,
                           n: int = 3) -> List[Dict[str, Any]]:
        """
        Eşiği geçemeyen en yakın adaylar — yalnızca teşhis amaçlı.
        "Hiçbir şey bulunamadı" ile "bulundu ama eşiğin altında kaldı"
        ayrımını kullanıcıya göstermeyi sağlar.
        """
        from .bm25 import keyword_coverage
        try:
            qvec = embed_query(question)
            where = None
            if source_filter:
                where = ({"source_file": {"$in": list(source_filter)}}
                         if len(source_filter) > 1
                         else {"source_file": source_filter[0]})
            rows = vectorstore.query(self.collection, qvec, top_k=n, where=where)
            for c in rows:
                c["keyword_coverage"] = keyword_coverage(question, c.get("text", ""))
            return rows
        except Exception:
            return []

    # -------------------------------------------------- takip sorusu

    def rewrite_query(self, question: str, history: List[Tuple[str, str]]) -> str:
        """Kısa takip sorularını bağımsız hale getirir. Geçmiş yoksa dokunmaz."""
        if not history:
            return question
        if len(question.split()) > 12:
            return question
        hist = "\n".join(f"Kullanıcı: {q}\nAsistan: {a[:300]}" for q, a in history[-2:])
        try:
            out = self.llm.chat(
                system="Sen bir arama sorgusu yeniden yazma aracısın. Sadece soruyu yaz.",
                user=QUERY_REWRITE_PROMPT.format(history=hist, question=question),
                temperature=0.0,
            ).strip().strip('"')
            return out.split("\n")[0][:300] if out else question
        except Exception:
            return question

    # -------------------------------------------------- atıf doğrulama

    def _validate_and_finalize(self, raw_answer: str,
                               sources: List[Source],
                               question: str = "") -> Tuple[str, bool, str]:
        """
        GUARDRAIL 2-6 — atıf var mı, atıflar geçerli mi, her cümle
        kaynağa dayanıyor mu, sayılar kaynakta geçiyor mu?

        -> (nihai_yanıt, reddedildi_mi, gerekçe_veya_not)
           Reddedilmediyse üçüncü değer bilgilendirme notudur.
        """
        g = self.cfg.get_path("guardrail", {}) or {}
        refusal = g.get("refusal_text", REFUSAL)
        answer = (raw_answer or "").strip()

        if not answer:
            return refusal, True, "Model boş yanıt üretti."

        # RET CÜMLESİNİ AYIKLA — "içeriyorsa ret say" DEĞİL.
        #
        # Model çoğu zaman doğru cevabı yazıp arkasına ezbere ret cümlesini
        # de ekliyor. Eski kural ("ret cümlesi geçiyor ve yanıt kısaysa
        # reddet") bu doğru cevapları çöpe atıyordu — gerçek testte üç
        # sorunun cevabı bu yüzden kayboldu.
        #
        # Doğru ölçüt: ret cümlesi çıkarıldıktan sonra geriye BİLGİ kalıyor mu?
        from . import verify as _verify

        answer, dropped_refusals = _verify.strip_refusal_sentences(answer, refusal)
        if not answer.strip():
            return refusal, True, "Model belgelerde bilgi bulamadı."

        found = {citation_index(m) for m in CITATION_RE.findall(answer)}
        valid_ids = {s.n for s in sources}

        if bool(g.get("validate_citation_ids", True)):
            hallucinated = found - valid_ids
            if hallucinated:
                # Var olmayan kaynak numarası üretildi -> güvenilmez
                return (refusal, True,
                        f"Model geçersiz kaynak etiketi üretti: "
                        f"{sorted('K' + citation_label(h) for h in hallucinated)}")

        if bool(g.get("require_citation", True)) and not found:
            return refusal, True, "Yanıtta hiçbir kaynak atfı bulunmuyor."

        # GUARDRAIL 5 & 6 — cümle bazında atıf + sayı doğrulama.
        # "Yanıtta atıf var mı?" yetmez: model atıflı doğru cümleyi yazıp
        # arkasına atıfsız uydurma bir özet ekleyebiliyor (gerçek testte
        # "otuziki aydır [K2]" yazıp sonra "toplam 30 aydır" dedi).
        ok, reason, details, cleaned = _verify.check(
            answer,
            [s.text for s in sources],
            question=question,
            require_sentence_citation=bool(g.get("require_citation_per_sentence", True)),
            sentence_action=str(g.get("sentence_citation_action", "strip")),
            verify_numbers=bool(g.get("verify_numbers", True)),
            min_sentence_len=int(g.get("min_factual_sentence_len", 40)),
        )
        if not ok:
            return refusal, True, reason

        # Atıfsız cümleler çıkarıldıysa yanıt kısalmış olabilir; atıf
        # kümesi de değişebileceğinden yeniden hesaplanır.
        answer = cleaned
        found = {citation_index(m) for m in CITATION_RE.findall(answer)}

        for s in sources:
            s.cited = s.n in found

        note = ""
        if details.get("removed"):
            note = (f"{len(details['removed'])} atıfsız cümle yanıttan çıkarıldı "
                    f"(kaynağa dayandırılmamıştı).")

        return answer, False, note

    # -------------------------------------------------- bağlam bütçesi

    def _fit_char_budget(self, question: str, configured: int) -> int:
        """
        Kaynaklara ayrılabilecek GERÇEK karakter sayısını hesaplar.

        num_ctx = sistem promptu + kaynaklar + soru + üretilecek yanıt.
        Yapılandırmadaki context_char_budget bunu bilmez; sistem promptu
        büyüdüğünde toplam sessizce pencereyi aşabilir. Burada aşmayacak
        şekilde daraltılır.
        """
        num_ctx = int(self.cfg.get_path("llm.num_ctx", 4096))
        num_predict = int(self.cfg.get_path("llm.num_predict", 700))
        # Türkçe'de kabaca 2.75 karakter = 1 token (ölçülmüş yaklaşık değer)
        cpt = float(self.cfg.get_path("llm.chars_per_token", 2.75))

        overhead_chars = len(SYSTEM_PROMPT) + len(question) + 400  # şablon payı
        available_tokens = num_ctx - num_predict - 96               # emniyet payı
        available_chars = int(available_tokens * cpt) - overhead_chars

        budget = max(600, min(configured, available_chars))
        if budget < configured:
            self._last_budget_note = (
                f"Bağlam bütçesi {configured} → {budget} karaktere daraltıldı "
                f"(num_ctx={num_ctx} sınırı)."
            )
        else:
            self._last_budget_note = ""
        return budget

    # -------------------------------------------------- denetim günlüğü

    def _audit(self, result: RAGResult) -> None:
        if not self.cfg.get_path("security.audit_log", False):
            return
        try:
            path = self.cfg.resolve("security.audit_log_file")
            path.parent.mkdir(parents=True, exist_ok=True)
            record = {
                "ts": int(time.time()),
                "question": result.question,
                "refused": result.refused,
                "refusal_reason": result.refusal_reason,
                "top_similarity": round(result.top_similarity, 4),
                "sources": [
                    {"file": s.source_file, "locator": s.locator,
                     "sim": round(s.similarity, 4), "cited": s.cited}
                    for s in result.sources
                ],
                "answer_chars": len(result.answer),
                "elapsed_s": round(result.elapsed_s, 2),
            }
            with open(path, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(record, ensure_ascii=False) + "\n")
        except Exception:
            pass  # denetim günlüğü hatası uygulamayı durdurmamalı

    # -------------------------------------------------- ana giriş noktaları

    def answer_stream(self,
                      question: str,
                      history: Optional[List[Tuple[str, str]]] = None,
                      source_filter: Optional[List[str]] = None,
                      ) -> Generator[Dict[str, Any], None, None]:
        """
        Akışlı yanıt üretir.
        Üretilen olaylar:
            {"type": "status",  "text": ...}
            {"type": "sources", "sources": [Source, ...]}
            {"type": "token",   "text": ...}
            {"type": "final",   "result": RAGResult}
        """
        t0 = time.time()
        g = self.cfg.get_path("guardrail", {}) or {}
        refusal = g.get("refusal_text", REFUSAL)
        r = self.cfg.get_path("retrieval", {}) or {}

        yield {"type": "status", "text": "Belgeler taranıyor..."}

        search_q = self.rewrite_query(question, history or []) if history else question
        chunks, top_sim, retrieved = self.retrieve(search_q, source_filter)

        def to_sources(items: List[Dict[str, Any]],
                       below: bool = False) -> List[Source]:
            return [
                Source(
                    n=i,
                    source_file=(c.get("metadata") or {}).get("source_file", "bilinmiyor"),
                    locator=(c.get("metadata") or {}).get("locator", ""),
                    section=(c.get("metadata") or {}).get("section", ""),
                    similarity=c.get("similarity", 0.0),
                    coverage=c.get("keyword_coverage", 0.0),
                    text=c.get("text", ""),
                    below_threshold=below,
                )
                for i, c in enumerate(items, start=1)
            ]

        # GUARDRAIL 1 — hiç ilgili parça yok: LLM çağrılmaz
        if not chunks:
            # Teşhis için en yakın adayları yine de göster: parça hiç mi
            # gelmedi, yoksa geldi de eşiği mi geçemedi? Bu ayrım olmadan
            # eşik ayarı körlemesine yapılır.
            near = self.nearest_candidates(search_q, source_filter, n=3)
            res = RAGResult(
                question=question, answer=refusal,
                sources=to_sources(near, below=True),
                sources_are_candidates=True,
                refused=True,
                refusal_reason=(f"İlgili içerik bulunamadı (en yüksek benzerlik "
                                f"{top_sim:.2f} < eşik {r.get('min_similarity', 0.35)})"),
                top_similarity=top_sim, elapsed_s=time.time() - t0,
                retrieved=retrieved, used=0,
            )
            self._audit(res)
            yield {"type": "token", "text": refusal}
            yield {"type": "final", "result": res}
            return

        sources = to_sources(chunks)
        yield {"type": "sources", "sources": sources}
        yield {"type": "status", "text": "Yanıt oluşturuluyor..."}

        # BAĞLAM PENCERESİNE SIĞDIRMA
        # Sistem promptu + kaynaklar + üretim payı num_ctx'i aşarsa Ollama
        # SESSİZCE kırpar; model bazen kurallarını bazen kaynakları kaybeder
        # ve aynı soruya farklı cevap verir. Gerçek bir testte tam bu oldu.
        # Bu yüzden bütçe her soruda hesaplanır ve gerekirse daraltılır.
        char_budget = self._fit_char_budget(
            question,
            configured=int(r.get("context_char_budget", 9000)),
        )
        user_prompt = build_user_prompt(question, chunks, char_budget=char_budget)

        buffer: List[str] = []
        try:
            for piece in self.llm.stream_chat(SYSTEM_PROMPT, user_prompt):
                buffer.append(piece)
                yield {"type": "token", "text": piece}
        except LLMUnavailable as exc:
            res = RAGResult(
                question=question,
                answer=f"⚠️ Yerel LLM sunucusuna ulaşılamadı. {exc}",
                sources=sources, refused=True, refusal_reason="LLM erişilemez",
                top_similarity=top_sim, elapsed_s=time.time() - t0,
                retrieved=retrieved, used=len(chunks),
            )
            yield {"type": "final", "result": res}
            return

        raw = "".join(buffer)
        final_answer, refused, reason = self._validate_and_finalize(
            raw, sources, question=question)

        res = RAGResult(
            question=question,
            answer=final_answer,
            # Reddedilse bile kaynaklar gösterilir (teşhis edilebilirlik).
            sources=sources,
            sources_are_candidates=refused,
            refused=refused,
            refusal_reason=reason,
            top_similarity=top_sim,
            low_confidence=top_sim < float(r.get("strong_similarity", 0.55)),
            elapsed_s=time.time() - t0,
            retrieved=retrieved,
            used=len(chunks),
            # HAM ÇIKTI HER ZAMAN SAKLANIR.
            # Önce yalnızca ret durumunda tutuluyordu; guardrail'in
            # cümle ayıkladığı (ama reddetmediği) durumlarda modelin ne
            # yazdığı görünmüyordu ve hata ayıklama körlemesine yapılıyordu.
            raw_answer=raw,
        )
        self._audit(res)
        yield {"type": "final", "result": res}

    def answer(self,
               question: str,
               history: Optional[List[Tuple[str, str]]] = None,
               source_filter: Optional[List[str]] = None) -> RAGResult:
        """Akışsız (senkron) yanıt — test ve değerlendirme betikleri için."""
        result: Optional[RAGResult] = None
        for ev in self.answer_stream(question, history, source_filter):
            if ev["type"] == "final":
                result = ev["result"]
        assert result is not None
        return result


_ENGINE: Optional[RAGEngine] = None


def get_engine(cfg: Optional[Config] = None) -> RAGEngine:
    global _ENGINE
    if _ENGINE is None:
        _ENGINE = RAGEngine(cfg)
    return _ENGINE
