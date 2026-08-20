"""
YANIT DOĞRULAMA — CÜMLE BAZINDA ATIF + SAYI DENETİMİ
=====================================================

NEDEN GEREKLİ?
Gerçek bir testte model şunu üretti:

    "İşin süresi, işe başlama tarihinden itibaren otuziki aydır [K2].
     İşe başlanacak tarih ise 01/05/2021'dir [K3].
     Bu nedenle ... toplam iş süresi 30 aydır."      ← ATIFSIZ ve YANLIŞ

Kaynakta 32 yazıyor. Model önce doğruyu atıflı yazdı, sonra kendi özet
cümlesinde sayıyı uydurdu. "Yanıtta atıf var mı?" denetimi bunu KAÇIRIR,
çünkü yanıtın başında atıflar var.

Başka bir örnekte "Mühendis 1, Tekniker 2, Teknisyen 5" dağılımı uyduruldu;
toplamı 8 ediyordu, modelin kendi verdiği 20 rakamıyla bile tutmuyordu.

Bu modül iki bağımsız denetim uygular:
  1. CÜMLE BAZINDA ATIF: sayı içeren veya uzun her cümlede [K#] olmalı.
     Modelin atıfsız "özet/sonuç" cümlesi eklemesini engeller.
  2. SAYI DOĞRULAMA: yanıttaki her sayı, verilen kaynak metinlerde
     birebir geçmeli. Uydurulan veya hesaplanan sayıyı yakalar.
"""

from __future__ import annotations

import re
from typing import Dict, List, Sequence, Set, Tuple

CITATION_RE = re.compile(r"\[K\s*(\d{1,2})\]")

# Sayı: 32 · 1.490,00 · %170 · 01/05/2021 (parçalar ayrı ayrı da yakalanır)
_NUMBER_RE = re.compile(r"\d+(?:[.,]\d+)*")

# Cümle sonu: nokta/soru/ünlem + boşluk. Ancak "9.2." ve "1.490,00" gibi
# sayı içi noktalarda BÖLMEZ (öncesinde rakam varsa atlanır).
# Cümle sonrası köşeli/normal parantezle başlayan parça da yeni cümledir:
# "... aydır. [K1] Bu konu ..." tek cümle sayılırsa ayıklama yanlış çalışır.
_SENT_SPLIT = re.compile(r"(?<=[.!?:])\s+(?=[A-ZÇĞİÖŞÜ«\"'\-•*\d\[(])")


# Köşeli parantezsiz atıf kalıntıları: "K1K3", "K2 ve K4", "kaynak K1"
# Model bazen biçimi bozuyor; bunlar sayı denetiminde 1, 3 gibi sahte
# rakamlar üretmesin diye ayrıca temizlenir.
_BARE_CITATION_RE = re.compile(r"\bK\s?\d{1,2}\b")


def strip_citations(text: str) -> str:
    out = CITATION_RE.sub(" ", text or "")
    return _BARE_CITATION_RE.sub(" ", out)


def normalize_number(token: str) -> str:
    """
    '1.490,00' -> '1490'      (binlik ayracı silinir, sondaki sıfırlar atılır)
    '1.490,50' -> '1490,5'
    '170'      -> '170'
    '9.2'      -> '9.2'       (madde numarası: binlik kalıbına uymaz, korunur)
    """
    s = (token or "").strip().replace(" ", "")
    if not s:
        return ""
    if "," in s:
        head, dec = s.rsplit(",", 1)
        head = head.replace(".", "")
        dec = dec.rstrip("0")
        return f"{head},{dec}" if dec else head
    # Virgülsüz: yalnızca 1.234.567 kalıbındaysa binlik ayracıdır
    if re.fullmatch(r"\d{1,3}(?:\.\d{3})+", s):
        return s.replace(".", "")
    return s


def numbers_in(text: str) -> List[str]:
    return [m.group(0) for m in _NUMBER_RE.finditer(text or "")]


def context_number_set(chunks: Sequence[str]) -> Set[str]:
    """Kaynak metinlerdeki tüm sayıların ham ve normalize edilmiş biçimleri."""
    out: Set[str] = set()
    for text in chunks:
        for raw in numbers_in(text):
            out.add(raw)
            out.add(normalize_number(raw))
            # '1.490,00' -> '1490,00' ara biçimi de kabul edilsin
            out.add(raw.replace(".", ""))
    return out


