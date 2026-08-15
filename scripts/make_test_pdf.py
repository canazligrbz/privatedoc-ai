"""
TEST BELGESİ ÜRETİCİ
====================

Sistemi ölçmek için, içeriği TAM OLARAK BİLİNEN 20 sayfalık bir sözleşme
belgesi üretir. Gerçek belgelerle test ederken "acaba bu bilgi gerçekten
belgede var mı?" belirsizliği ölçümü imkânsız kılıyor; burada o belirsizlik
yok, her cevabın doğrusu bellidir.

Belge bilinçli olarak zorlayıcı hazırlanmıştır:
  * Birbirine çok benzeyen ama FARKLI ceza maddeleri (9.2 / 9.3 / 9.4)
  * Aynı konunun iki farklı yerde geçmesi (süre: MADDE 4 ve Ek-2)
  * Yalnızca bir kez geçen kritik sayılar
  * Satır bazlı okunması gereken tablolar (aylık hakediş, unvan oranları)
  * Bir akış şeması (metin olarak çıkarılabilir kutular)
  * Tuzak: "fazla mesai ödenmez, izinle karşılanır"

Çıktılar:
    ornek_belgeler/depo_sozlesmesi.pdf     20 sayfa, dijital (temiz metin)
    ornek_belgeler/depo_ekler_taranmis.pdf  3 sayfa, taranmış görüntü (OCR testi)

Kullanım:
    python scripts/make_test_pdf.py
    python scripts/make_test_pdf.py --out ornek_belgeler
"""

from __future__ import annotations

import argparse
import random
import sys
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    BaseDocTemplate, Frame, PageBreak, PageTemplate, Paragraph, Spacer, Table,
    TableStyle,
)

# --------------------------------------------------------------------- yazı tipi

