"""
BM25 ANAHTAR KELİME ARAMASI (Türkçe uyarlı, saf Python)
=======================================================

NEDEN GEREKLİ?
Vektör (anlamsal) arama, metnin ANLAMINI yakalar ama NADİR ÖZEL İSİMLERİ ve
BİREBİR İFADELERİ ıskalayabilir. Örnek: bir sözleşme klasöründe
"ADL-2024/117 sözleşmesinin KDV hariç toplam bedeli" sorusu
sorulduğunda, tüm sayfalar birbirine anlamca çok benzer olduğu için doğru
sayfa ilk 4'e giremeyebilir.

BM25 tam tersini yapar: kelime eşleşmesine bakar ve nadir kelimelere
(ADL-2024/117, KDV) yüksek ağırlık verir. İkisini birleştirmek (hibrit arama),
tek başına her ikisinden de belirgin şekilde iyidir.

TÜRKÇE UYARLAMASI
  * Doğru küçültme: "İ"→"i", "I"→"ı" (Python'un varsayılan lower() yanlış yapar)
  * Ekleri kabaca budama: 7+ harfli kelimenin ilk 6 harfi ek terim olarak
    indekslenir. Böylece "sözleşmenin" ile "sözleşme" eşleşir. Tam bir
    biçimbilim çözümlemesi değildir ama ek bağımlılık gerektirmez ve
    Türkçe'nin eklemeli yapısında pratikte çok işe yarar.
  * Sayılar korunur: "1.490,00" tek terim olarak indekslenir.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from typing import Dict, Iterable, List, Sequence, Tuple

# Ayırt ediciliği olmayan yaygın kelimeler
STOPWORDS = {
    "ve", "veya", "ile", "için", "gibi", "kadar", "daha", "çok", "az", "bir",
    "bu", "şu", "o", "da", "de", "ki", "mi", "mı", "mu", "mü", "ise", "ancak",
    "ama", "fakat", "yani", "göre", "olarak", "olan", "olup", "olduğu", "eden",
    "her", "hangi", "nedir", "kaç", "kaçtır", "nasıl", "ne", "neden", "nerede",
    "var", "yok", "the", "and", "for", "with", "of", "in", "to", "is", "are",
}

_TOKEN_RE = re.compile(r"\d[\d.,]*\d|\d|[^\W\d_]+", re.UNICODE)

# --------------------------------------------------------------------------
# TERİM DENKLEŞTİRME (Türkçe)
# --------------------------------------------------------------------------
# Gerçek testlerde şu üç eşleşmeme tipi ard arda hataya yol açtı:
#
#   soru "2024'ün 6. ayı"      ↔  tablo "06/2024"      (başta sıfır)
#   soru "Kasım 2024"          ↔  tablo "11/2024"      (ay adı ↔ numara)
#   soru "Üçüncü vardiya"      ↔  tablo "3. Vardiya"   (sayı sözcüğü ↔ rakam)
#
# Belgede "Kasım" kelimesi hiç geçmiyorsa hiçbir kelime araması onu bulamaz.
# Bu yüzden her terimin eşdeğerleri de indekse ve sorguya eklenir.

_MONTHS = {
    "ocak": "1", "şubat": "2", "mart": "3", "nisan": "4", "mayıs": "5",
    "haziran": "6", "temmuz": "7", "ağustos": "8", "eylül": "9",
    "ekim": "10", "kasım": "11", "aralık": "12",
}
_MONTH_BY_NUM = {v: k for k, v in _MONTHS.items()}

# Sayı sözcükleri: hem asıl sayı hem sıra sayısı biçimleri
_NUMBER_WORDS = {
    "bir": "1", "birinci": "1", "iki": "2", "ikinci": "2",
    "üç": "3", "üçüncü": "3", "dört": "4", "dördüncü": "4",
    "beş": "5", "beşinci": "5", "altı": "6", "altıncı": "6",
    "yedi": "7", "yedinci": "7", "sekiz": "8", "sekizinci": "8",
    "dokuz": "9", "dokuzuncu": "9", "on": "10", "onuncu": "10",
    "onbir": "11", "oniki": "12", "onsekiz": "18", "yirmi": "20",
    "yirmidört": "24", "otuz": "30", "otuziki": "32", "otuzaltı": "36",
    "kırk": "40", "kırkbeş": "45", "elli": "50", "altmış": "60",
    "yetmiş": "70", "seksen": "80", "doksan": "90", "yüz": "100",
    "onbinde": "0,0001", "yüzbinde": "0,00001", "binde": "0,001",
}


def _equivalents(token: str) -> List[str]:
    """
    Bir terimin arama sırasında eşdeğer sayılacak diğer biçimleri.

    Yalnızca SÖZCÜK -> SAYI yönü uygulanır. Ters yön (sayı -> ay adı)
    bilerek eklenmemiştir: "3. Vardiya" ifadesindeki 3'ü "mart" saymak
    anlamsız gürültü üretiyordu. Sorgu tarafı sayıya normalleştiği için
    tek yön yeterlidir:
        belge "11/2024"  →  11
        soru  "Kasım"    →  kasım, 11      ✔ eşleşir
    """
    out: List[str] = []

    # "06" -> "6"   (baştaki sıfırlar)
    if token.isdigit() and len(token) > 1 and token[0] == "0":
        out.append(token.lstrip("0") or "0")

    # "kasım" -> "11" ve "011" yerine sıfır dolgulu "11"
    if token in _MONTHS:
        num = _MONTHS[token]
        out.append(num)
        if len(num) == 1:
            out.append("0" + num)

    # "üçüncü" -> "3",  "otuziki" -> "32"
    if token in _NUMBER_WORDS:
        out.append(_NUMBER_WORDS[token])

    # Yinelenenleri at
    seen, uniq = set(), []
    for t in out:
        if t != token and t not in seen:
            seen.add(t)
            uniq.append(t)
    return uniq

_LOWER_MAP = str.maketrans({"I": "ı", "İ": "i", "Ş": "ş", "Ğ": "ğ",
                            "Ü": "ü", "Ö": "ö", "Ç": "ç"})

MIN_PREFIX_LEN = 7      # bu uzunluktan itibaren kök ekle
PREFIX_LEN = 6


def tr_lower(text: str) -> str:
    """Türkçe'ye doğru küçük harf. Python'un lower()'ı 'I'yı 'i' yapar (yanlış)."""
    return text.translate(_LOWER_MAP).lower()