def split_sentences(text: str) -> List[str]:
    """Yanıtı cümlelere böler. Madde imleri ayrı cümle sayılır."""
    parts: List[str] = []
    for line in (text or "").split("\n"):
        line = line.strip()
        if not line:
            continue
        # Liste maddesi ise tek başına bir "cümle" kabul edilir
        if re.match(r"^(?:[-*•]|\d+[.)])\s+", line):
            parts.append(line)
            continue
        parts.extend(s.strip() for s in _SENT_SPLIT.split(line) if s.strip())
    return parts


# "Meta" cümleler: kaynağın kendisinden bahseden ama HİÇBİR BİLGİ taşımayan
# cümleler. Örnek: "Bu bilgiler [K1][K3] kaynaklarından elde edilmiştir."
#
# Bunlar atıf içerdikleri için denetimden geçiyor; diğer cümleler atıfsız
# oldukları için silinince geriye YALNIZCA bu cümle kalabiliyor. Sonuç:
# geçerli görünen ama bomboş bir yanıt. Gerçek bir testte tam olarak bu oldu.
# NOT: Türkçe ünsüz yumuşaması yüzünden "kaynak" sözcüğü çekimlendiğinde
# "kaynağından", "kaynağı" olur. Desenler "kayna[kğ]" biçiminde yazılmazsa
# bu biçimler kaçar — gerçek bir testte tam olarak bu oldu.
_META_RE = re.compile(
    r"bu bilgi(?:ler)?\b[^.]*\b(kayna[kğ]|belge)"
    r"|kayna[kğ][a-zçğıöşü]*[ndan]* (?:elde edil|al[ıi]nm)"
    r"|yukar[ıi]daki (?:kayna[kğ]|belge)"
    r"|belirtilen kayna[kğ]"
    r"|kaynaklarda (?:yer alan|belirtildi)",
    re.IGNORECASE,
)


def is_meta(sentence: str) -> bool:
    """Cümle bilgi taşıyor mu, yoksa yalnızca kaynaktan mı bahsediyor?"""
    from .bm25 import content_terms, tr_lower
    s = strip_citations(sentence).strip()
    if not s:
        return True
    if _META_RE.search(tr_lower(s)):
        return True
    # Sayı içermeyen ve neredeyse hiç içerik kelimesi olmayan cümleler.
    # Sayı varsa bilgi taşıyor demektir ("32 aydır [K1]." meta değildir).
    #
    # EŞİK BİLİNÇLİ OLARAK ÇOK DÜŞÜK: "Bu iş için avans verilmeyecektir."
    # cümlesinde "bu" ve "için" durak kelimesi olduğu için geriye 3 içerik
    # kelimesi kalıyor. Daha yüksek bir eşik, kısa ama tamamen doğru
    # cevapları siliyordu (gerçek testte oldu). Yalnızca gerçekten içi boş
    # cümleler ("Evet.", "Belirtilmiştir.") elenmelidir.
    if _NUMBER_RE.search(s):
        return False
    return len(content_terms(s)) < 2


def is_factual(sentence: str, min_len: int = 40) -> bool:
    """
    Cümle olgusal bilgi taşıyor mu? (atıf gerektirir)
    Sayı içeren her cümle olgusaldır; uzun cümleler de öyle sayılır.
    Kısa bağlaç/geçiş cümleleri muaftır.
    """
    s = strip_citations(sentence).strip()
    if not s:
        return False
    if _NUMBER_RE.search(s):
        return True
    return len(s) >= min_len


def strip_refusal_sentences(answer: str, refusal: str) -> Tuple[str, int]:
    """
    Yanıttan ret cümlesini ayıklar ve geri kalanı döndürür.

    NEDEN: 7B model sık sık DOĞRU cevabı yazıp arkasına ezbere ret cümlesini
    de ekliyor:
        "FL-350 adedi 2, garanti 36 aydır [K1]. Bu konu hakkında yüklenen
         belgelerde bilgi bulunmamaktadır."
    Bu bir ret değil, biçim kusurudur. "Yanıt ret cümlesi içeriyorsa ret
    say" kuralı bu doğru cevapları çöpe atıyordu.

    -> (kalan metin, atılan ret cümlesi sayısı)
    """
    core = strip_citations(refusal).strip().strip(".").strip()
    if not core or not answer:
        return answer or "", 0

    # CÜMLE DEĞİL İFADE bazında siliyoruz. Cümle bazlı silme, atıf araya
    # girdiğinde ("... aydır. [K1] Bu konu hakkında ...") tüm metni tek
    # cümle sayıp doğru cevabı da götürüyordu. İfade bazlı silmede atıflar
    # yerinde kalır.
    words = [re.escape(w) for w in core.split() if w]
    sep = r"\s*(?:\[K\s*\d+\]\s*)*"          # kelimeler arasına atıf girebilir
    pattern = re.compile(
        r"(?:bu nedenle[,\s]*|ancak[,\s]*|fakat[,\s]*)?" + sep.join(words) + r"\s*\.?",
        re.IGNORECASE,
    )

    new_text, n = pattern.subn(" ", answer)
    if not n:
        return answer, 0

    # Geriye kalan artıkları temizle: " ." , çift boşluk, başıboş virgül
    new_text = re.sub(r"\s+([.,;])", r"\1", new_text)
    new_text = re.sub(r"(?<![\w\]])[.,;]\s*", " ", new_text)
    new_text = re.sub(r"[ \t]{2,}", " ", new_text)
    new_text = re.sub(r"\n{3,}", "\n\n", new_text)
    return new_text.strip(), n


