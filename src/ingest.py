"""
VERİ İŞLEME HATTI (INGESTION)
=============================

data/documents içindeki PDF/DOCX/TXT/MD/CSV/XLSX belgelerini okur,
konum bilgisini koruyarak parçalara böler, yerel embedding modeliyle
vektörleştirir ve ChromaDB'ye yazar.

ÖZELLİKLER
  * Artımlı indeksleme: SHA-256 özeti değişmeyen dosya yeniden işlenmez.
  * Silinen belgeler indeksten otomatik düşürülür.
  * Her parça; dosya adı, sayfa/paragraf numarası ve başlık zinciri ile etiketlenir.
  * Sıfır ağ erişimi.

KULLANIM
    python -m src.ingest                    # artımlı
    python -m src.ingest --rebuild          # sıfırdan
    python -m src.ingest --path /veri/klasor
    python -m src.ingest --dry-run          # sadece rapor, yazma yok
"""

from __future__ import annotations

# --- AIR-GAP: her şeyden önce ---
from .airgap import enforce_airgap  # noqa: E402
from .config import load_config as _lc  # noqa: E402

_cfg_boot = _lc()
enforce_airgap(
    allowed_hosts=_cfg_boot.get_path("security.allowed_hosts", []),
    block_network=bool(_cfg_boot.get_path("security.block_outbound_network", True)),
)
# -------------------------------------

import argparse  # noqa: E402
import hashlib  # noqa: E402
import json  # noqa: E402
import re  # noqa: E402
import sys  # noqa: E402
import time  # noqa: E402
from dataclasses import dataclass  # noqa: E402
from pathlib import Path  # noqa: E402
from typing import Any, Dict, List, Optional  # noqa: E402

from . import vectorstore  # noqa: E402
from .config import Config, ensure_directories, load_config  # noqa: E402
from .embedder import embed_passages  # noqa: E402
from .loaders import Block, iter_documents, load_document  # noqa: E402


# ============================================================ veri yapıları

@dataclass
class Chunk:
    id: str
    text: str
    metadata: Dict[str, Any]


# ============================================================ yardımcılar

