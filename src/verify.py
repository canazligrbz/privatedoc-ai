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


def _inherit_trailing_citations(answer: str) -> str:
    """
    Paragraf sonundaki "kaynak belirten" cümlenin atıflarını, o paragraftaki
    atıfsız bilgi cümlelerine dağıtır ve kapanış cümlesini kaldırır.

    Girdi : "145,00 TL yemek bedeli ödenir. Bu bilgi [K2] kaynağından alınmıştır."
    Çıktı : "145,00 TL yemek bedeli ödenir. [K2]"
    """
    out_lines: List[str] = []
    for line in (answer or "").split("\n"):
        if not line.strip():
            out_lines.append(line)
            continue

        sents = split_sentences(line)
        if len(sents) < 2:
            out_lines.append(line)
            continue

        last = sents[-1]
        cites = CITATION_RE.findall(last)
        # Kapanış cümlesi bilgi taşımıyor ve atıf içeriyorsa devret
        if cites and is_meta(last):
            tag = "".join(f"[K{c}]" for c in dict.fromkeys(cites))
            body = []
            for s in sents[:-1]:
                if CITATION_RE.search(s):
                    body.append(s)
                else:
                    # Atıf, cümle sonu noktalamasının ÖNÜNE eklenir.
                    # Sonrasına eklenirse ("... aydır. [K1]") bir sonraki
                    # cümle bölme adımında yeniden ayrı cümle sayılıyor ve
                    # devir işlemi boşa gidiyor.
                    m = re.match(r"^(.*?)([.!?:]*)\s*$", s.rstrip(), re.DOTALL)
                    govde, nokta = (m.group(1), m.group(2)) if m else (s.rstrip(), "")
                    body.append(f"{govde.rstrip()} {tag}{nokta}")
            out_lines.append(" ".join(body))
        else:
            out_lines.append(line)
    return "\n".join(out_lines)


def check(answer: str,
          chunk_texts: Sequence[str],
          question: str = "",
          require_sentence_citation: bool = True,
          sentence_action: str = "strip",
          verify_numbers: bool = True,
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
    details: Dict[str, List[str]] = {"uncited": [], "bad_numbers": [], "removed": []}
    if not answer or not answer.strip():
        return False, "Model boş yanıt üretti.", details, ""

    # ---------- 0) ATIF DEVRİ
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
        allowed = context_number_set(chunk_texts)
        # Kullanıcının sorusunda geçen sayılar meşrudur (soru tekrarlanabilir)
        allowed |= context_number_set([question or ""])
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

    return True, "", details, cleaned