# Kapanış/bağlaç cümleleri: "Bu nedenle ...", "Sonuç olarak ...", "Bu, ...".
# Model bilgiyi atıfsız yazıp atfı BU cümleye koyduğunda, atıfsız bilgi
# cümlesi ayıklanıyor ve geriye içi boş bir kapanış kalıyordu.
_CONNECTIVE_RE = re.compile(
    r"^\s*(?:\[K\s*\d+\]\s*)*"
    r"(bu nedenle|bu sebeple|dolay[ıi]s[ıi]yla|sonu[cç] olarak|[oö]zetle"
    r"|bu [sş]ekilde|b[oö]ylece|buna g[oö]re|bu bilgi|bu veriler|bu de[ğg]erler"
    r"|yani|k[ıi]sacas[ıi]|bu,|bu\b)",
    re.IGNORECASE,
)


# Madde/fıkra referansı: "13.2", "MADDE 9.1". Bunlar olgu değil, konum
# bilgisidir; kapanış cümlesinde geçmeleri bilgi taşıdıkları anlamına gelmez.
_CLAUSE_REF_RE = re.compile(r"^\d{1,2}\.\d{1,2}$")


def _is_citation_carrier(sentence: str, prev_text: str) -> bool:
    """
    Cümle "atıf taşıyıcısı" mı? Yani atfı var ama YENİ BİR OLGU getirmiyor mu?

    Böyle bir cümlenin atıfları, kendinden önceki atıfsız bilgi cümlelerine
    devredilebilir; devir güvenlidir çünkü cümle zaten bilgi taşımıyordur.

    GÜVENLİK SINIRI — bu fonksiyonun yapabileceği en tehlikeli hata, GERÇEK
    BİLGİ taşıyan bir kapanış cümlesini taşıyıcı sanıp silmektir:

        "Gizlilik ihlali cezası uygulanır [K1]. Bu ceza sözleşme bedelinin
         yüzde ikisidir [K1]."          ← ikinci cümle SİLİNEMEZ, cevap odur

    ...ve uydurma sayı içeren bir kapanışı onaylamaktır:

        "... otuziki aydır [K2]. Bu nedenle toplam iş süresi 30 aydır [K2]."

    Her iki hatayı da tek ölçüt engeller: kapanış cümlesindeki sayılar YA
    kendinden önceki cümlelerde zaten geçmeli (yani yeni bir şey söylemiyor)
    YA DA madde referansı olmalı. Aksi hâlde cümle bilgi taşıyor demektir;
    taşıyıcı sayılmaz, normal cümle olarak kalır ve sayı denetimine girer.

    "Kaynaklarda geçiyor mu?" ölçütü BİLEREK kullanılmadı: kaynakta geçen ama
    önceki cümlelerde geçmeyen bir sayı, yeni bilgidir ve silinmemelidir.
    """
    if not CITATION_RE.search(sentence):
        return False
    if is_meta(sentence):
        return True
    if not _CONNECTIVE_RE.match(sentence.strip()):
        return False

    onceki = {normalize_number(n) for n in numbers_in(strip_citations(prev_text))}
    for raw in numbers_in(strip_citations(sentence)):
        if _CLAUSE_REF_RE.match(raw):
            continue                      # madde referansı: olgu değil
        if normalize_number(raw) in onceki:
            continue                      # zaten söylenmiş: tekrar
        return False                      # yeni sayı -> bilgi taşıyor
    return True


def _distribute_citations(sents: List[str], tag: str) -> List[str]:
    """Atıfsız cümlelerin sonuna verilen atıf etiketini ekler."""
    body: List[str] = []
    for s in sents:
        if CITATION_RE.search(s):
            body.append(s)
        else:
            # Atıf, cümle sonu noktalamasının ÖNÜNE eklenir. Sonrasına
            # eklenirse ("... aydır. [K1]") bir sonraki cümle bölme adımında
            # yeniden ayrı cümle sayılıyor ve devir işlemi boşa gidiyor.
            m = re.match(r"^(.*?)([.!?:]*)\s*$", s.rstrip(), re.DOTALL)
            govde, nokta = (m.group(1), m.group(2)) if m else (s.rstrip(), "")
            body.append(f"{govde.rstrip()} {tag}{nokta}")
    return body


