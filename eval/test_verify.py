"""
GUARDRAIL BİRİM TESTLERİ — src/verify.py
=========================================

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

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

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


def main() -> int:
    gecen = 0
    print(f"{len(DURUMLAR)} guardrail birim testi çalıştırılıyor...\n")

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

    print("\n" + "=" * 62)
    print(f"  {gecen}/{len(DURUMLAR)} test geçti")
    print("=" * 62)
    return 0 if gecen == len(DURUMLAR) else 1


if __name__ == "__main__":
    sys.exit(main())
