"""
ÖRNEKLEM İSTATİSTİĞİ — oranları belirsizlikleriyle birlikte raporlamak
======================================================================

NEDEN GEREKLİ?
Test setlerimiz 29 soruluk. Bir soru **3,4 puan** ediyor. Bu ölçekte
"%96,6" ile "%93,1" arasındaki fark tam olarak BİR sorudur; virgülden
sonraki basamak, var olmayan bir hassasiyet iddia eder.

Güven aralığı bunu görünür kılar:

    geliştirme  28/29  ->  %96,6   (GA %82,8 - %99,4)
    ayrılmış    27/29  ->  %93,1   (GA %78,0 - %98,1)

Aralıklar örtüşüyor. Yani "3,5 puanlık genelleme farkı" ölçüm gürültüsünden
ayırt EDİLEMİYOR. Bunu kendi raporunda söylemek, sorulmasını beklemekten
iyidir — ve elimizdeki veriyle söylenebilecek dürüst şey budur.

NEDEN WILSON, NEDEN NORMAL YAKLAŞIM DEĞİL?
Klasik normal (Wald) aralığı küçük örneklemde ve oran 1'e yakınken bozulur:
28/29 için üst sınırı %100'ün ÜSTÜNE çıkarır, 29/29 için ise genişliği sıfır
verir ("hiç belirsizlik yok" der ki saçmadır). Wilson aralığı her iki durumda
da [0,1] içinde kalır ve küçük örneklemde çok daha iyi davranır. Bizim
örneklem büyüklüğümüzde fark önemlidir.
"""

from __future__ import annotations

import math
from typing import Tuple

# %95 güven düzeyi için standart normal z değeri
Z95 = 1.959963984540054


def wilson_interval(basarili: int, toplam: int, z: float = Z95) -> Tuple[float, float]:
    """
    Wilson skor aralığı (0.0-1.0 arası alt ve üst sınır).

    >>> lo, hi = wilson_interval(28, 29)
    >>> round(lo, 3), round(hi, 3)
    (0.828, 0.994)
    """
    if toplam <= 0:
        return 0.0, 0.0
    basarili = max(0, min(basarili, toplam))

    p = basarili / toplam
    z2 = z * z
    payda = 1.0 + z2 / toplam
    merkez = (p + z2 / (2 * toplam)) / payda
    yaricap = (z / payda) * math.sqrt(
        p * (1 - p) / toplam + z2 / (4 * toplam * toplam)
    )
    return max(0.0, merkez - yaricap), min(1.0, merkez + yaricap)


def oran_ozeti(basarili: int, toplam: int) -> dict:
    """Bir oranı sayım, yüzde ve güven aralığıyla birlikte döndürür."""
    if toplam <= 0:
        return {"basarili": 0, "toplam": 0, "yuzde": 0.0,
                "ga_alt": 0.0, "ga_ust": 0.0}
    alt, ust = wilson_interval(basarili, toplam)
    return {
        "basarili": basarili,
        "toplam": toplam,
        "yuzde": round(100.0 * basarili / toplam, 1),
        "ga_alt": round(100.0 * alt, 1),
        "ga_ust": round(100.0 * ust, 1),
    }


def bicimle(ozet: dict) -> str:
    """'28/29  %96,6  (GA %82,8-99,4)' biçiminde okunabilir satır."""
    if not ozet.get("toplam"):
        return "veri yok"
    return (f"{ozet['basarili']}/{ozet['toplam']}  "
            f"%{ozet['yuzde']:.1f}".replace(".", ",")
            + f"  (GA %{ozet['ga_alt']:.0f}-{ozet['ga_ust']:.0f})")


def fark_araligi(b1: int, n1: int, b2: int, n2: int) -> dict:
    """
    İki oran ARASINDAKİ FARKIN güven aralığı (Newcombe skor yöntemi).

    NEDEN AYRI BİR HESAP GEREKİYOR?
    "Aralıklar örtüşüyor mu?" sorusu farkın YÖNÜ hakkında kabaca fikir verir
    ama BÜYÜKLÜĞÜ hakkında hiçbir şey söylemez. Örneğin:

        geliştirme 28/29 (%97)  ↔  taranmış 9/16 (%56)

    Nokta tahmini 40 puan. Ama bu iki küçük örneklemle farkın kendisi de
    belirsizdir: gerçek etki 15 puan da olabilir 64 puan da. "OCR maliyeti
    40 puandır" demek, veriden daha kesin konuşmaktır. Doğru ifade şudur:
    "etki gerçektir (aralık sıfırı içermiyor), büyüklüğü bu örneklemle
    kesinleştirilemez".

    -> {"fark", "alt", "ust", "anlamli"}  (yüzde puan cinsinden)
       anlamli=True ise aralık sıfırı içermez, yani fark yön olarak gerçektir.
    """
    if n1 <= 0 or n2 <= 0:
        return {"fark": 0.0, "alt": 0.0, "ust": 0.0, "anlamli": False}

    p1, p2 = b1 / n1, b2 / n2
    l1, u1 = wilson_interval(b1, n1)
    l2, u2 = wilson_interval(b2, n2)
    d = p1 - p2
    alt = d - math.sqrt((p1 - l1) ** 2 + (u2 - p2) ** 2)
    ust = d + math.sqrt((u1 - p1) ** 2 + (p2 - l2) ** 2)
    return {
        "fark": round(100 * d, 1),
        "alt": round(100 * alt, 1),
        "ust": round(100 * ust, 1),
        "anlamli": not (alt <= 0 <= ust),
    }


def ortusuyor_mu(a: dict, b: dict) -> bool:
    """
    İki oranın güven aralıkları örtüşüyor mu?

    Örtüşüyorsa aradaki fark, bu örneklem büyüklüğüyle ölçüm gürültüsünden
    ayırt edilemez demektir. Bu, "fark yok" anlamına GELMEZ; "bu veriyle
    fark olduğunu söyleyemeyiz" anlamına gelir.
    """
    if not a.get("toplam") or not b.get("toplam"):
        return False
    return a["ga_alt"] <= b["ga_ust"] and b["ga_alt"] <= a["ga_ust"]