def _inherit_trailing_citations(answer: str) -> str:
    """
    Kapanış cümlesindeki atıfları, kendinden önceki atıfsız bilgi cümlelerine
    dağıtır ve kapanış cümlesini kaldırır.

    Girdi : "145,00 TL yemek bedeli ödenir. Bu bilgi [K2] kaynağından alınmıştır."
    Çıktı : "145,00 TL yemek bedeli ödenir. [K2]"

    İKİ GEÇİŞ YAPILIR:
      1) Satır içi — kapanış cümlesi bilgi cümlesiyle aynı satırdaysa.
      2) Satırlar arası — model kapanışı ayrı satıra yazdığında. Gerçek
         testte model şunu üretti:
             "06/2024 hakediş 1.548.750,00 TL, personel 38'dir.\\n
              [K4][K3] Bu nedenle tablodaki değerler bu şekilde geçerlidir."
         Yalnızca satır içi geçiş yapılırsa bu durum kaçar ve doğru cevap
         ayıklanıp geriye içi boş kapanış cümlesi kalır.
    """
    lines = (answer or "").split("\n")

    # ---- 1) Satır içi geçiş
    out_lines: List[str] = []
    for line in lines:
        if not line.strip():
            out_lines.append(line)
            continue
        sents = split_sentences(line)
        if len(sents) < 2 or not _is_citation_carrier(sents[-1], " ".join(sents[:-1])):
            out_lines.append(line)
            continue
        cites = CITATION_RE.findall(sents[-1])
        tag = "".join(f"[K{c}]" for c in dict.fromkeys(cites))
        out_lines.append(" ".join(_distribute_citations(sents[:-1], tag)))

    # ---- 2) Satırlar arası geçiş
    dolu = [i for i, l in enumerate(out_lines) if l.strip()]
    if len(dolu) >= 2:
        son = dolu[-1]
        sents_son = split_sentences(out_lines[son])
        onceki_metin = " ".join(out_lines[i] for i in dolu[:-1])
        if len(sents_son) == 1 and _is_citation_carrier(sents_son[0], onceki_metin):
            # Önceki satırlarda atıfsız bilgi cümlesi var mı?
            eksik = any(
                not CITATION_RE.search(s)
                for i in dolu[:-1]
                for s in split_sentences(out_lines[i])
            )
            if eksik:
                cites = CITATION_RE.findall(sents_son[0])
                tag = "".join(f"[K{c}]" for c in dict.fromkeys(cites))
                yeni: List[str] = []
                for i, l in enumerate(out_lines):
                    if i == son:
                        continue
                    if not l.strip():
                        yeni.append(l)
                        continue
                    yeni.append(" ".join(
                        _distribute_citations(split_sentences(l), tag)))
                out_lines = yeni

    return "\n".join(out_lines)


