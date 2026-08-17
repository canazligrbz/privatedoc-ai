"""
TARANMIŞ (GÖRÜNTÜ) PDF'LER İÇİN OCR
===================================

Bazı kurum belgeleri fotokopi/tarayıcı çıktısıdır: PDF içinde metin katmanı
yoktur, yalnızca sayfa görüntüsü vardır. Bu dosyalar OCR olmadan indekslenemez
ve sistem onlara dair hiçbir soruyu cevaplayamaz.

Bu modül sayfayı görüntüye çevirip (pypdfium2) Tesseract ile metne dönüştürür.

BAĞIMLILIKLAR
  * pypdfium2, pytesseract, pillow  → pip ile kurulur (requirements.txt'te)
  * Tesseract OCR motoru + Türkçe dil verisi → AYRI kurulur:
      Windows: https://github.com/UB-Mannheim/tesseract/wiki
               kurulumda "Turkish" dil paketini işaretleyin
      Linux  : sudo apt install tesseract-ocr tesseract-ocr-tur
    Air-gap ortamda kurulum dosyasını transfer paketine eklemeyi unutmayın.

TASARIM NOTU: OCR yalnızca METİN KATMANI OLMAYAN sayfalara uygulanır.
Metin katmanı olan sayfa çok daha hızlı ve doğru okunur; gereksiz OCR
hem yavaşlatır hem hata oranını artırır. Karma belgelerde (bazı sayfa
taranmış, bazısı dijital) sayfa sayfa karar verilir.
"""

from __future__ import annotations

import re
import shutil
from pathlib import Path
from typing import Dict, Optional, Tuple

_STATE: Dict[str, object] = {"checked": False, "ok": False, "reason": ""}


def _resolve_exe(tesseract_cmd: Optional[str]) -> Optional[str]:
    """
    Kullanılabilir tesseract yolunu bulur.

    Öncelik: (1) config'te verilen yol GERÇEKTEN VARSA o, (2) PATH,
    (3) bilinen kurulum konumları.

    Yapılandırmadaki yolun var olup olmadığını denetlemek şart: kurulum
    yardımcısıyla yazılan yol sonradan geçersizleşebilir (program başka
    diske taşınır, örnek değer düzenlenmeden bırakılır). Bu durumda
    PATH'te çalışan bir Tesseract varken sistemin pes etmesi anlamsızdır.
    """
    if tesseract_cmd:
        p = Path(str(tesseract_cmd))
        if p.exists():
            return str(p)
        # verilen yol geçersiz -> sessizce PATH'e düş
    found = shutil.which("tesseract")
    if found:
        return found
    for cand in (r"C:\Program Files\Tesseract-OCR\tesseract.exe",
                 r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
                 "/usr/bin/tesseract", "/usr/local/bin/tesseract",
                 "/opt/homebrew/bin/tesseract"):
        if Path(cand).exists():
            return cand
    return None


def configure(tesseract_cmd: Optional[str] = None) -> None:
    """Tesseract çalıştırılabilir yolunu ayarlar."""
    try:
        import pytesseract
    except ImportError:
        return
    exe = _resolve_exe(tesseract_cmd)
    if exe:
        pytesseract.pytesseract.tesseract_cmd = exe
        _STATE["checked"] = False  # yeniden denetlensin


def availability(tesseract_cmd: Optional[str] = None) -> Tuple[bool, str]:
    """
    OCR yapılabilir mi? -> (uygun_mu, açıklama)
    Sonuç önbelleklenir; her sayfada tekrar denetlenmez.
    """
    if _STATE["checked"]:
        return bool(_STATE["ok"]), str(_STATE["reason"])

    configure(tesseract_cmd)
    _STATE["checked"] = True

    missing = []
    for mod in ("pypdfium2", "pytesseract", "PIL"):
        try:
            __import__(mod)
        except ImportError:
            missing.append({"PIL": "pillow"}.get(mod, mod))
    if missing:
        _STATE["ok"] = False
        _STATE["reason"] = ("Python paketleri eksik: " + ", ".join(missing) +
                            ". Kurulum:  pip install " + " ".join(missing))
        return False, str(_STATE["reason"])

    import pytesseract
    exe = _resolve_exe(tesseract_cmd)
    if not exe:
        _STATE["ok"] = False
        hint = ""
        if tesseract_cmd:
            hint = (f" (config.yaml'daki yol geçersiz: {tesseract_cmd} — "
                    "böyle bir dosya yok)")
        _STATE["reason"] = (
            "Tesseract OCR motoru bulunamadı" + hint + ". Windows için "
            "https://github.com/UB-Mannheim/tesseract/wiki adresinden kurun "
            "(kurulumda Turkish dil paketini işaretleyin), sonra ocr-kur.bat "
            "dosyasını çalıştırın."
        )
        return False, str(_STATE["reason"])
    pytesseract.pytesseract.tesseract_cmd = exe

    try:
        langs = set(pytesseract.get_languages(config=""))
    except Exception:
        langs = set()

    if langs and "tur" not in langs:
        _STATE["ok"] = True
        _STATE["reason"] = ("Tesseract kurulu ancak Türkçe dil verisi (tur) yok — "
                            "İngilizce ile denenecek, doğruluk düşük olur. "
                            "tur.traineddata dosyasını tessdata klasörüne ekleyin.")
        return True, str(_STATE["reason"])

    _STATE["ok"] = True
    _STATE["reason"] = "hazır"
    return True, "hazır"


