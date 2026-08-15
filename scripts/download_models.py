"""
BU BETİK YALNIZCA İNTERNETLİ (STAGING) MAKİNEDE ÇALIŞTIRILIR.
=============================================================

Air-gap makineye taşınacak tüm yapay zekâ modellerini indirir ve
`models/` klasörüne, çevrimdışı yüklenebilir formatta yerleştirir.

Kullanım (internetli makine):
    pip install -U "huggingface_hub>=0.25" sentence-transformers
    python scripts/download_models.py --out models
    python scripts/download_models.py --out models --with-reranker

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


def download(name: str, out_root: Path) -> Path:
    from huggingface_hub import snapshot_download

    spec = MODELS[name]
    target = out_root / name
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
        p = download(name, out_root)
        if not args.no_verify and name != "bge-reranker-v2-m3":
            ok = verify_load(p) and ok

    write_manifest(out_root, todo)

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
