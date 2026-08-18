"""
SIZINTI TARAYICI — depoya kurum/kişi bilgisi kaçmasın

Projenin ilk şartı şuydu: kaynak kodda hiçbir kurum adı, kişisel bilgi veya
yerel makine izi bulunmayacak. Bu şart insan dikkatine bırakıldığında BİR KEZ
KAÇTI: `server.py` ve `verify_offline.py` başlıklarında kurum adı depoya
gönderildi ve ilk üç taramada da görülmedi.

SEBEBİ ÖĞRETİCİ: `grep -i` Türkçe "İ" harfini "i" ile eşleştirmez. Büyük
harfle yazılmış "ETİ MADEN" desenden kaçtı. Bu yüzden burada Python'un
lower() metodu değil, TÜRKÇEYE DOĞRU küçültme kullanılır.

Kullanım:
    python scripts/check_leaks.py           # git'in bildiği dosyaları tarar
    python scripts/check_leaks.py --all     # çalışma ağacındaki her şeyi tarar

Çıkış kodu 1 ise sızıntı var; CI derlemeyi kırmızıya çevirir.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path
from typing import List

# --------------------------------------------------------------------- desen

# Kuruma özgü terimler. Yeni bir müşteri/proje adıyla çalışılacaksa buraya
# eklenmelidir — liste projeye göre uyarlanır.
KURUM_TERIMLERI = [
    "etimaden", "eti maden", "bandırma", "kolemanit", "trona",
    "asit fabrika", "bor madeni", "kırka",
]

# Kişisel bilgi ve yerel makine izleri
KISISEL_DESENLER = [
    (r"[\w.+-]+@[\w-]+\.[\w.]+", "e-posta adresi"),
    # Ayraç bir VEYA daha fazla olabilir: kaynak kodda hem ham dize
    # (C:\Users\...) hem kaçışlı dize (C:\\Users\\...) biçimi görülür.
    # İlk sürüm tek ayraç bekliyordu ve kaçışlı biçimi KAÇIRIYORDU —
    # tarayıcının kendi testi yakaladı.
    (r"[Cc]:[\\/]+Users[\\/]+[A-Za-z0-9_.-]+", "yerel Windows kullanıcı yolu"),
    (r"/home/[a-z][a-z0-9_-]+/", "yerel Linux kullanıcı yolu"),
]

# Sır/kimlik bilgisi
SIR_DESENLERI = [
    (r"\b(?:api[_-]?key|secret|passwd|password)\s*[:=]\s*['\"][^'\"]{4,}", "sabit kodlanmış sır"),
    (r"\bsk-[A-Za-z0-9]{16,}", "OpenAI biçimli anahtar"),
    (r"\bghp_[A-Za-z0-9]{20,}", "GitHub token"),
]

# İkili/üretilmiş dosyalar taranmaz
ATLA_UZANTI = {".pdf", ".jpg", ".jpeg", ".png", ".svg", ".bin", ".sqlite3",
               ".whl", ".gz", ".zip", ".ico", ".woff", ".woff2"}

# Bu dosyalar YEM İÇERİR: tarayıcının kendisi desenleri tanımlar, testi de
# yakalanması gereken örnekleri ("ETİ MADEN", sahte API anahtarı, yerel yol)
# bilerek barındırır. Taranırlarsa tarayıcı kendi kendini suçlar ve CI hiç
# yeşile dönmez.
#
# TAKAS: Bu iki dosya kör nokta olur. Kabul edilebilir, çünkü ikisi de yalnızca
# test verisi içerir ve gerçek bir belgeye/yapılandırmaya dokunmaz. Alternatifi
# (satır bazlı istisna işaretleri) daha kırılgan olurdu.
ATLA_DOSYA_SONEKI = (
    "scripts/check_leaks.py",
    "tests/test_leak_scanner.py",
)


def tr_lower(s: str) -> str:
    """Türkçeye doğru küçültme. Python'un lower()'ı 'İ' harfinde yanılır."""
    for buyuk, kucuk in (("I", "ı"), ("İ", "i"), ("Ş", "ş"), ("Ğ", "ğ"),
                         ("Ü", "ü"), ("Ö", "ö"), ("Ç", "ç")):
        s = s.replace(buyuk, kucuk)
    return s.lower()


def dosyalari_bul(hepsi: bool) -> List[str]:
    if not hepsi:
        r = subprocess.run(["git", "ls-files"], capture_output=True, text=True)
        if r.returncode == 0:
            return [d for d in r.stdout.split("\n") if d.strip()]
    return [str(p) for p in Path(".").rglob("*")
            if p.is_file() and ".git" not in p.parts and ".venv" not in p.parts]


def tara(dosyalar: List[str]) -> List[str]:
    bulgular: List[str] = []
    for yol in dosyalar:
        norm = yol.replace("\\", "/")
        if norm.endswith(ATLA_DOSYA_SONEKI) or Path(yol).suffix.lower() in ATLA_UZANTI:
            continue
        try:
            icerik = Path(yol).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue

        for i, satir in enumerate(icerik.splitlines(), 1):
            kucuk = tr_lower(satir)
            for terim in KURUM_TERIMLERI:
                if terim in kucuk:
                    bulgular.append(f"{yol}:{i}  kurum terimi {terim!r}")
            for desen, aciklama in KISISEL_DESENLER + SIR_DESENLERI:
                if re.search(desen, satir):
                    bulgular.append(f"{yol}:{i}  {aciklama}")
    return bulgular


def main() -> int:
    ap = argparse.ArgumentParser(description="Depoda kurum/kişi bilgisi taraması")
    ap.add_argument("--all", action="store_true",
                    help="git'in bilmediği dosyaları da tara")
    args = ap.parse_args()

    dosyalar = dosyalari_bul(args.all)
    bulgular = tara(dosyalar)

    print(f"Taranan dosya: {len(dosyalar)}")
    if not bulgular:
        print("✔ Sızıntı bulunamadı.")
        return 0

    print(f"\n✖ {len(bulgular)} olası sızıntı:\n")
    for b in bulgular:
        print("   " + b)
    print("\nBu terimler depoya girmemeli. Düzeltin ya da gerçekten zararsızsa")
    print("scripts/check_leaks.py içindeki listelerden çıkarın.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