def _clean_ocr(text: str) -> str:
    """OCR gürültüsünü azaltır."""
    if not text:
        return ""
    # Tek başına kalan noktalama/çizgi satırları
    lines = []
    for line in text.replace("\r", "").split("\n"):
        s = line.strip()
        if not s:
            continue
        # Harf/rakam oranı çok düşükse gürültüdür
        useful = sum(ch.isalnum() for ch in s)
        if useful < max(2, len(s) * 0.35):
            continue
        lines.append(s)
    out = "\n".join(lines)
    out = re.sub(r"[ \t]{2,}", " ", out)
    return out.strip()


def _enhance(image):
    """
    Tarama kalitesini OCR öncesi iyileştirir.

    Kurumsal belgeler genelde fotokopinin fotokopisidir: soluk, düşük
    kontrastlı, hafif bulanık. Otomatik kontrast + keskinleştirme, özellikle
    tablo içindeki rakamlarda hata oranını belirgin düşürür.
    """
    try:
        from PIL import ImageFilter, ImageOps
        img = image.convert("L")
        img = ImageOps.autocontrast(img, cutoff=1)
        img = img.filter(ImageFilter.UnsharpMask(radius=1.4, percent=140, threshold=3))
        return img
    except Exception:
        return image


def _ink_ratio(image) -> float:
    """
    Görüntüdeki koyu piksel oranı — sayfada "ne kadar mürekkep var".

    Bu, üretilen metnin beklenen miktarla karşılaştırılmasını sağlar. Sayfada
    bol mürekkep varken az karakter çıkmışsa, OCR içeriği okuyamamış demektir.
    """
    try:
        import numpy as np
        arr = np.asarray(image.convert("L"))
        return float((arr < 200).mean())
    except Exception:
        return 0.0


# OCR, karakter yüksekliği ~20 pikselin altına düştüğünde belirgin şekilde
# bozulur. Düşük çözünürlüklü taramalar ve telefonla çekilmiş görüntüler bu
# sınırın altında kalabilir; büyütmek bilgi eklemez ama Tesseract'ın harf
# ayrıştırmasını kolaylaştırır ve pratikte hata oranını düşürür.
_MIN_UZUN_KENAR = 1600
_HEDEF_UZUN_KENAR = 2200
# Aşırı büyük görüntülerde OCR süresi ve bellek patlar; makul bir tavan.
_MAX_UZUN_KENAR = 6000


def _olcekle(image):
    """Çok küçük görüntüyü büyütür, aşırı büyüğü sınırlar."""
    try:
        from PIL import Image
        w, h = image.size
        uzun = max(w, h)
        if uzun == 0:
            return image
        if uzun < _MIN_UZUN_KENAR:
            k = _HEDEF_UZUN_KENAR / uzun
            return image.resize((max(1, int(w * k)), max(1, int(h * k))),
                                Image.LANCZOS)
        if uzun > _MAX_UZUN_KENAR:
            k = _MAX_UZUN_KENAR / uzun
            return image.resize((max(1, int(w * k)), max(1, int(h * k))),
                                Image.LANCZOS)
        return image
    except Exception:
        return image


