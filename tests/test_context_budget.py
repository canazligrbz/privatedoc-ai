"""
BAĞLAM PENCERESİ BÜTÇESİ — src/rag_engine.fit_char_budget

NEDEN VAR?
num_ctx = sistem promptu + kaynaklar + soru + üretilecek yanıt.
Yapılandırmadaki `context_char_budget` bunu bilmez. Gerçek bir hatada sistem
promptu zamanla 4000 karaktere ulaştı, toplam 4096'lık pencereyi aştı, Ollama
SESSİZCE kırptı ve model aynı soruya farklı zamanlarda farklı cevap verdi.
Hatanın bulunması günler aldı çünkü hiçbir yerde hata mesajı yoktu.
"""

from __future__ import annotations

import pytest

from src.rag_engine import _BUDGET_MIN_CHARS, fit_char_budget

# Projenin gerçek varsayılanları
VARSAYILAN = dict(num_ctx=4096, num_predict=700, chars_per_token=2.75,
                  system_prompt_len=1741, question_len=60)


def test_normal_durumda_yapilandirma_degeri_kullanilir():
    """Pencere yeterliyse bütçeye dokunulmaz."""
    assert fit_char_budget(configured=5500, **VARSAYILAN) == 5500


def test_kucuk_pencerede_butce_daraltilir():
    """
    num_ctx düşürülünce bütçe otomatik daralmalı — kullanıcının ayrıca
    context_char_budget'i elle düşürmesi beklenmemeli.
    """
    ayar = {**VARSAYILAN, "num_ctx": 2048}
    assert fit_char_budget(configured=5500, **ayar) < 5500


def test_dev_sistem_promptu_butceyi_yer():
    """
    Asıl hatanın senaryosu: prompt 1741'den 4000 karaktere çıkarsa kaynaklara
    kalan yer belirgin şekilde azalmalı.
    """
    kucuk = fit_char_budget(configured=5500, **VARSAYILAN)
    buyuk = fit_char_budget(configured=5500,
                            **{**VARSAYILAN, "system_prompt_len": 4000})
    assert buyuk < kucuk


def test_uzun_soru_butceyi_azaltir():
    normal = fit_char_budget(configured=5500, **VARSAYILAN)
    uzun = fit_char_budget(configured=5500,
                           **{**VARSAYILAN, "question_len": 2000})
    assert uzun < normal


def test_alt_sinir_korunur():
    """
    Bütçe sıfıra inerse hiç kaynak gönderilmez ve sistem HER soruyu reddeder.
    Az kaynakla denemek, hiç denememeye yeğdir.
    """
    ayar = dict(num_ctx=1024, num_predict=900, chars_per_token=2.75,
                system_prompt_len=4000, question_len=500)
    assert fit_char_budget(configured=5500, **ayar) == _BUDGET_MIN_CHARS


def test_asla_yapilandirmadan_buyuk_olmaz():
    """Pencere bol olsa bile kullanıcının koyduğu üst sınır aşılmaz."""
    ayar = {**VARSAYILAN, "num_ctx": 32768}
    assert fit_char_budget(configured=5500, **ayar) == 5500


@pytest.mark.parametrize("num_ctx", [1024, 2048, 4096, 8192, 16384])
def test_butce_pencereye_sigar(num_ctx):
    """
    Asıl güvence: hesaplanan bütçe + sistem promptu + soru + üretim payı,
    pencereye SIĞMALI. Bu test bozulursa sessiz kırpma geri gelir.
    """
    ayar = {**VARSAYILAN, "num_ctx": num_ctx}
    butce = fit_char_budget(configured=9000, **ayar)

    toplam_karakter = butce + ayar["system_prompt_len"] + ayar["question_len"]
    toplam_token = toplam_karakter / ayar["chars_per_token"] + ayar["num_predict"]

    # Alt sınıra dayanmış durumlarda pencere zaten yetersizdir; orada
    # sığmama beklenen davranıştır (uyarı verilir, sistem yine de çalışır).
    if butce > _BUDGET_MIN_CHARS:
        assert toplam_token <= num_ctx, f"num_ctx={num_ctx} aşıldı"
