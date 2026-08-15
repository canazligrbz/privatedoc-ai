"""
İNDEKSTE METİN ARAMA — "bu bilgi belgelerimde var mı?"
======================================================

Sistem bir soruya "bilgi bulunamadı" dediğinde iki ihtimal vardır:
  (a) Bilgi belgelerde YOK              -> doğru davranış, yapacak bir şey yok
  (b) Bilgi VAR ama arama bulamadı      -> getirme sorunu, ayar/reranker gerekir

Bu ikisini ayırt etmeden eşik ayarlamak körlemesine olur. Bu betik indekslenmiş
TÜM parçalarda düz metin araması yapar; vektör araması devreye girmez, yani
"arama bulamadı" ihtimalini tamamen dışlar.

Kullanım:
    python scripts/find_text.py yemek
    python scripts/find_text.py "fazla mesai" servis yol
    python scripts/find_text.py --regex "\\d+\\s*TL"
    python scripts/find_text.py yemek --full          # parçanın tamamını yaz
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.airgap import enforce_airgap  # noqa: E402
from src.config import load_config  # noqa: E402

CFG = load_config()
enforce_airgap(
    allowed_hosts=CFG.get_path("security.allowed_hosts", []),
    block_network=bool(CFG.get_path("security.block_outbound_network", True)),
)

from src import vectorstore  # noqa: E402
from src.bm25 import tr_lower  # noqa: E402


def highlight(text: str, term: str, width: int = 130) -> str:
    """Eşleşmenin etrafından bir pencere keser."""
    low = tr_lower(text)
    pos = low.find(tr_lower(term))
    if pos < 0:
        return " ".join(text.split())[:width]
    start = max(0, pos - width // 3)
    end = min(len(text), pos + width)
    snippet = " ".join(text[start:end].split())
    return ("…" if start > 0 else "") + snippet + ("…" if end < len(text) else "")


def main() -> int:
    ap = argparse.ArgumentParser(description="İndekslenmiş parçalarda metin ara")
    ap.add_argument("terms", nargs="+", help="Aranacak kelime(ler)")
    ap.add_argument("--regex", action="store_true", help="Terimleri regex olarak yorumla")
    ap.add_argument("--full", action="store_true", help="Parçanın tamamını yazdır")
    ap.add_argument("--limit", type=int, default=15, help="Terim başına maks. sonuç")
    args = ap.parse_args()

    col = vectorstore.get_collection(cfg=CFG)
    rows = vectorstore.fetch_all(col)
    if not rows:
        print("İndeks boş. Önce belgeleri indeksleyin.")
        return 1

    print(f"\n{len(rows)} parça taranıyor...\n")
    any_hit = False

    for term in args.terms:
        if args.regex:
            pat = re.compile(term, re.IGNORECASE)
            hits = [r for r in rows if pat.search(r["text"] or "")]
        else:
            needle = tr_lower(term)
            hits = [r for r in rows if needle in tr_lower(r["text"] or "")]

        print("=" * 78)
        if not hits:
            print(f"  '{term}'  ->  HİÇ GEÇMİYOR")
            print("     Bilgi belgelerde yok demektir; sistemin reddetmesi DOĞRU davranıştır.")
            print("     (Belge taranmışsa OCR bu kelimeyi okuyamamış da olabilir.)")
            print("=" * 78 + "\n")
            continue

        any_hit = True
        print(f"  '{term}'  ->  {len(hits)} parçada geçiyor")
        print("     Bilgi indekste VAR. Sistem bulamıyorsa sorun GETİRMEDEDİR")
        print("     (eşik / final_k / reranker).")
        print("=" * 78)

        for r in hits[:args.limit]:
            m = r.get("metadata") or {}
            loc = f"{m.get('source_file', '?')} — {m.get('locator', '')}"
            print(f"\n  ▸ {loc}")
            if args.full:
                print("    " + "\n    ".join((r["text"] or "").splitlines()))
            else:
                print(f"    {highlight(r['text'], term)}")
        if len(hits) > args.limit:
            print(f"\n  ... {len(hits) - args.limit} sonuç daha (--limit ile artırın)")
        print()

    if not any_hit:
        print("Aranan terimlerin hiçbiri indekste yok.\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
