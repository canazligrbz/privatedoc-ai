"""
BU BETİK YALNIZCA İNTERNETLİ (STAGING) MAKİNEDE ÇALIŞTIRILIR.
=============================================================

Air-gap makineye taşınacak tüm yapay zekâ modellerini indirir ve
`models/` klasörüne, çevrimdışı yüklenebilir formatta yerleştirir.

Kullanım (internetli makine):
    python scripts/download_models.py --out models
    python scripts/download_models.py --out models --with-reranker

╔══════════════════════════════════════════════════════════════════════╗
║  UYARI — BU BETİK İÇİN PAKET YÜKSELTMEYİN                            ║
║                                                                      ║
║  Bu dosyanın eski hâli şunu söylüyordu:                              ║
║      pip install -U "huggingface_hub>=0.25" sentence-transformers    ║
║                                                                      ║
║  Bu komut proje sanal ortamında çalıştırıldığında sentence-          ║
║  transformers'ı 6.x'e, transformers'ı 5.x'e yükseltti. İkisi de      ║
║  torch >= 2.5 istiyor; proje torch 2.4.1'e sabitli. Sonuç:           ║
║  "name 'torch' is not defined" ve embedding tamamen çalışmaz hâle    ║
║  geldi — indeksleme sıfır parça üretti.                              ║
║                                                                      ║
║  Bu betik zaten projenin kendi bağımlılıklarıyla çalışır. Ek kurulum ║
║  GEREKMEZ. Yeni bir ortamda çalıştırıyorsanız sürümleri SABİTLEYİN:  ║
║      pip install -r requirements.txt                                 ║
╚══════════════════════════════════════════════════════════════════════╝

Sonra `models/` klasörünü USB/onaylı transfer yöntemiyle air-gap makineye
kopyalayın. Air-gap makinede bu betik ÇALIŞTIRILMAZ.
"""

from __future__ import annotations

import argparse

import json

import sys
from pathlib import Path

# Bu dosyaya özel: air-gap koruması İSTEYEREK devre dışıdır (indirme makinesi).
MODELS = {
    "bge-m3": {
        "repo": "BAAI/bge-m3",
        "desc": "Çok dilli embedding (Türkçe güçlü, 1024 boyut) — VARSAYILAN",
        "allow": ["*.json", "*.txt", "*.md", "*.model",
                  "pytorch_model.bin", "model.safetensors",
                  "1_Pooling/*", "sentence_bert_config.json",
                  "tokenizer*", "special_tokens_map.json", "modules.json"],
        "size": "~2.3 GB",
    },
    "multilingual-e5-large": {
        "repo": "intfloat/multilingual-e5-large",
        "desc": "Yedek embedding modeli (prefix gerektirir: 'query: ' / 'passage: ')",
        "allow": ["*.json", "*.txt", "*.model", "model.safetensors",
                  "pytorch_model.bin", "1_Pooling/*", "tokenizer*", "modules.json"],
        "size": "~2.2 GB",
    },
    "multilingual-e5-small": {
        "repo": "intfloat/multilingual-e5-small",
        "desc": "Zayıf donanım için küçük embedding (384 boyut)",
        "allow": ["*.json", "*.txt", "*.model", "model.safetensors",
                  "pytorch_model.bin", "1_Pooling/*", "tokenizer*", "modules.json"],
        "size": "~470 MB",
    },
    "bge-reranker-v2-m3": {
        "repo": "BAAI/bge-reranker-v2-m3",
        "desc": "Cross-encoder yeniden sıralayıcı (opsiyonel, doğruluğu artırır)",
        "allow": ["*.json", "*.txt", "*.model", "model.safetensors",
                  "pytorch_model.bin", "tokenizer*"],
        "size": "~2.3 GB",
    },
}


def download(name: str, out_root: Path, force: bool = False) -> Path:
    from huggingface_hub import snapshot_download

    spec = MODELS[name]
    target = out_root / name
    # ZATEN İNDİRİLMİŞ MODELİ TEKRAR ÇEKME.
    # --with-reranker bayrağı embedding modelini de listeye aldığı için,
    # yalnızca reranker eklemek isteyen kullanıcı 2,3 GB'ı boşuna indiriyordu.
    # Ağırlık dosyası iki addan biriyle gelir; yalnızca birine bakmak yetmez
    # (bge-m3 pytorch_model.bin, çoğu yeni model model.safetensors kullanır).
    agirlik_var = any(target.rglob("*.safetensors")) or any(target.rglob("*.bin"))
    if target.exists() and agirlik_var and not force:
        print(f"\n= {name} zaten mevcut, atlanıyor ({target})")
        print("  Yeniden indirmek için: --force")
        return target
    print(f"\n▶ {name} indiriliyor ({spec['size']}) — {spec['repo']}")
    snapshot_download(
        repo_id=spec["repo"],
        local_dir=str(target),
        local_dir_use_symlinks=False,   # air-gap transferi için gerçek dosyalar şart
        allow_patterns=spec["allow"],
        ignore_patterns=["*.onnx", "*.h5", "*.ot", "*.msgpack", "onnx/*"],
    )
    print(f"  ✔ {target}")
    return target


