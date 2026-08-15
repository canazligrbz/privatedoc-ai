@echo off
REM =====================================================================
REM  Belge Asistani - Baslatici (Windows)
REM  Masaustune kisayol olusturup son kullaniciya verebilirsiniz.
REM =====================================================================
setlocal
cd /d "%~dp0"
chcp 65001 >nul

echo.
echo   BELGE ASISTANI
echo   ---------------------------------
echo.

REM --- Sanal ortam ---
if exist ".venv\Scripts\activate.bat" (
    call ".venv\Scripts\activate.bat"
) else (
    echo [HATA] .venv bulunamadi. Once kurulum.bat calistirin.
    pause
    exit /b 1
)

REM --- Cevrimdisi zorlama ---
set HF_HUB_OFFLINE=1
set TRANSFORMERS_OFFLINE=1
set ANONYMIZED_TELEMETRY=False
set TOKENIZERS_PARALLELISM=false

REM --- Ollama servisi ayakta mi? ---
curl -s -o nul -m 3 http://127.0.0.1:11434/api/tags
if errorlevel 1 (
    echo [i] Ollama calismiyor, baslatiliyor...
    start "" /min ollama serve
    timeout /t 8 /nobreak >nul
)

echo [i] Uygulama baslatiliyor: http://127.0.0.1:8501
echo     Kapatmak icin bu pencerede Ctrl+C yapin.
echo.
start "" http://127.0.0.1:8501
python -m uvicorn server:app --host 127.0.0.1 --port 8501 --log-level warning

endlocal
