"""
STRICT RAG PROMPT ŞABLONLARI
============================

Halüsinasyon engellemenin üç ayağı vardır; ikisi bu dosyadadır:
  1. Talimat katmanı   -> aşağıdaki SYSTEM_PROMPT (kapalı-kitap yasağı, atıf zorunluluğu)
  2. Bağlam katmanı    -> build_user_prompt (numaralı, sınırları belirgin kaynak blokları)
  3. Doğrulama katmanı -> rag_engine.py içindeki citation validation (kod ile zorlama)

Talimat tek başına yeterli DEĞİLDİR. Üçü birlikte kullanılmalıdır.
"""

from __future__ import annotations

from typing import List

REFUSAL = "Bu konu hakkında yüklenen belgelerde bilgi bulunmamaktadır."


# --------------------------------------------------------------------------
# ATIF ETİKETLERİ — DENENDİ, ÖLÇÜLDÜ, GERİ ALINDI
# --------------------------------------------------------------------------
# SORUN (gerçek): Kaynaklar [K1], [K2] diye numaralı. Gerçek bir kira
# sözleşmesinde maddeler de sade rakamla numaralıydı ("7 Kiracı kontrat
# müddetinin son ayı içinde ... karşı koymaz."). Model MADDE numarasını
# kaynak numarası sanıp [K7] üretti; yalnızca 4 kaynak vardı, guardrail
# "uydurma kaynak" deyip yanıtı reddetti. Cevap elindeyken YANLIŞ RET.
# Guardrail doğru çalıştı; kusur etiket şemasındaydı.
#
# DENENEN ÇÖZÜM: Etiketleri harfe çevirmek ([KA], [KB]...). Madde numaraları
# rakam, etiketler harf olunca çakışma matematiksel olarak imkânsız hale
# geliyordu. Mantık sağlamdı.
#
# ÖLÇÜM SONUCU — ÇÖZÜM MALİYETİ KAZANCINDAN BÜYÜK ÇIKTI:
#
#     etiket        koşu sayısı   geliştirme seti
#     [K1] rakam         3          28/29  (her seferinde)
#     [KA] harf          3          25, 26, 26
#
# Harf şeması geliştirme setinde tutarlı olarak İKİ SORUYA mal oldu,
# karşılığında bir gerçek belge sorusunu kurtardı. Üç düzeltme turu denendi;
# her tur iki soruyu kurtarıp iki soruyu bozdu. 7B model bu ölçekte etiket
# biçimine beklenmedik ölçüde duyarlı.
#
# KARAR: Rakama geri dönüldü. Ölçülen maliyeti olan, ölçülen net kazancı
# olmayan bir değişiklik tutulmaz.
#
# MADDE NUMARASI ÇAKIŞMASI ARTIK BİLİNEN BİR SINIRDIR: sade rakamla
# numaralanmış belgelerde (kira sözleşmesi, yönetmelik) model bazen madde
# numarasını atıf sanar ve guardrail yanıtı reddeder. Sonuç yanlış ret olur —
# yani sistem yanlış bilgi vermez, susar. Hata türü olarak kabul edilebilir
# olanıdır.
#
# YAN BULGU (iki kez tekrarlandı): Talimat metnine SOMUT ÖRNEK JETON koymak
# modelin o jetonu kopyalamasına yol açıyor.
#   · Sistem promptu: 'madde numarasını atıf sanma, [K7] DEĞİLDİR'
#         -> model iki soruda hiç metin üretmedi, yalnızca "[KA]" yazdı
#   · Kullanıcı promptu: 'atıfı koyarak yanıtla (örn. [KA])'
#         -> model iki soruda yanıta "[KA] " ile başladı
# Çalışan hâlde talimat SOYUT: "[K numarası] atıfı koyarak". Kopyalanacak
# jeton yok; biçimi bağlam bloklarının kendisi gösteriyor.
# --------------------------------------------------------------------------


def citation_label(index: int) -> str:
    """1 tabanlı kaynak sırasını atıf etiketine çevirir."""
    return str(max(1, int(index)))


def citation_index(label: str) -> int:
    """Etiketi 1 tabanlı sıraya çevirir. Geçersizse 0."""
    s = (label or "").strip()
    return int(s) if s.isdigit() else 0


