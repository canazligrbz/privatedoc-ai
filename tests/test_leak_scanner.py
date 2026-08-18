"""
SIZINTI TARAYICISI — scripts/check_leaks.py

Bu tarayıcı, projenin ilk şartını (kaynak kodda kurum/kişi bilgisi olmasın)
insan dikkatinden alıp makineye bağlar. Şart bir kez insan dikkatine
bırakıldı ve KAÇTI: kurum adı iki dosyanın başlığında depoya gönderildi ve
üç ayrı taramada da görülmedi.

Kaçmasının sebebi bu testlerin varlık nedenidir: `grep -i` Türkçe "İ"
harfini "i" ile eşleştirmez, dolayısıyla BÜYÜK HARFLE yazılmış "ETİ MADEN"
desenden kaçar.

Hiç ateşlemeyen bir tarayıcı, olmayan tarayıcıdan daha tehlikelidir —
güvence hissi verir. Bu yüzden hem YAKALADIĞI hem YAKALAMADIĞI sınanır.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from check_leaks import tara, tr_lower  # noqa: E402


def _tara_metin(icerik: str) -> list:
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "ornek.py"
        p.write_text(icerik, encoding="utf-8")
        return tara([str(p)])


# =====================================================================
#  TÜRKÇE BÜYÜK HARF — asıl kaçış yolu
# =====================================================================

def test_tr_lower_buyuk_I_dogru_donusur():
    assert tr_lower("ETİ MADEN") == "eti maden"
    assert tr_lower("IZIN") == "ızın"


@pytest.mark.parametrize("yazim", [
    "eti maden",
    "ETİ MADEN",
    "Eti Maden",
    "ETİMADEN",
    "EtiMaden".replace("M", "m"),
])
def test_kurum_adi_her_yazimda_yakalanir(yazim):
    """
    BÜYÜK HARFLİ yazım tam olarak depoya kaçan biçimdi. Bu test o kaçışın
    tekrarını engeller.
    """
    assert _tara_metin(f'"""{yazim} — Web Sunucusu"""'), f"{yazim!r} kaçtı"


# =====================================================================
#  KİŞİSEL BİLGİ VE YEREL İZLER
# =====================================================================

@pytest.mark.parametrize("satir, aciklama", [
    ('EPOSTA = "birisi@ornek.com"', "e-posta"),
    (r'YOL = "C:\\Users\\Ahmet\\Desktop\\proje"', "Windows kullanıcı yolu"),
    ('YOL = "/home/ahmet/proje"', "Linux kullanıcı yolu"),
    ('API_KEY = "sk-abcdefghijklmnopqrstuvwx"', "API anahtarı"),
    ('password = "gizli123"', "sabit kodlanmış parola"),
])
def test_kisisel_ve_sir_bilgisi_yakalanir(satir, aciklama):
    assert _tara_metin(satir), f"{aciklama} yakalanmadı"


# =====================================================================
#  YANLIŞ POZİTİF — sürekli ateşleyen tarayıcı da işe yaramaz
# =====================================================================

@pytest.mark.parametrize("satir", [
    "# Sözleşme bedeli 24.750.000 TL",
    "from src.bm25 import tr_lower",
    'REFUSAL = "Bu konu hakkında bilgi bulunmamaktadır."',
    "# Aydın mahkemeleri ve icra daireleri yetkilidir",   # sentetik belge içeriği
    "chunk_size: 700  # karakter",
])
def test_zararsiz_satir_uyari_URETMEZ(satir):
    assert not _tara_metin(satir), f"yanlış pozitif: {satir!r}"


def test_ikili_dosyalar_atlanir():
    """PDF/JPG taranmaz; içlerindeki sıkıştırılmış baytlar yanlış eşleşir."""
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "belge.pdf"
        p.write_bytes(b"eti maden")
        assert not tara([str(p)])