FONT_CANDIDATES = [
    ("DejaVuSans", "DejaVuSans-Bold",
     "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
     "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
    ("Arial", "Arial-Bold", r"C:\Windows\Fonts\arial.ttf", r"C:\Windows\Fonts\arialbd.ttf"),
    ("Calibri", "Calibri-Bold", r"C:\Windows\Fonts\calibri.ttf", r"C:\Windows\Fonts\calibrib.ttf"),
]


def register_font() -> tuple:
    """Türkçe karakterleri destekleyen bir yazı tipi bulur ve kaydeder."""
    for name, bold, reg_path, bold_path in FONT_CANDIDATES:
        if Path(reg_path).exists():
            pdfmetrics.registerFont(TTFont(name, reg_path))
            if Path(bold_path).exists():
                pdfmetrics.registerFont(TTFont(bold, bold_path))
            else:
                bold = name
            return name, bold
    raise RuntimeError(
        "Türkçe karakter destekli yazı tipi bulunamadı. "
        "DejaVuSans veya Arial gereklidir."
    )


BASE, BOLD = register_font()

# --------------------------------------------------------------------- stiller

ss = getSampleStyleSheet()
H1 = ParagraphStyle("H1", parent=ss["Heading1"], fontName=BOLD, fontSize=15,
                    spaceAfter=10, textColor=colors.HexColor("#1F3B5C"))
H2 = ParagraphStyle("H2", parent=ss["Heading2"], fontName=BOLD, fontSize=12,
                    spaceBefore=10, spaceAfter=6, textColor=colors.HexColor("#2E4C6E"))
BODY = ParagraphStyle("BODY", parent=ss["BodyText"], fontName=BASE, fontSize=9.5,
                      leading=14.5, alignment=TA_JUSTIFY, spaceAfter=6)
SMALL = ParagraphStyle("SMALL", parent=BODY, fontSize=8.5, leading=12)
CENTER = ParagraphStyle("CENTER", parent=BODY, alignment=TA_CENTER)
MONO = ParagraphStyle("MONO", parent=BODY, fontName=BASE, fontSize=8.5, leading=13)

TBL_STYLE = TableStyle([
    ("FONTNAME", (0, 0), (-1, -1), BASE),
    ("FONTNAME", (0, 0), (-1, 0), BOLD),
    ("FONTSIZE", (0, 0), (-1, -1), 8.5),
    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E7EDF4")),
    ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#1F3B5C")),
    ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#B9C4D2")),
    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ("ALIGN", (1, 1), (-1, -1), "CENTER"),
    ("TOPPADDING", (0, 0), (-1, -1), 3.5),
    ("BOTTOMPADDING", (0, 0), (-1, -1), 3.5),
])


def P(text: str, style=BODY) -> Paragraph:
    return Paragraph(text, style)


def T(data, widths=None) -> Table:
    t = Table(data, colWidths=widths, hAlign="LEFT")
    t.setStyle(TBL_STYLE)
    return t


# --------------------------------------------------------------------- içerik

def build_story() -> list:
    s: list = []

    # ---------------------------------------------------------- 1. KAPAK
    s += [Spacer(1, 45 * mm),
          P("AYDIN LOJİSTİK VE DEPOLAMA A.Ş.", ParagraphStyle(
              "c1", parent=CENTER, fontName=BOLD, fontSize=17, leading=24)),
          Spacer(1, 8 * mm),
          P("MERKEZ DEPO İŞLETME, BAKIM VE<br/>LOJİSTİK HİZMET ALIMI SÖZLEŞMESİ",
            ParagraphStyle("c2", parent=CENTER, fontName=BOLD, fontSize=13, leading=20)),
          Spacer(1, 16 * mm),
          P("Sözleşme No: ADL-2024/117", CENTER),
          P("Düzenlenme Tarihi: 12 Şubat 2024", CENTER),
          Spacer(1, 30 * mm),
          P("Bu belge test amaçlı üretilmiştir. İçeriğindeki kurum, kişi ve "
            "tutarlar gerçek değildir.", ParagraphStyle(
                "c3", parent=CENTER, fontSize=8, textColor=colors.grey)),
          PageBreak()]

    # ---------------------------------------------------------- 2. İÇİNDEKİLER
    s += [P("İÇİNDEKİLER", H1)]
    toc = [["Bölüm", "Konu", "Sayfa"]]
    for no, ad, sf in [
        ("BÖLÜM 1", "Tanımlar ve Kısaltmalar", "3"),
        ("MADDE 1-3", "Taraflar, Konu ve Kapsam", "4"),
        ("MADDE 4", "Sözleşme Süresi ve İşe Başlama", "5"),
        ("MADDE 5", "Sözleşme Bedeli ve Ödeme Koşulları", "6"),
        ("EK TABLO", "Aylık Hakediş Planı", "7"),
        ("MADDE 6", "Personel Yapısı ve Ücretlendirme", "8"),
        ("MADDE 7", "Çalışma Düzeni ve Vardiyalar", "9"),
        ("MADDE 8", "Ekipman ve Araç Envanteri", "10"),
        ("ŞEMA", "Sevkiyat İş Akışı", "11"),
        ("MADDE 9", "Periyodik Bakım Programı", "12"),
        ("MADDE 10", "Cezai Şartlar", "13"),
        ("MADDE 11", "Teminat ve Sigorta", "14"),
        ("MADDE 12", "İş Sağlığı ve Güvenliği", "15"),
        ("MADDE 13", "Sosyal Haklar", "16"),
        ("MADDE 14", "Gizlilik ve Veri Koruma", "17"),
        ("MADDE 15", "Fesih ve Uyuşmazlık", "18"),
        ("EK-1", "Depo Ortam Ölçüm Değerleri", "19"),
        ("EK-2", "Özet Bilgi Kartı", "20"),
    ]:
        toc.append([no, ad, sf])
    s += [T(toc, [30 * mm, 105 * mm, 20 * mm]), PageBreak()]

    # ---------------------------------------------------------- 3. TANIMLAR
    s += [P("BÖLÜM 1 — TANIMLAR VE KISALTMALAR", H1),
          P("1.1. Bu sözleşmede geçen terimler aşağıdaki anlamları taşır.", BODY)]
    tanim = [["Terim", "Tanım"]]
    for a, b in [
        ("İDARE", "Aydın Lojistik ve Depolama A.Ş."),
        ("YÜKLENİCİ", "Sözleşmeyi imzalayan Karabük Tesis Hizmetleri Ltd. Şti."),
        ("MERKEZ DEPO", "Aydın ili Efeler ilçesinde bulunan 18.400 m² kapalı alan"),
        ("SEVKİYAT", "Depodan çıkan ürünün araca yüklenip yola çıkarılması"),
        ("HAKEDİŞ", "Aylık olarak düzenlenen ve ödemeye esas olan belge"),
        ("KRİTİK STOK", "Asgari 500 palet altına düşen ürün seviyesi"),
        ("VARDİYA", "Sekiz saatlik kesintisiz çalışma dilimi"),
        ("ARIZA SÜRESİ", "Ekipmanın devre dışı kaldığı toplam dakika"),
        ("SGK", "Sosyal Güvenlik Kurumu"),
        ("İSG", "İş Sağlığı ve Güvenliği"),
    ]:
        tanim.append([a, b])
    s += [T(tanim, [35 * mm, 120 * mm]),
          Spacer(1, 4 * mm),
          P("1.2. Bu sözleşmede geçen tüm parasal tutarlar Türk Lirası (TL) "
            "cinsindendir ve aksi belirtilmedikçe <b>KDV hariçtir</b>.", BODY),
          PageBreak()]

    # ---------------------------------------------------------- 4. TARAFLAR
    s += [P("MADDE 1 — SÖZLEŞMENİN TARAFLARI", H2),
          P("1.1. Bu sözleşme, Aydın Lojistik ve Depolama A.Ş. (bundan sonra "
            "İDARE olarak anılacaktır) ile Karabük Tesis Hizmetleri Ltd. Şti. "
            "(bundan sonra YÜKLENİCİ olarak anılacaktır) arasında aşağıdaki "
            "şartlarda akdedilmiştir.", BODY),
          P("1.2. İDARE'nin adresi Efeler/Aydın, YÜKLENİCİ'nin adresi "
            "Merkez/Karabük olarak kayıtlıdır. Tebligatlar bu adreslere yapılır.", BODY),
          P("MADDE 2 — SÖZLEŞMENİN KONUSU", H2),
          P("2.1. Sözleşmenin konusu, İDARE'ye ait Merkez Depo tesisinde "
            "depolama, iç lojistik, sevkiyat hazırlığı ve periyodik bakım "
            "hizmetlerinin toplam <b>34 kişi</b> ile yürütülmesidir.", BODY),
          P("2.2. Hizmet kapsamına ürün kabul, adresleme, sayım, sipariş "
            "toplama, paketleme, sevkiyat hazırlığı ve depo içi temizlik "
            "faaliyetleri dahildir.", BODY),
          P("2.3. Depo dışı karayolu taşımacılığı bu sözleşmenin kapsamı "
            "DIŞINDADIR ve ayrı bir sözleşmeye konu edilir.", BODY),
          P("MADDE 3 — KAPSAM DIŞI İŞLER", H2),
          P("3.1. Gümrük işlemleri, ihracat evrak hazırlığı ve uluslararası "
            "taşıma organizasyonu bu sözleşme kapsamında değildir.", BODY),
          P("3.2. Deponun çatı, cephe ve altyapı onarımları İDARE "
            "sorumluluğundadır.", BODY),
          PageBreak()]

    # ---------------------------------------------------------- 5. SÜRE
    s += [P("MADDE 4 — SÖZLEŞME SÜRESİ VE İŞE BAŞLAMA", H2),
          P("4.1. <b>01/03/2024</b> tarihinde işe başlanacak olup işin süresi, "
            "işe başlama tarihinden itibaren <b>18 (onsekiz) aydır</b>.", BODY),
          P("4.2. Sözleşme süresinin bitiminde, İDARE'nin uygun görmesi ve "
            "YÜKLENİCİ'nin kabul etmesi kaydıyla, aynı fiyat ve şartlarla en "
            "fazla 6 (altı) aya kadar, bir defadan fazla olmamak üzere süre "
            "uzatımı yapılabilir.", BODY),
          P("4.3. Süre uzatımı, tarafların yetkililerince imzalanacak bir ek "
            "protokol ile yürürlüğe girer. Sözlü mutabakat geçerli değildir.", BODY),
          P("4.4. YÜKLENİCİ, işe başlama tarihinden en az 10 (on) gün önce "
            "personel listesini ve SGK kayıtlarını İDARE'ye sunmak zorundadır.", BODY),
          P("4.5. Mücbir sebep hâllerinde geçen süre, sözleşme süresine "
            "eklenmez; bu süre boyunca karşılıklı yükümlülükler askıya alınır.", BODY),
          PageBreak()]

    # ---------------------------------------------------------- 6. BEDEL
    s += [P("MADDE 5 — SÖZLEŞME BEDELİ VE ÖDEME KOŞULLARI", H2),
          P("5.1. İşin toplam sözleşme bedeli <b>24.750.000,00 TL</b> "
            "(yirmidörtmilyonyediyüzellibin Türk Lirası) olup bu tutar "
            "<b>KDV hariçtir</b>.", BODY),
          P("5.2. Ödemeler aylık hakediş esasına göre yapılır. Hakediş "
            "belgesi, hizmetin verildiği ayı takip eden ayın ilk 5 (beş) iş "
            "günü içinde YÜKLENİCİ tarafından düzenlenir.", BODY),
          P("5.3. İDARE, hakediş belgesini teslim aldıktan sonra 15 (onbeş) "
            "gün içinde inceler ve uygun bulması hâlinde 30 (otuz) gün içinde "
            "ödemeyi gerçekleştirir.", BODY),
          P("5.4. YÜKLENİCİ'nin SGK ve vergi borcu bulunması hâlinde, borç "
            "tutarı hakedişten kesilerek ilgili kuruma doğrudan yatırılır.", BODY),
          P("5.5. Bu iş için <b>avans verilmeyecektir</b>.", BODY),
          P("5.6. Fiyat farkı, yıllık olarak TÜİK tarafından açıklanan yurt "
            "içi ÜFE oranının %80'i uygulanarak hesaplanır.", BODY),
          PageBreak()]

    # ---------------------------------------------------------- 7. HAKEDİŞ TABLOSU
    s += [P("EK TABLO — AYLIK HAKEDİŞ PLANI", H1),
          P("Aşağıdaki tablo, sözleşme süresi boyunca öngörülen aylık hakediş "
            "tutarlarını göstermektedir. Tutarlar KDV hariçtir.", BODY)]
    hak = [["Dönem", "Açıklama", "Personel", "Tutar (TL)"]]
    veri = [
        ("03/2024", "Kuruluş ve devir dönemi", "28", "1.185.400,00"),
        ("04/2024", "Tam kapasite", "34", "1.372.500,00"),
        ("05/2024", "Tam kapasite", "34", "1.372.500,00"),
        ("06/2024", "Yaz sezonu ek vardiya", "38", "1.548.750,00"),
        ("07/2024", "Yaz sezonu ek vardiya", "38", "1.548.750,00"),
        ("08/2024", "Yaz sezonu ek vardiya", "38", "1.548.750,00"),
        ("09/2024", "Tam kapasite", "34", "1.372.500,00"),
        ("10/2024", "Tam kapasite", "34", "1.372.500,00"),
        ("11/2024", "Envanter sayım dönemi", "36", "1.455.200,00"),
        ("12/2024", "Yıl sonu kapanış", "36", "1.455.200,00"),
        ("01/2025", "Tam kapasite", "34", "1.372.500,00"),
        ("02/2025", "Tam kapasite", "34", "1.372.500,00"),
    ]
    for r in veri:
        hak.append(list(r))
    s += [T(hak, [25 * mm, 62 * mm, 25 * mm, 33 * mm]),
          Spacer(1, 4 * mm),
          P("Not: 06/2024–08/2024 döneminde ek vardiya nedeniyle personel "
            "sayısı geçici olarak 38'e çıkarılmıştır.", SMALL),
          PageBreak()]

    # ---------------------------------------------------------- 8. PERSONEL
    s += [P("MADDE 6 — PERSONEL YAPISI VE ÜCRETLENDİRME", H2),
          P("6.1. İşin yürütülmesinde toplam <b>34 kişi</b> görevlendirilecek "
            "olup unvanlara göre dağılım aşağıdaki gibidir.", BODY)]
    per = [["Unvan", "Kişi", "Ücret (asgari ücretin yüzde fazlası)"]]
    for a, b, c in [
        ("Depo Müdürü", "1", "% 145 fazlası"),
        ("Vardiya Amiri", "3", "% 95 fazlası"),
        ("Tekniker", "4", "% 75 fazlası"),
        ("Forklift Operatörü", "8", "% 55 fazlası"),
        ("Depo Görevlisi", "16", "% 30 fazlası"),
        ("İSG Uzmanı", "1", "% 110 fazlası"),
        ("İdari Personel", "1", "% 40 fazlası"),
    ]:
        per.append([a, b, c])
    s += [T(per, [50 * mm, 20 * mm, 70 * mm]),
          Spacer(1, 3 * mm),
          P("6.2. Yukarıdaki oranlar brüt asgari ücret üzerinden hesaplanır ve "
            "her yıl asgari ücret artışına paralel olarak güncellenir.", BODY),
          P("6.3. YÜKLENİCİ, personel ücretlerini en geç izleyen ayın "
            "<b>7'nci günü</b> mesai bitimine kadar banka hesaplarına yatırmak "
            "zorundadır.", BODY),
          P("6.4. Personel değişikliklerinde İDARE'nin yazılı onayı alınır. "
            "Onaysız personel değişikliği sözleşmeye aykırılık teşkil eder.", BODY),
          PageBreak()]

    # ---------------------------------------------------------- 9. VARDİYA
    s += [P("MADDE 7 — ÇALIŞMA DÜZENİ VE VARDİYALAR", H2),
          P("7.1. Depo <b>üç vardiya</b> hâlinde kesintisiz çalışır. Vardiya "
            "saatleri aşağıdaki tabloda gösterilmiştir.", BODY)]
    vard = [["Vardiya", "Başlangıç", "Bitiş", "Personel", "Ara Dinlenme"]]
    for r in [("1. Vardiya", "08:00", "16:00", "16", "45 dakika"),
              ("2. Vardiya", "16:00", "24:00", "12", "45 dakika"),
              ("3. Vardiya", "24:00", "08:00", "6", "60 dakika")]:
        vard.append(list(r))
    s += [T(vard, [28 * mm, 25 * mm, 25 * mm, 25 * mm, 32 * mm]),
          Spacer(1, 3 * mm),
          P("7.2. Haftalık çalışma süresi 45 saati aşamaz.", BODY),
          P("7.3. <b>Fazla mesai çalışması yaptırılmayacaktır.</b> Zorunlu "
            "hâllerde haftalık 45 saati aşan çalışma yapılması durumunda, "
            "her 7,5 saatlik fazla çalışma karşılığında personele "
            "<b>1 (bir) gün ücretli izin</b> verilir. Fazla çalışma için "
            "ayrıca nakit ödeme yapılmaz.", BODY),
          P("7.4. Ulusal bayram ve genel tatil günlerinde çalışma yapılması "
            "hâlinde, 4857 sayılı İş Kanunu hükümleri uygulanır.", BODY),
          P("7.5. Yıllık izinler, depo yoğunluğu dikkate alınarak İDARE'nin "
            "onayıyla planlanır. Haziran–Ağustos döneminde toplu izin "
            "kullandırılmaz.", BODY),
          PageBreak()]

    # ---------------------------------------------------------- 10. EKİPMAN
    s += [P("MADDE 8 — EKİPMAN VE ARAÇ ENVANTERİ", H2),
          P("8.1. İşin yürütülmesinde kullanılacak ekipmanlar ve garanti "
            "süreleri aşağıdadır. Ekipmanlar İDARE tarafından sağlanır.", BODY)]
    ekip = [["Kod", "Ekipman", "Adet", "Garanti", "Yıllık Bakım (TL)"]]
    for r in [("FL-220", "Akülü forklift 2,2 ton", "6", "24 ay", "48.600,00"),
              ("FL-350", "Dizel forklift 3,5 ton", "2", "36 ay", "72.400,00"),
              ("TR-120", "Transpalet elektrikli", "9", "12 ay", "16.200,00"),
              ("KP-075", "Vidalı kompresör 75 kW", "1", "24 ay", "94.800,00"),
              ("JN-400", "Jeneratör 400 kVA", "1", "60 ay", "128.500,00"),
              ("RF-050", "El terminali (RF)", "22", "12 ay", "9.350,00")]:
        ekip.append(list(r))
    s += [T(ekip, [20 * mm, 55 * mm, 18 * mm, 22 * mm, 35 * mm]),
          Spacer(1, 3 * mm),
          P("8.2. Ekipmanların günlük kontrolü vardiya amiri tarafından yapılır "
            "ve kontrol formu imzalanarak arşivlenir.", BODY),
          P("8.3. Arıza hâlinde YÜKLENİCİ, arızayı <b>2 saat</b> içinde "
            "İDARE'ye bildirmekle yükümlüdür.", BODY),
          PageBreak()]

    # ---------------------------------------------------------- 11. ŞEMA
    s += [P("ŞEMA 1 — SEVKİYAT İŞ AKIŞI", H1),
          P("Sipariş alındıktan sonra izlenen adımlar aşağıdaki akışta "
            "gösterilmiştir. Her adımın sorumlusu parantez içinde belirtilmiştir.", BODY),
          Spacer(1, 5 * mm)]
    akis = [
        ("1", "SİPARİŞ ALIMI", "Sipariş sisteme düşer (İdari Personel)"),
        ("2", "STOK KONTROLÜ", "Kritik stok seviyesi denetlenir (Vardiya Amiri)"),
        ("3", "TOPLAMA", "RF terminal ile ürün toplanır (Depo Görevlisi)"),
        ("4", "KONTROL", "Miktar ve parti numarası doğrulanır (Tekniker)"),
        ("5", "PAKETLEME", "Palet sarılır ve etiketlenir (Depo Görevlisi)"),
        ("6", "YÜKLEME", "Forklift ile araca yüklenir (Forklift Operatörü)"),
        ("7", "SEVK", "İrsaliye kesilir ve araç çıkar (Vardiya Amiri)"),
    ]
    for no, ad, aciklama in akis:
        s += [T([[f"ADIM {no}", ad, aciklama]], [22 * mm, 45 * mm, 88 * mm])]
        if no != "7":
            s += [P("▼", ParagraphStyle("arw", parent=CENTER, fontSize=10,
                                        textColor=colors.HexColor("#2E4C6E"),
                                        spaceBefore=1, spaceAfter=1))]
    s += [Spacer(1, 4 * mm),
          P("Toplama adımından sevk adımına kadar geçen hedef süre "
            "<b>90 dakikadır</b>. Bu süre aşıldığında vardiya amiri gerekçe "
            "raporu düzenler.", BODY),
          PageBreak()]

    # ---------------------------------------------------------- 12. BAKIM
    s += [P("MADDE 9 — PERİYODİK BAKIM PROGRAMI", H2),
          P("9.1. Ekipmanların periyodik bakımları aşağıdaki tabloda "
            "belirtilen aralıklarla yapılır.", BODY)]
    bak = [["Ekipman", "Bakım Periyodu", "Süre", "Sorumlu"]]
    for r in [("Vidalı kompresör", "500 çalışma saati", "4 saat", "Tekniker"),
              ("Akülü forklift", "250 çalışma saati", "2 saat", "Tekniker"),
              ("Dizel forklift", "300 çalışma saati", "3 saat", "Yetkili servis"),
              ("Jeneratör", "6 ayda bir", "6 saat", "Yetkili servis"),
              ("Yangın sistemi", "3 ayda bir", "8 saat", "Yetkili servis"),
              ("RF terminal", "Yılda bir", "1 saat", "Tekniker")]:
        bak.append(list(r))
    s += [T(bak, [45 * mm, 42 * mm, 25 * mm, 38 * mm]),
          Spacer(1, 3 * mm),
          P("9.2. Bakım kayıtları elektronik ortamda tutulur ve İDARE'nin "
            "erişimine açık olur.", BODY),
          P("9.3. Planlı bakımlar, depo faaliyetini aksatmayacak şekilde "
            "3. vardiya saatlerinde yapılır.", BODY),
          PageBreak()]

    # ---------------------------------------------------------- 13. CEZALAR
    s += [P("MADDE 10 — CEZAİ ŞARTLAR", H2),
          P("10.1. YÜKLENİCİ'nin sözleşmeye aykırı davranışları hâlinde "
            "aşağıdaki cezalar uygulanır. Cezalar hakedişten kesilir.", BODY),
          P("10.2. YÜKLENİCİ'nin, işin başlangıcında sunması gereken belgeleri "
            "süresi içinde vermemesi durumunda, geciken her gün için sözleşme "
            "bedelinin <b>onbinde beş (0,0005)</b> oranında ceza uygulanır.", BODY),
          P("10.3. YÜKLENİCİ'nin, çalışan ücretlerini 6.3 maddesinde belirtilen "
            "süre içinde yatırmaması hâlinde, sözleşme bedeli ile "
            "<b>yüzbinde üç (0,00003)</b> ceza oranı çarpılarak bir çalışan "
            "için bir günlük ceza tutarı hesaplanır. Bu tutar, ücreti geciken "
            "çalışan sayısı ve gecikme günü ile çarpılarak uygulanır.", BODY),
          P("10.4. Gizlilik yükümlülüğünün ihlali hâlinde, sözleşme bedelinin "
            "<b>yüzde ikisi (%2)</b> oranında tek seferlik ceza uygulanır.", BODY),
          P("10.5. Onaysız personel değişikliği yapılması hâlinde, her bir "
            "personel için <b>15.000,00 TL</b> ceza uygulanır.", BODY),
          P("10.6. Toplam ceza tutarı sözleşme bedelinin %10'unu aştığında "
            "İDARE sözleşmeyi tek taraflı feshedebilir.", BODY),
          PageBreak()]

    # ---------------------------------------------------------- 14. TEMİNAT
    s += [P("MADDE 11 — TEMİNAT VE SİGORTA", H2),
          P("11.1. YÜKLENİCİ, sözleşme bedelinin <b>%6'sı</b> oranında kesin "
            "teminat mektubu verir. Teminat mektubu süresiz olmalıdır.", BODY),
          P("11.2. Teminat, işin kabulünden ve SGK ilişiksizlik belgesinin "
            "ibrazından sonra iade edilir.", BODY),
          P("11.3. YÜKLENİCİ, üçüncü şahıslara verilebilecek zararlara karşı "
            "asgari <b>5.000.000,00 TL</b> teminatlı sorumluluk sigortası "
            "yaptırmak zorundadır.", BODY),
          P("11.4. Emtia sigortası İDARE tarafından yaptırılır; YÜKLENİCİ'nin "
            "bu konuda yükümlülüğü yoktur.", BODY),
          PageBreak()]

    # ---------------------------------------------------------- 15. İSG
    s += [P("MADDE 12 — İŞ SAĞLIĞI VE GÜVENLİĞİ", H2),
          P("12.1. İşin görüleceği yer <b>tehlikeli işler</b> sınıfında olup "
            "YÜKLENİCİ, 6331 sayılı Kanun kapsamındaki tüm yükümlülükleri "
            "yerine getirir.", BODY),
          P("12.2. YÜKLENİCİ, tam zamanlı <b>1 (bir) İSG uzmanı</b> "
            "görevlendirmek zorundadır.", BODY),
          P("12.3. Tüm personele işe başlamadan önce en az <b>16 saat</b> "
            "temel İSG eğitimi verilir; eğitim kayıtları saklanır.", BODY),
          P("12.4. Kişisel koruyucu donanımlar (baret, çelik burunlu ayakkabı, "
            "reflektörlü yelek, iş eldiveni) YÜKLENİCİ tarafından karşılanır "
            "ve <b>6 ayda bir</b> yenilenir.", BODY),
          P("12.5. İş kazası hâlinde İDARE derhal bilgilendirilir ve 24 saat "
            "içinde yazılı rapor sunulur.", BODY),
          PageBreak()]

    # ---------------------------------------------------------- 16. SOSYAL HAKLAR
    s += [P("MADDE 13 — SOSYAL HAKLAR", H2),
          P("13.1. Personele her fiilî çalışma günü için <b>145,00 TL</b> "
            "tutarında nakdî <b>yemek bedeli</b> ödenir. Yemek bedeli maaş "
            "bordrosunda ayrı kalem olarak gösterilir.", BODY),
          P("13.2. Personelin işyerine ulaşımı için <b>servis aracı "
            "sağlanacaktır</b>. Servis hizmeti YÜKLENİCİ tarafından karşılanır "
            "ve personelden ücret talep edilemez.", BODY),
          P("13.3. Servis güzergâhı, personel ikamet adresleri dikkate "
            "alınarak İDARE onayıyla belirlenir. Güzergâh değişiklikleri en az "
            "7 gün önceden duyurulur.", BODY),
          P("13.4. Personele yılda <b>2 (iki) takım</b> iş kıyafeti verilir.", BODY),
          P("13.5. Eşinin doğum yapması hâlinde personele 5 gün, birinci "
            "derece yakınının vefatı hâlinde 3 gün ücretli izin verilir.", BODY),
          PageBreak()]

    # ---------------------------------------------------------- 17. GİZLİLİK
    s += [P("MADDE 14 — GİZLİLİK VE VERİ KORUMA", H2),
          P("14.1. YÜKLENİCİ, İDARE'ye ait stok, müşteri ve fiyat bilgilerini "
            "gizli tutmakla yükümlüdür. Bu yükümlülük sözleşme sona erdikten "
            "sonra <b>5 (beş) yıl</b> devam eder.", BODY),
          P("14.2. Personel, işe başlamadan önce gizlilik taahhütnamesi imzalar.", BODY),
          P("14.3. Depo alanında YÜKLENİCİ personelinin fotoğraf veya video "
            "çekmesi yasaktır.", BODY),
          P("14.4. Kişisel verilerin işlenmesinde 6698 sayılı Kanun hükümleri "
            "uygulanır. YÜKLENİCİ veri işleyen sıfatıyla hareket eder.", BODY),
          PageBreak()]

    # ---------------------------------------------------------- 18. FESİH
    s += [P("MADDE 15 — FESİH VE UYUŞMAZLIK", H2),
          P("15.1. Taraflar, <b>30 (otuz) gün</b> önceden yazılı bildirimde "
            "bulunmak kaydıyla sözleşmeyi feshedebilir.", BODY),
          P("15.2. YÜKLENİCİ'nin ağır kusuru hâlinde İDARE, ihbar süresi "
            "beklemeksizin sözleşmeyi derhal feshedebilir ve teminatı gelir "
            "kaydeder.", BODY),
          P("15.3. Fesih hâlinde YÜKLENİCİ, devir işlemlerini 15 gün içinde "
            "tamamlar.", BODY),
          P("15.4. Bu sözleşmeden doğacak uyuşmazlıklarda <b>Aydın "
            "mahkemeleri ve icra daireleri</b> yetkilidir.", BODY),
          P("15.5. Sözleşme 15 madde ve 2 ekten ibaret olup taraflarca "
            "12/02/2024 tarihinde imzalanmıştır.", BODY),
          PageBreak()]

    # ---------------------------------------------------------- 19. EK-1
    s += [P("EK-1 — DEPO ORTAM ÖLÇÜM DEĞERLERİ", H1),
          P("Depo bölümlerinde sağlanması gereken ortam koşulları aşağıdadır. "
            "Ölçümler günde iki kez kaydedilir.", BODY)]
    olcum = [["Bölüm", "Sıcaklık (°C)", "Nem (%)", "Aydınlatma (lux)", "Ölçüm Sıklığı"]]
    for r in [("Genel depolama", "18 - 24", "45 - 60", "200", "Günde 2 kez"),
              ("Soğuk oda", "2 - 8", "80 - 90", "150", "Saatte 1 kez"),
              ("Kimyasal deposu", "15 - 22", "40 - 55", "300", "Günde 2 kez"),
              ("Sevkiyat alanı", "16 - 26", "40 - 65", "250", "Günde 1 kez"),
              ("Ofis alanı", "20 - 24", "40 - 60", "500", "Haftada 1 kez")]:
        olcum.append(list(r))
    s += [T(olcum, [38 * mm, 28 * mm, 24 * mm, 32 * mm, 30 * mm]),
          Spacer(1, 4 * mm),
          P("Ölçüm değerlerinin sınır dışına çıkması hâlinde vardiya amiri "
            "derhal müdahale eder ve olay kaydı oluşturur.", BODY),
          PageBreak()]

    # ---------------------------------------------------------- 20. EK-2
    s += [P("EK-2 — ÖZET BİLGİ KARTI", H1),
          P("Sözleşmenin temel bilgileri hızlı erişim için aşağıda "
            "özetlenmiştir.", BODY)]
    ozet = [["Bilgi", "Değer"]]
    for a, b in [
        ("Sözleşme No", "ADL-2024/117"),
        ("Sözleşme Bedeli", "24.750.000,00 TL (KDV hariç)"),
        ("İşe Başlama Tarihi", "01/03/2024"),
        ("Süre", "18 ay"),
        ("Azami Süre Uzatımı", "6 ay"),
        ("Toplam Personel", "34 kişi"),
        ("Vardiya Sayısı", "3"),
        ("Kesin Teminat Oranı", "% 6"),
        ("Günlük Yemek Bedeli", "145,00 TL"),
        ("Fesih İhbar Süresi", "30 gün"),
        ("Yetkili Mahkeme", "Aydın"),
    ]:
        ozet.append([a, b])
    s += [T(ozet, [55 * mm, 90 * mm]),
          Spacer(1, 8 * mm),
          P("İDARE                                              YÜKLENİCİ", CENTER),
          P("Aydın Lojistik ve Depolama A.Ş.        Karabük Tesis Hizmetleri Ltd. Şti.",
            SMALL)]
    return s


# --------------------------------------------------------------------- üretim

def page_footer(canvas, doc):
    canvas.saveState()
    canvas.setFont(BASE, 7.5)
    canvas.setFillColor(colors.HexColor("#7A8794"))
    canvas.drawString(20 * mm, 12 * mm, "ADL-2024/117 — Merkez Depo Hizmet Sözleşmesi")
    canvas.drawRightString(190 * mm, 12 * mm, f"Sayfa {doc.page}")
    canvas.setStrokeColor(colors.HexColor("#D5DCE4"))
    canvas.line(20 * mm, 15 * mm, 190 * mm, 15 * mm)
    canvas.restoreState()


def build_pdf(path: Path) -> None:
    doc = BaseDocTemplate(str(path), pagesize=A4,
                          leftMargin=20 * mm, rightMargin=20 * mm,
                          topMargin=18 * mm, bottomMargin=20 * mm,
                          title="Merkez Depo Hizmet Sözleşmesi",
                          author="Test Belgesi")
    frame = Frame(doc.leftMargin, doc.bottomMargin,
                  doc.width, doc.height, id="normal")
    doc.addPageTemplates([PageTemplate(id="all", frames=[frame],
                                       onPage=page_footer)])
    doc.build(build_story())


def build_scanned(src_pdf: Path, out_pdf: Path, pages=(6, 7, 12)) -> None:
    """
    Belirtilen sayfaları görüntüye çevirip metin katmanı OLMAYAN bir PDF
    üretir — OCR yolunu test etmek için. Hafif gürültü ve eğiklik eklenir;
    gerçek fotokopi çıktısına benzemesi kasıtlıdır.
    """
    try:
        import pypdfium2 as pdfium
        from PIL import Image
    except ImportError:
        print("  ! pypdfium2/Pillow yok, taranmış sürüm üretilemedi.")
        return

    pdf = pdfium.PdfDocument(str(src_pdf))
    images = []
    random.seed(7)
    for pno in pages:
        page = pdf[pno - 1]
        img = page.render(scale=200 / 72, grayscale=True).to_pil()
        img = img.rotate(random.uniform(-0.6, 0.6), resample=Image.BICUBIC,
                         fillcolor=250, expand=False)
        px = img.load()
        w, h = img.size
        for _ in range(int(w * h * 0.015)):
            x, y = random.randrange(w), random.randrange(h)
            px[x, y] = max(0, min(255, px[x, y] + random.randint(-60, 45)))
        images.append(img.convert("L"))
    pdf.close()

    if images:
        images[0].save(str(out_pdf), "PDF", resolution=150.0,
                       save_all=True, append_images=images[1:])


def main() -> int:
    ap = argparse.ArgumentParser(description="Test belgesi üretici")
    ap.add_argument("--out", default="ornek_belgeler", help="Hedef klasör")
    args = ap.parse_args()

    root = Path(__file__).resolve().parent.parent
    out_dir = (root / args.out) if not Path(args.out).is_absolute() else Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    # İki ayrı alt klasör: dijital ve taranmış sürümler ayrı ayrı
    # indekslenebilsin. Aynı içerik hem temiz hem bozuk hâlde indekste
    # bulunursa hangi hatanın nereden geldiği ölçülemez.
    dij_dir = out_dir / "dijital"
    tar_dir = out_dir / "taranmis"
    dij_dir.mkdir(parents=True, exist_ok=True)
    tar_dir.mkdir(parents=True, exist_ok=True)
    digital = dij_dir / "depo_sozlesmesi.pdf"
    scanned = tar_dir / "depo_ekler_taranmis.pdf"

    print(f"\nYazı tipi: {BASE}")
    print("Dijital sözleşme üretiliyor...")
    build_pdf(digital)
    print(f"  ✔ {digital}")

    print("Taranmış ek üretiliyor (OCR testi için)...")
    build_scanned(digital, scanned, pages=(7, 8, 13))
    if scanned.exists():
        print(f"  ✔ {scanned}")

    print("\n" + "=" * 66)
    print("  1. TUR — yalnızca dijital belge (saf RAG ölçümü)")
    print("=" * 66)
    print(f"  python -m src.ingest --rebuild --path {args.out}/dijital")
    print("  python eval/run_eval.py --testset eval/testset_depo.yaml")
    print("\n" + "=" * 66)
    print("  2. TUR — taranmış sürüm de eklenir (OCR etkisi ölçülür)")
    print("=" * 66)
    print(f"  python -m src.ingest --rebuild --path {args.out}")
    print("  python eval/run_eval.py --testset eval/testset_depo.yaml")
    print("\n  Gerçek belgelerine dönmek için:  python -m src.ingest --rebuild")
    return 0


if __name__ == "__main__":
    sys.exit(main())