def strip_question_echo(answer: str, question: str) -> str:
    """
    Modelin yanıta soruyu aynen kopyalamasını temizler.

    Gerçek testte model şunları üretti:
        "Kaç adet Depo Görevlisi çalıştırılacaktır [K1]?"
        "Forklift Operatörü ... ödenecektir? Bu konu hakkında ... bulunmamaktadır."

    Birincisi atıf taşıdığı için geçerli bir yanıt sanılıyordu; oysa hiçbir
    bilgi vermiyor. Soruyu geri yazmak yanıt değildir; ayıklanır. Geriye bir
    şey kalmazsa yanıt reddedilir — bu, boş bir cevabı doğruymuş gibi
    göstermekten dürüsttür.

    ÖLÇÜT: "yeni içerik terimi var mı?" — ORAN DEĞİL.
    İlk sürümde kelime örtüşme oranı (%85) kullanıldı ve bu, sistemin en
    kötü hatalarından birini üretti. Türkçede iyi bir cevap zaten soruyu
    tekrarlayıp boşluğu doldurur:

        soru  : "... asgari ücretin yüzde KAÇ fazlası ödenecektir?"
        cevap : "... asgari ücretin yüzde 55 fazlası ödenecektir."   %89 örtüşme

    Tek fark "kaç" yerine "55" — yani cevabın ta kendisi. Oran ölçütü bu
    doğru cevabı yankı sanıp sildi. Artık soruda geçmeyen TEK bir içerik
    terimi bile varsa cümle yankı sayılmaz.

    Yön tercihi bilinçlidir: bir yankıyı kaçırmak zayıf bir yanıt üretir,
    doğru cevabı silmek ise yanlış bir ret üretir. İkincisi daha pahalıdır.
    """
    from .bm25 import content_terms
    if not answer or not question:
        return answer or ""

    q_terim = set(content_terms(strip_citations(question)))
    if len(q_terim) < 3:
        return answer

    sents = split_sentences(answer)
    if not sents:
        return answer

    ilk = sents[0]
    f_terim = content_terms(strip_citations(ilk))
    if len(f_terim) < 3:
        return answer

    # TAM KELİME karşılaştırması — kök/ek ayıklaması YAPILMAZ.
    #
    # İlk sürüm ilk 6 harfi kök sayıyordu ("çalıştırılacaktır" ≈
    # "çalıştırılacak"). Bu, Türkçede OLUMSUZLUK EKİNİ görünmez kılıyor:
    #
    #     soru  : "avans verilecek midir?"      -> "verilecek"        -> "verile"
    #     cevap : "avans verilemeyecektir"      -> "verilemeyecektir" -> "verile"
    #
    # İki kelime zıt anlamlı ama aynı köke iniyor. Ayıklayıcı "yeni terim yok"
    # deyip DOĞRU cevabı yankı sanıp sildi (gerçek ölçümde oldu).
    #
    # Tam kelime karşılaştırmasında "verilemeyecektir" soruda geçmez, cümle
    # korunur. Bedeli: küçük bir çekim farkı olan gerçek yankılar artık
    # yakalanmaz. Bu bilinçli bir tercih — yankıyı kaçırmak zayıf bir yanıt
    # üretir, doğru cevabı silmek yanlış bir ret üretir; ikincisi pahalıdır.
    if any(t not in q_terim for t in f_terim):
        return answer

    kalan = answer[answer.find(ilk) + len(ilk):].strip()
    return kalan


# ==========================================================================
# METİN TARAFI DOĞRULAMA
# ==========================================================================
#
# NEDEN GEREKLİ?
# Yukarıdaki sayı denetimi, yanıttaki her sayının kaynakta geçmesini şart
# koşar. Güçlü bir denetimdir ama YALNIZCA SAYI GÖRÜRSE çalışır. Sayısız bir
# belgede tüm katman boşta kalır. Yönetmelik ölçümünde tam olarak bu oldu:
#
#     kaynak : "...bağlı bulunduğu en yakın üst yöneticiyi ifade eder."
#     model  : "...bağlı bulunduğu en yakın üst yındıktıyı ifade eder. [K1][K2]"
#
# Yanıt atıflıydı, uydurma sayı içermiyordu, cümle yapısı düzgündü — altı
# katmanın hiçbiri yakalamadı. Oysa "yındıktıyı" kaynakta hiç geçmiyor.
#
# ÖLÇÜT YÖNÜ — strip_question_echo'nun TERSİ:
# Burada gevşek eşleşme GÜVENLİ taraftır. Gevşeklik bir uydurmayı kaçırmakla
# sonuçlanır (yanıt olduğu gibi kalır); katılık ise DOĞRU bir cevabı yanlışlıkla
# işaretlemekle sonuçlanır. Bu yüzden Türkçe çekim eklerine karşı bilinçli
# olarak cömert davranılır. Aynı gerekçeyle "verilecek ≈ verilemeyecektir"
# çakışması burada zarar vermez: olsa olsa bir kaçırma üretir.

_WORD_RE = re.compile(r"[^\W\d_]+", re.UNICODE)

# EŞLEŞME ÖLÇÜTÜ: ortak önek (LCP) uzunluğu.
#
# Sabit uzunlukta önek (bm25'teki 6 harf) BURADA ÇALIŞMAZ. Türkçe fiil
# kökleri üç harfe kadar inebilir ve çatı/olumsuzluk ekleri kökün hemen
# ardına gelir:
#
#     kaynak "kesme"    ↔  model "kesilmesi"    ortak önek: "kes"   (3)
#     kaynak "verilir"  ↔  model "verilmez"     ortak önek: "veril" (5)
#     kaynak "dolduran" ↔  model "doldurmayan"  ortak önek: "doldur"(6)
#
# 6 harflik sabit önek ilk ikisini kaçırır ve DOĞRU cevabı işaretler. Bu
# yüzden ölçüt orantısal: ortak önek, kısa olan kelimenin en az %60'ını
# kaplamalı ve en az 3 harf olmalı.
#
#     "yönetici" ↔ "yındıktıyı"  ortak önek: "y" (1)  → işaretlenir ✔
#
# Oranın paydası KISA olan kelimedir; aksi hâlde kaynaktaki "ceza",
# modeldeki "cezalandırma" ile eşleşemezdi.
_MIN_LCP = 3
_LCP_RATIO = 0.6

