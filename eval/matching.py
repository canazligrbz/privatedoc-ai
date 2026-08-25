"""
BEKLENTİ EŞLEŞTİRME — değerlendirme ölçütü
==========================================

`run_eval.py` bir yanıtın beklenen bilgiyi içerip içermediğine burada karar
verir. Ayrı bir modül olmasının sebebi, ölçütün LLM/indeks yüklemeden
sınanabilmesidir (bkz. eval/test_verify.py).

NEDEN DÜZ ALT DİZİ ARAMASI YETMİYOR?
Kısa sayısal beklentilerde ölçümü şişiriyordu:

    "Kesin teminat oranı nedir?"   beklenen: "6"
        model "%16'dır"  -> "16" içinde "6" var   -> GEÇER (yanlış)
        model "36 ay"    -> "36" içinde "6" var   -> GEÇER (yanlış)
    "Soğuk oda sıcaklığı?"         beklenen: "2", "8"
        neredeyse her yanıt geçer

İki test setinde 23 kısa sayısal beklenti vardı. Bu, yasaklı değer
listeleriyle kapatılamaz: yanlış olabilecek HER sayıyı önceden saymak
gerekirdi. Rakam sınırı hepsini tek kuralla çözer.
"""

from __future__ import annotations

import re

# Tümüyle sayı/noktalama olan beklentiler "sayısal" sayılır: 6 · 1.548.750 ·
# 24:00 · %10 · 2-8
_NUM_LIKE = re.compile(r"^[\d.,:%/-]+$")


def normalize(s: str) -> str:
    """Türkçe duyarlı küçük harfe indirger."""
    return (s or "").lower().replace("i̇", "i").replace("İ", "i")


def value_in(text_n: str, expected: str) -> bool:
    """
    Beklenen değer, NORMALİZE EDİLMİŞ metinde geçiyor mu?

    SINIRLAR BİLİNÇLİ SEÇİLDİ:
      solda  (?<![\\d.,])  "1.500" içindeki "500" eşleşmesin (binlik ayracı)
      sağda  (?!\\d)       "16" içindeki "6" eşleşmesin

    Sağda nokta/virgül YASAKLANMAZ: "1.548.750" beklentisi, yanıtta geçen
    "1.548.750,00" biçimini karşılamalıdır. Aynı şekilde "%6'sı", "2 - 8 °C",
    "18 (onsekiz)" gibi doğal yazımlar da eşleşir.

    METİN beklentileri ("aydın", "servis") ALT DİZİ olarak kalır. Türkçe
    çekim ekleri yüzünden kelime sınırı burada ters teper: "servis"
    beklentisi "servisin" içinde \\b ile eşleşmez ve DOĞRU bir yanıt yanlış
    işaretlenirdi. Yön tercihi bilinçlidir — metin beklentilerinde şişme
    riski, sayısal beklentilerdeki kadar yüksek değildir.
    """
    e = (expected or "").strip()
    if not e:
        return False
    if _NUM_LIKE.match(e):
        return re.search(rf"(?<![\d.,]){re.escape(e)}(?!\d)", text_n) is not None
    return normalize(e) in text_n


# Ayrı bir sözcük olarak gelen olumsuzlama. Türkçede olumsuzluk genellikle
# EK'tir ("yapılamaz") ama ayrı sözcükle de kurulabilir ("yapılabilir değil").
_OLUMSUZ_RE = re.compile(r"\s*(değildir|değil|olmaz|hayır)\b")


def forbidden_in(text_n: str, forbidden: str) -> bool:
    """
    Yasaklı ifade, yanıtta GERÇEKTEN İDDİA EDİLMİŞ olarak geçiyor mu?

    NEDEN value_in() YETMİYOR — ölçülmüş vaka:
    İkinci ayrılmış set, 4. soru. Yasaklı ifade "yapılabilir", modelin
    yanıtı ise şuydu:

        "Süre uzatımı sözlü mutabakatla YAPILABİLİR DEĞİL. Sözlü mutabakat
         geçerli değildir, ek protokol ile yürürlüğe girer."

    Cevap tamamen doğru. Ama "yapılabilir" dizgisi "yapılabilir değil"in
    içinde geçtiği için alt dizi araması tuzağa düşüldü sandı ve DOĞRU cevap
    yanlış işaretlendi.

    Bu, 13 Ağustos'ta düzeltilen şişme hatasının TERSİ. Orada alt dizi
    eşleşmesi yanlış cevabı doğru sayıyordu (beklenen "6", yanıtta "16");
    sayısal beklentilere rakam sınırı kondu ama YASAKLI ifadeler alt dizi
    olarak bırakıldı. Aynı zayıflık öbür yönden vurdu.

    KURAL: eşleşmenin hemen ardından ayrı bir olumsuzlama sözcüğü geliyorsa,
    ifade iddia edilmemiş, aksine reddedilmiş demektir; ihlal sayılmaz.

    Yön tercihi: bu düzeltme yalnızca YANLIŞ ALARMI kaldırır, gerçek bir
    ihlali gizlemez — çünkü tuzağa düşen bir yanıt "evet, yapılabilir" der,
    "yapılabilir değil" demez.
    """
    f = (forbidden or "").strip()
    if not f:
        return False
    if _NUM_LIKE.match(f):
        return value_in(text_n, f)

    kalip = re.escape(normalize(f))
    for m in re.finditer(kalip, text_n):
        if _OLUMSUZ_RE.match(text_n, m.end()):
            continue          # "... yapılabilir değil" -> iddia edilmemiş
        return True
    return False
