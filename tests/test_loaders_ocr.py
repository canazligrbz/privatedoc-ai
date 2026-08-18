"""
BELGE OKUMA VE OCR — src/loaders.py, src/ocr.py

Bu katmandaki hatalar en sinsi olanlardır: veri sessizce bozulur ya da
kaybolur, guardrail bunu YAKALAYAMAZ (sayı gerçekten kaynakta vardır).
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from src.loaders import (IMAGE_EXTENSIONS, SUPPORTED_EXTENSIONS, _DISPATCH,
                         _detect_boilerplate, _strip_boilerplate, load_image)
from src.ocr import assess_content_loss, chars_per_ink


# =====================================================================
#  ÜSTBİLGİ / ALTBİLGİ AYIKLAMA
# =====================================================================
#  Sayfa altbilgisi tablo satırı olarak indekslenip sözleşme numarası
#  içerdiği için aramada ilk sıralara çıkıyordu; gerçek bir ölçümde dört
#  kaynak slotundan biri altbilgi parçasına gitti.

SAYFALAR = [
    "ADL-2024/117 — Sözleşme    Sayfa 1\nMADDE 1 — TARAFLAR\n1.1. Taraflar şunlardır.",
    "ADL-2024/117 — Sözleşme    Sayfa 2\nMADDE 2 — KONU\n2.1. Konu depolamadır.",
    "ADL-2024/117 — Sözleşme    Sayfa 3\nMADDE 3 — BEDEL\n3.1. Bedel 100 TL'dir.",
    "ADL-2024/117 — Sözleşme    Sayfa 4\nMADDE 4 — SÜRE\n4.1. Süre 18 aydır.",
]


def test_altbilgi_tespit_edilir():
    """Sayfa numaraları değiştiği için karşılaştırmadan önce maskelenir."""
    assert len(_detect_boilerplate(SAYFALAR)) == 1


def test_altbilgi_ayiklanir_icerik_korunur():
    bp = _detect_boilerplate(SAYFALAR)
    for sayfa in SAYFALAR:
        temiz = _strip_boilerplate(sayfa, bp)
        assert "Sayfa" not in temiz.splitlines()[0]
        assert "MADDE" in temiz


def test_sayfa_ORTASINDAKI_ayni_ifade_korunur():
    """
    Konum kısıtı bilinçli: aynı ifade sayfa ortasında GERÇEK İÇERİK olabilir
    (sözleşme numarasının metin içinde anılması gibi).
    """
    bp = _detect_boilerplate(SAYFALAR)
    orta = ("MADDE 5 — ATIF\n"
            "5.1. ADL-2024/117 — Sözleşme    Sayfa 9 ibaresi burada içeriktir.\n"
            "5.2. Devam.")
    assert "ibaresi burada içeriktir" in _strip_boilerplate(orta, bp)


def test_az_sayfada_tespit_yapilmaz():
    """İki sayfada "her sayfada tekrarlıyor" demek güvenilir değildir."""
    assert _detect_boilerplate(SAYFALAR[:2]) == set()


# =====================================================================
#  GÖRÜNTÜ DOSYASI DESTEĞİ
# =====================================================================

def test_goruntu_uzantilari_kayitli():
    assert IMAGE_EXTENSIONS <= SUPPORTED_EXTENSIONS
    assert all(e in _DISPATCH for e in IMAGE_EXTENSIONS)


def test_ocr_kapaliyken_goruntu_SESSIZ_gecilmez():
    """
    PDF'te OCR bir yedek yoldur; GÖRÜNTÜDE tek yoldur. Sessizce boş dönmek
    kullanıcıyı "belge indekslendi ama hiçbir soruya cevap yok" durumunda
    bırakır ve sebebini bulamaz.
    """
    with tempfile.TemporaryDirectory() as d:
        sahte = Path(d) / "tarama.jpg"
        sahte.write_bytes(b"gecerli bir jpeg degil")
        with pytest.raises(RuntimeError, match="ocr.enabled"):
            load_image(sahte, ocr_options={"enabled": False})


# =====================================================================
#  SESSİZ İÇERİK KAYBI
# =====================================================================
#  assess_quality bozuk KARAKTER arar. Bir ücret tablosunun yedi veri
#  satırının tamamı OCR'da kayboldu ve o sayfa 1.00 (kusursuz) aldı:
#  bozulmamış metinde aranacak bozukluk yoktur, kaybolan içerik iz bırakmaz.
#  Çözüm metni SAYFA GÖRÜNTÜSÜYLE karşılaştırmaktır.
#
#  Değerler gerçek ölçümden (300 dpi, ornek_belgeler/taranmis):
#      hasarsız düz metin sayfası : 4,0 krk/mürekkep
#      tablo satırı kaybeden sayfa: 2,5 - 2,7

def _stat(karakter: int, murekkep: float) -> dict:
    return {"ink_ratio": murekkep, "chars": float(karakter),
            "chars_per_ink": chars_per_ink(karakter, murekkep)}


HASARLI = _stat(577, 0.0214)    # -> 2,7  (ücret tablosu, 7 satır kayıp)
SAGLAM = _stat(1014, 0.0254)    # -> 4,0  (düz metin, kayıp yok)


def test_icerik_kaybeden_sayfa_yakalanir():
    skor, sorunlar = assess_content_loss(HASARLI, doc_best=SAGLAM["chars_per_ink"])
    assert sorunlar
    assert skor < 0.8
    assert any("tablo satırları" in s for s in sorunlar), "uyarı eyleme dönüşmeli"


def test_saglam_sayfa_uyari_ALMAZ():
    """Sürekli uyaran bir sistem, hiç uyarmayan kadar işe yaramaz."""
    skor, sorunlar = assess_content_loss(SAGLAM, doc_best=SAGLAM["chars_per_ink"])
    assert not sorunlar
    assert skor == 1.0


def test_neredeyse_bos_sayfa_uyari_ALMAZ():
    """Kapak/ayraç sayfası gerçekten boştur; bu bir kayıp değildir."""
    _, sorunlar = assess_content_loss(_stat(12, 0.0005), doc_best=4.0)
    assert not sorunlar


def test_tum_sayfalar_hasarliysa_mutlak_esik_devrede():
    """
    Göreli ölçüt (belgenin en iyi sayfasıyla kıyas) yazı boyutuna göre kendini
    ayarlar ama TÜM sayfalar hasarlıysa işe yaramaz — referans da bozuktur.
    Mutlak eşik tam olarak o boşluğu kapatır.
    """
    _, sorunlar = assess_content_loss(HASARLI, doc_best=HASARLI["chars_per_ink"])
    assert sorunlar


def test_chars_per_ink_sifira_bolmez():
    assert chars_per_ink(100, 0.0) == 0.0