def verify_load(path: Path) -> bool:
    """İndirilen modelin çevrimdışı yüklenebildiğini staging'de doğrular."""
    try:
        from sentence_transformers import SentenceTransformer
        m = SentenceTransformer(str(path), device="cpu")
        v = m.encode(["sözleşme kapsamında çalışacak personel sayısı"], normalize_embeddings=True)
        print(f"  ✔ Yükleme testi başarılı — vektör boyutu: {len(v[0])}")
        return True
    except Exception as exc:
        print(f"  ✖ Yükleme testi BAŞARISIZ: {exc}")
        return False


def verify_reranker(path: Path) -> bool:
    """
    Reranker bir CrossEncoder'dır, SentenceTransformer değil; ayrı doğrulanır.

    NEDEN GEREKLİ: eksik indirilmiş bir reranker, `_get_reranker()` içinde
    sessizce None döner ve sistem hiçbir uyarı vermeden reranker'sız çalışır.
    Kullanıcı "açtım ama bir şey değişmedi" durumunda kalır. Burada
    yüklenebildiği VE anlamlı sıraladığı doğrulanır.
    """
    try:
        from sentence_transformers import CrossEncoder
        m = CrossEncoder(str(path), device="cpu", local_files_only=True)
        soru = "Personele ödenecek günlük yemek bedeli ne kadardır?"
        ilgili = "Personele her fiilî çalışma günü için 145,00 TL yemek bedeli ödenir."
        alakasiz = "Depoda 12 adet güvenlik kamerası bulunmaktadır."
        s_ilgili, s_alakasiz = m.predict([(soru, ilgili), (soru, alakasiz)])
        print(f"  ✔ Yükleme testi başarılı — ilgili {s_ilgili:.3f} / "
              f"alakasız {s_alakasiz:.3f}")
        if s_ilgili <= s_alakasiz:
            print("  ✖ UYARI: ilgili parça alakasızdan yüksek puan ALMADI. "
                  "Model bozuk indirilmiş olabilir.")
            return False
        return True
    except Exception as exc:
        print(f"  ✖ Yükleme testi BAŞARISIZ: {exc}")
        return False


def _read_manifest(out_root: Path) -> list:
    try:
        data = json.loads((out_root / "MANIFEST.json").read_text(encoding="utf-8"))
        return [m for m in data.get("models", []) if m.get("name") in MODELS]
    except Exception:
        return []


def write_manifest(out_root: Path, entries: list) -> None:
    """Transfer bütünlüğü için dosya sayısı ve toplam boyut kaydı."""
    manifest = {"models": []}
    for name in entries:
        d = out_root / name
        if not d.exists():
            continue
        files = [p for p in d.rglob("*") if p.is_file()]
        total = sum(p.stat().st_size for p in files)
        manifest["models"].append({
            "name": name,
            "repo": MODELS[name]["repo"],
            "files": len(files),
            "bytes": total,
            "size_human": f"{total / 1e9:.2f} GB",
        })
    (out_root / "MANIFEST.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n📄 Bütünlük dosyası yazıldı: {out_root / 'MANIFEST.json'}")


def main() -> int:
    ap = argparse.ArgumentParser(description="Air-gap için model indirici (internetli makine)")
    ap.add_argument("--out", default="models", help="Hedef klasör")
    ap.add_argument("--embedding", default="bge-m3",
                    choices=["bge-m3", "multilingual-e5-large", "multilingual-e5-small"])
    ap.add_argument("--with-fallback", action="store_true",
                    help="Yedek embedding modelini de indir")
    ap.add_argument("--with-reranker", action="store_true",
                    help="Cross-encoder reranker'ı da indir")
    ap.add_argument("--no-verify", action="store_true")
    ap.add_argument("--force", action="store_true",
                    help="Zaten indirilmiş modeli yeniden indir")
    args = ap.parse_args()

    out_root = Path(args.out).resolve()
    out_root.mkdir(parents=True, exist_ok=True)

    todo = [args.embedding]
    if args.with_fallback and "multilingual-e5-large" not in todo:
        todo.append("multilingual-e5-large")
    if args.with_reranker:
        todo.append("bge-reranker-v2-m3")

    ok = True
    for name in todo:
        p = download(name, out_root, force=args.force)
        if args.no_verify:
            continue
        if name == "bge-reranker-v2-m3":
            ok = verify_reranker(p) and ok
        else:
            ok = verify_load(p) and ok

    # MANIFEST ÜZERİNE YAZILMAZ, BİRLEŞTİRİLİR.
    # Yalnızca reranker eklendiğinde önceki kayıtlar siliniyordu ve transfer
    # bütünlüğü dosyası eksik kalıyordu.
    mevcut = [m["name"] for m in _read_manifest(out_root)]
    write_manifest(out_root, list(dict.fromkeys(mevcut + todo)))

    print("\n" + "=" * 62)
    print("SONRAKİ ADIMLAR")
    print("=" * 62)
    print("1) LLM ağırlığını da indirin (aynı makinede):")
    print("     ollama pull qwen2.5:7b-instruct-q4_K_M")
    print("     # Windows: %USERPROFILE%\\.ollama\\models")
    print("     # Linux  : /usr/share/ollama/.ollama/models veya ~/.ollama/models")
    print("   Bu klasörü de air-gap makineye kopyalayın.")
    print("2) Python paketlerini indirin:")
    print("     pip download -r requirements.txt -d wheelhouse")
    print("     pip download torch==2.4.1 --index-url https://download.pytorch.org/whl/cpu -d wheelhouse")
    print("3) models/, wheelhouse/ ve ollama model klasörünü transfer edin.")
    print("=" * 62)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