# NOT — PROMPT UZUNLUĞU BİR KAYNAK MESELESİDİR:
# Bu metin her soruda bağlam penceresine girer. Kurallar zamanla birikip
# ~4000 karaktere ulaştığında (~1450 token), 4096'lık pencerede kaynaklara
# yer kalmadı ve Ollama sessizce kırpma yaptı; model bazen kurallarını
# bazen kaynakları kaybetti ve AYNI SORUYA FARKLI CEVAP verdi.
# Bu yüzden burası bilinçli olarak sıkı tutulur: her kural tek satır,
# örnek yalnızca karıştırılması muhtemel yerlerde.

SYSTEM_PROMPT = """Kurum içi belge asistanısın. YALNIZCA sana verilen KAYNAK bloklarını kullanarak Türkçe yanıt verirsin.

## KURALLAR
1. Eğitim verindeki genel bilgini KULLANMA. Her cümle kaynaklardan doğrulanabilir olmalı.
2. Sayı, tarih, oran veya isim içeren HER cümlenin sonuna atıf koy: [K2] ya da [K1][K3]. Atıfını veremeyeceğin cümleyi hiç yazma.
3. Yanıt kaynaklarda yoksa tahmin yürütme; yalnızca şunu yaz: "{refusal}"
   Bu cümleyi YA TEK BAŞINA yaz YA DA hiç yazma. Cevabını verdiysen sonuna bu cümleyi EKLEME.
4. Sorunun bir kısmı cevaplanabiliyorsa o kısmı atıfla ver, eksik konuyu adıyla belirt ("Servis bedeline ilişkin bilgi ... yer almamaktadır").
5. Sana verilmemiş kaynak numarası, madde numarası, tarih veya sayı ÜRETME.
6. Kaynaklar çelişiyorsa ikisini de atıfla göster, kendin karar verme.
7. Hukuki/mali yorum yapma; belgede yazanı aktar.
8. Sayıları kaynaktaki biçimiyle kopyala. Toplama, çıkarma, yuvarlama YAPMA.
9. TABLOLARDA SATIR EŞLEŞMESİ: Soruda tarih/dönem/kod geçiyorsa yalnızca o değerin BİREBİR bulunduğu satırı kullan, komşu satırı asla kullanma. Yazmadan önce satırdaki değerin sorudakiyle aynı olduğunu doğrula.
10. ŞU YAZIMLAR AYNIDIR; farklı yazıldı diye "bilgi yok" DEME:
    Ocak=01 · Haziran=06 · Kasım=11 · Aralık=12 | birinci=1, üçüncü=3 | onsekiz=18, otuziki=32
    Soru "Kasım 2024" ise kaynaktaki "11/2024" satırı bu soruyu KARŞILAR.
11. "Bu nedenle", "Sonuç olarak", "Özetle" gibi kapanış/özet cümlesi KURMA. Bilgiyi bir kez atıfla ver ve dur.

## BİÇİM
- Doğrudan yanıtla başla, giriş cümlesi kurma.
- Liste yazarsan her maddenin kendi atıfı olsun.
- Atıfları ayrı ayrı yaz: [K1][K3] doğru, "K1K3" yanlış.
- Sona kaynak listesi ekleme; sistem otomatik ekler.
""".format(refusal=REFUSAL)


# Belge dışı/genel sohbet sorularında kullanılacak kısa kural seti (opsiyonel mod)
SYSTEM_PROMPT_NON_STRICT_SUFFIX = """
NOT: Kullanıcı selamlaşma veya sistemin ne yaptığına dair bir soru sorarsa,
kısaca kendini tanıt ve hangi belgelerde arama yapabileceğini söyle. Bu durumda atıf gerekmez.
"""


CONTEXT_BLOCK_TEMPLATE = """[K{label}] Belge: {source} | Konum: {locator}{section}
---
{text}
---"""


USER_PROMPT_TEMPLATE = """Aşağıda kurum belgelerinden alınmış {count} adet KAYNAK bloğu bulunmaktadır.

{context}

## SORU
{question}

## TALİMAT
Yukarıdaki KAYNAK bloklarını dikkatle oku. Soruyu yalnızca bu bloklardaki bilgilere dayanarak,
her cümlenin sonuna [K numarası] atıfı koyarak yanıtla.

Soruda bir tarih, ay, dönem, kod veya isim geçiyorsa: kullanacağın satırdaki değerin
sorudakiyle BİREBİR aynı olduğunu doğrula. Yakın/komşu satırı kullanma.

Yanıt bu bloklarda yoksa yalnızca şunu yaz: "{refusal}"
"""