# Bu uzunluğun altındaki kelimeler denetlenmez. Kısa kelimelerde meşru
# yeniden ifade etme olasılığı yüksek, bozulmayı ayırt etme gücü düşüktür.
_MIN_CHECK_LEN = 6

# Modelin KAYNAKTAN BAĞIMSIZ olarak üretmesi meşru olan kelimeler: bağlaçlar,
# yüklem kalıpları, kaynağa gönderme yapan ifadeler.
#
# BU LİSTE EKSİKTİR ve eksik olduğu bilinerek yazılmıştır. Tam bir Türkçe
# sözlük olmadan hangi kelimenin "modelin kendi üslubu" olduğunu kestirmek
# mümkün değil. Bu yüzden katman ÖNCE gölge modda ölçülür; listenin yeterli
# olup olmadığına yanlış alarm oranına bakılarak karar verilir.
_DISCOURSE_WORDS = {
    # kaynağa gönderme
    "kaynak", "kaynakta", "kaynaklarda", "kaynaklardan",
    "kaynağında", "kaynağından", "belgede", "belgelerde", "belgelerden",
    "yüklenen", "belirtilen", "belirtilmiş", "belirtilmiştir",
    "belirtilmektedir", "belirtilmemiştir", "geçmektedir", "yazmaktadır",
    # varlık/yokluk kalıpları
    "bulunmamaktadır", "bulunmaktadır", "bulunmuyor", "bulunmakta",
    "mevcuttur", "mevcut", "değildir", "değil", "yoktur",
    # bağlaç ve geçişler
    "dolayısıyla", "nedenle", "sebeple", "sonuç", "sonucunda", "özetle",
    "kısacası", "böylece", "ayrıca", "buna", "bunun", "şekilde", "şöyledir",
    "durumda", "durumunda", "halinde", "hâlinde", "ancak", "dolayı",
    # soru/yanıt üstdili
    "soru", "sorunun", "soruda", "sorulan", "cevap", "cevabı", "cevaben",
    "yanıt", "yanıtı", "bilgi", "bilgiler", "bilgisi", "bilgiye",
    # çok yaygın yüklemler
    "ifade", "eder", "edilir", "edilmektedir", "olarak", "olan", "olduğu",
    "göre", "ilgili", "hakkında", "yönelik", "üzere", "gerekir",
    "gerekmektedir", "yapılır", "yapılmaktadır", "verilir", "verilmektedir",

    # --------------------------------------------------------------------
    # GELİŞTİRME SETİ ÖLÇÜMÜNDEN EKLENENLER
    #
    # İlk gölge ölçümde depo setinde 2 yanlış alarm çıktı; işaretlenen dört
    # kelimenin dördü de içerik değil DİLBİLGİSİ kelimesiydi:
    #     Q15 "arasında", "olmalıdır"      Q16 "aralığında", "tarafından"
    #
    # Bunlar geliştirme setinden görülerek eklendi — yani aşağıdaki liste
    # ölçüme göre ayarlanmıştır ve bundan sonraki yanlış alarm oranı
    # İYİMSERDİR. Katman "block" kipine alınmadan önce bu listeyi hiç
    # görmemiş bir sette doğrulanması gerekir (bkz. YAPILACAKLAR → C).
    #
    # SINIR: buraya yalnızca EDAT, ÇEKİM ve YÜKLEM kalıpları girer. İçerik
    # taşıyan isimler (unvan, tutar birimi, ekipman adı) BİLEREK dışarıda
    # bırakılmıştır; onları beyaz listeye almak katmanın varlık sebebini
    # ortadan kaldırır.
    "arasında", "arasındaki", "aralığında", "aralığındadır", "tarafından",
    "içinde", "içerisinde", "üzerinden", "boyunca", "süresince",
    "kapsamındaki", "itibaren", "doğrultusunda", "karşılığında",
    "olmalıdır", "olmaktadır", "olabilir", "olmuştur", "olacaktır",
    "edilmiştir", "edilmelidir", "yapılmalıdır", "sağlanmalıdır",
    "belirlenmiştir", "belirlenir", "uygulanır", "uygulanmaktadır",
    "sayılır", "sayılmaz", "geçerlidir", "zorunludur",
}


def _tokens(text: str) -> List[str]:
    """Sayısız, Türkçe-doğru küçültülmüş sözcükler."""
    from .bm25 import tr_lower
    return _WORD_RE.findall(tr_lower(text or ""))


