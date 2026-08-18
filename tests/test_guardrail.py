"""
HALÜSİNASYON GUARDRAIL — src/verify.py

Buradaki her durum GERÇEK bir hatadan doğdu ve iki yönlü koruma sağlar:

  DÜZELTİLENLER  Guardrail'in DOĞRU cevabı silmesi. Model bilgiyi atıfsız
                 yazıp atfı "Bu nedenle..." cümlesine koyduğunda, atıfsız
                 cümle ayıklanıyor ve geriye içi boş bir kapanış kalıyordu.

  KORUNANLAR     Guardrail'in asıl görevi. Bu testler gevşetilirse sistem
                 uydurma sayıları onaylamaya başlar. Bir düzeltme bunları
                 bozuyorsa DÜZELTME YANLIŞTIR.
"""

from __future__ import annotations

import pytest

from src.verify import check, is_meta, split_sentences, strip_question_echo

# --------------------------------------------------------------- kaynaklar
HAKEDIS_11 = ["11/2024 Envanter sayım dönemi 36 1.455.200,00"]
HAKEDIS_06 = ["06/2024 Yaz sezonu ek vardiya 38 1.548.750,00"]
SERVIS = ["13.2. Personelin işyerine ulaşımı için servis aracı sağlanacaktır. "
          "Servis hizmeti YÜKLENİCİ tarafından karşılanır."]
SURE = ["İşin süresi otuziki (32) aydır. Başlangıç 01/05/2021'dir."]
CEZA = ["10.4. Gizlilik yükümlülüğünün ihlali hâlinde sözleşme bedelinin "
        "yüzde ikisi (%2) oranında ceza uygulanır."]
YEMEK = ["13.1. Personele günlük 145,00 TL yemek bedeli ödenir."]
PERSONEL = ["6.1. İşin yürütülmesinde toplam 34 kişi görevlendirilir."]
ORAN = ["Depo Müdürü 145 Forklift Operatörü 55"]
TALIP = ["7 Kiracı kontrat müddetinin son ayı içinde kiralanan şeyi görmek "
         "için gelen taliplerin gezip görmesine karşı koymaz. 8 Kira müddeti..."]
AVANS = ["5.5. Bu iş için avans verilmeyecektir."]


# =====================================================================
#  DÜZELTİLENLER — guardrail doğru cevabı silmemeli
# =====================================================================

@pytest.mark.parametrize("ad, ham, kaynak, soru, beklenen", [
    ("tablo satırı + içi boş kapanış",
     "11/2024 dönemi Envanter sayım dönemidir ve tutarı 1.455.200,00 TL'dir. "
     "Bu nedenle, [K1][K3] doğru.",
     HAKEDIS_11, "Kasım 2024 döneminin tutarı nedir?", "1.455.200"),

    ("madde referanslı kapanış",
     "Personel için servis aracı sağlanacaktır ve ücreti YÜKLENİCİ tarafından "
     "karşılanır. Bu, [K1] kaynakta MADDE 13.2'de belirtilmiştir.",
     SERVIS, "Servis aracı sağlanacak mıdır?", "servis"),

    ("kapanış cümlesi AYRI SATIRDA",
     "06/2024 döneminde hakediş tutarı 1.548.750,00 TL ve personel sayısı "
     "38'dir.\n[K4][K3] Bu nedenle, tablodaki bilgilere göre bu dönem için "
     "belirlenen değerler bu şekilde geçerli olmaktadır.",
     HAKEDIS_06, "6. ayda hakediş tutarı nedir?", "1.548.750"),

    ("atıf cümle sonu noktasından SONRA gelmiş",
     "Günlük yemek bedeli 145,00 TL'dir. [K2]",
     YEMEK, "Yemek bedeli nedir?", "145"),

    ("gerçek meta cümlesinin atfı devrediliyor",
     "Günlük yemek bedeli 145,00 TL'dir. Bu bilgi [K2] kaynağından alınmıştır.",
     YEMEK, "Yemek bedeli nedir?", "145"),

    ("tek cümlelik kısa yanıt korunur",
     "Bu iş için avans verilmeyecektir [K1].",
     AVANS, "Avans verilecek mi?", "avans"),

    ("madde imli liste bozulmaz",
     "- Depo Müdürü: %145 [K1]\n- Forklift Operatörü: %55 [K1]",
     ORAN, "Unvanlara göre oranlar nedir?", "55"),
])
def test_dogru_cevap_korunur(ad, ham, kaynak, soru, beklenen):
    ok, sebep, _, temiz = check(ham, kaynak, question=soru)
    assert ok, f"{ad}: reddedildi — {sebep}"
    assert beklenen in temiz, f"{ad}: '{beklenen}' yanıttan silinmiş — {temiz!r}"


# =====================================================================
#  KORUNANLAR — guardrail'in asıl görevi
# =====================================================================

def test_uydurma_sayi_atifli_REDDEDILIR():
    """
    Gerçek hata: model doğruyu atıflı yazdı, sonra kendi özet cümlesinde
    sayıyı uydurdu. Kaynakta 32 var, model 30 dedi.
    """
    ok, sebep, _, _ = check(
        "İşin süresi otuziki aydır [K1]. Bu nedenle toplam iş süresi 30 aydır [K1].",
        SURE, question="Sözleşme süresi nedir?")
    assert not ok
    assert "30" in sebep


def test_uydurma_sayi_atifsiz_AYIKLANIR():
    """Atıfsız uydurma cümle silinir, doğru cümle korunur."""
    ok, _, ayrinti, temiz = check(
        "İşin süresi otuziki aydır [K1]. Bu nedenle toplam iş süresi 30 aydır.",
        SURE, question="Sözleşme süresi nedir?")
    assert ok
    assert "otuziki" in temiz
    assert "30 aydır" not in temiz
    assert ayrinti["removed"]


