@echo off
REM =====================================================================
REM  Taranmis PDF destegi - Tesseract OCR kurulum yardimcisi
REM  Bu dosyaya CIFT TIKLAYIN.
REM =====================================================================
setlocal
cd /d "%~dp0"
chcp 65001 >nul

if exist ".venv\Scripts\activate.bat" (
    call ".venv\Scripts\activate.bat"
) else (
    echo [HATA] .venv bulunamadi. Once kurulum.bat calistirin.
    pause
    exit /b 1
)

python scripts\setup_ocr.py
if errorlevel 1 (
    echo.
    echo   Tesseract kurulum sayfasi aciliyor...
    start https://github.com/UB-Mannheim/tesseract/wiki
    echo   Kurulumu tamamladiktan sonra bu dosyaya tekrar cift tiklayin.
)

echo.
pause
endlocal
