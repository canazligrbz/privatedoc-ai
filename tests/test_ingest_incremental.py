"""
ARTIMLI İNDEKSLEME (src/ingest.py → file_digest, manifest)

Artımlı indeksleme SHA-256 özetine dayanır: değişmemiş dosya yeniden
işlenmez. Bu, taranmış belgelerde saatlerce OCR'ı gereksiz yere tekrar
etmemenin tek yoludur — 28 sayfalık bir tarama her indekslemede yeniden
okunsaydı sistem kullanılamaz olurdu.

Özet mantığı bozulursa iki yönde de zarar verir:
  * çok agresif  -> değişen dosya güncellenmez, indeks bayat kalır (sessiz)
  * çok gevşek   -> her şey her seferinde yeniden işlenir (yavaş ama görünür)
İlki daha tehlikelidir; bu yüzden asıl sınanan odur.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from src.config import Config
from src.ingest import file_digest, load_manifest, save_manifest


@pytest.fixture
def klasor():
    with tempfile.TemporaryDirectory() as d:
        yield Path(d)


def test_ayni_icerik_ayni_ozet(klasor):
    a, b = klasor / "a.txt", klasor / "b.txt"
    a.write_text("aynı içerik", encoding="utf-8")
    b.write_text("aynı içerik", encoding="utf-8")
    assert file_digest(a) == file_digest(b)


def test_icerik_degisince_ozet_degisir(klasor):
    f = klasor / "a.txt"
    f.write_text("ilk hâl", encoding="utf-8")
    once = file_digest(f)
    f.write_text("değişmiş hâl", encoding="utf-8")
    assert file_digest(f) != once


def test_tek_karakter_degisikligi_yakalanir(klasor):
    """
    Sözleşmede "32 ay" -> "30 ay" gibi tek karakterlik bir düzeltme,
    yeniden indekslemeyi TETİKLEMELİ. Kaçarsa indeks sessizce bayat kalır.
    """
    f = klasor / "sozlesme.txt"
    f.write_text("İşin süresi 32 aydır.", encoding="utf-8")
    once = file_digest(f)
    f.write_text("İşin süresi 30 aydır.", encoding="utf-8")
    assert file_digest(f) != once


def test_dosya_adi_ozeti_etkilemez(klasor):
    """Özet İÇERİĞE bağlıdır; yeniden adlandırma içeriği değiştirmez."""
    a = klasor / "eski_ad.txt"
    a.write_text("içerik", encoding="utf-8")
    ozet = file_digest(a)
    yeni = klasor / "yeni_ad.txt"
    a.rename(yeni)
    assert file_digest(yeni) == ozet


def test_bos_dosya_cokmez(klasor):
    f = klasor / "bos.txt"
    f.write_bytes(b"")
    assert len(file_digest(f)) > 0


def test_manifest_gidip_geliyor(klasor):
    """Manifest yazılıp okunduğunda aynı veri dönmeli."""
    cfg = Config({"paths": {"manifest": str(klasor / "manifest.json")}})
    veri = {"a.pdf": {"hash": "abc", "chunks": 12, "pages": 3}}
    save_manifest(cfg, veri)
    assert load_manifest(cfg) == veri


def test_manifest_yoksa_bos_doner(klasor):
    cfg = Config({"paths": {"manifest": str(klasor / "yok.json")}})
    assert load_manifest(cfg) == {}


def test_bozuk_manifest_cokmez(klasor):
    """
    Yarım yazılmış bir manifest (disk doldu, süreç öldürüldü) indekslemeyi
    tamamen durdurmamalı; boş sayılıp yeniden kurulmalı.
    """
    yol = klasor / "manifest.json"
    yol.write_text("{bozuk json", encoding="utf-8")
    cfg = Config({"paths": {"manifest": str(yol)}})
    assert load_manifest(cfg) == {}


def test_degismemis_dosya_atlanir_mantigi(klasor):
    """
    ingest() içindeki karar kuralı: manifest'teki özet dosyanınkiyle
    aynıysa ve --rebuild verilmemişse dosya ATLANIR.
    """
    f = klasor / "belge.txt"
    f.write_text("içerik", encoding="utf-8")
    manifest = {"belge.txt": {"hash": file_digest(f)}}

    def atlanir_mi(rel, path, manifest, rebuild=False):
        onceki = manifest.get(rel)
        return bool(onceki and onceki.get("hash") == file_digest(path)
                    and not rebuild)

    assert atlanir_mi("belge.txt", f, manifest) is True
    assert atlanir_mi("belge.txt", f, manifest, rebuild=True) is False

    f.write_text("değişti", encoding="utf-8")
    assert atlanir_mi("belge.txt", f, manifest) is False


def test_bloklu_okuma_sinirinda_dogru_calisir(klasor):
    """
    Özet 1 MB'lık bloklar hâlinde hesaplanıyor (13 MB'lık gerçek bir sözleşme
    belleğe sığmasın diye). Blok sınırında hata olursa özet yanlış çıkar ve
    DEĞİŞEN dosya değişmemiş sanılır — kullanıcı eski belgeden cevap alır.
    """
    veri = (b"A" * (1024 * 1024)) + b"B" + (b"C" * 1024)
    a = klasor / "buyuk1.bin"
    b = klasor / "buyuk2.bin"
    kopya = klasor / "kopya.bin"
    a.write_bytes(veri)
    kopya.write_bytes(veri)
    b.write_bytes(veri[:-1] + b"D")          # yalnızca SON bayt farklı

    assert file_digest(a) == file_digest(kopya)
    assert file_digest(a) != file_digest(b)
