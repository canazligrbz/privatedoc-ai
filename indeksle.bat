@echo off
REM =====================================================================
REM  Belgeleri indeksle (data\documents -> vektor veri tabani)
REM  Yeni belge ekledikce bu dosyaya cift tiklayin.
REM =====================================================================
setlocal
cd /d "%~dp0"
chcp 65001 >nul

if not exist ".venv\Scripts\activate.bat" (
    echo [HATA] Kurulum yapilmamis. Once kurulum.bat calistirin.
    pause
    exit /b 1
)
call ".venv\Scripts\activate.bat"

set HF_HUB_OFFLINE=1
set TRANSFORMERS_OFFLINE=1
set ANONYMIZED_TELEMETRY=False
set TOKENIZERS_PARALLELISM=false

echo.
echo  Belgeler indeksleniyor: %cd%\data\documents
echo  (Ilk calistirmada embedding modeli yuklenir, 1-2 dk bekleyin)
echo.

if /I "%~1"=="rebuild" (
    python -m src.ingest --rebuild
) else (
    python -m src.ingest
)

echo.
pause
endlocal
