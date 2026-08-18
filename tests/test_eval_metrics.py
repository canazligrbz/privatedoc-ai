"""
DEĞERLENDİRME ARAÇLARI — eval/matching.py ve eval/stats.py

Ölçüm aletinin kendisi de sınanmalıdır: fazla gevşekse sistem olduğundan iyi,
fazla katıysa olduğundan kötü görünür. İkisi de yanlış karar verdirir.
"""

from __future__ import annotations

import pytest
from matching import normalize, value_in
from stats import fark_araligi, oran_ozeti, ortusuyor_mu, wilson_interval


# =====================================================================
#  BEKLENTİ EŞLEŞMESİ
# =====================================================================
#  Düz alt dizi araması kısa sayısal beklentilerde ölçümü şişiriyordu:
#  "6" beklentisi "%16'dır" içinde eşleşiyor ve YANLIŞ cevap geçiyordu.
#  İki test setinde 23 kısa sayısal beklenti vardı.

@pytest.mark.parametrize("beklenen, cevap", [
    ("6", "Kesin teminat oranı sözleşme bedelinin %6'sıdır [K1]."),
    ("6", "Teminat oranı yüzde 6 olarak belirlenmiştir [K1]."),
    ("1.548.750", "06/2024 döneminde tutar 1.548.750,00 TL'dir [K1]."),
    ("145", "Günlük yemek bedeli 145,00 TL'dir [K1]."),
    ("18", "İşin süresi 18 (onsekiz) aydır [K1]."),
    ("2", "Soğuk odada sıcaklık 2 - 8 °C aralığında olmalıdır [K1]."),
    ("24:00", "Üçüncü vardiya 24:00-08:00 arasındadır [K1]."),
    ("500", "Bakım periyodu 500 çalışma saatidir [K1]."),
    ("%10", "Toplam ceza %10'u aştığında fesih edilebilir [K1]."),
    ("18.400", "Merkez Deponun kapalı alanı 18.400 m²'dir [K1]."),
    ("servis", "Personele servis aracı sağlanır, ücreti YÜKLENİCİ karşılar [K1]."),
    ("aydın", "Aydın mahkemeleri ve icra daireleri yetkilidir [K1]."),
])
def test_dogru_cevap_gecer(beklenen, cevap):
    """
    Ölçüt fazla katı olursa doğru cevap yanlış işaretlenir ve var olmayan
    hatalar kovalanır. Bu yön, şişmeden daha tehlikelidir.
    """
    assert value_in(normalize(cevap), beklenen)


@pytest.mark.parametrize("beklenen, cevap, neden", [
    ("6", "Kesin teminat oranı %16'dır [K1].", "16 içindeki 6"),
    ("6", "Garanti süresi 36 aydır [K1].", "36 içindeki 6"),
    ("2", "Sözleşme 2024 tarihlidir [K1].", "2024 içindeki 2"),
    ("2", "Toplam 12 vardiya vardır [K1].", "12 içindeki 2"),
    ("500", "Tutar 1.500,00 TL'dir [K1].", "binlik ayracı"),
    ("8", "Süre 18 aydır [K1].", "18 içindeki 8"),
    ("34", "Toplam 340 palet bulunmaktadır [K1].", "340 içindeki 34"),
    ("145", "Bakım bedeli 1.450,00 TL'dir [K1].", "1.450 içindeki 145"),
])
def test_yakin_yanlis_cevap_elenir(beklenen, cevap, neden):
    assert not value_in(normalize(cevap), beklenen), f"şişme kırılmadı: {neden}"


def test_metin_beklentisi_alt_dizi_kalir():
    """
    Metin beklentilerinde kelime sınırı UYGULANMAZ: Türkçe çekim ekleri
    yüzünden "servis" beklentisi "servisin" içinde \\b ile eşleşmez ve doğru
    bir yanıt yanlış işaretlenirdi.
    """
    assert value_in(normalize("Servisin ücreti yükleniciye aittir."), "servis")


# =====================================================================
#  ÖRNEKLEM İSTATİSTİĞİ
# =====================================================================

def test_wilson_bilinen_deger():
    alt, ust = wilson_interval(28, 29)
    assert round(alt, 3) == 0.828
    assert round(ust, 3) == 0.994


@pytest.mark.parametrize("basarili, toplam", [(29, 29), (0, 29), (1, 29), (16, 16)])
def test_wilson_sinir_disina_tasmaz(basarili, toplam):
    """
    Wilson'ın seçilme sebebi: klasik (Wald) yaklaşımı küçük örneklemde ve
    oran 1'e yakınken [0,1] dışına taşar — 28/29 için üst sınırı %100'ün
    üstüne çıkarır, 29/29 için "hiç belirsizlik yok" der.
    """
    alt, ust = wilson_interval(basarili, toplam)
    assert 0.0 <= alt <= ust <= 1.0


def test_wilson_bos_orneklem_cokmez():
    assert wilson_interval(0, 0) == (0.0, 0.0)


def test_tam_basarida_bile_belirsizlik_var():
    """5/5 = %100 ama aralık %57'ye kadar iner; küçük örneklem böyledir."""
    alt, _ = wilson_interval(5, 5)
    assert alt < 0.7


def test_genelleme_farki_sifiri_iceriyor():
    """
    Geliştirme 28/29 ↔ ayrılmış 27/29. Fark 3,4 puan ama aralık sıfırı
    içeriyor: bu örneklemle AŞIRI UYUMA DAİR KANIT BULUNAMADI. Bu,
    "sistem genelliyor" demek DEĞİLDİR.
    """
    d = fark_araligi(28, 29, 27, 29)
    assert not d["anlamli"]
    assert d["alt"] < 0 < d["ust"]


def test_ocr_farki_gercek_ama_buyuklugu_belirsiz():
    """
    Geliştirme 28/29 ↔ taranmış 9/16. Aralık sıfırı içermiyor → etki gerçek.
    Ama genişliği 30 puandan fazla → "OCR 40 puana mal oluyor" demek
    veriden daha kesin konuşmaktır.
    """
    d = fark_araligi(28, 29, 9, 16)
    assert d["anlamli"]
    assert d["alt"] > 0
    assert (d["ust"] - d["alt"]) > 30


def test_ortusme_kontrolu():
    assert ortusuyor_mu(oran_ozeti(28, 29), oran_ozeti(27, 29))
    assert not ortusuyor_mu(oran_ozeti(28, 29), oran_ozeti(9, 16))