def tokenize(text: str) -> List[str]:
    """Metni BM25 terimlerine ayırır (kelime + kaba kök + eşdeğerler)."""
    out: List[str] = []
    for raw in _TOKEN_RE.findall(tr_lower(text or "")):
        if raw in STOPWORDS:
            continue
        # Tek haneli sayılar korunur ("3. vardiya"); tek harfler atılır
        if len(raw) < 2 and not raw.isdigit():
            continue
        out.append(raw)
        if len(raw) >= MIN_PREFIX_LEN and not raw[0].isdigit():
            out.append(raw[:PREFIX_LEN] + "~")   # kök terimi, "~" ile işaretli
        out.extend(_equivalents(raw))
    return out


def content_terms(text: str) -> List[str]:
    """
    Kök türevleri olmadan, yalnızca gerçek kelimeler (kapsama hesabı için).
    Eşdeğerler burada da eklenir; aksi hâlde "Kasım" içeren bir soru,
    "11/2024" yazan bir parçada %0 kapsam alır ve eşiği geçemez.
    """
    out: List[str] = []
    for t in _TOKEN_RE.findall(tr_lower(text or "")):
        if t in STOPWORDS:
            continue
        if len(t) < 2 and not t.isdigit():
            continue
        out.append(t)
        out.extend(_equivalents(t))
    return out