def _support_index(texts: Sequence[str]) -> Dict[str, List[str]]:
    """
    Kaynak kelimelerini ilk 3 harflerine göre kovalara ayırır.

    Ortak önek en az 3 harf olmak zorunda olduğu için, bir kelimeyle
    eşleşebilecek tüm adaylar zorunlu olarak aynı kovadadır. Böylece her
    kelime için tüm kaynak sözlüğünü taramak gerekmez.
    """
    buckets: Dict[str, List[str]] = {}
    seen: Set[str] = set()
    for t in texts:
        for w in _tokens(t):
            if len(w) < _MIN_LCP or w in seen:
                continue
            seen.add(w)
            buckets.setdefault(w[:_MIN_LCP], []).append(w)
    return buckets


def _lcp(a: str, b: str) -> int:
    n = min(len(a), len(b))
    i = 0
    while i < n and a[i] == b[i]:
        i += 1
    return i


def _is_supported(word: str, buckets: Dict[str, List[str]]) -> bool:
    """Kaynakta bu kelimenin çekimli bir akrabası var mı?"""
    for cand in buckets.get(word[:_MIN_LCP], ()):
        ortak = _lcp(word, cand)
        if ortak >= _MIN_LCP and ortak / min(len(word), len(cand)) >= _LCP_RATIO:
            return True
    return False


def unsupported_terms(answer: str,
                      chunk_texts: Sequence[str],
                      question: str = "",
                      min_len: int = _MIN_CHECK_LEN) -> List[str]:
    """
    Yanıtta geçip kaynakların HİÇBİRİNDE karşılığı olmayan içerik kelimeleri.

    Sorunun kelimeleri destekleyici sayılır: model soruyu tekrarlamakta
    serbesttir ve soru metni kullanıcıdan gelir, uydurma değildir.

    -> yanıttaki görülme sırasına göre, yinelenmeden
    """
    from .bm25 import STOPWORDS
    body = strip_citations(answer or "")
    if not body.strip():
        return []

    buckets = _support_index(list(chunk_texts) + [question or ""])

    out: List[str] = []
    seen: Set[str] = set()
    for w in _tokens(body):
        if len(w) < min_len or w in seen:
            continue
        if w in STOPWORDS or w in _DISCOURSE_WORDS:
            continue
        if _is_supported(w, buckets):
            continue
        seen.add(w)
        out.append(w)
    return out


