@echo off
REM =====================================================================
REM  BELGE ASISTANI - ILK KURULUM (Windows, INTERNETLI makine)
REM  ---------------------------------------------------------------------
REM  Bu dosyaya CIFT TIKLAYIN. Tek seferlik calistirilir.
REM  Air-gap makinede DEGIL, internetli kurulum makinesinde kullanilir.
REM =====================================================================
setlocal enabledelayedexpansion
cd /d "%~dp0"
chcp 65001 >nul

echo.
echo ======================================================
echo   BELGE ASISTANI - KURULUM
echo ======================================================
echo.

REM ---------------------------------------------- 1) Python kontrolu
echo [1/6] Python kontrol ediliyor...
python --version >nul 2>&1
if errorlevel 1 (
    echo   [HATA] Python bulunamadi.
    echo   https://www.python.org/downloads/ adresinden Python 3.11 kurun.
    echo   Kurulumda "Add python.exe to PATH" kutusunu MUTLAKA isaretleyin.
    pause
    exit /b 1
)
for /f "tokens=2" %%v in ('python --version 2^>^&1') do set PYVER=%%v
echo   OK - Python !PYVER!
for /f "tokens=1,2 delims=." %%a in ("!PYVER!") do set PYMAJ=%%a& set PYMIN=%%b
if !PYMAJ! NEQ 3 ( echo   [HATA] Python 3 gerekli. & pause & exit /b 1 )
if !PYMIN! GEQ 13 (
    echo.
    echo   [!] UYARI: Python 3.!PYMIN! icin torch 2.4.1 hazir paketi yok.
    echo       Python 3.11 veya 3.12 kurmaniz onerilir.
    echo       Devam etmek icin bir tusa basin, iptal icin pencereyi kapatin.
    pause
)
if !PYMIN! LSS 10 ( echo   [HATA] En az Python 3.10 gerekli. & pause & exit /b 1 )

REM ---------------------------------------------- 2) Sanal ortam
echo.
echo [2/6] Sanal ortam hazirlaniyor (.venv)...
if not exist ".venv\Scripts\python.exe" (
    python -m venv .venv
    if errorlevel 1 ( echo   [HATA] venv olusturulamadi. & pause & exit /b 1 )
    echo   OK - .venv olusturuldu
) else (
    echo   OK - .venv zaten var
)
call ".venv\Scripts\activate.bat"
python -m pip install --upgrade pip --quiet

REM ---------------------------------------------- 3) Python paketleri
echo.
echo [3/6] Python paketleri kuruluyor... (5-15 dk surebilir, ~2.5 GB)
echo   - torch (CPU surumu) indiriliyor...
pip install torch==2.4.1 --index-url https://download.pytorch.org/whl/cpu --quiet
if errorlevel 1 ( echo   [HATA] torch kurulamadi. & pause & exit /b 1 )
echo   - diger paketler...
pip install -r requirements.txt --quiet --only-binary=chromadb,chroma-hnswlib
if errorlevel 1 (
    echo.
    echo   [HATA] Paketler kurulamadi.
    echo.
    echo   "Microsoft Visual C++ 14.0 or greater is required" hatasi aldiysaniz:
    echo     requirements.txt icinde chromadb 1.5.9 olmali ^(0.5.x DEGIL^).
    echo     Kontrol edin, sonra su komutu calistirin:
    echo        .venv\Scripts\activate
    echo        pip install "chromadb==1.5.9"
    echo.
    pause
    exit /b 1
)
pip install "huggingface_hub>=0.25" --quiet
echo   OK - paketler kuruldu

REM ---------------------------------------------- 4) Embedding modeli
echo.
echo [4/6] Embedding modeli indiriliyor (bge-m3, ~2.3 GB)...
if exist "models\bge-m3\config.json" (
    echo   OK - model zaten mevcut, atlaniyor
) else (
    python scripts\download_models.py --out models
    if errorlevel 1 ( echo   [HATA] Model indirilemedi. & pause & exit /b 1 )
)

REM ---------------------------------------------- 5) Ollama + LLM
echo.
echo [5/6] LLM (Ollama) kontrol ediliyor...
where ollama >nul 2>&1
if errorlevel 1 (
    echo   [!] Ollama kurulu degil.
    echo       https://ollama.com/download/windows adresinden indirip kurun,
    echo       sonra bu dosyayi TEKRAR calistirin.
    start https://ollama.com/download/windows
    pause
    exit /b 1
)
echo   OK - Ollama bulundu
curl -s -o nul -m 3 http://127.0.0.1:11434/api/tags
if errorlevel 1 (
    echo   [i] Ollama servisi baslatiliyor...
    start "" /min ollama serve
    timeout /t 8 /nobreak >nul
)
echo   - qwen2.5:7b-instruct-q4_K_M indiriliyor (~4.7 GB)...
ollama pull qwen2.5:7b-instruct-q4_K_M
if errorlevel 1 ( echo   [HATA] Model indirilemedi. & pause & exit /b 1 )
echo   OK - LLM hazir

REM ---------------------------------------------- 6) Dogrulama
echo.
echo [6/6] Kurulum dogrulaniyor...
python scripts\verify_offline.py

echo.
echo ======================================================
echo   KURULUM TAMAMLANDI
echo ======================================================
echo.
echo   SIRADAKI ADIMLAR:
echo     1) Belgelerinizi su klasore kopyalayin:
echo          %cd%\data\documents
echo     2) Indeksleme icin calistirin:  indeksle.bat
echo     3) Uygulamayi baslatin:         baslat.bat
echo.
pause
endlocal