def file_digest(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def load_manifest(cfg: Config) -> Dict[str, Any]:
    p = cfg.resolve("paths.manifest")
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def save_manifest(cfg: Config, manifest: Dict[str, Any]) -> None:
    p = cfg.resolve("paths.manifest")
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")


_HEADING_RE = re.compile(
    r"^(?:(?:MADDE|Madde)\s+\d+|(?:BÖLÜM|Bölüm)\s+[\dIVXA-ZÇĞİÖŞÜ]+|"
    r"\d+(?:\.\d+)*\.?\s+[A-ZÇĞİÖŞÜ][^\n]{2,80})$",
    re.MULTILINE,
)


def detect_heading(text: str) -> Optional[str]:
    """Parçanın başındaki başlığı yakalar; atıflarda bağlam sağlar."""
    for line in text.split("\n")[:3]:
        line = line.strip()
        if not line or len(line) > 120:
            continue
        if _HEADING_RE.match(line) or (line.isupper() and 4 <= len(line) <= 100):
            return line
    return None


# Madde / alt madde başlangıçları:  "MADDE 9-"  "Madde 12."  "9.2."  "5.1-"
#
# İki konumda bölünür:
#   (a) satır başı                        -> "9.3. YÜKLENİCİ'nin..."
#   (b) cümle sonundan hemen sonra        -> "...uygulanır. 9.3. YÜKLENİCİ..."
#
# (b) şart: taranmış PDF'lerde satır sonları kaybolabiliyor, tüm sayfa tek
# satır hâline gelebiliyor. Yalnızca satır başına bakınca madde bölme hiç
# çalışmıyor ve 9.2 ile 9.3 aynı parçaya düşüyor (gerçek testte oldu).
#
# Ancak "(5.1, 5.2) maddelerinde belirtilen" gibi METİN İÇİ ATIFLARDA
# bölmemek gerekir; orada cümle ortasından kesilir ve anlam bozulur.
# Bu yüzden (b) yalnızca NOKTA + BOŞLUK sonrası geçerlidir — parantez içi
# atıflar virgül veya parantezle geldiği için eşleşmez.
_ARTICLE_SPLIT_RE = re.compile(
    r"(?=(?:^[ \t]*|(?<=[.:]\s))"
    r"(?:MADDE\s+\d+|Madde\s+\d+|\d{1,2}\.\d{1,2}(?:\.\d{1,2})?)"
    r"[ \t]*[-–—.)]?[ \t])",
    re.MULTILINE,
)


def split_articles(text: str, min_len: int = 60) -> List[str]:
    """
    Metni madde/alt madde sınırlarında ön böler.

    NEDEN: Gerçek bir testte "9.2 (belge vermeme cezası, onbinde dört)" ile
    "9.3 (maaş gecikme cezası, yüzbinde iki)" AYNI parçaya girdi; model
    yanlış maddeyi okuyup yanlış ceza oranı verdi. Her alt madde ayrı parça
    olursa model iki maddeyi karıştıramaz.

    Çok kısa parçalar (tek satırlık başlıklar) bir sonrakine yapıştırılır.
    """
    if not text:
        return []
    raw = [p.strip() for p in _ARTICLE_SPLIT_RE.split(text) if p and p.strip()]
    if len(raw) <= 1:
        return [text]

    merged: List[str] = []
    for part in raw:
        if merged and len(part) < min_len:
            merged[-1] = merged[-1] + "\n" + part
        elif merged and len(merged[-1]) < min_len:
            merged[-1] = merged[-1] + "\n" + part
        else:
            merged.append(part)
    return merged


def get_splitter(cfg: Config):
    from langchain_text_splitters import RecursiveCharacterTextSplitter

    return RecursiveCharacterTextSplitter(
        chunk_size=int(cfg.get_path("retrieval.chunk_size", 900)),
        chunk_overlap=int(cfg.get_path("retrieval.chunk_overlap", 150)),
        length_function=len,
        # Türkçe mevzuat/teknik doküman yapısına göre öncelik sırası:
        separators=[
            "\n\nMADDE ", "\n\nMadde ", "\n\nBÖLÜM ", "\n\nBölüm ",
            "\n\n", "\n", ". ", "; ", ", ", " ", "",
        ],
        keep_separator=True,
    )


# ============================================================ parçalama

def blocks_to_chunks(cfg: Config,
                     rel_path: str,
                     file_name: str,
                     file_hash: str,
                     blocks: List[Block]) -> List[Chunk]:
    """Blokları, konum bilgisi korunarak chunk'lara böler."""
    splitter = get_splitter(cfg)
    min_chars = int(cfg.get_path("retrieval.min_chunk_chars", 80))
    article_split = bool(cfg.get_path("retrieval.article_aware_split", True))
    chunks: List[Chunk] = []
    current_heading: Optional[str] = None
    seq = 0

    for block in blocks:
        heading = detect_heading(block.text)
        if heading:
            current_heading = heading

        # Tablo satırları zaten atomik: bölme ve kısa-parça filtresi UYGULANMAZ.
        # "2021-05 | 1.490,00" gibi bir satır 80 karakterin altındadır ve
        # min_chunk_chars filtresine takılıp sessizce kaybolurdu.
        is_table = (block.extra or {}).get("type") == "table"
        if is_table:
            pieces = [block.text]
            effective_min = 1
        else:
            # Önce madde sınırlarında böl, sonra hâlâ uzun kalanları
            # karakter bazlı bölücüye ver.
            if article_split:
                segments = split_articles(block.text)
            else:
                segments = [block.text]
            pieces = []
            for seg in segments:
                pieces.extend(splitter.split_text(seg) or [])
            effective_min = min_chars

        for piece in pieces:
            piece = piece.strip()
            if len(piece) < effective_min:
                continue
            seq += 1
            uid = hashlib.sha1(
                f"{rel_path}|{block.order}|{seq}|{piece[:120]}".encode("utf-8")
            ).hexdigest()

            meta: Dict[str, Any] = {
                "source_file": file_name,
                "source_path": rel_path,
                "file_hash": file_hash,
                "locator": block.locator or "",
                "page": int(block.page) if block.page else -1,
                "section": current_heading or "",
                "chunk_index": seq,
                "char_count": len(piece),
                "indexed_at": int(time.time()),
            }
            meta.update({k: str(v) for k, v in (block.extra or {}).items()})
            chunks.append(Chunk(id=uid, text=piece, metadata=meta))

    return chunks


# ============================================================ ana akış

def ingest(cfg: Optional[Config] = None,
           doc_root: Optional[Path] = None,
           rebuild: bool = False,
           dry_run: bool = False,
           verbose: bool = True,
           progress_cb=None) -> Dict[str, Any]:
    """
    Tüm indeksleme akışını yürütür.
    progress_cb(pct: float, message: str) -> Streamlit ilerleme çubuğu için.
    """
    cfg = cfg or load_config()
    ensure_directories(cfg)
    doc_root = Path(doc_root) if doc_root else cfg.resolve("paths.documents")

    def log(msg: str) -> None:
        if verbose:
            print(msg, flush=True)

    def progress(pct: float, msg: str) -> None:
        if progress_cb:
            try:
                progress_cb(max(0.0, min(1.0, pct)), msg)
            except Exception:
                pass

    report: Dict[str, Any] = {
        "added": [], "updated": [], "unchanged": [], "removed": [], "failed": [],
        "ocr_used": [], "ocr_low_quality": [],
        "chunks_written": 0, "started": time.time(),
    }

    if rebuild and not dry_run:
        log("[i] Tam yeniden indeksleme: mevcut koleksiyon siliniyor...")
        vectorstore.reset(cfg)

    manifest = {} if rebuild else load_manifest(cfg)
    collection = vectorstore.get_collection(cfg=cfg)

    files = list(iter_documents(doc_root))
    if not files:
        log(f"[!] '{doc_root}' içinde desteklenen belge bulunamadı.")
        progress(1.0, "Belge bulunamadı")
        report["finished"] = time.time()
        return report

    seen_rel: set = set()
    total = len(files)

    for i, path in enumerate(files):
        rel = str(path.relative_to(doc_root)).replace("\\", "/")
        seen_rel.add(rel)
        pct = i / total
        progress(pct, f"İşleniyor: {path.name}")

        try:
            digest = file_digest(path)
        except Exception as exc:
            report["failed"].append({"file": rel, "error": f"okunamadı: {exc}"})
            continue

        prev = manifest.get(rel)
        if prev and prev.get("hash") == digest and not rebuild:
            report["unchanged"].append(rel)
            log(f"[=] Değişmemiş: {rel}")
            continue

        try:
            ocr_warnings: List[Dict[str, Any]] = []
            blocks = load_document(
                path,
                table_rows_per_chunk=int(cfg.get_path("retrieval.table_rows_per_chunk", 1)),
                pdf_split_table_rows=bool(cfg.get_path("retrieval.pdf_split_table_rows", True)),
                ocr_options=cfg.get_path("ocr", {}) or {},
                progress=lambda m: (log("    " + m), progress(pct, m)),
                warnings=ocr_warnings,
            )
            if any((b.extra or {}).get("ocr") for b in blocks):
                report["ocr_used"].append(rel)
            if ocr_warnings:
                # Bozuk OCR, yanlış sayıların sessizce indekse girmesine
                # yol açar; guardrail bunu yakalayamaz (sayı gerçekten
                # kaynakta vardır). Kullanıcı hangi sayfaların şüpheli
                # olduğunu bilmelidir.
                pages = [str(w["page"]) for w in ocr_warnings]
                report["ocr_low_quality"].append({
                    "file": rel,
                    "pages": pages,
                    "detail": ocr_warnings[:5],
                })
                log(f"[!] {rel}: OCR kalitesi düşük sayfalar: {', '.join(pages)}")
            chunks = blocks_to_chunks(cfg, rel, path.name, digest, blocks)
            if not chunks:
                raise RuntimeError("Anlamlı metin parçası üretilemedi.")

            if dry_run:
                log(f"[?] (kuru çalışma) {rel}: {len(chunks)} parça")
            else:
                # Güncelleme ise önce eski parçaları temizle
                if prev:
                    removed = vectorstore.delete_by_source(collection, rel)
                    log(f"[-] {rel}: {removed} eski parça silindi")

                log(f"[+] {rel}: {len(chunks)} parça vektörleştiriliyor...")
                vectors = embed_passages([c.text for c in chunks], show_progress=verbose)
                vectorstore.upsert(
                    collection,
                    ids=[c.id for c in chunks],
                    documents=[c.text for c in chunks],
                    embeddings=vectors,
                    metadatas=[c.metadata for c in chunks],
                )
                manifest[rel] = {
                    "hash": digest,
                    "chunks": len(chunks),
                    "pages": max((b.page or 0) for b in blocks) or None,
                    "indexed_at": int(time.time()),
                    "size_bytes": path.stat().st_size,
                }

            report["chunks_written"] += len(chunks)
            (report["updated"] if prev else report["added"]).append(rel)

        except Exception as exc:
            log(f"[x] HATA {rel}: {exc}")
            report["failed"].append({"file": rel, "error": str(exc)})

    # Diskten silinmiş belgeleri indeksten düşür
    for rel in list(manifest.keys()):
        if rel not in seen_rel:
            if not dry_run:
                vectorstore.delete_by_source(collection, rel)
                manifest.pop(rel, None)
            report["removed"].append(rel)
            log(f"[-] İndeksten kaldırıldı (dosya yok): {rel}")

    if not dry_run:
        save_manifest(cfg, manifest)

    report["finished"] = time.time()
    report["duration_s"] = round(report["finished"] - report["started"], 1)
    report["collection_count"] = collection.count() if not dry_run else None
    progress(1.0, "Tamamlandı")

    log("\n" + "=" * 58)
    log(f"  Yeni      : {len(report['added'])}")
    log(f"  Güncellenen: {len(report['updated'])}")
    log(f"  Değişmemiş: {len(report['unchanged'])}")
    log(f"  Kaldırılan: {len(report['removed'])}")
    log(f"  Hatalı    : {len(report['failed'])}")
    log(f"  Toplam parça (indeks): {report['collection_count']}")
    log(f"  Süre      : {report['duration_s']} sn")
    log("=" * 58)
    return report


def main() -> int:
    ap = argparse.ArgumentParser(description="Belge Asistanı — belge indeksleyici")
    ap.add_argument("--path", type=str, default=None, help="Belge klasörü (varsayılan: config)")
    ap.add_argument("--rebuild", action="store_true", help="İndeksi sıfırdan oluştur")
    ap.add_argument("--dry-run", action="store_true", help="Yazma yapmadan raporla")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    cfg = load_config()
    rep = ingest(
        cfg=cfg,
        doc_root=Path(args.path) if args.path else None,
        rebuild=args.rebuild,
        dry_run=args.dry_run,
        verbose=not args.quiet,
    )
    return 1 if rep["failed"] else 0


if __name__ == "__main__":
    sys.exit(main())
