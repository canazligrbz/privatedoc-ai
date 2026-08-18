"""
BELGE ASİSTANI — Web Sunucusu (FastAPI)
=======================================

Streamlit yerine hafif bir FastAPI sunucusu + saf HTML/CSS/JS arayüz.
Neden? Streamlit her etkileşimde tüm sayfayı yeniden çalıştırır, tasarımı
CSS enjeksiyonuyla zorlamak gerekir ve sonuç "araç gibi" görünür. Burada
DOM üzerinde tam kontrol var, yanıt token token akıyor, hiçbir CDN/dış
kaynak kullanılmıyor (air-gap uyumlu).

Çalıştırma:
    uvicorn server:app --host 127.0.0.1 --port 8501
veya
    python server.py
"""

from __future__ import annotations

# ---------------------------------------------------------------- AIR-GAP
from src.airgap import enforce_airgap, is_enforced  # noqa: E402
from src.config import PROJECT_ROOT, ensure_directories, load_config  # noqa: E402

CFG = load_config()
enforce_airgap(
    allowed_hosts=CFG.get_path("security.allowed_hosts", []),
    block_network=bool(CFG.get_path("security.block_outbound_network", True)),
)
ensure_directories(CFG)
# --------------------------------------------------------------------------


import json  # noqa: E402
import mimetypes  # noqa: E402
import os  # noqa: E402
import sys  # noqa: E402

import threading  # noqa: E402
from pathlib import Path  # noqa: E402
from typing import Any, Dict, Generator, List  # noqa: E402

from fastapi import FastAPI, HTTPException, UploadFile, File, Body  # noqa: E402
from fastapi.responses import (  # noqa: E402
    FileResponse, HTMLResponse, StreamingResponse,
)
from fastapi.staticfiles import StaticFiles  # noqa: E402

from src.loaders import SUPPORTED_EXTENSIONS  # noqa: E402

WEB_DIR = PROJECT_ROOT / "web"

app = FastAPI(title="Belge Asistanı", docs_url=None, redoc_url=None)

# --- Motor: ilk istekte tembel yüklenir (model RAM'e alınır) ---
_engine = None
_engine_lock = threading.Lock()
_ingest_lock = threading.Lock()


def get_engine():
    global _engine
    if _engine is None:
        with _engine_lock:
            if _engine is None:
                from src.rag_engine import RAGEngine
                _engine = RAGEngine(CFG)
    return _engine


# ============================================================ statik dosyalar

if WEB_DIR.exists():
    app.mount("/assets", StaticFiles(directory=str(WEB_DIR)), name="assets")


@app.get("/", response_class=HTMLResponse)
def index() -> HTMLResponse:
    html = (WEB_DIR / "index.html").read_text(encoding="utf-8")
    return HTMLResponse(html)


@app.get("/logo")
def logo():
    rel = CFG.get_path("app.logo_path", "assets/logo.svg")
    path = PROJECT_ROOT / rel
    if not path.exists():
        raise HTTPException(404, "Logo bulunamadı")
    mime = mimetypes.guess_type(str(path))[0] or "image/svg+xml"
    return FileResponse(str(path), media_type=mime)


# ============================================================ API

@app.get("/api/config")
def api_config() -> Dict[str, Any]:
    """Arayüzün başlangıçta ihtiyaç duyduğu her şey (tema dahil)."""
    r = CFG.get_path("retrieval", {}) or {}
    return {
        "title": CFG.get_path("app.title", ""),
        "subtitle": CFG.get_path("app.subtitle", ""),
        "organization": CFG.get_path("app.organization", ""),
        "footer_note": CFG.get_path("app.footer_note", ""),
        "theme": CFG.get_path("app.theme", {}),
        "accepted_types": sorted(SUPPORTED_EXTENSIONS),
        "settings": {
            "top_k": r.get("top_k", 20),
            "final_k": r.get("final_k", 4),
            "min_similarity": r.get("min_similarity", 0.35),
            "temperature": CFG.get_path("llm.temperature", 0.0),
        },
    }


