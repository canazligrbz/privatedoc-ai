"""
METİN TARAFI DOĞRULAMA — src/verify.unsupported_terms()

Sayı denetimi yalnızca SAYI GÖRÜRSE çalışır. Sayısız bir belgede tüm katman
boşta kalır. Bu modül o boşluğu kapatır; buradaki testler iki şeyi birden
korur:

  YAKALANMALI   Kaynakta hiç karşılığı olmayan kelimeler. Baş örnek gerçek
                bir ölçümden: model "yöneticiyi" yerine "yındıktıyı" yazdı,
                yanıt atıflıydı, uydurma sayı yoktu, altı katman da geçirdi.

  GEÇMELİ       Türkçe çekim ekleri. Bu testler bozulursa katman doğru
                cevapları işaretlemeye başlar — bu projede üç kez yaşanan
                "guardrail doğru cevabı sildi" hatasının tekrarı olur.

ÖLÇÜT YÖNÜ: gevşeklik güvenlidir (kaçırır), katılık pahalıdır (yanlış alarm).
Bir düzeltme "GEÇMELİ" testlerini bozuyorsa düzeltme yanlıştır.
"""

from __future__ import annotations

import pytest

from src.verify import check, unsupported_terms

# --------------------------------------------------------------- kaynaklar
# Gerçek yönetmelik metninden (personel_yonetmeligi.pdf, madde 4)
BIRIM_AMIRI = ["4 Bu yönetmelikte geçen Birim Amiri deyimi, personelin bağlı "
               "bulunduğu en yakın üst yöneticiyi ifade eder."]
CEZA = ["16 Disiplin cezaları uyarma, kınama, aylıktan kesme, kademe "
        "ilerlemesinin durdurulması ve görevden çıkarma cezalarıdır."]
IZIN = ["10 Yıllık izin, hizmet süresi bir yılı dolduran personele verilir."]


# =====================================================================
#  YAKALANMALI — kaynakta karşılığı olmayan kelime
# =====================================================================

def test_gercek_bozulma_yakalanir():
    """
    ÖLÇÜLMÜŞ VAKA. Yönetmelik setinde Q2, iki bağımsız koşuda birebir aynı
    çıktıyı üretti. Bu testin amacı o çıktının bir daha sessizce geçmemesi.
    """
    yanit = ("Birim Amiri deyimi, personelin bağlı bulunduğu en yakın üst "
             "yındıktıyı ifade eder. [K1][K2]")
    assert "yındıktıyı" in unsupported_terms(yanit, BIRIM_AMIRI)


def test_tamamen_uydurma_terim():
    yanit = "Disiplin cezaları arasında maaştan mahrumiyet de vardır. [K1]"
    flagged = unsupported_terms(yanit, CEZA)
    assert "mahrumiyet" in flagged


def test_kaynakta_olmayan_ozel_isim():
    yanit = "Bu karar Yükseloğlu Komisyonu tarafından verilir. [K1]"
    assert "yükseloğlu" in unsupported_terms(yanit, CEZA)


# =====================================================================
#  GEÇMELİ — Türkçe çekimi işaretlememeli
# =====================================================================

@pytest.mark.parametrize("ad, yanit, kaynak", [
    # kaynak "yöneticiyi" -> model aynısı
    ("birebir",
     "Birim Amiri, en yakın üst yöneticiyi ifade eder. [K1]", BIRIM_AMIRI),

    # iki taraf da farklı çekimli: "yöneticiyi" ↔ "yöneticiye"
    ("iki taraf da çekimli",
     "En yakın üst yöneticiye ifade eder. [K1]", BIRIM_AMIRI),

    # kaynak "cezaları", model "cezalandırma" — ortak önek "cezal" (5/8)
    ("kısa kökten uzun türev",
     "Cezalandırma yapılır. [K1]", CEZA),

    # kaynak "kesme"(5), model "kesilmesi"(9) — ortak önek yalnızca "kes"(3).
    # Sabit 6 harflik önek kuralı bunu KAÇIRIRDI; oransal ölçüt yakalar.
    ("kısa fiil kökü + çatı eki",
     "Aylıktan kesilmesi gerekir. [K1]", CEZA),

    # kaynak "verilir", model "verilmez" — OLUMSUZ hâli işaretlenmemeli.
    # (Olumsuzluğu ayırt etmek bu katmanın işi değil; kelimenin kaynakta
    #  karşılığı olup olmadığına bakar. Olumsuzluk denetimi ayrı bir sorun.)
    ("olumsuzluk eki kök eşleşmesini bozmaz",
     "Bir yılı doldurmayan personele verilmez. [K1]", IZIN),
])
def test_cekim_ekleri_isaretlenmez(ad, yanit, kaynak):
    assert unsupported_terms(yanit, kaynak) == [], ad


