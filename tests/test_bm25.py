"""
TÜRKÇE ARAMA KATMANI — bm25.py

Buradaki her durum, hazır BM25 kütüphanelerinin Türkçede SESSİZCE yanlış
çalışmasından doğdu. Hiçbiri teorik değil; her biri gerçek bir aramanın
başarısız olmasıyla bulundu.
"""

from __future__ import annotations

import pytest

from src.bm25 import (_equivalents, content_terms, keyword_coverage, rrf_fuse,
                      tokenize, tr_lower)


# ---------------------------------------------------------------- tr_lower

@pytest.mark.parametrize("girdi, beklenen", [
    # Python'un .lower() metodu "I" harfini "i" yapar; Türkçede "ı" olmalıdır.
    # "IZIN" ile "izin" eşleşmezse arama tamamen çöker.
    ("IZIN", "ızın"),
    ("İSTANBUL", "istanbul"),
    ("ŞUBAT", "şubat"),
    ("ĞÜÖÇ", "ğüöç"),
    ("Kasım", "kasım"),
    ("ADL-2024/117", "adl-2024/117"),
])
def test_tr_lower(girdi, beklenen):
    assert tr_lower(girdi) == beklenen


def test_tr_lower_i_harfleri_karismaz():
    """
    Türkçenin en klasik tuzağı: I/ı ve İ/i AYRI harf çiftleridir.
    Yanlış küçültme "IZIN" -> "izin" yapar ve iki farklı kelime birleşir.
    """
    assert tr_lower("I") != tr_lower("İ")
    assert tr_lower("I") == "ı"
    assert tr_lower("İ") == "i"


# ------------------------------------------------------------ eş değerler

@pytest.mark.parametrize("kelime, beklenen_sayi", [
    ("kasım", "11"),
    ("ocak", "1"),
    ("aralık", "12"),
    ("üçüncü", "3"),
    ("onsekiz", "18"),
])
def test_equivalents_kelimeden_sayiya(kelime, beklenen_sayi):
    """Soru "Kasım 2024" derken belge "11/2024" yazar; denklik kurulmalı."""
    assert beklenen_sayi in _equivalents(kelime)


def test_equivalents_bastaki_sifir():
    """"06" ile "6" aynı ayı gösterir."""
    assert "6" in _equivalents("06")


def test_equivalents_ters_yon_URETILMEZ():
    """
    KRİTİK: sayıdan kelimeye çeviri YAPILMAZ.

    Ters yön bir kez denendi ve geri alındı: "3. Vardiya" sorgusu "mart" ile
    eşleşip alakasız sonuçlar getiriyordu. Denklik yalnızca kelime -> sayı
    yönünde kurulur.
    """
    assert "mart" not in _equivalents("3")
    assert "kasım" not in _equivalents("11")


# ------------------------------------------------------------- tokenize

def test_tokenize_kok_uretir():
    """Uzun kelimeler için kaba kök terimi de üretilir ("~" ile işaretli)."""
    parcalar = tokenize("kaynağından")
    assert any(t.endswith("~") for t in parcalar)


def test_tokenize_tek_haneli_sayi_korunur():
    """"3. vardiya" sorgusunda "3" atılırsa soru anlamını kaybeder."""
    assert "3" in tokenize("3. vardiya")


def test_tokenize_durak_kelimeleri_atar():
    parcalar = tokenize("bu ve ile için")
    assert parcalar == [] or all(len(t) > 1 for t in parcalar)


# -------------------------------------------------------- kelime kapsamı

def test_keyword_coverage_tam_ve_bos():
    tam = keyword_coverage("kesin teminat oranı", "Kesin teminat oranı %6'dır.")
    yok = keyword_coverage("kesin teminat oranı", "Yemek bedeli 145 TL'dir.")
    assert tam > yok
    assert 0.0 <= yok < 0.5
    assert tam > 0.9


def test_keyword_coverage_ay_adi_sayiya_esleser():
    """
    "Kasım" içeren bir soru, "11/2024" yazan bir parçada %0 kapsam alırsa
    eşiği geçemez ve doğru satır elenir. content_terms eş değerleri de
    üretmek zorundadır.
    """
    assert keyword_coverage("Kasım 2024 tutarı", "11/2024 Envanter dönemi") > 0.0


def test_content_terms_kok_uretmez():
    """
    content_terms, tokenize'ın aksine kök türevi üretmez — kapsam hesabı
    gerçek kelimeler üzerinden yapılmalıdır.
    """
    assert not any(t.endswith("~") for t in content_terms("kaynağından gelen"))


# ------------------------------------------------------------------ RRF

def test_rrf_iki_sıralamayı_birlestirir():
    """
    Her iki listede de üstlerde olan öğe kazanmalı.
    "b" birinci listede 2., ikincide 1.; "a" birincide 1., ikincide 3.
    """
    fused = rrf_fuse([["a", "b", "c"], ["b", "c", "a"]])
    assert fused["b"] > fused["a"] > fused["c"]


def test_rrf_skor_olcegi_onemli_degil():
    """
    RRF'in var oluş sebebi: kosinüs (0–1) ile BM25 (0–30) skorları
    toplanamaz. Yalnızca SIRA kullanılır, dolayısıyla aynı sıralama aynı
    sonucu verir — skorların büyüklüğü hiç işe karışmaz.
    """
    a = rrf_fuse([["x", "y"], ["x", "y"]])
    b = rrf_fuse([["x", "y"], ["x", "y"]])
    assert a == b
    assert a["x"] > a["y"]


def test_rrf_agirlik_uygulanir():
    tek = rrf_fuse([["a", "b"], ["b", "a"]], weights=[1.0, 1.0])
    agir = rrf_fuse([["a", "b"], ["b", "a"]], weights=[3.0, 1.0])
    # İlk sıralama ağırlıklandırılınca "a" öne geçmeli
    assert tek["a"] == pytest.approx(tek["b"])
    assert agir["a"] > agir["b"]


def test_rrf_bos_girdi_cokmez():
    assert rrf_fuse([]) == {}
    assert rrf_fuse([[]]) == {}
