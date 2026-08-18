"""
BAĞLAM PENCERESİ BÜTÇESİ

num_ctx = sistem promptu + kaynaklar + soru + üretilecek yanıt.
Yapılandırmadaki `context_char_budget` bunu bilmez; sistem promptu büyüdüğünde
toplam sessizce pencereyi aşar.

GERÇEK HATA: prompt zamanla ~4000 karaktere ulaştı, 4096'lık pencere doldu,
Ollama SESSİZCE kırptı ve model aynı soruya farklı zamanlarda farklı cevap
verdi. Hiçbir yerde hata mesajı yoktu; teşhis günler aldı.

NEDEN AYRI MODÜL?
Bu saf bir aritmetik. rag_engine içinde durduğunda, onu test etmek için
llm_client -> httpx zincirinin tamamını kurmak gerekiyordu; CI ortamı bu
yüzden çöktü. Hesabın ağır bağımlılığı yok, dolayısıyla ağır bir modülde
oturmasının da sebebi yok.
"""

from __future__ import annotations

# Kullanıcı promptu şablonunun kendi payı (başlıklar, talimat metni)
TEMPLATE_CHARS = 400
# Tokenizasyon sapmasına karşı emniyet payı
SAFETY_TOKENS = 96
# Bu değerin altında hiç kaynak sığmaz; bütçe buraya kadar daraltılabilir
MIN_CHARS = 600


def fit_char_budget(configured: int,
                    num_ctx: int,
                    num_predict: int,
                    chars_per_token: float,
                    system_prompt_len: int,
                    question_len: int) -> int:
    """
    Kaynaklara ayrılabilecek GERÇEK karakter sayısını hesaplar.

    Alt sınır bilinçli: bütçe sıfıra inerse hiç kaynak gönderilmez ve sistem
    HER soruyu reddeder. Böyle bir durumda az kaynakla denemek, hiç
    denememeye yeğdir — kullanıcı en azından bir şey görür.
    """
    overhead = system_prompt_len + question_len + TEMPLATE_CHARS
    available_tokens = num_ctx - num_predict - SAFETY_TOKENS
    available_chars = int(available_tokens * chars_per_token) - overhead
    return max(MIN_CHARS, min(configured, available_chars))
