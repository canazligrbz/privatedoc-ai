#!/usr/bin/env bash
# =====================================================================
#  1. AŞAMA — İNTERNETLİ (STAGING) MAKİNEDE ÇALIŞTIRIN  [Linux/macOS]
#  Kullanım:  bash scripts/prepare_offline_bundle.sh
# =====================================================================
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BUNDLE="$PROJECT_ROOT/offline_bundle"
LLM_MODEL="qwen2.5:7b-instruct-q4_K_M"

echo "=== Belge Asistanı — Çevrimdışı Paket Hazırlığı ==="
mkdir -p "$BUNDLE"/{wheelhouse,models,proje}

echo "[1/5] Python paketleri indiriliyor..."
python3 -m pip download torch==2.4.1 \
    --index-url https://download.pytorch.org/whl/cpu -d "$BUNDLE/wheelhouse"
python3 -m pip download -r "$PROJECT_ROOT/requirements.txt" -d "$BUNDLE/wheelhouse"
python3 -m pip download huggingface_hub -d "$BUNDLE/wheelhouse"

echo "[2/5] Embedding modelleri indiriliyor..."
python3 "$PROJECT_ROOT/scripts/download_models.py" --out "$BUNDLE/models"

echo "[3/5] LLM ağırlıkları hazırlanıyor..."
if command -v ollama >/dev/null 2>&1; then
    ollama pull "$LLM_MODEL"
    for SRC in "$HOME/.ollama/models" "/usr/share/ollama/.ollama/models"; do
        if [ -d "$SRC" ]; then
            cp -r "$SRC" "$BUNDLE/ollama_models"
            echo "  ✔ Kopyalandı: $SRC"
            break
        fi
    done
else
    echo "  ! Ollama kurulu değil. https://ollama.com/download/linux kurulum betiğini"
    echo "    ve ollama-linux-amd64.tgz arşivini offline_bundle içine ekleyin."
fi

echo "[4/5] Proje kodu kopyalanıyor..."
cd "$PROJECT_ROOT"
cp -r src assets scripts eval web "$BUNDLE/proje/"
cp server.py config.yaml requirements.txt "$BUNDLE/proje/"
[ -f README.md ] && cp README.md "$BUNDLE/proje/"

echo "[5/5] Kurulum notu ve bütünlük özeti yazılıyor..."
cat > "$BUNDLE/KURULUM.txt" <<'EOF'
BELGE ASISTANI — AIR-GAP KURULUM ADIMLARI
=========================================
1) Python 3.11 kurun.
2) Ollama kurun ve servisi durdurun (systemctl stop ollama).
3) ollama_models/ -> /usr/share/ollama/.ollama/models altına kopyalayın,
   sahipliği düzeltin:  chown -R ollama:ollama /usr/share/ollama/.ollama
4) Ollama'yı başlatın:  systemctl start ollama && ollama list
5) proje/ -> /opt/belge-asistani olarak kopyalayın.
6) models/ -> /opt/belge-asistani/models altına kopyalayın.
7) Kurulum:
       cd /opt/belge-asistani
       python3 -m venv .venv && source .venv/bin/activate
       pip install --no-index --find-links=<USB>/offline_bundle/wheelhouse -r requirements.txt
8) Doğrulama:   python scripts/verify_offline.py
9) İndeksleme:  python -m src.ingest
10) Başlatma:   python server.py

Kurulum sonrası ağ arayüzünü kapatın:  nmcli networking off
EOF

( cd "$BUNDLE" && find . -type f ! -name SHA256SUMS -exec sha256sum {} \; > SHA256SUMS )

echo
echo "✔ Paket hazır: $BUNDLE ($(du -sh "$BUNDLE" | cut -f1))"
echo "  Transfer sonrası doğrulama:  cd offline_bundle && sha256sum -c SHA256SUMS"
