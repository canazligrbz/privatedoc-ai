"""
OCR KURULUM YARDIMCISI
======================

Tesseract OCR motorunu bilgisayarda arar, bulursa config.yaml içindeki
`ocr.tesseract_cmd` satırını otomatik doldurur ve Türkçe dil verisini
kontrol eder.

    python scripts/setup_ocr.py
    python scripts/setup_ocr.py --path "D:/Programlar/Tesseract/tesseract.exe"

config.yaml yalnızca TEK SATIRI değiştirilerek güncellenir; dosyadaki
açıklama satırları ve biçim korunur (PyYAML ile yeniden yazılsaydı tüm
yorumlar silinirdi).
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONFIG = PROJECT_ROOT / "config.yaml"

# Windows'ta Tesseract'ın kurulabileceği olağan yerler
CANDIDATES = [
    r"C:\Program Files\Tesseract-OCR\tesseract.exe",
    r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
    os.path.expandvars(r"%LOCALAPPDATA%\Programs\Tesseract-OCR\tesseract.exe"),
    os.path.expandvars(r"%LOCALAPPDATA%\Tesseract-OCR\tesseract.exe"),
    "/usr/bin/tesseract",
    "/usr/local/bin/tesseract",
    "/opt/homebrew/bin/tesseract",
]


def find_tesseract(explicit: str | None = None) -> str | None:
    if explicit:
        p = Path(explicit)
        return str(p) if p.exists() else None
    on_path = shutil.which("tesseract")
    if on_path:
        return on_path
    for c in CANDIDATES:
        if c and Path(c).exists():
            return c
    return None


def run(exe: str, *args: str) -> str:
    try:
        out = subprocess.run([exe, *args], capture_output=True, text=True, timeout=20)
        return (out.stdout or "") + (out.stderr or "")
    except Exception as exc:
        return f"HATA: {exc}"


def update_config(exe_path: str) -> bool:
    """config.yaml içindeki tesseract_cmd satırını yerinde günceller."""
    if not CONFIG.exists():
        print(f"  ✖ config.yaml bulunamadı: {CONFIG}")
        return False

    text = CONFIG.read_text(encoding="utf-8")
    # YAML'da ters bölü sorun çıkarır; ileri bölü kullan
    value = exe_path.replace("\\", "/")
    pattern = re.compile(r'^(\s*tesseract_cmd:\s*).*$', re.MULTILINE)

    if not pattern.search(text):
        print("  ✖ config.yaml içinde 'tesseract_cmd' satırı yok. "
              "ocr bölümünü elle ekleyin.")
        return False

    new_text = pattern.sub(lambda m: f'{m.group(1)}"{value}"', text, count=1)
    if new_text == text:
        print("  = Değer zaten güncel.")
        return True

    CONFIG.write_text(new_text, encoding="utf-8")
    print(f'  ✔ config.yaml güncellendi:  tesseract_cmd: "{value}"')
    return True


def main() -> int:
    ap = argparse.ArgumentParser(description="Tesseract OCR kurulum yardımcısı")
    ap.add_argument("--path", default=None, help="tesseract.exe tam yolu (elle)")
    args = ap.parse_args()

    print("\n" + "=" * 64)
    print("  OCR KURULUM YARDIMCISI")
    print("=" * 64)

    exe = find_tesseract(args.path)

    if not exe:
        print("""
  ✖ Tesseract OCR bulunamadı.

  TARANMIŞ PDF'LERİ OKUMAK İÇİN GEREKLİ. Kurulum:

    1) Şu adrese gidin:
         https://github.com/UB-Mannheim/tesseract/wiki
    2) "tesseract-ocr-w64-setup-...exe" dosyasını indirin (64-bit).
    3) Kurulumu başlatın. "Choose Components" ekranında
       "Additional language data" bölümünü açıp TURKISH kutusunu
       İŞARETLEYİN. Bu adım atlanırsa Türkçe metinler hatalı okunur.
    4) Kurulum bitince bu betiği tekrar çalıştırın:
         python scripts/setup_ocr.py

  Not: Tesseract'ı farklı bir klasöre kurduysanız yolu elle verin:
       python scripts/setup_ocr.py --path "D:/Tesseract/tesseract.exe"
""")
        return 1

    print(f"\n  ✔ Tesseract bulundu: {exe}")

    version = run(exe, "--version").splitlines()
    if version:
        print(f"  ✔ Sürüm: {version[0].strip()}")

    langs_raw = run(exe, "--list-langs")
    langs = {l.strip() for l in langs_raw.splitlines()[1:] if l.strip()}
    print(f"  ℹ Yüklü diller: {', '.join(sorted(langs)) or '(okunamadı)'}")

    if "tur" in langs:
        print("  ✔ Türkçe dil verisi (tur) mevcut.")
    else:
        print("""
  ! TÜRKÇE DİL VERİSİ YOK (tur). Türkçe taramalar hatalı okunacaktır.

    Çözüm A — Kurulumu onarın:
      Tesseract kurulumunu tekrar çalıştırıp "Additional language data"
      altından Turkish'i seçin.

    Çözüm B — Dil dosyasını elle ekleyin:
      https://github.com/tesseract-ocr/tessdata/raw/main/tur.traineddata
      dosyasını indirip Tesseract klasöründeki 'tessdata' alt klasörüne
      kopyalayın, örn:
        C:\\Program Files\\Tesseract-OCR\\tessdata\\tur.traineddata
""")

    print("\n  config.yaml güncelleniyor...")
    ok = update_config(exe)

    # Python tarafındaki paketleri de denetle
    print("\n  Python paketleri kontrol ediliyor...")
    missing = []
    for mod, pkg in (("pypdfium2", "pypdfium2"), ("pytesseract", "pytesseract"), ("PIL", "pillow")):
        try:
            __import__(mod)
            print(f"    ✔ {pkg}")
        except ImportError:
            missing.append(pkg)
            print(f"    ✖ {pkg} eksik")
    if missing:
        print("\n    Kurmak için:  pip install " + " ".join(missing))

    print("\n" + "=" * 64)
    if ok and not missing and "tur" in langs:
        print("  HAZIR. Taranmış PDF'ler artık okunabilir.")
        print("  Sıradaki adım: uygulamada 'Sıfırla' ile yeniden indeksleyin.")
    else:
        print("  Eksikler yukarıda listelendi.")
    print("=" * 64 + "\n")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
