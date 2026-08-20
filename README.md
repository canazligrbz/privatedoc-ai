# Belge Asistanı — Yerel (Air-Gap) RAG Sistemi

![testler](https://github.com/canazligrbz/privatedoc-ai/actions/workflows/test.yml/badge.svg)

İnternete hiç çıkmadan çalışan, yalnızca size ait belgelere dayanarak yanıt veren, **her cümlesinde kaynak gösteren** ve bilmediğinde bilmediğini söyleyen bir RAG (Retrieval-Augmented Generation) uygulaması.

Dil modeli, embedding modeli ve vektör veri tabanı **aynı makinede** çalışır. Uygulama süreci localhost dışına hiçbir bağlantı kuramaz; bu bir yapılandırma tercihi değil, kod seviyesinde zorlanan bir kısıttır (`src/airgap.py`).

> **Korumanın kapsamı — dürüst sınır.** `airgap.py` **uygulama sürecini** yamalar. LLM'i çalıştıran Ollama ise **ayrı bir süreçtir** ve bu yamanın kapsamı dışındadır: belgeleriniz ona localhost üzerinden ulaşır, ancak Ollama'nın kendi dış bağlantıları (ör. sürüm denetimi) süreç içi koruma tarafından engellenemez. **Makine düzeyinde tam yalıtım için ağ arayüzü kapatılmalı veya güvenlik duvarı kuralı yazılmalıdır** (§9, Aşama 4). Kurulum sonrası "ağı kesin" adımının neden isteğe bağlı değil zorunlu olduğunun cevabı budur.

> **Tasarım hedefi:** *"Doğru cevap veremiyorsa cevap vermesin."*
> Sistem, yanlış bilgi üretmektense `Bu konu hakkında yüklenen belgelerde bilgi bulunmamaktadır.` demeye zorlanmıştır. Ölçülen ret doğruluğu **%100**'dür (bkz. [§2](#2-değerlendirme-sonuçları)).

---

## Öne çıkanlar

| | |
|---|---|
| 🔒 **Çevrimdışı** | Uygulama sürecinde localhost dışı TCP ve DNS bloklanır — Ollama ayrı süreç olduğu için kapsam dışı, bkz. kapsam notu |
| 📑 **Zorunlu atıf** | Sayı/tarih içeren her cümle kaynak numarası taşımak zorunda; taşımayan cümle yanıttan çıkarılır |
| 🔢 **Sayı doğrulama** | Yanıttaki her sayı, getirilen kaynak metinlerde birebir aranır — model kendi hesapladığı sayıyı yazamaz |
| 🔎 **Hibrit arama** | Anlamsal (bge-m3) + kelime bazlı (BM25) arama, RRF ile birleştirilir; özel isimler ve kod numaraları kaybolmaz |
| 🇹🇷 **Türkçeye uyarlanmış** | `İ/ı` duyarlı küçültme, ek ayıklama, ünsüz yumuşaması, "Kasım = 11" / "üçüncü = 3" denklikleri |
| 🖼 **OCR** | Taranmış PDF'ler sayfa bazında tespit edilip OCR'lanır; OCR kalitesi puanlanıp kullanıcıya bildirilir |
| 📊 **Ölçülebilir** | 45 soruluk altın test seti + `run_eval.py` ile tekrar üretilebilir doğruluk ölçümü |
| 💻 **CPU yeter** | GPU gerekmez. 16 GB RAM'li bir masaüstünde çalışır |

---

## İçindekiler

1. [Hızlı başlangıç](#1-hızlı-başlangıç)
2. [Değerlendirme sonuçları](#2-değerlendirme-sonuçları)
3. [Mimari ve teknoloji seçimleri](#3-mimari-ve-teknoloji-seçimleri)
4. [Proje yapısı](#4-proje-yapısı)
5. [Kullanım](#5-kullanım)
6. [Halüsinasyon önleme mimarisi](#6-halüsinasyon-önleme-mimarisi)
7. [Parametre optimizasyonu](#7-parametre-optimizasyonu)
8. [Donanım gereksinimleri](#8-donanım-gereksinimleri-cpu-only)
9. [Air-gap kurulum (transfer paketi)](#9-air-gap-kurulum-transfer-paketi)
10. [Güvenlik ve KVKK](#10-güvenlik-ve-kvkk)
11. [Sorun giderme](#11-sorun-giderme)
12. [Bilinen sınırlar](#12-bilinen-sınırlar)
13. [Lisans](#13-lisans)

---

## 1. Hızlı başlangıç

Bu bölüm **internete erişimi olan** bir makinede sistemi ilk kez ayağa kaldırmak içindir. Air-gap makineye kurulum [§9](#9-air-gap-kurulum-transfer-paketi)'dadır.

### Ön koşullar

| Gereksinim | Sürüm | Not |
|---|---|---|
| Python | 3.10 – 3.12 | 3.11 önerilir |
| [Ollama](https://ollama.com/download) | güncel | LLM'i çalıştırır |
| RAM | en az 16 GB | 32 GB rahat |
| Disk | ~15 GB boş | modeller + paketler |
| (opsiyonel) [Tesseract OCR](https://github.com/UB-Mannheim/tesseract/wiki) | 5.x | yalnızca taranmış PDF'ler için, **Türkçe dil paketiyle** |

### Adımlar

```bash
# 1) Depoyu alın
git clone <depo-adresi> belge-asistani
cd belge-asistani

# 2) Sanal ortam
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # Linux / macOS

# 3) Bağımlılıklar
pip install -r requirements.txt

# 4) Embedding modelini indirin (~2.3 GB, tek seferlik)
python scripts/download_models.py --out models

# 5) Dil modelini indirin (~4.7 GB, tek seferlik)
ollama pull qwen2.5:7b-instruct-q4_K_M

# 6) Kurulumu doğrulayın — 13 kontrol
python scripts/verify_offline.py
```

Windows'ta 2–5. adımların tamamı için `kurulum.bat` dosyasına çift tıklamanız yeterlidir.

### İlk çalıştırma

```bash
# Belgelerinizi data/documents içine kopyalayın, sonra:
python -m src.ingest             # indeksleme
python server.py                 # sunucu
```

Tarayıcıdan **http://127.0.0.1:8501** adresine gidin. Windows'ta: `indeksle.bat` → `baslat.bat`.

### Denemek için hazır belge

Depoda, içeriği **tam olarak bilinen** sentetik bir test sözleşmesi vardır. Kendi belgeleriniz olmadan da sistemi deneyebilirsiniz:

```bash
python -m src.ingest --rebuild --path ornek_belgeler/dijital
python server.py
```

Deneyebileceğiniz sorular:
- *"Sözleşmenin KDV hariç toplam bedeli nedir?"* → 24.750.000,00 TL, kaynak gösterilerek
- *"2024 yılının 6. ayında öngörülen hakediş tutarı nedir?"* → tablodan doğru satır okunmalı
- *"Depoda kaç adet güvenlik kamerası bulunmaktadır?"* → **reddetmeli**, çünkü belgede yok

---

## 2. Değerlendirme sonuçları

Sistem "iyi görünüyor" diye değil, **ölçülerek** geliştirildi. Gerçek belgelerle test ederken *"acaba bu bilgi gerçekten belgede var mı?"* belirsizliği ölçümü imkânsız kılıyordu; bu yüzden içeriği bilinçli olarak üretilmiş, her sorunun doğru cevabı kesin olan bir test belgesi hazırlandı (`scripts/make_test_pdf.py` → 20 sayfa; benzer ceza maddeleri, satır bazlı okunması gereken tablolar, bir akış şeması ve kasıtlı tuzaklar içerir).

### Son ölçüm

**Yapılandırma:** `qwen2.5:7b-instruct-q4_K_M`, `temperature 0.0`, `seed 42`, CPU-only (GPU yok), depodaki `config.yaml` varsayılanları

| Metrik | Geliştirme seti | **Ayrılmış set** | Yönetmelik² | Taranmış¹ | Hedef |
|---|---|---|---|---|---|
| Belge | depo sözleşmesi | depo sözleşmesi | **yönetmelik** | depo (taranmış) | — |
| Sorular görüldü mü? | evet, ayar buna göre | **hayır** | hayır ama alan kısmen görülmüş | evet | — |
| **Genel başarı** | 28/29 · %97<br><sub>GA %83–99</sub> | **27/29 · %93**<br><sub>GA %78–98</sub> | **17/20 · %85**<br><sub>GA %64–95</sub> | 9/16 · %56<br><sub>GA %33–77</sub> | ≥ %85 |
| **Ret doğruluğu** | 9/9 · %100<br><sub>GA %70–100</sub> | **5/5 · %100**<br><sub>GA %57–100</sub> | **3/3 · %100**<br><sub>GA %44–100</sub> | 5/5 · %100<br><sub>GA %57–100</sub> | ≥ %95 |
| **Yanlış ret** | 1/20 · %5<br><sub>GA %1–24</sub> | 2/20 · %10<br><sub>GA %3–30</sub> | 2/14 · %14<br><sub>GA %4–40</sub> | 5/11 · %45<br><sub>GA %21–72</sub> | ≤ %10 |
| **Kaynaklı yanıt** | 20/20 · %100 | **20/20 · %100** | 14/14 · %100 | 11/11 · %100 | %100 |
| Gecikme (medyan)³ | 25–41 sn | 22–36 sn | 34 sn | 22 sn | ≤ 60 sn |
| Gecikme (p95)³ | 30–48 sn | 28–45 sn | 47 sn | 32 sn | — |

### Bu sayılar ne kadar kesin? — örneklem uyarısı

29 soruluk bir sette **bir soru 3,4 puandır.** "%96,6" ile "%93,1" arasındaki fark tam olarak bir sorudur; virgülden sonraki basamak, var olmayan bir hassasiyet iddia eder. Bu yüzden tüm oranlar **sayım ve %95 Wilson güven aralığıyla** birlikte veriliyor (`eval/stats.py`).

Sonuç ikiye ayrılıyor ve ikisi de dürüstçe söylenmeli:

| Karşılaştırma | Fark | Farkın GA'sı | Yorum |
|---|---|---|---|
| Geliştirme ↔ **Ayrılmış** | 3,4 puan | **−11,2 … +18,8** | Sıfırı içeriyor → **aşırı uyuma dair kanıt yok** |
| Geliştirme ↔ **Yönetmelik** | 11,6 puan | **−5,3 … +32,8** | Sıfırı içeriyor → **alan farkı gösterilemiyor** |
| Geliştirme ↔ **Taranmış** | 40,3 puan | **15,5 … 63,5** | Sıfırı içermiyor → **etki gerçek**, büyüklüğü belirsiz |

Farkın güven aralığı, iki ayrı aralığa bakmaktan daha bilgilendiricidir (Newcombe skor yöntemi, `eval/stats.py → fark_araligi`). "Aralıklar örtüşüyor mu?" sorusu farkın **yönü** hakkında kabaca fikir verir ama **büyüklüğü** hakkında hiçbir şey söylemez.

Yani ayrılmış set için söylenebilecek dürüst şey "sistem genelliyor" değil, **"aşırı uyuma dair kanıt bulunamadı"**dır. Aradaki fark önemlidir: ikincisi verinin desteklediği, birincisi desteklemediği iddiadır. Farkı gerçekten ölçmek için çok daha büyük bir set gerekir.

Buna karşılık OCR etkisi net: aralıklar örtüşmüyor, yani 40 puanlık düşüş rastlantı değil.

Wilson aralığı bilinçli seçildi; klasik (Wald) yaklaşımı küçük örneklemde ve oran 1'e yakınken bozulur — 28/29 için üst sınırı %100'ün üstüne çıkarır, 29/29 için ise "hiç belirsizlik yok" der.

### İkinci belge alanı ne gösterdi?

Skor farkı istatistiksel olarak gösterilemedi, ama **mekanizma bulgusu istatistik gerektirmiyor**: yönetmeliğin üç hatasının üçünde de doğru cevap getirilen parçanın **içindeydi**. Yirmi sorunun yirmisinde getirme çalıştı; başarısızlıkların tamamı üretim tarafında.

En öğretici olanı 2. soru:

```
kaynak : "...bağlı bulunduğu en yakın üst yöneticiyi..."
model  : "...bağlı bulunduğu en yakın üst yındıktıyı ifade eder [K1][K2]."
```

Model kelimeyi bozdu ve **hiçbir guardrail yakalamadı.** Yanıt düzgün kurulmuş, atıflı, uydurma sayı içermiyor. Sebebi yapısal: doğrulama katmanımızın en güçlü ayağı olan **sayı denetimi, sayısız bir belgede tamamen boştadır**. Depo sözleşmesinde 367 sayı vardı ve her biri kaynakla karşılaştırılıyordu; yönetmelikte 40 sayı var ve hiçbiri bu cümlede geçmiyor.

Bu, ikinci alanın ortaya çıkardığı asıl kazançtır: doğrulama mimarimiz **sayı merkezli** ve düz metin ağırlıklı belgelerde koruma yüzeyi belirgin şekilde daralıyor. Tek belgeyle çalışırken görülemezdi.

### Ret doğruluğu

**Üç sette de %100.** Ayrılmış setteki 5 "reddedilmesi zorunlu" sorunun tamamı ve 4 tuzak sorunun tamamı doğru davranışla sonuçlandı. Sistemin var oluş amacı olan davranış — bilmediğinde uydurmamak — görülmemiş sorulara tam olarak aktarılıyor.

Ayrılmış setteki iki hatanın **ikisi de aynı sınıftan** ve geliştirme setindeki tek hatayla aynı: doğru kaynak getirilmiş, model onu kullanmayı reddetmiş.

| # | Soru | Getirilen kaynak | Model |
|---|---|---|---|
| 10 | "Aralık 2024 döneminin açıklaması nedir?" | `12/2024 Yıl sonu kapanış 36 1.455.200,00` (1. sırada) | reddetti |
| 2 | "Kritik stok seviyesi kaç palet?" | `KRİTİK STOK Asgari 500 palet altına düşen ürün seviyesi` (1. sırada) | reddetti |

10. soru, aşağıda belgelenen **bilinen sınırın** ta kendisidir; ayrılmış sette de görülmesi, bunun tek bir soruya özgü bir tuhaflık değil gerçek bir zayıflık olduğunu doğrular. 2. soru aynı ailenin yeni bir örneğidir: getirme çalışıyor, üretim aşırı temkinli davranıyor.

Sistemin kalan zayıflığı **tek bir yerde toplanmış durumda: getirme değil, üretim.** Üç sette de aynı imza görülüyor — bu, zayıflığın rastgele değil yapısal olduğunu ve dolayısıyla hedeflenebilir olduğunu gösterir.

> **Ayrılmış set artık harcanmıştır.** Tek seferlik açıldı ve sonuçları raporlandı. Buradan sonra yapılacak iyileştirmeler geliştirme seti üzerinde yürütülmeli, genelleme yeniden ölçülecekse **yeni** bir ayrılmış set yazılmalıdır. Bu setin sonuçlarına bakarak parametre ayarlamak, onu ikinci bir geliştirme setine dönüştürür.

² **Yönetmelik seti AYRILMIŞ DEĞİLDİR.** Sorular görülmemiştir ama belge ailesi görülmüştür: gerçek bir kira sözleşmesi daha önce incelenmiş, üç kusur tespit edilmiş ve ikisine müdahale edilmişti (olumsuzluk düzeltmesi tutuldu, harf etiketi geri alındı). Belge o profili bilinçli hedefler ve 14 cevaplanabilir sorunun altısı olumsuz hüküm üzerinedir — yani en çok soru konan kategori, yamalanan kategoriyle aynıdır. Bu yüzden alanın **geliştirme seti** sayılır; gerçek belge-genellemesi ölçümü için ayrı ve kilitli bir set yazılacaktır.

¹ Taranmış sürüm, aynı sözleşmenin 7., 8. ve 13. sayfalarının taranmış görüntüsüdür. Ayrıntılı çözümleme aşağıda.

³ Gecikme aynı makinede koşudan koşuya iki kata kadar değişti (p50 için 22–47 sn arası gözlendi). Tek bir sayı yazmak yanıltıcı olurdu; aralık verilmiştir. Doğruluk metrikleri ise tekrarlanan koşularda **birebir sabit** kaldı (`temperature 0.0`, `seed 42`).

### Ölçüm aletinin doğrulanması

Değerlendirme başlangıçta beklenen ifadeyi **alt dizi** olarak arıyordu. Bu, kısa sayısal beklentilerde yanlış yanıtlara puan verebilirdi:

```
"Kesin teminat oranı nedir?"   beklenen: "6"
   model "%16'dır" derse  → "16" içinde "6" var → GEÇER (hak edilmemiş)
   model "36 ay" derse    → "36" içinde "6" var → GEÇER (hak edilmemiş)
```

İki test setinde 23 kısa sayısal beklenti vardı. Ölçüt, rakam sınırı zorunlu kılacak şekilde sıkılaştırıldı (`eval/matching.py`). Sınırlar iki yönlü sınandı: modelin doğal olarak yazacağı 12 doğru biçim (`%6'sı`, `1.548.750,00 TL`, `18 (onsekiz) ay`, `2 - 8 °C`, `24:00-08:00`) geçmeye devam ediyor, 8 yakın-yanlış biçim artık eleniyor.

**Sonuç: her iki setin skoru da değişmedi** (%96,6 ve %93,1). Yani hiçbir soru tesadüfen geçmiyormuş; rapor edilen sayılar sıkı ölçütle de aynı. Bu bir negatif sonuçtur ve önemlidir — şişme olmadığı artık varsayım değil, ölçüm.

> **En kritik satır ret doğruluğudur.** Kurumsal bir asistanda yanlış bilgi vermek, "bilmiyorum" demekten çok daha pahalıdır. Geliştirme boyunca bu metrik, bozuk OCR metni üzerinde bile hiç %100'ün altına düşmedi — guardrail katmanları veri kalitesinden bağımsız çalışıyor.

### Ölçüm metodolojisi — geliştirme seti ve ayrılmış set

Yukarıdaki **%96,6**, `testset_depo.yaml` üzerinde ölçüldü. Bu setle yapılan ilerlemenin (%50 → %96,6) tamamı, aynı 29 soruya bakılarak yapılan düzeltmelerle elde edildi. Eşikler, guardrail kuralları ve parametreler o sorulardaki hatalara göre şekillendi.

Bu nedenle **o skor bir genelleme ölçümü değildir.** Geliştirmeyi yöneten setin skorudur; makine öğrenmesindeki karşılığı *test setine aşırı uyum*tur. Set artık sınav değil, ders kitabıdır.

Bunu ölçmek için `eval/testset_holdout.yaml` yazıldı: aynı belgeye ait, **aynı dağılımda** (20 cevaplanabilir · 5 reddedilmeli · 4 tuzak) ve aynı zorluk kategorilerinde 29 yeni soru. Sorular, geliştirme setinin hiç dokunmadığı olgulara dayanır — böylece iki set arasında değişen tek şey, soruların görülmüş olup olmamasıdır.

| | Geliştirme seti | Ayrılmış set |
|---|---|---|
| Dosya | `testset_depo.yaml` | `testset_holdout.yaml` |
| Soru | 29 | 29 |
| Rol | Parametreler buna göre ayarlandı | **Hiç görülmedi** |
| Skor | %96,6 | **%93,1** |
| Ret doğruluğu | %100 | **%100** |

Ayrılmış setin tüm değeri görülmemiş olmasından gelir; bir kez bakılıp sonucuna göre ayar yapıldığında "yanar" ve genelleme ölçme özelliğini kaybeder. Bu disiplin hafızaya bırakılmadı, **koda gömüldü** — `run_eval.py` dosya adında `holdout` geçen bir seti açık onay olmadan çalıştırmaz ve bu set üzerinde parametre taramasına hiç izin vermez:

```bash
$ python eval/run_eval.py --testset eval/testset_holdout.yaml
  AYRILMIŞ TEST SETİ — KİLİTLİ
  testset_holdout.yaml, geliştirme sırasında çalıştırılmamalıdır.
```

Ölçüm yapıldı: fark **3,4 puan**, güven aralığı **−11,2 … +18,8 puan** — aralık sıfırı içerdiği için bu örneklemle **aşırı uyuma dair kanıt bulunamadı**. Bu, "sistem genelliyor" demek DEĞİLDİR; veri ne genellediğini ne genellemediğini gösterecek güçte. Ayrılmış set bir kez açıldı, sonuçları yukarıda raporlandı ve **artık harcanmıştır**; genelleme yeniden ölçülecekse yeni bir set yazılmalıdır.

Sonuçları kendiniz üretmek için:

```bash
# Dijital (geliştirme seti)
python -m src.ingest --rebuild --path ornek_belgeler/dijital
python eval/run_eval.py --testset eval/testset_depo.yaml

# Taranmış (OCR maliyeti)
python -m src.ingest --rebuild --path ornek_belgeler/taranmis
python eval/run_eval.py --testset eval/testset_taranmis.yaml

# Birim testleri (LLM gerekmez, ~1 saniye)
pytest
```

### Geliştirme boyunca ilerleme

Her sıçrama, ölçümün ortaya çıkardığı somut bir mühendislik hatasının düzeltilmesidir:

| Aşama | Genel başarı | Yanlış ret | Ne düzeltildi |
|---|---|---|---|
| İlk sürüm | %50 | %75 | — |
| Hibrit arama + RRF | %75 | %30 | Saf vektör araması özel isimleri ve kod numaralarını ıskalıyordu |
| Satır bazlı tablo parçalama | %82,8 | %20 | Tüm tablo tek parçaya giriyor, model komşu satırı okuyordu |
| Cümle bazlı atıf: red yerine **ayıklama** | %89,7 | %10 | Guardrail atıfsız tek cümle yüzünden doğru yanıtın tamamını çöpe atıyordu |
| Bağlam penceresi taşmasının giderilmesi | %89,7 | **%0** | Prompt zamanla 4000 karaktere ulaşmış, `num_ctx` dolduğu için kaynaklar sessizce kırpılıyordu |
| Atıf devri kapısının genişletilmesi | **%96,6** | **%0** | Guardrail, modelin doğru cevabını silip yerine boş kapanış cümlesini bırakıyordu |

Bağlam taşması özellikle öğreticidir: sistem prompt'una kural eklemek bedava değildir. Kurallar biriktikçe pencere doldu, Ollama sessizce kırpma yaptı ve **aynı soruya farklı zamanlarda farklı yanıt** gelmeye başladı. Çözüm iki parçalıydı — prompt 1741 karaktere indirildi ve `_fit_char_budget()` eklenerek bağlam bütçesi pencereye göre otomatik daraltıldı.

### Nasıl teşhis edildi

%89,7'lik koşudaki üç hatanın hiçbiri arama ya da model hatası değildi. Üçünde de doğru kaynak getirilmiş, model doğru cevabı üretmiş, **guardrail cevabı silmişti**:

```
soru  : Kasım 2024 döneminin açıklaması ve tutarı nedir?
model : "11/2024 dönemi Envanter sayım dönemidir ve tutarı 1.455.200,00 TL'dir.
         Bu nedenle, [K1][K3] doğru."
kullanıcıya gösterilen: "Bu nedenle, [K1][K3] doğru."          ← bilgi yok oldu
```

Model bilgiyi atıfsız yazıp atfı sonraki kapanış cümlesine koyuyor. Cümle bazlı atıf denetimi (katman 5) atıfsız cümleyi ayıklıyor, geriye içi boş kapanış kalıyor. Atıf devri mekanizması (`_inherit_trailing_citations`) tam bunun için vardı ama kapısı yalnızca "kaynak/belge" sözcüğü geçen cümleleri tanıyacak kadar dardı.

Kapı genişletildi: bir kapanış cümlesi, atfı varsa ve **yeni bir olgu getirmiyorsa** taşıyıcı sayılır; atıfları kendinden önceki cümlelere devredilir. "Yeni olgu getirmiyor" ölçütü, cümledeki sayıların ya önceki cümlelerde zaten geçmesi ya da madde referansı olmasıdır. Bu ölçüt iki hatayı birden engeller — bilgi taşıyan bir kapanışın silinmesini *ve* uydurma sayı içeren bir kapanışın onaylanmasını.

Aynı koşuda ayrıca modelin soruyu aynen geri yazdığı iki durum görüldü (`"Kaç adet Depo Görevlisi çalıştırılacaktır [K1]?"`). Atıf taşıdığı için geçerli yanıt sanılıyordu; artık ayıklanıyor ve geriye bir şey kalmazsa reddediliyor.

**Bu ayıklayıcının ilk sürümü, sistemin en pahalı hatalarından birini üretti.** Ölçüt olarak kelime örtüşme oranı (%85) kullanılmıştı. Oysa Türkçede iyi bir cevap zaten soruyu tekrarlayıp boşluğu doldurur:

```
soru  : "... asgari ücretin yüzde KAÇ fazlası ödenecektir?"
cevap : "... asgari ücretin yüzde 55 fazlası ödenecektir."      → %89 örtüşme
```

Tek fark `kaç` → `55`, yani cevabın kendisi. Ayıklayıcı bunu yankı sanıp sildi ve iki soru daha bozuldu. Ölçüt orandan **"soruda geçmeyen tek bir içerik terimi var mı"**ya çevrildi. Yön tercihi bilinçlidir: bir yankıyı kaçırmak zayıf bir yanıt üretir, doğru cevabı silmek yanlış bir ret üretir — ikincisi daha pahalıdır.

Bu mantığın gerilemesini önlemek için birim testleri yazıldı (`tests/`, pytest). LLM gerektirmezler ve yarım saniyede koşarlar. Bir kısmı düzeltmeleri, `🔒` işaretli olanlar guardrail'in **asıl görevini** korur: bir değişiklik uydurma sayı testlerini bozuyorsa o değişiklik yanlıştır.

### Bilinen sınır — ay adı ↔ ay numarası eşleştirmesi

29 sorudan biri geçmiyor ve bu artık guardrail değil, **modelin sınırıdır**:

```
soru  : "Kasım 2024 döneminin açıklaması ve tutarı nedir?"
K1    : "[TABLO SATIRI] ... 11/2024 Envanter sayım dönemi 36 1.455.200,00"   ← 1. sırada
model : "Kasım 2024 döneminin açıklaması ve tutarı belgede açık olarak verilmedi [K1][K3]."
```

Arama görevini yapıyor: BM25'teki `Kasım → 11` denkliği doğru satırı ilk sıraya taşıyor. Model, elindeki satırla soruyu eşleştirmeyi reddediyor.

Üç müdahale denendi, üçü de ölçüldü, **hiçbiri kazanç sağlamadı**:

| # | Müdahale | Sonuç |
|---|---|---|
| 1 | Sistem promptuna genel kural (`Kasım=11`) | "belgede açık olarak verilmedi" |
| 2 | Kullanıcı mesajına soruya özel NOT | "belirtilmemiş bir dönemdir" |
| 3 | Eşleştirme kuralını denklik farkındalıklı sürümle değiştirmek | Düpedüz ret — biraz daha kötü |

2. denemenin başarısızlığı öğretici: not, hemen üstündeki *"kullanacağın satırdaki değerin sorudakiyle **BİREBİR aynı** olduğunu doğrula"* kuralıyla çelişiyordu. "Kasım 2024" ile "11/2024" harfi harfine aynı olmadığı için model, kuralı doğru uygulayıp satırı eledi. **Çelişen iki talimattan daha kesin ifade edilmiş olan kazanıyor.** O "BİREBİR" kuralı da bir başka hatayı (tabloda komşu satıra kayma) düzeltmek için eklenmişti; iki gereksinim doğrudan çatışıyor.

3. deneme **geri alındı**: kazanç göstermeyen bir değişikliği iki ayrı kod yolu pahasına tutmak doğru değil. Karar, dördüncü bir denemeye girişmek yerine sınırı belgelemek oldu — bu noktada tek bir soruya yapılan her ek müdahale, ölçtüğü setin skorunu iyileştirir ama genelleme hakkında bilgi vermez. Kod içinde de negatif bulgu olarak kayıtlıdır (`src/prompts.py`), aynı yol tekrar denenmesin diye.

**Denenmemiş seçenek:** indeksleme sırasında tarih hücresini zenginleştirmek (`"11/2024"` → `"11/2024 (Kasım 2024)"`). Model eşleştirme yapmak zorunda kalmazdı. Kaynak metnini değiştirdiği için gösterim metnini indeks metninden ayırmak gerekir; tek bir soru için bu mimari değişiklik yapılmadı.

### Yan bulgu — sayfa altbilgisi indekse giriyordu

Bu soruyu incelerken görüldü: dört kaynak slotundan biri çöp bir parçaya gidiyordu.

```
[K3] "[TABLO SATIRI] Dönem Açıklama Personel Tutar (TL) ADL-2024/117 — Merkez Depo Hizmet Sözleşmesi"
```

Sayfa altbilgisi, tablo satırı olarak indekslenmişti. Sözleşme numarası içerdiği için BM25'te skor alıyor ve gerçek kaynakların yerini kapıyordu. Kurumsal belgelerin neredeyse tamamında her sayfada üstbilgi/altbilgi bulunduğu için bu, belgeye özel değil **genel** bir kusurdur.

Çözüm sabit kalıp değil, **tekrar tespiti**: sayfaların %60'ından fazlasında ve sayfa başında/sonunda görünen satır boilerplate sayılır (karşılaştırmadan önce rakamlar maskelenir, çünkü sayfa numarası değişir). Konum kısıtı bilinçlidir — aynı ifade sayfa ortasında gerçek içerik olabilir ve korunur.

Sonuç: 55 → 50 blok, beş tablo sayfasının her birinden bir çöp parça temizlendi, **897 → 897 ayrık terim** (sıfır içerik kaybı). Gecikme p50 26,7 → **25,3 sn**, p95 34,1 → **30,1 sn**.

### Taranmış (OCR) sürüm

Aynı sözleşmenin 7., 8. ve 13. sayfaları taranmış görüntü olarak da üretildi (`ornek_belgeler/taranmis/`). Amaç, **OCR'ın doğruluğa maliyetini sayısal olarak ölçmek**: aynı bilgiler, aynı sorular, tek fark belgenin taranmış olması.

```bash
python -m src.ingest --rebuild --path ornek_belgeler/taranmis
python eval/run_eval.py --testset eval/testset_taranmis.yaml
```

`eval/testset_taranmis.yaml` — 16 soru (11 cevaplanabilir · 5 reddedilmesi zorunlu). Sorular kasıtlı olarak **komşu satır ayrımı** gerektirir: "Forklift Operatörü %55" sorulduğunda hemen yanındaki 145, 95, 75, 30 değerleri tuzaktır.

Ölçülen bozulma, tablo satırlarında gözle görülür:

```
dijital  : 11/2024 Envanter sayım dönemi        36   1.455.200,00
taranmış : 11/2024 Envanter sayım dönemi        36 © 1.455.200,00
taranmış : 12/2024 | Vil sovid kapaiiis  | | 36. —«*1..455.200,00
taranmış : sözleşme bedelinin yüzde ikisi (962) oranında      ← (%2) → (962)
```

**Ölçülen: 28/29 (%97) → 9/16 (%56).**

Fark **40,3 puan**, güven aralığı **15,5 … 63,5 puan** (Newcombe). Aralık sıfırı içermiyor, yani **etki gerçek**. Ancak büyüklüğü bu örneklemle kesinleştirilemez: gerçek maliyet 15 puan da olabilir 64 puan da. "OCR 40 puana mal oluyor" demek veriden daha kesin konuşmak olurdu.

Bu sonuç iki tahmini birden çürüttü ve ikisi de bu README'de yazılıydı:

- *"Guardrail düzeltmeleri taranmış skoru yükseltecek."* **Yükseltmedi.** Aynı ölçütle bakıldığında düzeltmelerden önce de sonra da 9/16. Etki tam olarak sıfır.
- *"Altı hatanın üçü guardrail kusuruydu, OCR değil."* **Yanlıştı.** O üç hata guardrail'den değil, aşağıdaki nedenlerden kaynaklanıyordu.

Ara ölçümdeki %62,5 ile buradaki %56,2 farkı da bir gerileme değildir: eski ölçüt 10. soruyu hak etmeden geçiriyordu (OCR `(%2)`'yi `(962)` okumuş, alt dizi araması `962` içinde `2` bulmuştu). Aynı cetvelle iki koşu da 9/16'dır.

**Yedi hatanın gerçek dağılımı:**

| Neden | Soru | Ayrıntı |
|---|---|---|
| OCR veriyi **yok etti** | 5, 6, 7 | Ücret tablosunun 7 veri satırının tamamı kayboldu |
| OCR sayıyı **bozdu** | 10 | `(%2)` → `(962)`; model bozuk değeri sadakatle aktardı |
| Getirme sıralaması | 1 | `06/2024` satırı OCR metninde VAR ama ilk 4'e giremedi; `"Not: 06/2024-08/2024..."` satırı onu geçti |
| Bilinen model sınırı | 2, 3 | Ay adı ↔ ay numarası (`Kasım`→11, `Mart`→03) — dijitalde de olan sınır |

Ücret tablosunun kaybı en ağır olanı. OCR başlığı okumuş, satırları okumamış:

```
   Unvan   Kisi | Ucret (asgari ucretin yuzde fazlasi) |
   6.2. Yukaridaki oranlar brut asgari ucret uzerinden hesaplanir...
```

Depo Müdürü %145, Forklift Operatörü %55, Depo Görevlisi 16 kişi — hiçbiri indekse girmedi. Bu üç soruda getirme de model de kusursuz çalıştı; **cevaplanacak veri hiç var olmadı.**

**Kalite ölçer bu sayfayı kaçırmıştı.** `assess_quality()` sayfa 2'ye **1.00** (kusursuz) verdi ve sıfır sorun bildirdi. Ölçer bozuk *karakter* arıyordu; kaybolan *içerik* geride iz bırakmaz ki aranabilsin. Tablosunun tamamını yitirmiş bir sayfa "temiz" işaretlendi ve kullanıcı "bu bilgi belgede yok" cevabını alıp inanırdı.

Bu, sistemin üretebileceği en tehlikeli hata türüdür: **sessiz veri kaybı.** Bozuk bir karakteri görürsünüz, eksik bir tabloyu göremezsiniz.

### Çözüm — metni sayfa görüntüsüyle karşılaştırmak

Kaybolan içerik metinde iz bırakmaz, ama **görüntüde bırakır**: sayfada mürekkep vardır, karşılığı olan karakterler yoktur. Ölçüt bu orandır (`src/ocr.py → assess_content_loss`).

Kalibrasyon, tahminle değil ölçümle yapıldı (300 dpi, taranmış üç sayfa):

| sayfa | içerik | karakter kaybı | krk/mürekkep |
|---|---|---|---|
| 1 | hakediş tablosu | %34 | 2,5 |
| 2 | ücret tablosu | %30 | 2,7 |
| 3 | düz metin | %0 | **4,0** |

Dijital orijinallerde üç sayfa da ~3,9–4,0 veriyor; yani sapmanın kendisi kaybın ölçüsü. Eşik **3,0** seçildi — hasarlı iki sayfayı yakalar, temiz sayfayı rahat bırakır.

Ölçüt iki katmanlıdır: mutlak eşiğin yanında **belge-içi göreli** karşılaştırma da yapılır (sayfa, belgenin en iyi sayfasının %70'inin altında mı). Göreli ölçüt yazı boyutu farklarına göre kendini ayarlar; belgenin tüm sayfaları hasarlıysa mutlak eşik devreye girer.

Aynı belgede artık şu uyarı üretiliyor:

```
sayfa 2  skor 0.64
  - sayfada mürekkep var ama az metin çıktı (2.7 krk/mürekkep, eşik 3.0)
    — tablo satırları okunamamış olabilir
  - belgenin en iyi sayfasının %70'inin altında (2.7 / 3.9)
```

> **Bu bir sezgisel ölçüttür, kanıt değil.** Fotoğraf, kaşe veya logo içeren sayfalarda mürekkep yüksek çıkar ve yanlış uyarı üretebilir. Bu yüzden çıktı bir *uyarıdır*, hata değil: sayfa yine indekslenir, kullanıcıya yalnızca "buradaki verilere güvenme" denir. Eşik `config.yaml → ocr.min_chars_per_ink` ile ayarlanabilir.

> **OCR bozulması guardrail ile düzeltilemez.** Model, bozuk kaynaktaki sayıyı sadakatle aktarır; `%2` yerine `962` okunmuşsa doğru davranış o sayıyı yazmaktır. Çözüm gizlemek değil görünür kılmaktır — ama görünür kılma mekanizmasının kendisi de çalışmak zorundadır.

> **Buna karşılık ret doğruluğu %100'de kaldı.** Verinin yarısı yok olmuşken bile sistem yanlış cevap üretmedi, sustu. 5 "reddedilmesi zorunlu" sorunun tamamı doğru sonuçlandı. Bozuk veride bile uydurmama davranışı korunuyor — asıl güvence bu.

---

## 3. Mimari ve teknoloji seçimleri

### 3.1 Akış

```
                    ┌───────────────────── AIR-GAP SINIRI ─────────────────────┐
                    │                                                           │
 Kullanıcı          │  ┌──────────────┐   soru    ┌───────────────┐            │
 (tarayıcı) ────────┼─▶│  FastAPI     │──────────▶│  RAG Motoru   │            │
 127.0.0.1:8501     │  │  server.py   │◀──────────│ rag_engine.py │            │
                    │  └──────────────┘  yanıt +  └──┬────────┬───┘            │
                    │                    kaynaklar   │        │                 │
                    │           ┌────────────────────┘        └─────────┐       │
                    │           ▼                                       ▼       │
                    │   ┌───────────────┐   vektör            ┌──────────────────┐
                    │   │  bge-m3       │──────────┐          │  Ollama          │
                    │   │  (embedding)  │          ▼          │  Qwen2.5-7B Q4   │
                    │   └───────────────┘   ┌─────────────┐   │  127.0.0.1:11434 │
                    │   ┌───────────────┐   │  ChromaDB   │   └──────────────────┘
                    │   │  BM25 (saf    │──▶│  (yerel)    │                       │
                    │   │  Python)      │   └─────────────┘                       │
                    │   └───────────────┘         ▲                               │
                    │                             │                               │
                    │   ingest.py ────────────────┘                               │
                    │   (PDF · DOCX · XLSX · CSV · TXT  →  OCR gerekirse)         │
                    └───────────────────────────────────────────────────────────┘
                          ✗ Dış ağa hiçbir bağlantı yok (kod seviyesinde bloklu)
```

### 3.2 Bileşen seçimleri ve gerekçeleri

| Katman | Seçim | Neden bu? | Değerlendirilen alternatifler |
|---|---|---|---|
| **LLM** | **Qwen2.5-7B-Instruct (Q4_K_M GGUF)** | Bu boyut sınıfındaki açık modeller arasında **Türkçe akıcılığı ve talimat uyumu en yüksek** olanlardan biri. RAG'de kritik olan "verilen bağlama sadık kalma" ve "atıf biçimine uyma" davranışı güçlü. Apache-2.0 (kurumsal kullanım serbest). CPU'da Q4_K_M ile ~4.7 GB. | **Llama-3.1-8B**: Türkçe çıktıda daha çok İngilizce sızıntısı. **Gemma-2-9B**: kaliteli ama 8K bağlam ve kısıtlı lisans. **Command R+ (104B)**: RAG için mükemmel, CPU'da imkânsız (~60 GB). **Qwen2.5-14B**: daha doğru, 32 GB RAM + sabır ister. |
| **Embedding** | **BAAI/bge-m3** | 100+ dilde eğitilmiş, **Türkçe morfolojisinde belirgin şekilde başarılı**. 1024 boyut, 8192 token pencere. Sorgu/pasaj için prefix gerektirmez → operasyonel hata riski düşük. | **multilingual-e5-large**: yakın performans ama `query:`/`passage:` prefix zorunlu; unutulursa doğruluk **sessizce** düşer. **e5-small**: zayıf donanımda hız için makul. **OpenAI embeddings**: air-gap'te kullanılamaz. |
| **Vektör DB** | **ChromaDB 1.x (PersistentClient)** | Ayrı sunucu süreci **gerektirmez** — air-gap'te "bakımı yapılacak bir servis daha" olmaması büyük avantaj. İndeks tek klasörde; yedekleme = klasör kopyalama. 1.x çekirdeği Rust ile yazıldı, hazır wheel gelir, **C++ derleyici istemez**. | **Qdrant**: 1M+ parçada ve çok kullanıcıda daha iyi; Docker/servis yönetimi gerekir. Geçiş için yalnızca `src/vectorstore.py` yeniden yazılır. **FAISS**: hızlı ama metadata/silme elle yönetilir. |
| **Arama** | **Hibrit: vektör + BM25, RRF birleştirme** | Yalnızca vektör araması nadir özel isimleri ve birebir ifadeleri ("KDV hariç", "ADL-2024/117") ıskalar; kendi içinde çok benzer sözleşme metinlerinde doğru sayfa ilk sıralara giremez. BM25 tam bunu yakalar. Sıralamalar RRF ile birleşir, ardından kelime kapsamıyla ölçeklenir. **Ek model/RAM gerekmez.** | Saf vektör: özel isimlerde zayıf. Saf BM25: eşanlamlıları kaçırır. Skorları doğrudan toplamak: ölçekler uyuşmaz (kosinüs 0–1, BM25 0–30). |
| **Framework** | **İnce özel katman + `langchain-text-splitters`** | Tam LangChain/LlamaIndex kurulumu air-gap'te **onlarca geçişli bağımlılık** demek; ayrıca prompt'a görünmeyen metinler ekleyebiliyorlar. Halüsinasyon güvencesi verilen bir sistemde **LLM'e giden her karakterin denetlenebilir olması** şart. Yalnızca metin bölücüsü kütüphaneden alındı. | Tam LangChain: hızlı prototip, zor denetim. LlamaIndex: aynı sorun. |
| **Arayüz** | **FastAPI + saf HTML/CSS/JS** | DOM üzerinde tam kontrol. Yanıt token token akar, sayfa yeniden çalışmaz. **Hiçbir JS kütüphanesi/CDN yok** → air-gap'te tek satır bile dışarı bakmaz. | **Streamlit**: hızlı prototip ama her etkileşimde tüm betiği yeniden çalıştırır, tasarım hazır tema sınırlarına takılır. **Gradio**: benzer kısıt. **Open WebUI**: Docker + kendi RAG hattı; atıf/guardrail davranışı istenen sıkılıkta kurulamaz. |
| **LLM çalıştırıcı** | **Ollama** | CPU'da GGUF için en pratik; tek komutla servis, model RAM'de tutulur (`keep_alive`). | **vLLM**: GPU'da çok üstün, **CPU'da pratik değil**. GPU'ya geçilirse `config.yaml → llm.provider: vllm` yeterlidir. **llama.cpp server**: daha yalın ama model yönetimi elle. |

### 3.3 Türkçeye özgü uyarlamalar

Hazır BM25 kütüphaneleri İngilizce varsayımlarıyla gelir ve Türkçede sessizce yanlış çalışır. `src/bm25.py` saf Python ile yazıldı çünkü şunlar gerekliydi:

- **`tr_lower`** — Python'un `.lower()` metodu `I` harfini `i` yapar; Türkçede `I → ı` olmalıdır. `"IZIN"` ile `"izin"` eşleşmezse arama çöker.
- **Ek ayıklama** — `kaynağından`, `kaynaklar`, `kaynak` aynı kökten gelir; kaba bir önek eşleştirmesi kullanılır (tam morfolojik çözümleyici air-gap'te fazladan bağımlılıktır).
- **Ünsüz yumuşaması** — `kaynak → kaynağ-`; doğrulama düzenli ifadeleri bu yüzden `kayna[kğ]` biçiminde yazıldı.
- **Denklikler** — soru "Kasım 2024" derken belge "11/2024" yazar; "üçüncü" derken "3." yazar. `_equivalents()` bu eşleşmeleri **tek yönlü** (kelime → sayı) üretir. Ters yön denendi ve geri alındı: `"3. Vardiya"` sorgusu `"mart"` ile eşleşip gürültü yaratıyordu.

---

## 4. Proje yapısı

```
belge-asistani/
│
├── server.py                       ➤ FastAPI sunucusu (API + akışlı yanıt)
├── config.yaml                     ➤ TÜM parametreler burada (kodda sabit değer yok)
├── requirements.txt                ➤ Sürümleri sabitlenmiş bağımlılıklar
├── LICENSE                         ➤ MIT (+ model lisans notları)
│
├── baslat.bat                      ➤ [Windows] tek tıkla başlatıcı
├── kurulum.bat                     ➤ [Windows] tek seferlik kurulum
├── indeksle.bat                    ➤ [Windows] belge indeksleme
├── ocr-kur.bat                     ➤ [Windows] Tesseract tespiti + yapılandırma
│
├── src/
│   ├── airgap.py                   ➤ Ağ izolasyonu (socket yaması + offline env)
│   ├── config.py                   ➤ Yapılandırma yükleyici
│   ├── loaders.py                  ➤ PDF/DOCX/XLSX/CSV/TXT → konumlu metin blokları
│   ├── ocr.py                      ➤ Taranmış sayfa tespiti, OCR, kalite puanlama
│   ├── ingest.py                   ➤ Madde bazlı parçalama + embedding + artımlı indeks
│   ├── embedder.py                 ➤ bge-m3 sarmalayıcı (yalnızca yerel dosya)
│   ├── vectorstore.py              ➤ ChromaDB katmanı
│   ├── bm25.py                     ➤ Türkçeye uyarlanmış BM25 + RRF + kelime kapsamı
│   ├── prompts.py                  ➤ STRICT RAG prompt şablonları
│   ├── llm_client.py               ➤ Ollama / vLLM istemcisi (yalnızca 127.0.0.1)
│   ├── rag_engine.py               ➤ Arama → RRF → MMR → eşik → prompt → doğrulama
│   └── verify.py                   ➤ Atıf, meta-cümle ve sayı doğrulaması
│
├── web/
│   ├── index.html                  ➤ Tek sayfa arayüz
│   ├── style.css                   ➤ Tema (yalnızca CSS değişkenleri)
│   └── app.js                      ➤ Akış, yükleme, ayarlar — bağımlılık yok
│
├── assets/
│   └── logo.svg                    ➤ Nötr işaret (kendi logonuzla değiştirin)
│
├── scripts/
│   ├── download_models.py          ➤ [internetli] model indirici
│   ├── prepare_offline_bundle.ps1  ➤ [internetli] transfer paketi (Windows)
│   ├── prepare_offline_bundle.sh   ➤ [internetli] transfer paketi (Linux)
│   ├── verify_offline.py           ➤ Kurulum kabul testi (13 kontrol)
│   ├── setup_ocr.py                ➤ Tesseract tespiti + config.yaml güncelleme
│   ├── make_test_pdf.py            ➤ Sentetik test belgesi üreticisi
│   └── find_text.py                ➤ İndekste düz metin arama (teşhis aracı)
│
├── eval/
│   ├── run_eval.py                 ➤ Doğruluk ölçümü + parametre taraması
│   ├── matching.py                 ➤ Beklenti eşleştirme ölçütü
│   ├── stats.py                    ➤ Wilson / Newcombe güven aralıkları
│   ├── testset_depo.yaml           ➤ 29 soru — GELİŞTİRME seti
│   ├── testset_holdout.yaml        ➤ 29 soru — AYRILMIŞ set (kilitli)
│   └── testset_taranmis.yaml       ➤ 16 soru — taranmış sürüm (OCR maliyeti)
│
├── tests/                          ➤ 129 birim testi (pytest, LLM gerekmez)
│   ├── test_guardrail.py           ➤ Atıf/sayı doğrulama katmanı
│   ├── test_bm25.py                ➤ Türkçe arama uyarlamaları, RRF
│   ├── test_eval_metrics.py        ➤ Ölçüm aletinin kendisi
│   ├── test_context_budget.py      ➤ Bağlam penceresi taşması
│   ├── test_ingest_incremental.py  ➤ SHA-256 artımlı indeksleme
│   ├── test_leak_scanner.py        ➤ Sızıntı tarayıcısının kendisi
│   ├── test_loaders_ocr.py         ➤ Boilerplate ayıklama, OCR içerik kaybı
│   └── conftest.py                 ➤ import yolu ayarı
│
├── .github/workflows/test.yml      ➤ CI: her push'ta test + sızıntı taraması
│
├── ornek_belgeler/
│   ├── dijital/depo_sozlesmesi.pdf         ➤ 20 sayfa, temiz metin
│   └── taranmis/depo_ekler_taranmis.pdf    ➤ 3 sayfa, taranmış görüntü
│
├── data/                           ➤ [git dışı] belgeler, indeks, manifest
├── models/                         ➤ [git dışı] bge-m3, (ops.) reranker
└── logs/                           ➤ [git dışı] denetim günlüğü
```

> `data/`, `models/` ve `logs/` **bilinçli olarak** versiyon kontrolü dışındadır: kurumsal belgeler, belge metinlerinin tamamını barındıran vektör indeksi ve gerçek soru-yanıt kayıtları içerirler. Klasörler ilk çalıştırmada otomatik oluşur.

---

## 5. Kullanım

### 5.1 Desteklenen belge türleri

| Tür | Uzantı | Not |
|---|---|---|
| PDF (dijital) | `.pdf` | Sayfa numarası atıfta gösterilir; tablolar satır bütünlüğü korunarak okunur |
| PDF (taranmış) | `.pdf` | **Otomatik OCR** — bkz. §5.4 |
| Taranmış görüntü | `.jpg` `.jpeg` `.png` `.tif` `.tiff` `.bmp` `.webp` | **OCR zorunlu** — görüntüde metin katmanı yoktur. Çok sayfalı TIFF desteklenir; düşük çözünürlüklü görüntüler OCR öncesi büyütülür |
| Word | `.docx` | Paragraf ve tablo numarası korunur |
| Excel | `.xlsx` `.xlsm` `.xls` | Satır bazlı parçalama, birleştirilmiş hücreler yayılır |
| Metin | `.txt` `.md` | Kodlama otomatik tespit edilir |
| Ayraçlı | `.csv` `.tsv` | Ayraç otomatik tespit edilir |

### 5.2 Belge indeksleme

```bash
python -m src.ingest                  # artımlı — yalnızca değişen dosyalar
python -m src.ingest --rebuild        # sıfırdan (chunk ayarı değiştiyse ZORUNLU)
python -m src.ingest --dry-run        # yazmadan raporla
python -m src.ingest --path <klasör>  # farklı bir klasörü indeksle
```

Artımlı indeksleme SHA-256 özetine dayanır: değişmemiş dosya yeniden işlenmez, güncellenen dosyanın eski parçaları silinir, diskten silinen belge indeksten otomatik düşer.

> **Arayüzden yüklenen belgeler otomatik indekslenmez.** Yükleme sonrası çekmecedeki *"İndeksi güncelle"* düğmesine basın veya `indeksle.bat` çalıştırın. Belge listesindeki işaretler durumu gösterir: ● indekslendi · ○ indekslenmedi · ▲ hata.

### 5.3 Başlatma

```bash
ollama serve            # ayrı terminalde (Windows'ta servis olarak çalışır)
python server.py        # veya: uvicorn server:app --host 127.0.0.1 --port 8501
```

### 5.4 Taranmış PDF'ler — OCR

Fotokopi/tarayıcı çıktısı PDF'lerde metin katmanı yoktur. Sistem bunu **sayfa bazında** tespit eder ve yalnızca o sayfalara OCR uygular; dijital sayfalar hızlı yoldan okunmaya devam eder (karma belgeler desteklenir).

**Doğrudan görüntü dosyaları** (`.jpg`, `.png`, `.tiff` …) da desteklenir — kurumsal taramalar sıklıkla PDF değil JPG olarak gelir ya da telefonla fotoğraflanır. PDF'ten önemli bir farkı vardır: görüntüde metin katmanı **hiç yoktur**, dolayısıyla OCR yedek bir yol değil tek yoldur. Bu yüzden Tesseract kurulu değilse dosya sessizce atlanmaz, açık hata verilir — aksi hâlde kullanıcı "belge indekslendi ama hiçbir soruya cevap gelmiyor" durumunda kalırdı.

Düşük çözünürlüklü görüntüler OCR öncesi otomatik büyütülür: karakter yüksekliği ~20 pikselin altına düştüğünde Tesseract belirgin şekilde bozulur. Büyütmek bilgi eklemez ama harf ayrıştırmasını kolaylaştırır.

Python paketleri `requirements.txt` içindedir, ancak **Tesseract motoru ayrıca kurulmalıdır**:

- **Windows:** [UB-Mannheim kurulumu](https://github.com/UB-Mannheim/tesseract/wiki) — kurulumda **Turkish** dil paketini işaretleyin. Ardından `ocr-kur.bat` çalıştırın; kurulum yolunu bulup `config.yaml`'a yazar.
- **Linux:** `sudo apt install tesseract-ocr tesseract-ocr-tur`
- **Air-gap:** kurulum dosyasını ve `tur.traineddata` dosyasını transfer paketine ekleyin.

| Ayar (`config.yaml → ocr`) | Varsayılan | Açıklama |
|---|---|---|
| `enabled` | `true` | Kapatılırsa taranmış PDF'ler hata listesine düşer |
| `language` | `tur+eng` | Karma belgelerde iki dili birlikte kullanın |
| `dpi` | `300` | Düşürmek hızlandırır ama rakam hatalarını artırır |
| `preprocess` | `true` | Kontrast + keskinlik iyileştirmesi |
| `min_chars_per_page` | `60` | Bu değerin altındaki sayfa "taranmış" sayılır |
| `tesseract_cmd` | `""` | Boşsa PATH ve bilinen konumlar otomatik taranır |

> **Hız:** OCR sayfa başına CPU'da 3–10 saniye sürer; 200 sayfalık taranmış bir belge 15–30 dakika alabilir. Bu yalnızca ilk indekslemededir.
>
> **Kalite:** OCR çıktısı hatasız değildir (`5`↔`S`, `1`↔`l`, `0`↔`O`). Sistem her sayfaya kalite puanı verir ve düşük puanlıları raporda listeler. **Taranmış belgelerden gelen sayısal yanıtları kaynaktan doğrulayın.**

### 5.5 Arayüz

- **Sohbet:** soru koyu ve büyük, yanıt akıcı okuma tipografisiyle. Yanıt token token akar.
- **Atıflar:** `[K1]` rozetleri tıklanabilir — ilgili kaynak kartına kaydırır ve vurgular.
- **Kaynaklar:** katlanır panelde belge adı, sayfa/satır numarası, benzerlik yüzdesi ve ham metin. Yanıtta atıf verilen parçalar sol kenarında şeritle işaretlenir.
- **Reddedildiğinde bile** bulunan parçalar gösterilir ("bulunan en yakın N parça — yanıtta kullanılmadı"). Bu ayrım olmadan *"doğru parça hiç gelmedi mi, yoksa geldi de model mi kullanamadı?"* sorusu cevaplanamaz ve eşik ayarı körlemesine yapılır.
- **Tema:** `config.yaml → app.theme` değerleri açılışta CSS değişkenlerine yazılır; renk değiştirmek için kod dokunuşu gerekmez.

### 5.6 Markalama

`assets/logo.svg` dosyasının üzerine kendi logonuzu yazın (PNG kullanacaksanız `config.yaml → app.logo_path` güncelleyin). Başlık, alt başlık ve tüm renkler `config.yaml → app` altındadır; CSS içinde sabit renk yoktur.

---

## 6. Halüsinasyon önleme mimarisi

Tek bir prompt talimatı yeterli **değildir**. Sistemde birbirinden bağımsız **yedi katman** vardır:

| # | Katman | Nerede | Ne yapar |
|---|---|---|---|
| 1 | **Alaka eşiği** | `rag_engine.retrieve()` | En iyi parçanın benzerliği `min_similarity` altındaysa **LLM hiç çağrılmaz**. Model uydurma fırsatı bulamaz. |
| 2 | **Kelime kapsamı** | `bm25.keyword_coverage()` | Sorunun ayırt edici kelimeleri hiçbir parçada geçmiyorsa aday elenir. Anlamsal olarak "yakın" ama konu dışı parçaları keser. |
| 3 | **Strict prompt** | `prompts.SYSTEM_PROMPT` | Kapalı-kitap yasağı, atıf zorunluluğu, kısmi bilgi kuralı, tablo satır eşleşmesi kuralı, yorum yasağı. |
| 4 | **Atıf denetimi** | `rag_engine._validate_and_finalize()` | Yanıtta hiç `[K#]` yoksa **reddedilir**. Verilmemiş bir kaynak numarası varsa (`[K7]` ama 5 kaynak var) **tamamen reddedilir** — bu, modelin uydurmaya başladığının en güçlü sinyalidir. |
| 5 | **Cümle bazında atıf** | `verify.check()` | Sayı içeren veya uzun HER cümlede `[K#]` olmalı. Atıfsız cümle yanıttan **ayıklanır** (tüm yanıt reddedilmez). |
| 6 | **Sayı doğrulama** | `verify.check()` | Yanıttaki her sayı, verilen kaynak metinlerde birebir geçmeli. Uydurulan veya modelin kendi hesapladığı sayıyı yakalar. |
| 7 | **Metin doğrulama**<br><sub>*uyarı kipinde*</sub> | `verify.unsupported_terms()` | Yanıttaki içerik kelimelerinin kaynakta karşılığı var mı? Türkçe çekim eklerine toleranslı. **Şu an reddetmiyor, yalnızca uyarıyor** — gerekçesi aşağıda. |

> **5 ve 6 gerçek bir hatadan doğdu.** Model şunu üretti:
> *"İşin süresi ... otuziki aydır [K2]. ... Bu nedenle toplam iş süresi **30 aydır**."*
> Kaynakta 32 yazıyordu. Yanıtın başında atıf olduğu için "atıf var mı?" denetimi bunu kaçırıyordu. Başka bir denemede model personel dağılımını (1+2+5=8) uydurup kendi verdiği 20 rakamıyla çelişti. Katman 5 atıfsız cümleyi, katman 6 kaynakta olmayan sayıyı yakalar.

> **Katman 5'in ilk hâli fazla sertti.** Atıfsız tek cümle yüzünden yanıtın tamamı reddediliyordu ve yanlış ret oranı %75'e çıkmıştı. `sentence_citation_action: "strip"` ile davranış "reddet"ten "ayıkla"ya çevrildi; doğruluk %75 → %89,7'ye yükseldi.

Ek olarak: `temperature 0.0` + `seed 42` (tekrar üretilebilirlik), belge başına parça sınırı (tek belgenin bağlamı domine etmesini engeller), `strong_similarity` altında kullanıcıya düşük güven uyarısı.

#### Katman 7 neden hâlâ reddetmiyor?

Katman 6, adı üstünde, **sayı** merkezlidir; sayısız bir belgede tamamen boşta kalır. Yönetmelik ölçümünde model `yöneticiyi` yerine **`yındıktıyı`** yazdı — yanıt atıflıydı, uydurma sayı içermiyordu, cümle yapısı düzgündü ve **altı katmanın hiçbiri yakalamadı.** Katman 7 bu boşluğu kapatmak için yazıldı.

Katman ölçülmeden blokçu yapılmadı. Önce `config.yaml → guardrail.verify_text: "warn"` ile **gölge kipte** koşuldu: kelimeleri kaydeder, hiçbir yanıtı reddetmez. Ölçüm öncesinde karar kuralı yazıldı — yanlış alarm ≤ %5 ise blokçu yap, %5–20 ise uyarıda bırak, > %20 ise geri al.

| Set | Yanlış alarm<br><sub>doğru cevapta işaret</sub> | Yakalanan<br><sub>yanlış cevapta işaret</sub> |
|---|---|---|
| Geliştirme (depo) | 2/19 · %10,5 | veri yok¹ |
| Yönetmelik | 0/14 · %0 | **1/1** — `yındıktıyı` |
| Taranmış | 0/4 · %0 | 1/2 · %50 |
| **Toplam** | **2/37 · %5,4** | **2/3** |

<sub>¹ Depodaki tek hata bir RET'ti; ret'te denetlenecek yanıt yoktur.</sub>

**%5,4, ilan edilen %5–20 bandına düşüyor → katman uyarı kipinde kaldı.** Ölçüm ayrıca `warn` kipinin gerçekten atıl olduğunu doğruladı: üç setin üçünde de skorlar birebir aynı kaldı.

İki yanlış alarmın dördü de **dilbilgisi** kelimesiydi (`arasında`, `olmalıdır`, `aralığında`, `tarafından`), içerik değil. Beyaz listeye eklendiler — ama bu, **geliştirme setine bakarak** yapılmış bir ayardır, dolayısıyla bundan sonraki yanlış alarm oranı iyimserdir ve tek başına `block` kararına dayanak olamaz. Blokçu yapılmadan önce bu listeyi hiç görmemiş bir sette doğrulanması gerekir.

> **Beyaz liste kalıcı çözüm değil.** Herhangi bir Türkçe kelime listede olmayabilir. Yapısal alternatif, kelimeyi *getirilen parçalarla* değil *tüm korpus sözlüğüyle* karşılaştırmaktır: `tarafından` belgelerde onlarca kez geçer, listeye hiç gerek kalmazdı; `yındıktıyı` ise hiçbir belgede geçmez, yine yakalanırdı. Bunun bedeli garantinin anlamının değişmesidir — "her kelime atıf verilen kaynakta var"dan "kelime kullanıcının belgelerinde var"a düşer.

### 6.1 Kullanılan system prompt

```text
Kurum içi belge asistanısın. YALNIZCA sana verilen KAYNAK bloklarını
kullanarak Türkçe yanıt verirsin.

## KURALLAR
1. Eğitim verindeki genel bilgini KULLANMA. Her cümle kaynaklardan
   doğrulanabilir olmalı.
2. Sayı, tarih, oran veya isim içeren HER cümlenin sonuna atıf koy:
   [K2] ya da [K1][K3]. Atıfını veremeyeceğin cümleyi hiç yazma.
3. Yanıt kaynaklarda yoksa tahmin yürütme; yalnızca şunu yaz:
   "Bu konu hakkında yüklenen belgelerde bilgi bulunmamaktadır."
   Bu cümleyi YA TEK BAŞINA yaz YA DA hiç yazma. Cevabını verdiysen
   sonuna bu cümleyi EKLEME.
4. Sorunun bir kısmı cevaplanabiliyorsa o kısmı atıfla ver, eksik
   konuyu adıyla belirt.
5. Sana verilmemiş kaynak numarası, madde numarası, tarih veya sayı ÜRETME.
6. Kaynaklar çelişiyorsa ikisini de atıfla göster, kendin karar verme.
7. Hukuki/mali yorum yapma; belgede yazanı aktar.
8. Sayıları kaynaktaki biçimiyle kopyala. Toplama, çıkarma, yuvarlama YAPMA.
9. TABLOLARDA SATIR EŞLEŞMESİ: Soruda tarih/dönem/kod geçiyorsa yalnızca
   o değerin BİREBİR bulunduğu satırı kullan, komşu satırı asla kullanma.
10. ŞU YAZIMLAR AYNIDIR; farklı yazıldı diye "bilgi yok" DEME:
    Ocak=01 · Kasım=11 | birinci=1, üçüncü=3 | onsekiz=18, otuziki=32
11. "Bu nedenle", "Sonuç olarak" gibi kapanış cümlesi KURMA. Bilgiyi bir
    kez atıfla ver ve dur.
```

Kaynaklar `[K1]`, `[K2]` gibi **kısa ve makinece ayrıştırılabilir** etiketlerle numaralandırılır (dosya adı yazdırmak modele uzun ve hatalı atıf ürettirir). Her blok `---` ile sınırlandırılır. Talimat hem system hem user mesajında tekrarlanır — küçük modellerde bu tekrar kural uyumunu belirgin şekilde artırır.

> **Prompt uzunluğu bir kaynak meselesidir.** Bu metin her soruda bağlam penceresine girer; kurallar biriktikçe kaynaklara yer kalmaz. Kural eklerken `num_ctx` bütçesini kontrol edin.

---

## 7. Parametre optimizasyonu

### 7.1 Değerler ve gerekçeleri

| Parametre | Varsayılan | Aralık | Açıklama |
|---|---|---|---|
| `chunk_size` | **700** karakter | 500–1200 | Türkçe mevzuatta bir "MADDE" ortalama 400–900 karakterdir. `article_aware_split` zaten madde sınırlarını önceliklendirir; 700 çoğu maddeyi bölmeden kapsar. Büyütmek gürültüyü ve CPU'da prefill süresini artırır. |
| `chunk_overlap` | **150** (~%21) | %10–25 | Bir cümle iki parçaya bölünürse bilgi kaybolmasın diye. %25 üzeri indeksi ve tekrarlı sonuçları gereksiz büyütür. |
| `article_aware_split` | `true` | — | `MADDE 5.1` gibi sınırlarda böler. Yalnızca satır başında veya `.`/`:` sonrasında eşleşir — aksi hâlde `(5.1, 5.2)` gibi metin içi referanslar cümleyi ortadan bölüyordu. |
| `table_rows_per_chunk` | **1** | 1–3 | **Tablo doğruluğunun anahtarı.** Tüm tablo tek parçaya girerse model komşu satırı okur (sorulan 5. ay, gelen 6. ay). Her satır ayrı parça olunca bu imkânsızlaşır. |
| `top_k` | **20** | 10–40 | Her yöntemden çekilecek aday sayısı. Ucuzdur (ms mertebesi); asıl maliyet `final_k`'dadır. |
| `final_k` | **4** | 3–8 | LLM'e giden parça sayısı. 7B sınıfında 8 üzerinde **"lost in the middle"** başlar. CPU'da her ek parça ~5–10 sn prefill demektir. `num_ctx: 4096` ile 4 uygundur. |
| `min_similarity` | **0.35** | 0.25–0.50 | **Ret davranışının ana kolu.** Yükseltirseniz uydurma azalır, "bilgi bulunamadı" artar. Düşürürseniz tersi. §7.2'ye göre kalibre edin. |
| `min_keyword_coverage` | **0.5** | 0.3–0.7 | Sorunun ayırt edici kelimelerinin en az bu oranı bir parçada geçmeli. |
| `mmr_lambda` | **0.6** | 0.5–0.8 | 1.0 = saf benzerlik (tekrarlı parçalar), 0.0 = saf çeşitlilik (alakasızlaşır). MMR, hibrit sıralamayı bozmasın diye ham kosinüs yerine **birleştirilmiş skoru** kullanır. |
| `max_chunks_per_document` | **3** | 2–5 | Tek belgenin bağlamı doldurmasını engeller. Tek belge indekslendiğinde `final_k`'ya kadar geri doldurma yapılır. |
| `temperature` | **0.0** | 0.0–0.2 | RAG'de yaratıcılık **istenmeyen** bir özelliktir. 0.0 aynı soruya aynı yanıtı verir (denetlenebilirlik). 0.3 üzerinde belge dışına çıkma gözle görülür artar. |
| `num_ctx` | **4096** (16 GB) / 8192 (32 GB) | 4096–16384 | Sistem prompt + bağlam + yanıt toplamını karşılamalı. **`out-of-memory` hatasında ilk düşürülecek parametre budur.** |
| `context_char_budget` | **5500** | — | `num_ctx` ile birlikte ayarlanır. Kabaca `budget ≈ (num_ctx − num_predict − 900) × 2.7`. Kod ayrıca `_fit_char_budget()` ile bu değeri pencereye göre otomatik daraltır. |
| `num_gpu` | **0** | — | Saf CPU. Ollama aksi hâlde sabitlenmiş (pinned) ana bellek ayırmaya çalışır ve GPU'suz makinede `CUDA_Host buffer` hatası verir. |
| `keep_alive` | **30m** | — | Model RAM'de kalsın; her soruda diskten yeniden yüklenmesin. |

### 7.2 `min_similarity` kalibrasyonu

Bu tek parametre sistemin "fazla konuşkan" mı "fazla suskun" mu olacağını belirler. Gözle ayarlamayın, **ölçün**:

1. Kendi belgelerinizden **20 cevaplanabilir** + **20 cevaplanamaz** soru yazın (`eval/testset_depo.yaml` biçimini örnek alın).
2. Tarama çalıştırın:
   ```bash
   python eval/run_eval.py --testset eval/kendi_setim.yaml --sweep --out eval/tarama.json
   ```
3. İki metriğe bakın: `ret_dogrulugu_%` **≥ %95** olmalı, `yanlis_ret_%` **≤ %10**.
4. Ret doğruluğu düşükse eşiği 0.05 artırın; yanlış ret yüksekse 0.05 azaltın.

> İkisi arasında seçim gerekirse **eşiği yüksek tutun**. Kurumsal bir asistanda yanlış bilgi vermek, "bilmiyorum" demekten çok daha pahalıdır.

### 7.3 Doğruluk artırma sırası (maliyet/fayda)

1. **Belge kalitesi** — taranmış PDF'lere iyi OCR, bozuk karakterlerin düzeltilmesi. *En yüksek etki, sıfır çalışma zamanı maliyeti.*
2. **Eşik kalibrasyonu** (§7.2) — bedava.
3. **`chunk_size` denemesi** — 500 / 700 / 1000 ile üç kez `--rebuild` + eval. *Birkaç saat.*
4. **Reranker'ı açmak** (`reranker.enabled: true`) — isabeti belirgin artırır, soru başına **+3–8 sn** CPU maliyeti.
5. **14B modele geçmek** — 32 GB RAM gerektirir, hız ~%40 düşer.

### 7.4 Belge tipine göre chunk önerileri

| Belge tipi | `chunk_size` | `chunk_overlap` | Not |
|---|---|---|---|
| Yönetmelik / sözleşme (madde yapılı) | 700–900 | 150 | `article_aware_split` madde sınırlarını önceliklendirir |
| Teknik şartname / prosedür | 1000–1200 | 200 | Adım listeleri bölünmemeli |
| Toplantı tutanağı / yazışma | 500–700 | 120 | Kısa, bağımsız paragraflar |
| Tablo ağırlıklı (XLSX/CSV) | — | — | Satır bazlı bloklara ayrılır, başlık her bloğa eklenir |

---

## 8. Donanım gereksinimleri (CPU-only)

| | **Asgari** | **Önerilen** | **İdeal** |
|---|---|---|---|
| CPU | 8 çekirdek, AVX2 (i5-11400 / Ryzen 5 5600) | 12–16 çekirdek (i7-13700 / Ryzen 7 7700) | 24–32 çekirdek Xeon / EPYC |
| RAM | **16 GB** | **32 GB** | **64 GB** |
| Disk | 40 GB SSD | 120 GB NVMe | 250 GB NVMe (RAID1) |
| LLM | Qwen2.5-**3B** Q4_K_M | Qwen2.5-**7B** Q4_K_M | Qwen2.5-**14B** Q4_K_M |
| Embedding | e5-small (384 boyut) | **bge-m3** | bge-m3 + reranker |
| Beklenen hız | 4–7 token/sn | 8–14 token/sn | 10–16 token/sn |
| Yanıt gecikmesi | 30–70 sn | **12–30 sn** | 8–18 sn |
| Eşzamanlı kullanıcı | 1 | 1–2 | 3–5 |

**RAM bütçesi** (önerilen yapılandırma): LLM ağırlıkları ~4.7 GB · KV cache (`num_ctx 4096`) ~0.5 GB · bge-m3 ~2.3 GB · ChromaDB + Python + sunucu ~1.2 GB · işletim sistemi ~4 GB → **~13 GB**. 16 GB sınırda, 32 GB rahat.

**Disk bütçesi:** Qwen2.5-7B 4.7 GB · bge-m3 2.3 GB · (ops.) reranker 2.3 GB · Python + torch(CPU) ~4 GB · vektör indeksi (10.000 sayfa ≈ 40.000 parça) ~1.2 GB.

### CPU'ya özgü kritik uyarı — "prefill" darboğazı

CPU'da asıl bekleme token üretmekten çok **prompt'u okumaktan** gelir. 6.000 token'lık bir bağlam, 8 çekirdekli bir makinede 30–60 saniye ek gecikme yaratır. Varsayılanlar bu yüzden bilinçli olarak muhafazakârdır: `final_k: 4`, `context_char_budget: 5500`, `num_ctx: 4096`, `reranker.enabled: false`.

> **Genel kural:** CPU'da doğruluğu artırmanın en ucuz yolu bağlamı büyütmek değil, **daha isabetli 4 parça getirmektir** (iyi chunking + eşik kalibrasyonu).

---

## 9. Air-gap kurulum (transfer paketi)

Kurulum üç aşamalıdır. **1. aşama internetli bir makinede yapılır; air-gap makinede hiçbir indirme komutu çalıştırılmaz.**

### Aşama 1 — Staging (internetli makine)

```powershell
powershell -ExecutionPolicy Bypass -File scripts\prepare_offline_bundle.ps1   # Windows
```
```bash
bash scripts/prepare_offline_bundle.sh                                        # Linux
```

Betik şunu üretir:

```
offline_bundle/
├── wheelhouse/        # Tüm .whl dosyaları (torch CPU sürümü dahil)
├── models/            # bge-m3 (+ ops. reranker) — gerçek dosyalar, symlink DEĞİL
├── ollama_models/     # Qwen2.5-7B Q4_K_M blob'ları
├── proje/             # Kaynak kod
├── KURULUM.txt
└── SHA256SUMS         # Transfer bütünlük doğrulaması
```

Pakete elle eklenmesi gerekenler: Python kurulum dosyası, `OllamaSetup.exe` / `ollama-linux-amd64.tgz`, taranmış PDF varsa Tesseract kurulumu + `tur.traineddata`.

### Aşama 2 — Transfer

Kurumun onaylı taşınabilir medyasına kopyalayın (zararlı yazılım taraması zorunlu), sonra air-gap makinede bütünlüğü doğrulayın:

```bash
cd offline_bundle && sha256sum -c SHA256SUMS          # Linux
```

### Aşama 3 — Air-gap makinede kurulum

```powershell
# 1) Python 3.11 kurun (offline installer)
# 2) Ollama kurun, servisi durdurun, model deposunu yerleştirin
Stop-Service ollama -ErrorAction SilentlyContinue
Copy-Item -Recurse offline_bundle\ollama_models\* "$env:USERPROFILE\.ollama\models\"
Start-Process ollama -ArgumentList "serve"
ollama list                                    # model görünmeli

# 3) Proje ve modeller
Copy-Item -Recurse offline_bundle\proje  C:\belge-asistani
Copy-Item -Recurse offline_bundle\models C:\belge-asistani\models

# 4) Python ortamı — tamamen çevrimdışı
cd C:\belge-asistani
python -m venv .venv ; .venv\Scripts\activate
pip install --no-index --find-links=<USB>\offline_bundle\wheelhouse -r requirements.txt

# 5) Kabul testi
python scripts\verify_offline.py
```

`verify_offline.py` **13 kontrol** çalıştırır. İndeks henüz boşken 2 kontrol `!` verir (normaldir); makine ağa bağlıysa "Makine yalıtımı" kontrolü de `!` verir — bu, süreç içi korumanın kapsamadığı alanı hatırlatır:

```
 ✔  Python sürümü                     Python 3.11.9 (AMD64)
 ✔  Sanal ortam                       .venv etkin
 ✔  Python paketleri                  tümü kurulu
 ✔  Disk alanı                        184.2 GB boş
 ✔  Air-gap koruması                  harici bağlantı bloklandı, localhost açık
 ✔  Embedding modeli dosyaları        bge-m3 (14 dosya)
 ✔  Embedding üretimi                 models/bge-m3 → 1024 boyut
 !  Vektör veri tabanı                koleksiyon boş — 'python -m src.ingest'
 ✔  LLM servisi                       qwen2.5:7b-instruct-q4_K_M hazır
 ✔  LLM metin üretimi                 yanıt: 'HAZIR' (1.1 sn)
```

### Aşama 4 — Ağı fiziksel olarak kesin

```powershell
Get-NetAdapter | Disable-NetAdapter -Confirm:$false     # Windows
```
```bash
nmcli networking off                                    # Linux
```

Uygulama ayrıca **kendi süreci içinde** localhost dışı tüm TCP bağlantılarını ve DNS çözümlemelerini bloklar (`src/airgap.py`).

> **Bu adım atlanamaz.** Süreç içi koruma yalnızca uygulamayı kapsar; Ollama ayrı bir süreç olarak çalışır ve socket yaması ona ulaşmaz. Makinenin tamamının yalıtımı ancak ağ arayüzünün kapatılmasıyla sağlanır. `scripts/verify_offline.py` süreç içi korumayı doğrular; işletim sistemi düzeyindeki yalıtımı **doğrulamaz** — onu kurumun ağ ekibi teyit etmelidir.

---

## 10. Güvenlik ve KVKK

### Uygulanmış olanlar

- **Süreç içi ağ izolasyonu:** localhost dışı `connect()`, `connect_ex()`, `create_connection()` ve `getaddrinfo()` çağrıları `AirGapViolation` fırlatır.
- **Telemetri kapalı:** `HF_HUB_OFFLINE=1`, `TRANSFORMERS_OFFLINE=1`, `ANONYMIZED_TELEMETRY=False`.
- **Sıfır dış bağımlılık (ön yüz):** arayüzde hiçbir CDN, web fontu veya JS kütüphanesi yok.
- **LLM adresi kod seviyesinde doğrulanır:** yalnızca `127.0.0.1` kabul edilir.
- **Sunucu yalnızca `127.0.0.1` dinler.**
- **Denetim günlüğü:** soru, ret nedeni, benzerlik skoru, kullanılan kaynaklar → `logs/audit.jsonl`.
- **Belgeler, indeks ve günlükler `.gitignore` ile versiyon kontrolü dışında.**

### Devreye alma öncesi tamamlanması gerekenler

| Konu | Öneri |
|---|---|
| **Kimlik doğrulama** | Uygulamanın yerleşik kullanıcı yönetimi yoktur. Tek kullanıcılı kiosk değilse önüne kurumsal SSO/LDAP doğrulaması yapan bir ters vekil sunucu (IIS + Windows Authentication, nginx + Kerberos) koyun. |
| **Yetkilendirme** | Belge bazlı erişim gerekiyorsa metadata'ya `gizlilik_seviyesi` ekleyip `retrieve()` içindeki `where` filtresini kullanıcı rolüne bağlayın. |
| **Disk şifreleme** | `data/` ve `logs/` hassas veri içerir → BitLocker / LUKS zorunlu. Vektör indeksi belge metinlerinin **tamamını** barındırır; belge kadar hassastır. |
| **Günlük saklama** | `logs/audit.jsonl` soru metinlerini saklar; KVKK saklama sürenize göre rotasyon ve imha kuralı tanımlayın. Gerekirse `security.audit_log: false`. |
| **Ağ** | Kurulum sonrası ağ arayüzünü devre dışı bırakın; 8501 ve 11434 portlarını dışa kapatın. |
| **Değişiklik yönetimi** | Her model/parametre değişikliğinden sonra `verify_offline.py` + `run_eval.py` çalıştırılıp sonuç kayıt altına alınmalı. |
| **Kullanıcı bilgilendirmesi** | "Yanıtlar yalnızca yüklenen belgelere dayanır" uyarısı korunmalı; nihai sorumluluk kaynağı doğrulayan kullanıcıdadır. |

---

## 11. Sorun giderme

| Belirti | Neden / Çözüm |
|---|---|
| `Microsoft Visual C++ 14.0 or greater is required` | ChromaDB **0.5.x** kurulmaya çalışılıyor; bu sürüm `chroma-hnswlib` C++ eklentisini kaynaktan derler. Çözüm: `pip install "chromadb==1.5.9"`. Build Tools kurmanıza **gerek yok**. |
| `ModuleNotFoundError` — paketler kurulu olmasına rağmen | Sanal ortam etkin değil. Komut satırında `(.venv)` öneki görünmeli: `.venv\Scripts\activate`. |
| `unable to allocate CUDA_Host buffer` | GPU yokken Ollama sabitlenmiş bellek ayırmaya çalışıyor. `config.yaml → llm.num_gpu: 0`. |
| `out of memory` / LLM 500 hatası | `num_ctx`'i 4096'ya, `num_predict`'i 700'e, `context_char_budget`'i 5500'e düşürün. Sırasıyla en etkilisi `num_ctx`'tir. |
| `LLM sunucusuna ulaşılamıyor` / `WinError 10061` | Ollama çalışmıyor. `ollama serve` başlatın; `ollama list` ile modeli doğrulayın. |
| Eval koşusunda tüm sorular `YANLIŞ RET → LLM erişilemez` | Aynı sebep: Ollama kapalı. Gecikmenin 2–3 sn'ye düşmesi bunun işaretidir (normalde ~25 sn). `run_eval.py` artık başlamadan önce LLM sağlığını kontrol eder ve koşu ortasında kesinti olursa **sonuç üretmeden durur** — kesintili bir koşu, inandırıcı görünen yanlış bir skor üretiyordu. |
| `Embedding modeli bulunamadı` | `models/bge-m3` eksik veya symlink kopyalanmış. Transferi `local_dir_use_symlinks=False` ile yapın; klasörde `model.safetensors` + `config.json` + `1_Pooling/` olmalı. |
| `AirGapViolation` | Bir bileşen dışarı çıkmaya çalıştı — **bu bir güvenlik bulgusudur, koruma kapatılarak geçilmemelidir.** Hata mesajındaki hedef adresi ve çağıran kütüphaneyi inceleyin. |
| Belge klasörde ama cevap gelmiyor | Belge listesindeki işarete bakın: ● indekslendi · ○ indekslenmedi · ▲ hata. Yükleme sonrası indeksi güncellemeniz gerekir. |
| Taranmış PDF ▲ hata veriyor | Tesseract kurulu değil. `ocr-kur.bat` çalıştırın veya `sudo apt install tesseract-ocr tesseract-ocr-tur`. |
| Tabloda yanlış satır okunuyor (5. ay sorulup 6. ay geliyor) | Tüm tablo tek parçaya girmiş. `table_rows_per_chunk: 1` ve `pdf_split_table_rows: true` olmalı, ardından **`--rebuild`**. |
| Özel isim/kod içeren soru bulunamıyor | Hibrit arama açık olmalı: `retrieval.hybrid_enabled: true`. Kapalıysa yalnızca anlamsal arama çalışır ve nadir özel isimler kaybolur. |
| Her soruya "bilgi bulunamadı" | (a) İndeks boş → `python -m src.ingest`. (b) `min_similarity` çok yüksek → 0.30'a düşürüp §7.2'ye göre kalibre edin. (c) e5 modeli kullanıyorsanız `query_prefix: "query: "` ve `passage_prefix: "passage: "` ayarlayıp **yeniden indeksleyin**. |
| Aynı soruya farklı zamanlarda farklı yanıt | Bağlam penceresi taşıyor olabilir. Prompt + kaynaklar `num_ctx`'i aşarsa Ollama sessizce kırpar. `context_char_budget`'i düşürün. |
| `chunk_size` değiştirdim, etkisi yok | Parçalama indeksleme anında yapılır. `python -m src.ingest --rebuild` zorunludur. |
| Yanıtlar çok yavaş | `final_k`'yı 3'e düşürün; `reranker.enabled: false`; `keep_alive: 30m`; 3B modele geçin. |
| İlk soru yavaş, sonrakiler hızlı | Normal — model RAM'e yükleniyor. `keep_alive` süresini uzatın. |
| "port kullanımda" | `python -m uvicorn server:app --port 8502` veya 8501'i kullanan süreci kapatın. |

### Teşhis araçları

```bash
python scripts/verify_offline.py                     # 10 maddelik kurulum kontrolü
python scripts/find_text.py "aranan ifade"           # indekste düz metin ara
python -m src.ingest --dry-run                       # yazmadan indeksleme raporu
python eval/run_eval.py --testset eval/testset_depo.yaml
```

`find_text.py` özellikle değerlidir: *"bilgi gerçekten indekste yok mu, yoksa arama mı bulamadı?"* sorusunu ayırt eder. Bu ayrım olmadan eşik ayarı tahminle yapılır.

---

## 12. Bilinen sınırlar

Bu bölüm, sistemin ölçülmüş zayıflıklarını tek yerde toplar. Hepsi ölçümle tespit edildi; hiçbiri tahmin değildir.

### Ölçümün sınırları

- **Test seti tek belge ve tek alandan.** Üç setin üçü de aynı sentetik depo sözleşmesinden yazıldı. Ayrılmış set **soru genellemesini** ölçer, **belge genellemesini** ölçmez. "Bu sistem tek bir sözleşmeye göre mi ayarlandı?" sorusunun cevabı henüz yok.
- **Örneklem küçük.** 29 soruda bir soru 3,4 puan. Tüm oranlar güven aralığıyla verilir; geliştirme ↔ ayrılmış farkının aralığı sıfırı içerir, yani **aşırı uyuma dair kanıt bulunamadı** — "genelliyor" kanıtlanmadı.
- **Puanlama anahtar kelime tabanlı.** Beklenen ifadenin yanıtta geçip geçmediğine bakılır; anlamsal doğruluk ölçülmez. Sayısal beklentilerde rakam sınırı zorunlu kılınarak şişme kırıldı, ancak yöntem hâlâ kelime varlığı ölçer.
- **Gecikme oynak.** Aynı makinede p50 için 22–47 sn arası gözlendi. Doğruluk metrikleri ise tekrarlanan koşularda sabit kalıyor (`temperature 0.0`, `seed 42`).

### Sistemin sınırları

- **Ay adı ↔ ay numarası.** Belge `11/2024`, kullanıcı "Kasım 2024" diyor. Arama katmanı denkliği biliyor ve doğru satırı ilk sıraya taşıyor; üretim katmanı satırı kullanmayı reddediyor. Üç prompt müdahalesi denendi, üçü ölçüldü, hiçbiri kazanç sağlamadı.
- **Madde numarası ↔ atıf çakışması.** Sade rakamla numaralanmış belgelerde (kira sözleşmesi, yönetmelik) model bazen madde numarasını kaynak numarası sanıp `[K7]` üretir; guardrail bunu uydurma sayıp yanıtı reddeder. Harf etiketi denendi, geliştirme setinde iki soruya mal olduğu için geri alındı. Sonuç yanlış rettir — sistem yanlış bilgi vermez, susar.
- **Metin doğrulama henüz reddetmiyor.** Katman 6 sayı merkezlidir ve sayısız belgelerde (yönetmelik, prosedür, hukuk metni) boşta kalır; bozuk bir KELİME denetimden geçer (`yöneticiyi` → `yındıktıyı`). Katman 7 bunu kapatmak için yazıldı ve hedef vakayı ölçümde yakaladı, ancak yanlış alarm oranı (%5,4) blokçu yapma eşiğinin üzerinde kaldığı için **yalnızca uyarı üretiyor** — yani bu tür bir bozulma hâlâ kullanıcıya ulaşır, sadece yanında bir uyarı ile.
- **Doğrulama, kaynağa sadakati ölçer; doğruluğu değil.** Tüm katmanlar yanıtı KAYNAK METİNLE karşılaştırır. Kaynağın kendisi bozuksa hiçbir katman devreye giremez. Ölçümde görüldü: OCR, `(%2)` ifadesini `(962)` olarak okumuştu; model bunu sadakatle aktardı, sayı denetimi "kaynakta geçiyor" dedi ve metin denetimi de bir kelime hatası görmedi. **Çöp girdi, doğrulanmış çöp çıktı.** Taranmış belgelerde bu, OCR kalite uyarılarının neden ciddiye alınması gerektiğinin somut sebebidir.
- **Tablo satır bölme üç sayfada çalışmıyor.** Tanımlar, personel ücretleri ve bakım programı tabloları tek blok kalıyor; komşu satıra kayma riski o sayfalarda daha yüksek.
- **Madde tanıma yalnızca `MADDE 5.1` biçimini tanıyor.** Sade `4 ` biçimindeki numaralandırma tanınmaz; o belgelerde parçalama karakter sayısına göre yapılır ve maddeler ortadan bölünebilir.

### OCR sınırları

- **OCR maliyeti gerçek, büyüklüğü belirsiz.** Taranmış sürümde fark 40,3 puan, güven aralığı 15,5–63,5 puan. Etkinin varlığı istatistiksel olarak sağlam; miktarı bu örneklemle kesinleştirilemez.
- **Sessiz veri kaybı olabilir.** OCR bir tablonun tüm satırlarını kaybedebilir ve geriye bozulmuş bir iz bırakmaz. Tespit ölçütü (mürekkep başına karakter) bunu yakalamak için eklendi, ancak **sezgiseldir, kanıt değildir.**
- **Eşik üç sayfadan türetildi.** `min_chars_per_ink: 3.0` değeri tek bir belgenin üç taranmış sayfasıyla kalibre edildi (hasarsız 4,0 · hasarlı 2,5–2,7). Eşik **yazı tipine, punto boyutuna, DPI'ya ve belge türüne bağlıdır**; başka belge ailelerinde yeniden kalibrasyon gerekebilir. Belge-içi göreli karşılaştırma bunu kısmen telafi eder (sayfa, belgenin en iyi sayfasıyla kıyaslanır) ama tüm sayfaları benzer şekilde hasarlı bir belgede yalnızca mutlak eşik devrede kalır.
- **Fotoğraf/kaşe içeren sayfalarda yanlış uyarı verebilir.** Mürekkep yüksek, metin az olduğu için içerik kaybı sanılabilir. Çıktı bir uyarıdır, hata değil; sayfa yine indekslenir.

### Kapsam sınırları

- **Air-gap koruması süreç düzeyinde.** `airgap.py` uygulama sürecini yamalar; Ollama ayrı süreçtir ve kapsam dışıdır. Makine düzeyinde yalıtım için ağ arayüzü kapatılmalıdır.
- **Tek kullanıcı, kimlik doğrulama yok.** Çok kullanıcılı kurulum için önüne SSO/LDAP doğrulaması yapan bir ters vekil sunucu gerekir.
- **Reranker ölçülmedi.** Varsayılan olarak kapalı; açık/kapalı karşılaştırması yapılmadığı için kazancı hakkında sayısal bir iddia yok.

---

## 13. Lisans

Kaynak kod **MIT** lisanslıdır (bkz. `LICENSE`). Kullanılan modeller kendi lisanslarına tabidir:

| Bileşen | Lisans | Kurumsal kullanım |
|---|---|---|
| Qwen2.5-7B-Instruct | Apache-2.0 | Serbest |
| BAAI/bge-m3 | MIT | Serbest |
| bge-reranker-v2-m3 | Apache-2.0 | Serbest |
| ChromaDB | Apache-2.0 | Serbest |
| Ollama | MIT | Serbest |

> Llama-3.1 kullanılacaksa Meta Llama 3.1 Community License, Gemma-2 için Gemma Terms of Use ayrıca değerlendirilmelidir; bu iki lisans Apache/MIT'den farklı yükümlülükler içerir.

---

*Bu sistem karar destek amaçlıdır. Üretilen yanıtlar, gösterilen kaynak belgeden doğrulanmadan resmî işlemlere esas alınmamalıdır.*