def _ocr_image(image, lang: str, preprocess: bool,
               preserve_spaces: bool) -> Tuple[str, Dict[str, float]]:
    """
    Bir PIL görüntüsünü OCR'lar ve ölçüm istatistikleriyle döndürür.

    Hem PDF sayfaları hem de doğrudan görüntü dosyaları buradan geçer;
    böylece iyileştirme, mürekkep ölçümü ve temizleme mantığı tek yerde kalır.

    Mürekkep oranı, iyileştirmeden ÖNCE ölçülür: autocontrast/unsharp koyu
    piksel sayısını değiştirir ve ölçüyü belgeler arası karşılaştırılamaz
    hâle getirirdi.
    """
    import pytesseract

    ink = _ink_ratio(image)
    if preprocess:
        image = _enhance(image)

    # --psm 6: "tek tip metin bloğu" — cetvel/tablo sayfalarında en isabetlisi
    cfg = "--oem 3 --psm 6"
    if preserve_spaces:
        # Sütunlar arasındaki boşluğun korunması, tabloda hangi değerin
        # hangi sütuna ait olduğunu ayırt edebilmek için gereklidir.
        cfg += " -c preserve_interword_spaces=1"

    raw = pytesseract.image_to_string(image, lang=lang, config=cfg)
    text = _clean_ocr(raw)
    return text, {
        "ink_ratio": ink,
        "chars": float(len(text)),
        "chars_per_ink": chars_per_ink(len(text), ink),
    }


def ocr_image_file(path: Path, lang: str = "tur+eng",
                   preprocess: bool = True,
                   preserve_spaces: bool = True) -> List[Tuple[str, Dict[str, float]]]:
    """
    Görüntü dosyasını (JPG/PNG/TIFF/BMP) OCR ile metne çevirir.

    -> [(metin, istatistik), ...]  — çok sayfalı TIFF için birden fazla öğe

    PDF'ten farklı olarak görüntüde METİN KATMANI YOKTUR: OCR isteğe bağlı
    bir yedek değil, tek yoldur. Bu yüzden Tesseract eksikse sessizce boş
    dönmek yerine çağıran tarafın hata vermesi gerekir.
    """
    from PIL import Image, ImageSequence

    out: List[Tuple[str, Dict[str, float]]] = []
    with Image.open(str(path)) as im:
        for kare in ImageSequence.Iterator(im):
            g = _olcekle(kare.convert("L"))
            out.append(_ocr_image(g, lang, preprocess, preserve_spaces))
    return out


def ocr_page_with_stats(pdf_path: Path, page_index: int,
                        lang: str = "tur+eng", dpi: int = 300,
                        preprocess: bool = True,
                        preserve_spaces: bool = True) -> Tuple[str, Dict[str, float]]:
    """
    Sayfayı OCR ile metne çevirir ve ölçüm istatistiklerini de döndürür.

    -> (metin, {"ink_ratio": ..., "chars": ..., "chars_per_ink": ...})

    Mürekkep oranı, OCR için ZATEN üretilen görüntüden hesaplanır; ek render
    maliyeti yoktur. İyileştirmeden (autocontrast/unsharp) ÖNCE ölçülür:
    iyileştirme koyu piksel sayısını değiştirir ve ölçüyü belgeye göre
    karşılaştırılamaz hâle getirirdi.
    """
    bos = {"ink_ratio": 0.0, "chars": 0.0, "chars_per_ink": 0.0}
    try:
        import pypdfium2 as pdfium

        pdf = pdfium.PdfDocument(str(pdf_path))
        try:
            page = pdf[page_index]
            scale = max(1.0, min(5.0, dpi / 72.0))
            bitmap = page.render(scale=scale, grayscale=True)
            image = bitmap.to_pil()
        finally:
            pdf.close()

        return _ocr_image(image, lang, preprocess, preserve_spaces)
    except Exception:
        return "", dict(bos)


def ocr_page(pdf_path: Path, page_index: int,
             lang: str = "tur+eng", dpi: int = 300,
             preprocess: bool = True, preserve_spaces: bool = True) -> str:
    """
    Tek bir PDF sayfasını OCR ile metne çevirir (0 tabanlı indeks).
    Hata durumunda boş dize döner — indeksleme tamamen durmamalıdır.
    """
    return ocr_page_with_stats(pdf_path, page_index, lang=lang, dpi=dpi,
                               preprocess=preprocess,
                               preserve_spaces=preserve_spaces)[0]


def describe() -> str:
    return str(_STATE.get("reason") or "denetlenmedi")


