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