@app.get("/api/status")
def api_status() -> Dict[str, Any]:
    from src import vectorstore

    engine = get_engine()
    health = engine.llm.health()
    stats = vectorstore.stats(CFG)
    return {
        "llm_online": bool(health.get("online")),
        "llm_message": health.get("message", ""),
        "model_available": bool(health.get("model_available")),
        "model": CFG.get_path("llm.model", ""),
        "airgap": is_enforced(),
        "documents": stats.get("documents", 0),
        "chunks": stats.get("chunks", 0),
        "sources": stats.get("sources", []),
    }


@app.post("/api/settings")
def api_settings(payload: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
    """Arayüzden gelen doğruluk ayarlarını çalışma anında uygular."""
    r = CFG.setdefault("retrieval", {})
    if "top_k" in payload:
        r["top_k"] = max(5, min(50, int(payload["top_k"])))
    if "final_k" in payload:
        r["final_k"] = max(2, min(12, int(payload["final_k"])))
    if "min_similarity" in payload:
        r["min_similarity"] = max(0.10, min(0.80, float(payload["min_similarity"])))
    if "temperature" in payload:
        CFG.setdefault("llm", {})["temperature"] = max(0.0, min(1.0, float(payload["temperature"])))
    return {"ok": True, "settings": {
        "top_k": r.get("top_k"), "final_k": r.get("final_k"),
        "min_similarity": r.get("min_similarity"),
        "temperature": CFG.get_path("llm.temperature"),
    }}


@app.post("/api/upload")
async def api_upload(files: List[UploadFile] = File(...)) -> Dict[str, Any]:
    docs_dir = CFG.resolve("paths.documents")
    docs_dir.mkdir(parents=True, exist_ok=True)
    saved, skipped = [], []
    for uf in files:
        name = Path(uf.filename or "").name
        if not name or Path(name).suffix.lower() not in SUPPORTED_EXTENSIONS:
            skipped.append(name or "(isimsiz)")
            continue
        data = await uf.read()
        (docs_dir / name).write_bytes(data)
        saved.append(name)
    return {"saved": saved, "skipped": skipped}


@app.post("/api/ingest")
def api_ingest(payload: Dict[str, Any] = Body(default={})) -> Dict[str, Any]:
    if not _ingest_lock.acquire(blocking=False):
        raise HTTPException(409, "İndeksleme zaten sürüyor.")
    # KİLİT HER DURUMDA SERBEST BIRAKILMALI.
    # Aksi hâlde bir çökme sonrası sistem kalıcı olarak "İndeksleme zaten
    # sürüyor" (409) durumunda kalır ve yalnızca sunucuyu yeniden başlatmak
    # kurtarır. Bu yüzden tek bir try/finally kullanılıyor.
    try:
        try:
            from src.ingest import ingest
            rep = ingest(cfg=CFG, rebuild=bool(payload.get("rebuild")), verbose=False)
            get_engine().refresh()
        except Exception as exc:
            # İNDEKSLEME ÇÖKERSE SEBEBİ KULLANICIYA ULAŞMALI.
            # Ham 500 gövdesi ("Internal Server Error") arayüzde JSON olarak
            # ayrıştırılmaya çalışılıyor ve kullanıcı asıl hata yerine
            # "Unexpected token 'I'" görüyordu. Gerçek kullanımda tam olarak
            # bu oldu; mesaj hiçbir şey öğretmiyordu. Tam iz sunucu
            # konsolunda kalır, özeti kullanıcıya gider.
            import traceback
            traceback.print_exc()
            raise HTTPException(
                500,
                f"İndeksleme sırasında beklenmeyen hata: "
                f"{type(exc).__name__}: {exc}"
            ) from exc

        out = {
            "added": rep["added"], "updated": rep["updated"],
            "unchanged": rep["unchanged"], "removed": rep["removed"],
            "failed": rep["failed"], "duration_s": rep.get("duration_s", 0),
            "chunks": rep.get("collection_count", 0),
            "ocr_used": rep.get("ocr_used", []),
            "ocr_low_quality": rep.get("ocr_low_quality", []),
        }
        _save_report(out)   # belge durumu paneli bunu okur
        return out
    finally:
        _ingest_lock.release()


LAST_REPORT = None  # son indeksleme raporunun yolu (aşağıda çözülür)


def _report_path() -> Path:
    return CFG.resolve("paths.logs") / "last_ingest.json"


def _save_report(rep: Dict[str, Any]) -> None:
    try:
        p = _report_path()
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(rep, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass


def _load_report() -> Dict[str, Any]:
    try:
        p = _report_path()
        if p.exists():
            return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {}


@app.get("/api/documents")
def api_documents() -> Dict[str, Any]:
    """
    Klasördeki her belgenin İNDEKS DURUMU.

    Kritik teşhis bilgisi: bir belge klasörde duruyor olabilir ama
    indekslenememiş olabilir (ör. taranmış PDF + OCR kurulu değil).
    Bu durumda sistem o belgeye dair hiçbir soruyu cevaplayamaz ve
    kullanıcı sebebini bilemez. Panel bunu görünür kılar.
    """
    from src.ingest import load_manifest

    docs_dir = CFG.resolve("paths.documents")
    manifest = load_manifest(CFG)
    report = _load_report()
    failed = {f.get("file"): f.get("error", "") for f in (report.get("failed") or [])}
    ocr_files = set(report.get("ocr_used") or [])

    items, problems = [], 0
    if docs_dir.exists():
        for p in sorted(docs_dir.rglob("*")):
            if not (p.is_file() and p.suffix.lower() in SUPPORTED_EXTENSIONS):
                continue
            rel = str(p.relative_to(docs_dir)).replace("\\", "/")
            entry = manifest.get(rel)
            error = failed.get(rel, "")

            if error:
                state, note = "error", error
                problems += 1
            elif entry:
                state = "ok"
                note = f"{entry.get('chunks', 0)} parça"
                if rel in ocr_files:
                    note += " · OCR"
            else:
                state, note = "pending", "indekslenmedi"
                problems += 1

            items.append({
                "name": p.name,
                "rel": rel,
                "size_kb": round(p.stat().st_size / 1024, 1),
                "type": p.suffix.lower().lstrip("."),
                "state": state,
                "note": note,
                "chunks": (entry or {}).get("chunks", 0),
            })

    return {"documents": items, "problems": problems}


def _sse(event: Dict[str, Any]) -> str:
    return f"data: {json.dumps(event, ensure_ascii=False)}\n\n"


@app.post("/api/chat")
def api_chat(payload: Dict[str, Any] = Body(...)) -> StreamingResponse:
    """
    Akışlı yanıt (Server-Sent Events benzeri).
    Gövde: {"question": str, "history": [[soru, yanit], ...], "sources": [dosya adları]}
    """
    question = (payload.get("question") or "").strip()
    if not question:
        raise HTTPException(400, "Soru boş olamaz.")

    history = [(h[0], h[1]) for h in (payload.get("history") or []) if len(h) == 2][-3:]
    source_filter = payload.get("sources") or None
    engine = get_engine()

    def generate() -> Generator[str, None, None]:
        try:
            for ev in engine.answer_stream(question, history=history,
                                           source_filter=source_filter):
                t = ev["type"]
                if t == "status":
                    yield _sse({"type": "status", "text": ev["text"]})
                elif t == "token":
                    yield _sse({"type": "token", "text": ev["text"]})
                elif t == "sources":
                    yield _sse({"type": "sources_preview",
                                "count": len(ev["sources"])})
                elif t == "final":
                    res = ev["result"]
                    yield _sse({
                        "type": "final",
                        "answer": res.answer,
                        "refused": res.refused,
                        "refusal_reason": res.refusal_reason,
                        "low_confidence": res.low_confidence,
                        "top_similarity": round(res.top_similarity, 3),
                        "elapsed_s": round(res.elapsed_s, 1),
                        "retrieved": res.retrieved,
                        "used": res.used,
                        "candidates_only": res.sources_are_candidates,
                        "raw_answer": res.raw_answer,
                        "sources": [
                            {
                                "n": s.n,
                                "file": s.source_file,
                                "locator": s.locator,
                                "section": s.section,
                                "similarity": round(s.similarity, 3),
                                "coverage": round(s.coverage, 2),
                                "below_threshold": s.below_threshold,
                                "cited": s.cited,
                                "text": s.text,
                            } for s in res.sources
                        ],
                    })
        except Exception as exc:  # motor hatası arayüze taşınmalı
            yield _sse({"type": "error", "message": str(exc)})

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ============================================================ giriş noktası

# Sunucunun ÇALIŞMASI için değil, İŞ YAPMASI için gereken paketler.
# fastapi/uvicorn sistem Python'unda da kurulu olabilir; bunlar olmadan
# sunucu açılır ama ilk indeksleme isteğinde çöker.
_ZORUNLU_PAKETLER = {
    "chromadb": "vektör veri tabanı",
    "sentence_transformers": "embedding modeli",
    "torch": "embedding modeli (CPU)",
    "pypdf": "PDF okuma",
}


def _on_kontrol() -> None:
    """
    Açılışta ortamı denetler ve eksikse ANLAŞILIR bir mesajla durur.

    NEDEN GEREKLİ?
    Gerçek kullanımda şu oldu: kullanıcı sanal ortamı etkinleştirmeden
    `python server.py` çalıştırdı. Sistem Python'unda fastapi kurulu olduğu
    için sunucu sorunsuz açıldı, arayüz geldi, belgeler listelendi — ve
    hata ancak "İndeksi güncelle" düğmesine basılınca, üstelik anlaşılmaz
    bir biçimde ortaya çıktı:
        ModuleNotFoundError: No module named 'chromadb'
    Arayüzde görünen ise "Unexpected token 'I'" idi.

    Yanlış ortamda çalıştığını en geç indeksleme anında değil, AÇILIŞTA
    söylemek gerekir.
    """
    import importlib.util

    eksik = [(m, aciklama) for m, aciklama in _ZORUNLU_PAKETLER.items()
             if importlib.util.find_spec(m) is None]
    if not eksik:
        return

    proje = Path(__file__).resolve().parent
    venv = proje / ".venv"
    calisan = Path(sys.prefix).resolve()
    venv_disi = venv.exists() and calisan != venv

    print("\n" + "=" * 66)
    print("  BAŞLATILAMADI — ortam eksik")
    print("=" * 66)
    for m, aciklama in eksik:
        print(f"  ✖ {m:<24} ({aciklama})")
    print(f"\n  Kullanılan Python: {calisan}")

    if venv_disi:
        etkinlestir = (venv / "Scripts" / "activate" if os.name == "nt"
                       else venv / "bin" / "activate")
        print(f"  Proje sanal ortamı: {venv}")
        print("\n  SANAL ORTAM ETKİN DEĞİL. Paketler .venv içinde kurulu;")
        print("  sistem Python'u ile çalıştırıldığı için görünmüyorlar.")
        print(f"\n  Çözüm:\n      {etkinlestir}\n      python server.py")
    else:
        print("\n  Paketler kurulu değil. Çözüm:")
        print("      pip install -r requirements.txt")
    print("=" * 66 + "\n")
    sys.exit(1)


def main() -> None:
    _on_kontrol()
    import uvicorn
    print("\n  Belge Asistanı")
    print("  → http://127.0.0.1:8501\n")
    uvicorn.run(app, host="127.0.0.1", port=8501, log_level="warning")


if __name__ == "__main__":
    main()