# --------------------------------------------------------------------------
# SESSİZ İÇERİK KAYBI TESPİTİ
# --------------------------------------------------------------------------
# assess_quality() bozuk KARAKTER arar. Gerçek bir ölçümde bunun yetmediği
# görüldü: taranmış bir ücret tablosunun YEDİ VERİ SATIRININ TAMAMI OCR'da
# kayboldu, geriye yalnızca başlık kaldı —
#
#     Unvan   Kisi | Ucret (asgari ucretin yuzde fazlasi) |
#     6.2. Yukaridaki oranlar brut asgari ucret uzerinden hesaplanir...
#          ^ başlık var, 7 veri satırı YOK
#
# ...ve assess_quality o sayfaya 1.00 (kusursuz) verip sıfır sorun bildirdi.
# Bozulmamış metinde aranacak bir bozukluk yoktur; kaybolan içerik geride iz
# bırakmaz. Üç soru bu yüzden cevapsız kaldı ve kullanıcı "bu bilgi belgede
# yok" cevabını alıp inanırdı.
#
# Bu, sistemin üretebileceği en tehlikeli hata türüdür: SESSİZ veri kaybı.
#
# ÇÖZÜM: Metni kendisiyle değil, SAYFA GÖRÜNTÜSÜYLE karşılaştırmak. Sayfada
# bol mürekkep varken az karakter üretilmişse içerik okunamamıştır.
#
# KALİBRASYON (ornek_belgeler/taranmis, 3 sayfa, 300 dpi):
#     sayfa   içerik            karakter kaybı   krk/mürekkep
#       1     hakediş tablosu        %34             2.5
#       2     ücret tablosu          %30             2.7
#       3     düz metin               %0             4.0
# Dijital orijinallerde üç sayfa da ~3.9-4.0 veriyor; yani sapma doğrudan
# kaybın ölçüsüdür. Eşik 3.0 seçildi: hasarlı iki sayfayı yakalar, temiz
# sayfayı rahat bırakır.
#
# SINIRLARI: Bu bir sezgisel ölçüttür, kanıt değil. Yazı boyutu çok büyük
# belgelerde oran doğal olarak düşer; fotoğraf/logo/kaşe içeren sayfalarda da
# mürekkep yüksek çıkar. Bu yüzden ÇIKTI BİR UYARIDIR, hata değil — sayfa
# yine indekslenir, kullanıcıya yalnızca "buradaki verilere güvenme" denir.
# Mutlak eşiğin yanına belge-içi göreli karşılaştırma da eklenmiştir; belgenin
# kendi en iyi sayfası referans alındığında yazı boyutu etkisi kendiliğinden
# düşer.

INK_SCALE = 10000.0          # oranı okunabilir bir büyüklüğe taşır


def chars_per_ink(chars: int, ink_ratio: float) -> float:
    """Mürekkep birimi başına üretilen karakter sayısı."""
    if ink_ratio <= 0:
        return 0.0
    return float(chars) / (ink_ratio * INK_SCALE)


def assess_content_loss(stats: Dict[str, float],
                        doc_best: float = 0.0,
                        floor: float = 3.0,
                        relative: float = 0.7) -> Tuple[float, list]:
    """
    Sayfada sessiz içerik kaybı olup olmadığını değerlendirir.

    -> (0.0-1.0 güven skoru, sorunlar)

    İki ölçüt birlikte kullanılır:
      * MUTLAK  : krk/mürekkep < floor
      * GÖRELİ  : krk/mürekkep < belgenin en iyi sayfasının `relative` katı
    Göreli ölçüt yazı boyutuna göre kendini ayarlar ama belgenin TÜM sayfaları
    hasarlıysa işe yaramaz; mutlak eşik tam olarak o boşluğu kapatır.
    """
    issues: list = []
    ink = float(stats.get("ink_ratio", 0.0))
    oran = float(stats.get("chars_per_ink", 0.0))

    # Mürekkep yok denecek kadar azsa sayfa gerçekten boştur; kayıp değildir.
    if ink < 0.002:
        return 1.0, issues

    ceza = 0.0
    if oran < floor:
        ceza += min(0.6, (floor - oran) / max(floor, 1e-6))
        issues.append(
            f"sayfada mürekkep var ama az metin çıktı "
            f"({oran:.1f} krk/mürekkep, eşik {floor:.1f}) — "
            f"tablo satırları okunamamış olabilir")

    if doc_best > 0 and oran < doc_best * relative:
        ceza += 0.25
        issues.append(
            f"belgenin en iyi sayfasının %{relative*100:.0f}'inin altında "
            f"({oran:.1f} / {doc_best:.1f})")

    return max(0.0, 1.0 - ceza), issues