def check(answer: str,
          chunk_texts: Sequence[str],
          question: str = "",
          require_sentence_citation: bool = True,
          sentence_action: str = "strip",
          verify_numbers: bool = True,
          verify_text: str = "off",
          min_sentence_len: int = 40) -> Tuple[bool, str, Dict[str, List[str]], str]:
    """
    Yanıtı denetler ve gerekirse temizler.

    -> (geçerli_mi, gerekçe, ayrıntılar, temizlenmiş_yanıt)

    SIRALAMA ÖNEMLİ:
      1) Atıfsız olgusal cümleler ÇIKARILIR (sentence_action="strip").
         Tüm yanıtı çöpe atmak yerine sorunlu cümleyi atmak, hem daha az
         yanlış ret üretir hem de doğru bilgiyi korur. Gerçek örnekte
         "otuziki aydır [K2]" cümlesi kalır, uydurma "toplam 30 aydır"
         cümlesi silinir.
      2) Sayı denetimi KALAN metin üzerinde çalışır. Böylece zaten
         çıkarılmış bir cümledeki sayı gereksiz yere ret sebebi olmaz.
      3) Geriye atıflı hiçbir bilgi kalmadıysa yanıt reddedilir.
    """
    details: Dict[str, List[str]] = {"uncited": [], "bad_numbers": [],
                                     "removed": [], "unsupported": []}
    if not answer or not answer.strip():
        return False, "Model boş yanıt üretti.", details, ""

    # Kaynaklardaki sayı kümesi hem atıf devri kapısında hem de sayı
    # denetiminde kullanılır; bir kez hesaplanır.
    allowed = context_number_set(chunk_texts)
    allowed |= context_number_set([question or ""])

    # ---------- 0a) SORU YANKISI
    # Model bazen soruyu aynen geri yazıyor. Atıf da eklerse bu, bilgi
    # taşımayan ama geçerli görünen bir yanıt oluyor.
    onceki = answer
    answer = strip_question_echo(answer, question)
    if answer != onceki:
        details["removed"].append("[soru yankısı]")
    if not answer.strip():
        return False, "Model yalnızca soruyu tekrarladı, yanıt üretmedi.", details, ""

    # ---------- 0b) ATIF DEVRİ
    # Model sık sık bilgiyi atıfsız yazıp atfı sona ayrı bir cümleye koyuyor:
    #     "... 145,00 TL yemek bedeli ödenir. Bu bilgi [K2] kaynağından alınmıştır."
    # Bu, doğru bir cevaptır; sadece biçimi yanlıştır. Kapanış cümlesindeki
    # atıflar kendinden önceki atıfsız cümlelere devredilir, kapanış cümlesi
    # atılır. Böylece doğru cevap korunur.
    #
    # ÖNEMLİ: Devir YALNIZCA kapanış cümlesi "meta" ise (bilgi taşımıyorsa)
    # yapılır. Aksi hâlde uydurma bir özet cümlesi de atıf kapıp denetimden
    # geçerdi — asıl engellemek istediğimiz durum tam olarak buydu.
    answer = _inherit_trailing_citations(answer)

    # ---------- 1) Atıfsız olgusal cümleler
    kept_lines: List[str] = []
    for line in answer.split("\n"):
        if not line.strip():
            kept_lines.append(line)
            continue
        kept_parts: List[str] = []
        for s in split_sentences(line):
            if (require_sentence_citation
                    and is_factual(s, min_sentence_len)
                    and not CITATION_RE.search(s)):
                details["uncited"].append(s.strip()[:160])
                if sentence_action == "strip":
                    details["removed"].append(s.strip()[:160])
                    continue
            kept_parts.append(s)
        if kept_parts:
            kept_lines.append(" ".join(kept_parts))

    cleaned = "\n".join(kept_lines).strip()
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)

    if sentence_action != "strip" and details["uncited"]:
        return (False,
                f"Atıfsız bilgi cümlesi ({len(details['uncited'])} adet). "
                f"İlki: \"{details['uncited'][0]}\"",
                details, cleaned)

    # Temizlik sonrası ortada bilgi kalmadıysa
    if not cleaned or not CITATION_RE.search(cleaned):
        return (False,
                "Yanıttaki bilgi cümlelerinin hiçbiri kaynağa dayandırılmamış.",
                details, cleaned)

    # Geriye yalnızca "meta" cümleler kaldıysa (atıfı var ama bilgi yok),
    # bu bir yanıt değildir. Sessizce boş bir cevap göstermek yerine reddet.
    informative = [s for s in split_sentences(cleaned) if not is_meta(s)]
    if not informative:
        details["removed"].extend(split_sentences(cleaned))
        return (False,
                "Model bilgi içeren cümle üretmedi; yalnızca kaynağa atıfta "
                "bulunan boş bir cümle kaldı.",
                details, "")
    # Meta cümleler yanıttan da temizlenir (gereksiz gürültü)
    if len(informative) < len(split_sentences(cleaned)):
        cleaned = " ".join(informative)

    # ---------- 2) Sayı doğrulama (kalan metin üzerinde)
    if verify_numbers:
        body = strip_citations(cleaned)
        for raw in numbers_in(body):
            if (raw in allowed
                    or normalize_number(raw) in allowed
                    or raw.replace(".", "") in allowed):
                continue
            details["bad_numbers"].append(raw)

        if details["bad_numbers"]:
            uniq = sorted(set(details["bad_numbers"]))
            return (False,
                    f"Kaynaklarda geçmeyen sayı üretildi: {', '.join(uniq[:6])}"
                    + (" ..." if len(uniq) > 6 else ""),
                    details, cleaned)

    # ---------- 3) Metin doğrulama (sayı denetiminin metin tarafındaki eşi)
    #
    # ÜÇ KİPTE ÇALIŞIR:
    #   "off"   — hiç çalışmaz (varsayılan)
    #   "warn"  — kelimeleri details'e yazar, yanıtı REDDETMEZ  ← ölçüm kipi
    #   "block" — reddeder
    #
    # Varsayılanın "off" olması bilinçlidir. Bu katmanın yanlış alarm oranı
    # HENÜZ ÖLÇÜLMEDİ. Ölçmeden blokçu yapmak, bu projede üç kez yaşanan
    # "guardrail doğru cevabı sildi" hatasının dördüncüsünü davet ederdi.
    if verify_text in ("warn", "block"):
        details["unsupported"] = unsupported_terms(cleaned, chunk_texts, question)
        if verify_text == "block" and details["unsupported"]:
            uniq = details["unsupported"][:6]
            return (False,
                    f"Kaynaklarda karşılığı olmayan kelime üretildi: "
                    f"{', '.join(uniq)}"
                    + (" ..." if len(details["unsupported"]) > 6 else ""),
                    details, cleaned)

    return True, "", details, cleaned