# ---------------------------------------------------------------------------
# DENENDİ VE İŞE YARAMADI — AY ADI ↔ AY NUMARASI EŞLEŞTİRMESİ
# ---------------------------------------------------------------------------
# Belge tabloda "11/2024" yazıyor, kullanıcı "Kasım 2024" diye soruyor.
# ARAMA katmanı bu denkliği biliyor (bm25._equivalents) ve doğru satırı 1.
# sıraya taşıyor. ÜRETİM katmanı ise satırı kullanmayı reddediyor.
#
# Üç müdahale denendi, üçü de ölçüldü, hiçbiri kazanç sağlamadı:
#
#   1. Sistem promptuna genel kural (10. kural: "Kasım=11")
#         -> model: "belgede açık olarak verilmedi"
#   2. Kullanıcı mesajına soruya özel NOT eklemek
#         -> model: "belirtilmemiş bir dönemdir"
#         Sebep: not, hemen üstündeki "BİREBİR aynı olduğunu doğrula"
#         kuralıyla çelişiyordu ve daha kesin ifade edilmiş olan kazandı.
#   3. Ay adı geçen sorularda eşleştirme kuralını denklik farkındalıklı
#      bir sürümle değiştirmek
#         -> model: düpedüz ret. Biraz daha kötü.
#
# Üçüncü deneme geri alındı: kazanç göstermeyen bir değişikliği iki ayrı kod
# yolu pahasına tutmak doğru değil. Bu, 7B sınıfı modelin bilinen bir sınırı
# olarak belgelendi (README → "Bilinen sınırlar").
#
# Denenmemiş seçenek: indeksleme sırasında tarih hücresini zenginleştirmek
# ("11/2024" -> "11/2024 (Kasım 2024)"). Model eşleştirme yapmak zorunda
# kalmazdı. Kaynak metnini değiştirdiği için gösterim metnini indeks
# metninden ayırmak gerekir; tek soru için yapılmadı.
#
# DÖRDÜNCÜ BİR PROMPT DENEMESİ YAPMADAN ÖNCE: bu üç sonuç, geliştirme
# setindeki TEK bir soruya bakılarak elde edildi. Dördüncü müdahale, ölçtüğü
# setin skorunu iyileştirir ama genelleme hakkında bilgi vermez.
# ---------------------------------------------------------------------------


def build_context(chunks: List[dict], char_budget: int = 9000) -> str:
    """Getirilen parçaları numaralı, sınırları belirgin bloklara dönüştürür."""
    parts: List[str] = []
    used = 0
    for i, ch in enumerate(chunks, start=1):
        meta = ch.get("metadata", {}) or {}
        section = meta.get("section") or ""
        section_str = f" | Bölüm: {section}" if section else ""
        text = ch.get("text", "")

        block = CONTEXT_BLOCK_TEMPLATE.format(
            label=citation_label(i),
            source=meta.get("source_file", "bilinmiyor"),
            locator=meta.get("locator", "-"),
            section=section_str,
            text=text,
        )
        if used + len(block) > char_budget and parts:
            break
        parts.append(block)
        used += len(block)
    return "\n\n".join(parts)


def build_user_prompt(question: str, chunks: List[dict], char_budget: int = 9000) -> str:
    context = build_context(chunks, char_budget)
    return USER_PROMPT_TEMPLATE.format(
        count=len(chunks),
        context=context,
        question=question.strip(),
        refusal=REFUSAL,
    )


# --------------------------------------------------------------------------
# Soru yeniden yazma (opsiyonel): takip sorularını bağımsız hale getirir.
# Örn. "Peki süresi ne kadar?" -> "Yıllık izin süresi ne kadardır?"
# --------------------------------------------------------------------------
QUERY_REWRITE_PROMPT = """Aşağıdaki sohbet geçmişini ve son soruyu kullanarak, son soruyu
tek başına anlaşılabilir, bağımsız bir arama sorusuna dönüştür.
Yalnızca yeniden yazılmış soruyu yaz, açıklama ekleme. Soru zaten bağımsızsa aynen tekrarla.

SOHBET GEÇMİŞİ:
{history}

SON SORU: {question}

BAĞIMSIZ SORU:"""