def test_bilgi_tasiyan_kapanis_SILINMEZ():
    """
    Atıf devri mekanizmasının en tehlikeli hatası: gerçek bilgi taşıyan bir
    kapanış cümlesini "taşıyıcı" sanıp silmek. Cevabın kendisi orada.
    """
    ok, _, _, temiz = check(
        "Gizlilik ihlalinde ceza uygulanır [K1]. Bu ceza sözleşme bedelinin "
        "%2'sidir [K1].",
        CEZA, question="Gizlilik ihlali cezası nedir?")
    assert ok
    assert "2" in temiz


@pytest.mark.parametrize("ad, ham, kaynak, soru", [
    ("boş yanıt", "   ", YEMEK, "Yemek bedeli nedir?"),
    ("atıfsız yanıt", "Günlük yemek bedeli 145,00 TL'dir.", YEMEK,
     "Yemek bedeli nedir?"),
    ("yalnızca soru yankısı", "Kaç adet Depo Görevlisi çalıştırılacaktır [K1]?",
     PERSONEL, "Kaç adet Depo Görevlisi çalıştırılacaktır?"),
])
def test_bilgisiz_yanit_reddedilir(ad, ham, kaynak, soru):
    ok, _, _, _ = check(ham, kaynak, question=soru)
    assert not ok, f"{ad}: geçmemeliydi"


# =====================================================================
#  SORU YANKISI — olumsuzluk eki kaybolmamalı
# =====================================================================
#  İlk sürüm ilk 6 harfi kök sayıyordu ("verilecek" ≈ "verilemeyecektir").
#  Türkçede olumsuzluk eki kelimenin ORTASINDA; önek tabanlı kök ayıklama
#  onu göremez ve ZIT anlamlı iki kelime aynı köke iner. Ayıklayıcı doğru
#  cevabı yankı sanıp sildi.

@pytest.mark.parametrize("cevap, soru, korunmali", [
    ("Bu iş için avans verilemeyecektir. [K2]",
     "Bu iş için avans verilecek midir?", "verilemeyecektir"),
    ("Kiracı gelen taliplere karşı koymaz. [K1]",
     "Kiracı gelen taliplere karşı koyar mı?", "koymaz"),
    ("Forklift Operatörü unvanına asgari ücretin yüzde 55 fazlası ödenecektir. [K1]",
     "Forklift Operatörü unvanına asgari ücretin yüzde kaç fazlası ödenecektir?",
     "55"),
    ("Sözleşmenin feshi için 30 gün önceden bildirim yapılmalıdır. [K1]",
     "Sözleşmenin feshi için kaç gün önceden bildirim yapılmalıdır?", "30"),
])
def test_deger_veren_cevap_yanki_sanilmaz(cevap, soru, korunmali):
    kalan = strip_question_echo(cevap, soru)
    assert korunmali in kalan, f"cevap yankı sanılıp silindi: {cevap!r}"


def test_gercek_yanki_ayiklanir():
    """Hiçbir yeni terim getirmeyen cümle gerçekten yankıdır."""
    soru = "Kaç adet Depo Görevlisi çalıştırılacaktır?"
    kalan = strip_question_echo("Kaç adet Depo Görevlisi çalıştırılacaktır [K1]?", soru)
    assert not kalan.strip()


# =====================================================================
#  MADDE NUMARALI BELGELER
# =====================================================================
#  Gerçek bir kira sözleşmesinde maddeler sade rakamla numaralı. Model
#  madde numarasını atıf sandı ([K7]) ve guardrail yanıtı reddetti. Harf
#  etiketi denendi, ölçüldü, geliştirme setinde iki soruya mal olduğu için
#  geri alındı (gerekçe: src/prompts.py). Bu testler, DOĞRU atıflı yanıtların
#  madde numaralı belgelerde sorunsuz geçtiğini garanti eder.

def test_madde_numarali_belgede_dogru_atif_gecer():
    ok, sebep, _, temiz = check(
        "Kiracı, gelen taliplerin gezip görmesine karşı koymaz [K1].",
        TALIP, question="Kiracı taliplere karşı koyabilir mi?")
    assert ok, sebep
    assert "koymaz" in temiz


def test_metindeki_madde_numarasi_sayi_denetimini_bozmaz():
    """Kaynaktaki "7", "8" gibi madde numaraları meşru sayılardır."""
    ok, sebep, _, _ = check(
        "Kiracı 7. maddeye göre karşı koymaz [K1].",
        TALIP, question="Kiracı ne yapar?")
    assert ok, sebep


# =====================================================================
#  YARDIMCI FONKSİYONLAR
# =====================================================================

def test_cumle_bolme_atif_sonrasi_boler():
    """
    "... aydır. [K1] Bu konu ..." tek cümle sayılırsa ayıklama yanlış çalışır;
    gerçek bir hatada tam olarak bu oldu.
    """
    assert len(split_sentences("Süre 32 aydır. [K1] Bu konu ayrıdır.")) >= 2


@pytest.mark.parametrize("cumle, meta_mi", [
    ("[K1]", True),
    ("Bu bilgiler [K1] kaynağından alınmıştır.", True),
    ("Bu iş için avans verilmeyecektir.", False),
    ("Günlük yemek bedeli 145,00 TL'dir.", False),
])
def test_is_meta(cumle, meta_mi):
    """
    Eşik bilinçli olarak çok düşük: "Bu iş için avans verilmeyecektir."
    yalnızca 3 içerik kelimesi taşır ve tamamen doğru bir cevaptır.
    Daha yüksek bir eşik kısa doğru cevapları siliyordu.
    """
    assert is_meta(cumle) is meta_mi
