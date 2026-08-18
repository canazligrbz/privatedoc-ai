"""
İKİNCİ BELGE ALANI — YÖNETMELİK ÜRETİCİ
=======================================

NEDEN İKİNCİ BİR BELGE?
Elimizdeki üç test seti de AYNI belgeden (depo sözleşmesi) yazıldı. Ayrılmış
set SORU genellemesini ölçer: "hiç görülmemiş sorulara ne yapıyor?" Ama BELGE
genellemesini ölçmez: "sistem tek bir sözleşmenin biçimine göre mi ayarlandı?"
Bu sorunun tek gerçek cevabı, YAPISI FARKLI bir belgede aynı ölçümü
tekrarlamaktır.

FARKLILIK BİLİNÇLİ TASARLANDI. Gerçek bir kira sözleşmesi (taranmış JPG) bize
"farklı"nın neye benzediğini gösterdi; bu belge o profili hedefler:

    depo sözleşmesi (mevcut)          bu yönetmelik (yeni)
    ------------------------------    ------------------------------
    tablo ağırlıklı, 8 tablo          TABLO YOK
    sayı yoğun (tutar, oran, tarih)   neredeyse SAYISIZ
    "MADDE 5.1" numaralandırma        sade "5" numaralandırma
    olumlu hükümler                   OLUMSUZ hükümler bol
                                      ("verilmez", "sayılmaz", "kabul edilmez")
    kısa maddeler                     uzun, iç içe cümleler

Bu dört fark, sistemin en çok ayar yaptığımız mekanizmalarını devre dışı
bırakır: tablo satırı bölme çalışmaz, sayı doğrulama neredeyse boşta kalır,
madde bazlı bölme "MADDE" kalıbını bulamaz. Yani ölçüm gerçekten yeni bir
zemine oturur.

Çıktı:
    ornek_belgeler/yonetmelik/personel_yonetmeligi.pdf

Kullanım:
    python scripts/make_regulation_pdf.py
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (BaseDocTemplate, Frame, PageBreak, PageTemplate,
                                Paragraph, Spacer)

FONT_CANDIDATES = [
    ("DejaVuSans", "DejaVuSans-Bold",
     "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
     "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
    ("Arial", "Arial-Bold", r"C:\Windows\Fonts\arial.ttf", r"C:\Windows\Fonts\arialbd.ttf"),
    ("Calibri", "Calibri-Bold", r"C:\Windows\Fonts\calibri.ttf", r"C:\Windows\Fonts\calibrib.ttf"),
]


def register_font() -> tuple:
    for name, bold, reg, bd in FONT_CANDIDATES:
        if Path(reg).exists():
            pdfmetrics.registerFont(TTFont(name, reg))
            if Path(bd).exists():
                pdfmetrics.registerFont(TTFont(bold, bd))
            else:
                bold = name
            return name, bold
    raise RuntimeError("Türkçe karakter destekli yazı tipi bulunamadı.")


BASE, BOLD = register_font()
ss = getSampleStyleSheet()
H1 = ParagraphStyle("H1", parent=ss["Heading1"], fontName=BOLD, fontSize=14,
                    spaceAfter=10, textColor=colors.HexColor("#1F3B5C"))
H2 = ParagraphStyle("H2", parent=ss["Heading2"], fontName=BOLD, fontSize=11,
                    spaceBefore=12, spaceAfter=6, textColor=colors.HexColor("#2E4C6E"))
BODY = ParagraphStyle("BODY", parent=ss["BodyText"], fontName=BASE, fontSize=9.5,
                      leading=15, alignment=TA_JUSTIFY, spaceAfter=7)
MADDE = ParagraphStyle("MADDE", parent=BODY, leftIndent=14, firstLineIndent=-14)
CENTER = ParagraphStyle("CENTER", parent=BODY, alignment=TA_CENTER)


def P(t: str, s=BODY) -> Paragraph:
    return Paragraph(t, s)


def M(no: int, metin: str) -> Paragraph:
    """Sade rakamla numaralı madde — "MADDE 5.1" DEĞİL."""
    return Paragraph(f"<b>{no}</b>&nbsp;&nbsp;{metin}", MADDE)


# =====================================================================
#  İÇERİK — düz metin, olumsuz hüküm yoğun, tablo yok
# =====================================================================

BOLUMLER = [
    ("BİRİNCİ BÖLÜM — AMAÇ, KAPSAM VE TANIMLAR", [
        "Bu yönetmeliğin amacı, kurumda görev yapan personelin çalışma "
        "esaslarını, hak ve yükümlülüklerini, disiplin işlemlerini ve izin "
        "usullerini düzenlemektir.",
        "Bu yönetmelik, kurumun merkez ve taşra teşkilatında kadrolu, "
        "sözleşmeli veya geçici statüde görev yapan tüm personeli kapsar. "
        "Hizmet alımı yoluyla çalıştırılan yüklenici personeli bu yönetmeliğin "
        "kapsamı DIŞINDADIR ve haklarında kendi sözleşmeleri uygulanır.",
        "Staj ve zorunlu uygulama kapsamında kurumda bulunan öğrenciler "
        "personel sayılmaz; bunlara ilişkin esaslar ayrı bir yönergeyle "
        "belirlenir.",
        "Bu yönetmelikte geçen Birim Amiri deyimi, personelin bağlı bulunduğu "
        "en yakın üst yöneticiyi; Üst Yönetim deyimi, genel müdür ve "
        "yardımcılarını ifade eder.",
    ]),
    ("İKİNCİ BÖLÜM — ÇALIŞMA ESASLARI", [
        "Personel, kendisine verilen görevleri özenle, zamanında ve mevzuata "
        "uygun biçimde yerine getirmekle yükümlüdür. Görevin yerine "
        "getirilmesinde ihmal veya gecikme bulunması hâlinde birim amiri "
        "durumu yazılı olarak tespit eder.",
        "Personelin görev yerinin değiştirilmesi, hizmet gereklerine göre üst "
        "yönetim tarafından yapılır. Görev yeri değişikliği personelin rızasına "
        "bağlı değildir; ancak sağlık durumu veya eş durumu gerekçesiyle "
        "yapılan talepler öncelikle değerlendirilir.",
        "Personel, birim amirinin bilgisi olmaksızın görev yerinden ayrılamaz. "
        "Zorunlu hâllerde ayrılan personel, dönüşünde durumu yazılı olarak "
        "bildirir.",
        "Mesai saatleri dışında yapılan çalışmalar için ayrıca ücret ödenmez; "
        "bu çalışmalar karşılığında izin verilir. Verilecek iznin süresi ve "
        "kullanım zamanı birim amirinin onayına bağlıdır.",
        "Personelin kurum dışında ücretli veya ücretsiz başka bir işte "
        "çalışması yasaktır. Bilimsel yayın hazırlamak, ders vermek ve telif "
        "hakkı doğuran çalışmalar bu yasağın kapsamında değildir.",
    ]),
    ("ÜÇÜNCÜ BÖLÜM — İZİNLER", [
        "Yıllık izin, hizmet süresi bir yılı dolduran personele verilir. Bir "
        "yılını doldurmayan personele yıllık izin verilmez; bu personelin "
        "mazeret izni talepleri genel hükümlere göre değerlendirilir.",
        "Yıllık iznin ne zaman kullanılacağı, hizmetin aksamaması kaydıyla "
        "birim amiri tarafından belirlenir. Personelin talebi bağlayıcı "
        "değildir.",
        "Kullanılmayan yıllık izin bir sonraki yıla devredilir. Devredilen "
        "izin, devredildiği yıl içinde kullanılmadığı takdirde düşer ve "
        "karşılığında herhangi bir ödeme yapılmaz.",
        "Mazeret izni, personelin yazılı başvurusu ve birim amirinin uygun "
        "görüşü üzerine verilir. Mazeret izni yıllık izinden düşülmez.",
        "Refakat izni, birinci derece yakınının tedavisi için gerekli "
        "olduğunun sağlık kurulu raporuyla belgelenmesi hâlinde verilir. "
        "Rapor ibraz edilmeden refakat izni kullanılamaz.",
        "Ücretsiz izinde geçen süre, hizmet süresinin hesabında dikkate "
        "alınmaz. Bu süre için kurumca sosyal güvenlik primi yatırılmaz.",
    ]),
    ("DÖRDÜNCÜ BÖLÜM — DİSİPLİN", [
        "Disiplin cezaları uyarma, kınama, aylıktan kesme, kademe ilerlemesinin "
        "durdurulması ve görevden çıkarma olarak uygulanır. Cezalar, fiilin "
        "ağırlığına göre doğrudan verilir; hafiften ağıra doğru sıralı olarak "
        "uygulanması zorunlu değildir.",
        "Uyarma cezası, görevde kayıtsızlık göstermek veya iş arkadaşlarına "
        "karşı saygısız davranmak fiillerine uygulanır. Bu ceza sicile işlenir "
        "ancak özlük haklarında bir kayba yol açmaz.",
        "Kınama cezası, verilen emirleri yerine getirmemek veya görev sırasında "
        "kuruma ait araç ve gereci özensiz kullanmak fiillerine uygulanır.",
        "Aylıktan kesme cezası, izinsiz veya özürsüz olarak göreve gelmemek "
        "fiiline uygulanır ve brüt aylıktan kesinti yapılmasını gerektirir.",
        "Disiplin soruşturması, fiilin öğrenildiği tarihten itibaren başlatılır. "
        "Soruşturmacı olarak, hakkında soruşturma yapılan personelden daha alt "
        "unvanda bulunan biri görevlendirilemez.",
        "Hakkında disiplin soruşturması yürütülen personele savunma hakkı "
        "verilmesi zorunludur. Savunma alınmadan disiplin cezası verilemez.",
        "Disiplin cezasına karşı itiraz, cezanın tebliğinden itibaren yapılır. "
        "İtiraz, cezanın uygulanmasını kendiliğinden durdurmaz.",
    ]),
    ("BEŞİNCİ BÖLÜM — EĞİTİM VE GELİŞİM", [
        "Personelin hizmet içi eğitime katılması esastır. Eğitime katılım "
        "isteğe bağlı değildir; katılmayan personel hakkında birim amiri "
        "gerekçe raporu düzenler.",
        "Eğitim süresi çalışma süresinden sayılır. Eğitim nedeniyle yapılan "
        "yol ve konaklama giderleri kurumca karşılanır.",
        "Kurum dışında düzenlenen eğitimlere katılım, üst yönetimin onayına "
        "bağlıdır. Onay alınmadan katılınan eğitimin gideri personele ödenmez.",
        "Eğitim sonunda yapılan değerlendirmede başarısız olan personel, aynı "
        "eğitimi tekrar alır. Tekrarlanan eğitimin gideri de kurumca "
        "karşılanır.",
    ]),
    ("ALTINCI BÖLÜM — SONA ERME VE YÜRÜRLÜK", [
        "Personelin görevi; istifa, emeklilik, görevden çıkarma cezası veya "
        "sözleşme süresinin dolması hâllerinde sona erer.",
        "İstifa eden personel, devir teslim işlemlerini tamamlamadan kurumdan "
        "ilişiğini kesemez. Devir teslim tutanağı imzalanmadan son ödeme "
        "yapılmaz.",
        "Görevi sona eren personele ait kurum malzemeleri eksiksiz iade edilir. "
        "İade edilmeyen malzemenin bedeli son ödemeden mahsup edilir.",
        "Bu yönetmelikte hüküm bulunmayan hâllerde genel mevzuat hükümleri "
        "uygulanır.",
        "Bu yönetmelik, üst yönetimin onayladığı tarihte yürürlüğe girer ve "
        "hükümlerini genel müdür yürütür.",
    ]),
]


def build_story() -> list:
    s: list = []
    s += [Spacer(1, 50 * mm),
          P("KURUM PERSONEL YÖNETMELİĞİ", ParagraphStyle(
              "k", parent=CENTER, fontName=BOLD, fontSize=16, leading=24)),
          Spacer(1, 10 * mm),
          P("Yönerge No: PY-2024/03", CENTER),
          Spacer(1, 40 * mm),
          P("Bu belge test amaçlı üretilmiştir. İçeriğindeki kurum ve kişiler "
            "gerçek değildir.",
            ParagraphStyle("n", parent=CENTER, fontSize=8, textColor=colors.grey)),
          PageBreak()]

    madde_no = 1
    for baslik, maddeler in BOLUMLER:
        s.append(P(baslik, H1))
        for metin in maddeler:
            s.append(M(madde_no, metin))
            madde_no += 1
        s.append(Spacer(1, 4 * mm))
    return s


def main() -> int:
    ap = argparse.ArgumentParser(description="Yönetmelik biçimli test belgesi")
    ap.add_argument("--out", default="ornek_belgeler/yonetmelik")
    args = ap.parse_args()

    hedef = Path(args.out)
    hedef.mkdir(parents=True, exist_ok=True)
    yol = hedef / "personel_yonetmeligi.pdf"

    doc = BaseDocTemplate(str(yol), pagesize=A4,
                          leftMargin=22 * mm, rightMargin=22 * mm,
                          topMargin=20 * mm, bottomMargin=20 * mm,
                          title="Kurum Personel Yönetmeliği")
    frame = Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height, id="f")

    def alt_ust(canvas, d):
        canvas.saveState()
        canvas.setFont(BASE, 7.5)
        canvas.setFillColor(colors.grey)
        canvas.drawString(22 * mm, 12 * mm, "PY-2024/03 — Kurum Personel Yönetmeliği")
        canvas.drawRightString(A4[0] - 22 * mm, 12 * mm, f"Sayfa {d.page}")
        canvas.restoreState()

    doc.addPageTemplates([PageTemplate(id="n", frames=[frame], onPage=alt_ust)])
    doc.build(build_story())

    toplam = sum(len(m) for _, m in BOLUMLER)
    print(f"✔ {yol}")
    print(f"  bölüm: {len(BOLUMLER)} · madde: {toplam}")
    print("  profil: tablo YOK · sayı neredeyse yok · sade numaralandırma · "
          "olumsuz hüküm yoğun")
    return 0


if __name__ == "__main__":
    sys.exit(main())
