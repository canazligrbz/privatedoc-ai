"""
HIZLI BİRİM TESTLERİ
====================
Kapsam: guardrail (src/verify.py) · değerlendirme ölçütü (eval/matching.py)
        · belge okuma (src/loaders.py)

Buradaki her durum GERÇEK bir hatadan doğdu. Değerlendirme koşuları
(run_eval.py) LLM gerektirir ve ~15 dakika sürer; bu testler saniyeler
içinde çalışır ve guardrail mantığındaki gerilemeleri anında yakalar.

    python eval/test_verify.py

İki yönlü koruma sağlar:

  DÜZELTİLENLER  Guardrail'in DOĞRU cevabı silmesi. Model bilgiyi atıfsız
                 yazıp atfı "Bu nedenle..." cümlesine koyduğunda, atıfsız
                 cümle ayıklanıyor ve geriye içi boş kapanış kalıyordu.

  KORUNANLAR 🔒  Guardrail'in asıl görevi. Bu testler gevşetilirse sistem
                 uydurma sayıları onaylamaya başlar. Bir düzeltme bunları
                 bozuyorsa düzeltme yanlıştır.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import List, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from matching import normalize, value_in  # noqa: E402
from src.verify import check  # noqa: E402

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

# (ad, ham_yanıt, kaynaklar, soru, geçmeli_mi, yanıtta_bulunmalı)
DURUMLAR = [
    # ---------------------------------------------------------- DÜZELTİLENLER
    ("tablo satırı + boş kapanış",
     "11/2024 dönemi Envanter sayım dönemidir ve tutarı 1.455.200,00 TL'dir. "
     "Bu nedenle, [K1][K3] doğru.",
     HAKEDIS_11, "Kasım 2024 döneminin tutarı nedir?", True, "1.455.200"),

    ("madde referanslı kapanış",
     "Personel için servis aracı sağlanacaktır ve ücreti YÜKLENİCİ tarafından "
     "karşılanır. Bu, [K1] kaynakta MADDE 13.2'de belirtilmiştir.",
     SERVIS, "Servis aracı sağlanacak mıdır?", True, "servis"),

    ("kapanış AYRI SATIRDA",
     "06/2024 döneminde hakediş tutarı 1.548.750,00 TL ve personel sayısı 38'dir.\n"
     "[K4][K3] Bu nedenle, tablodaki bilgilere göre bu dönem için belirlenen "
     "değerler bu şekilde geçerli olmaktadır.",
     HAKEDIS_06, "6. ayda hakediş tutarı nedir?", True, "1.548.750"),

    ("soru yankısı reddedilmeli",
     "Kaç adet Depo Görevlisi çalıştırılacaktır [K1]?",
     PERSONEL, "Kaç adet Depo Görevlisi çalıştırılacaktır?", False, None),

    # Aşağıdaki iki durum, yankı ayıklayıcısının ORAN ölçütüyle yazılmış ilk
    # sürümünde BOZULDU. Cevap sorudan yalnızca aranan değer kadar farklı;
    # örtüşme %85 eşiğini aşıyor ve doğru cevap yankı sanılıp siliniyordu.
    ("🔒 cevap soruyu tekrarlıyor ama DEĞER veriyor (yüzde)",
     "Forklift Operatörü unvanına asgari ücretin yüzde 55 fazlası "
     "ödenecektir. [K1]",
     ORAN, "Forklift Operatörü unvanına asgari ücretin yüzde kaç fazlası "
           "ödenecektir?", True, "55"),

    ("🔒 cevap soruyu tekrarlıyor ama DEĞER veriyor (gün)",
     "Sözleşmenin feshi için 30 gün önceden bildirim yapılmalıdır. [K1]",
     ["15.1. Taraflar, 30 (otuz) gün önceden yazılı bildirimde bulunmak "
      "kaydıyla sözleşmeyi feshedebilir."],
     "Sözleşmenin feshi için kaç gün önceden bildirim yapılmalıdır?",
     True, "30"),

    ("atıf cümle sonu noktasından SONRA gelmiş",
     "Günlük yemek bedeli 145,00 TL'dir. [K2]",
     YEMEK, "Yemek bedeli nedir?", True, "145"),

    ("gerçek meta cümlesi devrediliyor",
     "Günlük yemek bedeli 145,00 TL'dir. Bu bilgi [K2] kaynağından alınmıştır.",
     YEMEK, "Yemek bedeli nedir?", True, "145"),

    # ------------------------------------------------------------- KORUNANLAR
    ("🔒 uydurma sayı (atıflı) REDDEDİLMELİ",
     "İşin süresi otuziki aydır [K1]. Bu nedenle toplam iş süresi 30 aydır [K1].",
     SURE, "Sözleşme süresi nedir?", False, None),

    ("🔒 uydurma sayı (atıfsız) AYIKLANMALI",
     "İşin süresi otuziki aydır [K1]. Bu nedenle toplam iş süresi 30 aydır.",
     SURE, "Sözleşme süresi nedir?", True, "otuziki"),

    ("🔒 BİLGİ TAŞIYAN kapanış SİLİNMEMELİ",
     "Gizlilik ihlalinde ceza uygulanır [K1]. Bu ceza sözleşme bedelinin "
     "%2'sidir [K1].",
     CEZA, "Gizlilik ihlali cezası nedir?", True, "2"),

    ("tek cümlelik kısa yanıt korunmalı",
     "Bu iş için avans verilmeyecektir [K1].",
     ["5.5. Bu iş için avans verilmeyecektir."], "Avans verilecek mi?",
     True, "avans"),

    ("madde imli liste bozulmamalı",
     "- Depo Müdürü: %145 [K1]\n- Forklift Operatörü: %55 [K1]",
     ORAN, "Unvanlara göre oranlar nedir?", True, "55"),

    ("boş yanıt reddedilmeli",
     "   ", YEMEK, "Yemek bedeli nedir?", False, None),

    ("atıfsız yanıt reddedilmeli",
     "Günlük yemek bedeli 145,00 TL'dir.",
     YEMEK, "Yemek bedeli nedir?", False, None),
]


# =====================================================================
#  BELGE OKUMA — üstbilgi/altbilgi (boilerplate) ayıklama
# ---------------------------------------------------------------------
#  Tekrarlayan sayfa altbilgisi indekse çöp parça olarak giriyordu ve
#  sözleşme numarası içerdiği için aramada ilk sıralara çıkabiliyordu.
#  Ayıklama KONUMA duyarlı olmalı: aynı ifade sayfa ortasında gerçek
#  içerik olabilir.
# =====================================================================

_SAYFALAR = [
    "ADL-2024/117 — Sözleşme    Sayfa 1\nMADDE 1 — TARAFLAR\n1.1. Taraflar şunlardır.",
    "ADL-2024/117 — Sözleşme    Sayfa 2\nMADDE 2 — KONU\n2.1. Konu depolamadır.",
    "ADL-2024/117 — Sözleşme    Sayfa 3\nMADDE 3 — BEDEL\n3.1. Bedel 100 TL'dir.",
    "ADL-2024/117 — Sözleşme    Sayfa 4\nMADDE 4 — SÜRE\n4.1. Süre 18 aydır.",
]


def _boilerplate_testleri() -> List[Tuple[str, bool]]:
    from src.loaders import _detect_boilerplate, _strip_boilerplate

    bp = _detect_boilerplate(_SAYFALAR)
    temiz = [_strip_boilerplate(s, bp) for s in _SAYFALAR]

    # Sayfa ortasında geçen aynı ifade korunmalı
    orta = "MADDE 5 — ATIF\n5.1. ADL-2024/117 — Sözleşme    Sayfa 9 ibaresi burada içeriktir.\n5.2. Devam."
    orta_temiz = _strip_boilerplate(orta, bp)

    # Az sayfalı belgede tespit yapılmamalı (güvenilir değil)
    az = _detect_boilerplate(_SAYFALAR[:2])

    return [
        ("altbilgi tespit edildi", len(bp) == 1),
        ("altbilgi tüm sayfalardan atıldı",
         all("Sayfa" not in t.splitlines()[0] for t in temiz)),
        ("gerçek içerik korundu",
         all(("MADDE" in t and "1." in t) or "MADDE" in t for t in temiz)),
        ("🔒 sayfa ORTASINDAKİ aynı ifade korundu",
         "ibaresi burada içeriktir" in orta_temiz),
        ("🔒 2 sayfalık belgede tespit yapılmadı", az == set()),
    ]


# =====================================================================
#  DEĞERLENDİRME ÖLÇÜTÜ — beklenti eşleştirme (eval/matching.py)
# ---------------------------------------------------------------------
#  İki yönlü sınanır:
#   · DOĞRU cevaplar geçmeye devam etmeli (yanlış negatif olmamalı)
#   · Yakın-yanlış cevaplar artık GEÇMEMELİ (şişme kırılmalı)
#  Birinci yön daha kritiktir: ölçüt fazla katı olursa sistem olduğundan
#  kötü görünür ve var olmayan hatalar kovalanır.
# =====================================================================

# (beklenen, cevap) — hepsi GEÇMELİ
OLCUT_DOGRU = [
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
]

# (beklenen, cevap) — hiçbiri GEÇMEMELİ
OLCUT_YANLIS = [
    ("6", "Kesin teminat oranı %16'dır [K1]."),
    ("6", "Garanti süresi 36 aydır [K1]."),
    ("2", "Sözleşme 2024 tarihlidir [K1]."),
    ("2", "Toplam 12 vardiya vardır [K1]."),
    ("500", "Tutar 1.500,00 TL'dir [K1]."),
    ("8", "Süre 18 aydır [K1]."),
    ("34", "Toplam 340 palet bulunmaktadır [K1]."),
    ("145", "Bakım bedeli 1.450,00 TL'dir [K1]."),
]


def _olcut_testleri() -> List[Tuple[str, bool]]:
    out: List[Tuple[str, bool]] = []
    yn = [b for b, c in OLCUT_DOGRU if not value_in(normalize(c), b)]
    out.append((f"🔒 doğru cevaplar geçiyor ({len(OLCUT_DOGRU)} durum)"
                + (f" — YANLIŞ NEGATİF: {yn}" if yn else ""), not yn))
    hg = [b for b, c in OLCUT_YANLIS if value_in(normalize(c), b)]
    out.append((f"yakın-yanlış cevaplar elendi ({len(OLCUT_YANLIS)} durum)"
                + (f" — HÂLÂ GEÇEN: {hg}" if hg else ""), not hg))
    return out


def main() -> int:
    olcut_testleri = _olcut_testleri()
    bp_testleri = _boilerplate_testleri()
    gecen = 0
    toplam = len(DURUMLAR) + len(olcut_testleri) + len(bp_testleri)
    print(f"{toplam} birim testi çalıştırılıyor...\n")

    print("-- guardrail (src/verify.py) " + "-" * 34)
    for ad, ham, kaynak, soru, bek_ok, bek_icerik in DURUMLAR:
        ok, sebep, ayrinti, temiz = check(ham, kaynak, question=soru)
        iyi = (ok == bek_ok) and (bek_icerik is None or bek_icerik in temiz)
        gecen += iyi
        print(f" {'✔' if iyi else '✖'} {ad}")
        if not iyi:
            print(f"     beklenen : gecerli={bek_ok}, içerik={bek_icerik!r}")
            print(f"     alınan   : gecerli={ok}, sebep={sebep[:70]}")
            print(f"     yanıt    : {temiz[:120]!r}")
            if ayrinti["removed"]:
                print(f"     atılan   : {ayrinti['removed']}")

    print("\n-- değerlendirme ölçütü (eval/matching.py) " + "-" * 20)
    for ad, sonuc in olcut_testleri:
        gecen += bool(sonuc)
        print(f" {'✔' if sonuc else '✖'} {ad}")

    print("\n-- belge okuma (src/loaders.py) " + "-" * 31)
    for ad, sonuc in bp_testleri:
        gecen += bool(sonuc)
        print(f" {'✔' if sonuc else '✖'} {ad}")

    print("\n" + "=" * 62)
    print(f"  {gecen}/{toplam} test geçti")
    print("=" * 62)
    return 0 if gecen == toplam else 1


if __name__ == "__main__":
    sys.exit(main())