class BM25:
    """
    Okapi BM25. Bellekte tutulur; 100.000 parçaya kadar sorunsuzdur
    (parça başına ~200 bayt sözlük yükü).
    """

    def __init__(self, corpus: Sequence[str], k1: float = 1.5, b: float = 0.75):
        self.k1 = k1
        self.b = b
        self.n = len(corpus)
        self.doc_terms: List[Counter] = []
        self.doc_len: List[int] = []
        df: Counter = Counter()

        for text in corpus:
            terms = tokenize(text)
            counts = Counter(terms)
            self.doc_terms.append(counts)
            self.doc_len.append(len(terms))
            df.update(counts.keys())

        self.avg_len = (sum(self.doc_len) / self.n) if self.n else 0.0
        # IDF (Robertson-Sparck Jones, negatif olmayacak şekilde)
        self.idf: Dict[str, float] = {
            term: max(0.0, math.log(1.0 + (self.n - freq + 0.5) / (freq + 0.5)))
            for term, freq in df.items()
        }

    def score(self, query: str) -> List[float]:
        q_terms = tokenize(query)
        if not q_terms or not self.n:
            return [0.0] * self.n

        scores = [0.0] * self.n
        for term in set(q_terms):
            idf = self.idf.get(term)
            if not idf:
                continue
            # Kök terimleri (~) tam eşleşmeden daha az güvenilirdir
            weight = 0.6 if term.endswith("~") else 1.0
            for i, counts in enumerate(self.doc_terms):
                tf = counts.get(term, 0)
                if not tf:
                    continue
                dl = self.doc_len[i] or 1
                denom = tf + self.k1 * (1 - self.b + self.b * dl / (self.avg_len or 1))
                scores[i] += weight * idf * (tf * (self.k1 + 1)) / denom
        return scores

    def top_n(self, query: str, n: int) -> List[Tuple[int, float]]:
        scores = self.score(query)
        ranked = sorted(
            (i for i, s in enumerate(scores) if s > 0),
            key=lambda i: scores[i], reverse=True,
        )[:n]
        return [(i, scores[i]) for i in ranked]


def keyword_coverage(query: str, text: str) -> float:
    """
    Sorudaki anlamlı kelimelerin kaçta kaçı metinde geçiyor? (0.0–1.0)

    Guardrail için kullanılır: kosinüs benzerliği düşük olsa bile sorunun
    kelimelerinin çoğu parçada geçiyorsa, parça büyük olasılıkla ilgilidir.
    Özellikle kod/özel isim içeren sorularda ("ADL-2024/117 ... sözleşmesi") kritiktir.
    """
    q = set(content_terms(query))
    if not q:
        return 0.0
    body = set(content_terms(text))
    # Kaba kök eşleşmesi de sayılır
    body_stems = {t[:PREFIX_LEN] for t in body if len(t) >= MIN_PREFIX_LEN}
    hit = 0
    for term in q:
        if term in body:
            hit += 1
        elif len(term) >= MIN_PREFIX_LEN and term[:PREFIX_LEN] in body_stems:
            hit += 1
    return hit / len(q)


def rrf_fuse(rankings: Iterable[Sequence[str]], k: int = 60,
             weights: Sequence[float] | None = None) -> Dict[str, float]:
    """
    Reciprocal Rank Fusion — farklı arama yöntemlerinin SIRALAMALARINI birleştirir.

    Skorları toplamak yerine sıraları kullanmak, iki yöntemin skor ölçekleri
    birbirinden tamamen farklı olduğu için (kosinüs 0–1, BM25 0–30) zorunludur.
    Standart ve gürbüz bir yöntemdir.
    """
    lists = list(rankings)
    w = list(weights) if weights else [1.0] * len(lists)
    fused: Dict[str, float] = {}
    for wi, ids in zip(w, lists):
        for rank, _id in enumerate(ids, start=1):
            fused[_id] = fused.get(_id, 0.0) + wi / (k + rank)
    return fused