def test_sorudaki_kelimeler_destekleyici_sayilir():
    """
    Model soruyu tekrarlamakta serbesttir ve soru metni kullanıcıdan gelir;
    uydurma değildir. Soru kelimeleri kaynakta geçmese de işaretlenmez.
    """
    soru = "Disiplin cezalarının uygulanma sıralaması zorunlu mudur?"
    yanit = "Sıralama zorunlu değildir. [K1]"
    assert unsupported_terms(yanit, CEZA, question=soru) == []


def test_baglac_ve_kalip_kelimeler_isaretlenmez():
    """Modelin kaynaktan bağımsız üretmesi meşru olan üstdil kelimeleri."""
    yanit = ("Dolayısıyla bu bilgiler kaynaklarda belirtilmektedir ve "
             "bulunmamaktadır. [K1]")
    assert unsupported_terms(yanit, CEZA) == []


def test_kisa_kelimeler_denetlenmez():
    """
    6 harften kısa kelimelerde meşru yeniden ifade olasılığı yüksek,
    bozulmayı ayırt etme gücü düşüktür. Bilinçli bir kaçırma.
    """
    yanit = "Bu ceza için asma vardır. [K1]"
    assert "asma" not in unsupported_terms(yanit, CEZA)


def test_sayilar_bu_katmanin_isi_degil():
    """Sayı denetimi ayrı katman; burada sayı hiç tokenlaştırılmaz."""
    yanit = "Disiplin cezaları 9999 olarak belirtilmiştir. [K1]"
    assert unsupported_terms(yanit, CEZA) == []


def test_BILINEN_YANLIS_ALARM_kaynakta_gecmeyen_yaygin_fiil():
    """
    KATMANIN BİLİNEN ZAYIFLIĞI — belgeleme amaçlı, kusur değil.

    Model, kaynakta hiç geçmeyen ama tamamen meşru bir Türkçe fiil
    kullanabilir. Katman bunu uydurma sayar:

        kaynak : "...cezalarıdır."   (düzenle- kökü geçmiyor)
        model  : "...ceza düzenlenir."

    Beyaz liste bu tür kelimeleri kapsamaya çalışır ama TAM DEĞİLDİR ve tam
    olamaz — çevrimdışı bir Türkçe sözlük yok. Nitekim ilk gölge ölçümde
    çıkan dört yanlış alarmın (arasında, olmalıdır, aralığında, tarafından)
    dördü de bu sınıftandı ve listeye sonradan eklendi.

    Listeyi büyütmek bu sorunu KAPATMAZ, yalnızca erteler; yapısal çözüm
    kelimeyi getirilen parçalar yerine TÜM KORPUS sözlüğüyle karşılaştırmak
    olurdu (bkz. YAPILACAKLAR → A2). Bu test, zayıflığın sessizce
    unutulmamasını sağlar.
    """
    yanit = "Bu durumda ceza düzenlenir. [K1]"
    assert "düzenlenir" in unsupported_terms(yanit, CEZA)


# =====================================================================
#  check() ENTEGRASYONU — kip davranışı
# =====================================================================

BOZUK = ("Birim Amiri deyimi, personelin bağlı bulunduğu en yakın üst "
         "yındıktıyı ifade eder. [K1]")


def test_off_kipinde_hic_calismaz():
    ok, _, details, _ = check(BOZUK, BIRIM_AMIRI, verify_text="off")
    assert ok is True
    assert details["unsupported"] == []


def test_warn_kipinde_kaydeder_ama_REDDETMEZ():
    """
    Gölge mod. Yanlış alarm oranı ölçülmeden hiçbir cevap reddedilmemeli;
    bu testin gevşetilmesi ölçümsüz blokçuya geçiş demektir.
    """
    ok, _, details, cleaned = check(BOZUK, BIRIM_AMIRI, verify_text="warn")
    assert ok is True, "warn kipi yanıtı reddetmemeli"
    assert "yındıktıyı" in details["unsupported"]
    assert cleaned.strip(), "yanıt korunmalı"


def test_block_kipinde_reddeder():
    ok, reason, details, _ = check(BOZUK, BIRIM_AMIRI, verify_text="block")
    assert ok is False
    assert "yındıktıyı" in reason
    assert "yındıktıyı" in details["unsupported"]


def test_block_kipi_dogru_cevabi_reddetmez():
    """Katmanın en tehlikeli hatası: doğru cevabı reddetmek."""
    dogru = ("Birim Amiri deyimi, personelin bağlı bulunduğu en yakın üst "
             "yöneticiyi ifade eder. [K1]")
    ok, reason, _, _ = check(dogru, BIRIM_AMIRI,
                             question="Birim Amiri deyimi neyi ifade eder?",
                             verify_text="block")
    assert ok is True, reason


def test_varsayilan_kip_reddetmez():
    """
    check() varsayılanı "off". Katman açıkça istenmeden devreye girmemeli;
    mevcut ölçüm sonuçlarının anlamı böylece korunur.
    """
    ok, _, details, _ = check(BOZUK, BIRIM_AMIRI)
    assert ok is True
    assert details["unsupported"] == []