# --------------------------------------------------------------------------
# OCR KALİTE DEĞERLENDİRMESİ
# --------------------------------------------------------------------------
# OCR sessizce bozuk çıktı üretebilir ve bu, sistemin en tehlikeli hata
# kaynağıdır: model bozuk sayıyı kaynaktan okur, sayı denetimi de "kaynakta
# var" diyerek onaylar. Gerçek bir testte "% 170" tablosu "9480", "%960"
# gibi çöpe dönüştü ve yanıta yansıdı.
#
# Guardrail bunu yakalayamaz — veri yanlış, model değil. Yapılabilecek tek
# doğru şey, hangi sayfaların şüpheli olduğunu KULLANICIYA BİLDİRMEKTİR.

_GLUED_RE = re.compile(r"\b(?=\w*[A-Za-zÇĞİÖŞÜçğıöşü])(?=\w*\d)\w{4,}\b")
_LONG_DIGITS_RE = re.compile(r"\d{6,}")
# Türkçe metinde neredeyse hiç görülmeyen, OCR'ın ürettiği işaretler.
# NOT: "|" ve köşeli parantez BİLEREK dışarıda bırakıldı — tablo çizgileri
# düzgün taramalarda da "|" olarak okunur, bunlar bozukluk göstergesi değildir.
_ODD_CHARS_RE = re.compile(r"[«»“”„~^_\\<>{}—–]|\.{2,}")
_SINGLE_ALPHA_RE = re.compile(r"(?<!\w)[A-Za-zÇĞİÖŞÜçğıöşü](?!\w)")


def assess_quality(text: str) -> Tuple[float, list]:
    """
    OCR çıktısının güvenilirliğini kabaca ölçer.

    -> (0.0-1.0 arası skor, tespit edilen sorunlar)
       1.0 = temiz görünüyor, 0.0 = büyük olasılıkla bozuk

    Eşikler, gerçek bozuk çıktılar üzerinde ayarlandı: birim fiyat cetveli
    (sütunları birleşmiş) ve kesik ceza maddesi. Amaç kusursuz bir sınıflandırma
    değil, "bu sayfadaki sayılara güvenme" uyarısını kaçırmamaktır.
    """
    issues: list = []
    t = (text or "").strip()
    if len(t) < 40:
        return 1.0, issues

    words = t.split()
    n = max(1, len(words))
    L = max(1, len(t))
    penalty = 0.0

    # 1) Harf+rakam yapışık kelimeler: "9480fazlası"
    glued = len(_GLUED_RE.findall(t))
    if glued / n > 0.02:
        penalty += min(0.35, glued / n * 5)
        issues.append(f"{glued} yapışık harf-rakam kelimesi")

    # 2) Anormal uzun rakam dizileri: "530867520" — birleşmiş tablo sütunları.
    #    Sözleşme metninde 6+ haneli bitişik sayı neredeyse hiç bulunmaz.
    longs = _LONG_DIGITS_RE.findall(t)
    if longs:
        penalty += min(0.40, 0.25 * len(longs))
        issues.append(f"{len(longs)} adet 6+ haneli bitişik sayı ({', '.join(longs[:3])})")

    # 3) Bozuk karakter yoğunluğu (| « » — … gibi)
    odd = len(_ODD_CHARS_RE.findall(t))
    if odd / L > 0.004:
        penalty += min(0.30, odd / L * 30)
        issues.append(f"{odd} bozuk karakter/işaret")

    # 4) Kopuk heceler: iki harfe kadar inen HARF içeren parçacıklar.
    #    "%", "7-", "80" gibi meşru kısa belirteçler sayılmaz.
    tiny = sum(1 for w in words
               if len(w) <= 2 and any(c.isalpha() for c in w))
    if tiny / n > 0.12:
        penalty += min(0.25, (tiny / n) * 1.2)
        issues.append(f"{tiny} kopuk hece/parçacık")

    # 5) Tek başına duran harfler: "i os", "lı" — tablo hücrelerinin dağılması
    singles = len(_SINGLE_ALPHA_RE.findall(t))
    if singles >= 2:
        penalty += min(0.20, 0.05 * singles)
        issues.append(f"{singles} tek başına harf")

    return max(0.0, 1.0 - penalty), issues
