@echo off
chcp 65001 >nul
echo ========================================
echo  Compilando MINKA VOZ como aplicacion
echo ========================================
echo.

call venv\Scripts\activate.bat

echo Compilando... esto tarda 3-5 minutos
echo.

pyinstaller --noconfirm --onefile --noconsole ^
    --name "MINKA VOZ" ^
    --paths "." ^
    --hidden-import "flet" ^
    --hidden-import "flet.controls" ^
    --hidden-import "flet.controls.alignment" ^
    --hidden-import "flet.controls.border" ^
    --hidden-import "flet.controls.colors" ^
    --hidden-import "flet.controls.icons" ^
    --hidden-import "flet.controls.scroll" ^
    --hidden-import "whisper" ^
    --hidden-import "sounddevice" ^
    --hidden-import "soundfile" ^
    --hidden-import "gTTS" ^
    --hidden-import "pygame" ^
    --hidden-import "numpy" ^
    --hidden-import "pynput" ^
    --hidden-import "database" ^
    --collect-all flet ^
    --collect-all whisper ^
    --collect-data gTTS ^
    --collect-data pygame ^
    --collect-data soundfile ^
    minka_gui.py

echo.
echo ========================================
echo  Build completado
echo ========================================
echo.
echo El archivo esta en: dist\MINKA VOZ.exe
echo.
pause