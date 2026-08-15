# =====================================================================
#  1. AŞAMA — İNTERNETLİ (STAGING) MAKİNEDE ÇALIŞTIRIN  [Windows]
#  ---------------------------------------------------------------------
#  Air-gap makineye taşınacak transfer paketini hazırlar:
#    offline_bundle\
#      ├── wheelhouse\        Python paketleri (.whl)
#      ├── models\            Embedding + reranker modelleri
#      ├── ollama_models\     LLM ağırlıkları
#      ├── proje\             Kaynak kod
#      └── KURULUM.txt
#
#  Kullanım:
#      powershell -ExecutionPolicy Bypass -File scripts\prepare_offline_bundle.ps1
# =====================================================================

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$Bundle      = Join-Path $ProjectRoot "offline_bundle"
$LlmModel    = "qwen2.5:7b-instruct-q4_K_M"

Write-Host "`n=== Belge Asistanı — Çevrimdışı Paket Hazırlığı ===" -ForegroundColor Cyan
New-Item -ItemType Directory -Force -Path $Bundle | Out-Null

# ---------------------------------------------------------- 1) Python paketleri
Write-Host "`n[1/5] Python paketleri indiriliyor..." -ForegroundColor Yellow
$Wheelhouse = Join-Path $Bundle "wheelhouse"
New-Item -ItemType Directory -Force -Path $Wheelhouse | Out-Null

# CPU-only torch ayrı indeksten gelir (CUDA paketleri ~2.5 GB gereksiz yer kaplar)
python -m pip download torch==2.4.1 --index-url https://download.pytorch.org/whl/cpu -d $Wheelhouse
python -m pip download -r (Join-Path $ProjectRoot "requirements.txt") -d $Wheelhouse
python -m pip download huggingface_hub -d $Wheelhouse

# ---------------------------------------------------------- 2) Embedding modelleri
Write-Host "`n[2/5] Embedding modelleri indiriliyor..." -ForegroundColor Yellow
python (Join-Path $ProjectRoot "scripts\download_models.py") --out (Join-Path $Bundle "models")

# ---------------------------------------------------------- 3) Ollama + LLM
Write-Host "`n[3/5] LLM ağırlıkları hazırlanıyor..." -ForegroundColor Yellow
if (Get-Command ollama -ErrorAction SilentlyContinue) {
    ollama pull $LlmModel
    $Src = Join-Path $env:USERPROFILE ".ollama\models"
    if (Test-Path $Src) {
        Copy-Item -Recurse -Force $Src (Join-Path $Bundle "ollama_models")
        Write-Host "  ✔ Ollama model deposu kopyalandı." -ForegroundColor Green
    }
} else {
    Write-Host "  ! Ollama kurulu değil. https://ollama.com/download adresinden" -ForegroundColor Red
    Write-Host "    OllamaSetup.exe dosyasını indirip offline_bundle klasörüne koyun." -ForegroundColor Red
}

# ---------------------------------------------------------- 4) Proje kodu
Write-Host "`n[4/5] Proje kodu kopyalanıyor..." -ForegroundColor Yellow
$Proje = Join-Path $Bundle "proje"
New-Item -ItemType Directory -Force -Path $Proje | Out-Null
Copy-Item -Recurse -Force (Join-Path $ProjectRoot "src")      $Proje
Copy-Item -Recurse -Force (Join-Path $ProjectRoot "assets")   $Proje
Copy-Item -Recurse -Force (Join-Path $ProjectRoot "scripts")  $Proje
Copy-Item -Recurse -Force (Join-Path $ProjectRoot "eval")     $Proje
Copy-Item -Recurse -Force (Join-Path $ProjectRoot "web")      $Proje
Copy-Item -Force (Join-Path $ProjectRoot "server.py")         $Proje
Copy-Item -Force (Join-Path $ProjectRoot "config.yaml")       $Proje
Copy-Item -Force (Join-Path $ProjectRoot "requirements.txt")  $Proje
Copy-Item -Force (Join-Path $ProjectRoot "README.md")         $Proje -ErrorAction SilentlyContinue

# ---------------------------------------------------------- 5) Kurulum notu + bütünlük
Write-Host "`n[5/5] Kurulum notu ve bütünlük özeti yazılıyor..." -ForegroundColor Yellow
@"
BELGE ASISTANI — AIR-GAP KURULUM ADIMLARI
=========================================
Hazırlanma tarihi: $(Get-Date -Format 'dd.MM.yyyy HH:mm')

1) Python 3.11 kurun (python.org offline installer paket içinde olmalı).
2) Ollama kurun (OllamaSetup.exe) ve servisi durdurun.
3) ollama_models\ klasörünü %USERPROFILE%\.ollama\models altına kopyalayın.
4) Ollama'yı başlatın, kontrol edin:  ollama list
5) proje\ klasörünü C:\belge-asistani olarak kopyalayın.
6) models\ klasörünü C:\belge-asistani\models altına kopyalayın.
7) Sanal ortam ve paketler:
       cd C:\belge-asistani
       python -m venv .venv
       .venv\Scripts\activate
       pip install --no-index --find-links=<USB>\offline_bundle\wheelhouse -r requirements.txt
8) Doğrulama:
       python scripts\verify_offline.py
9) Belgeleri data\documents klasörüne koyup indeksleyin:
       python -m src.ingest
10) Uygulamayı başlatın:
       baslat.bat   (veya: python server.py)

NOT: Kurulum sonrası makinenin ağ bağlantısı fiziksel olarak kesilmelidir.
Uygulama ayrıca süreç içinde localhost dışı tüm bağlantıları bloklar.
"@ | Out-File -FilePath (Join-Path $Bundle "KURULUM.txt") -Encoding utf8

Get-ChildItem -Recurse -File $Bundle |
    Get-FileHash -Algorithm SHA256 |
    Select-Object Hash, @{N='File';E={$_.Path.Replace($Bundle,'')}} |
    Export-Csv -NoTypeInformation -Encoding utf8 (Join-Path $Bundle "SHA256SUMS.csv")

$SizeGB = [math]::Round((Get-ChildItem -Recurse -File $Bundle | Measure-Object Length -Sum).Sum / 1GB, 2)
Write-Host "`n✔ Paket hazır: $Bundle  ($SizeGB GB)" -ForegroundColor Green
Write-Host "  Bütünlük dosyası: SHA256SUMS.csv — transfer sonrası doğrulayın.`n" -ForegroundColor Green
