@echo off
chcp 65001 >nul
echo.
echo ========================================
echo  Instalando MINKA VOZ para Windows
echo ========================================
echo.

REM 1. ffmpeg
echo [1/4] Verificando ffmpeg...
where ffmpeg >nul 2>&1
if %errorlevel% equ 0 (
    echo       ffmpeg ya esta instalado
) else (
    echo       Instalando ffmpeg via winget...
    winget install --id Gyan.FFmpeg --silent --accept-source-agreements --accept-package-agreements
    if %errorlevel% neq 0 (
        echo ERROR: No se pudo instalar ffmpeg. Instalalo manualmente: https://ffmpeg.org/download.html
        pause
        exit /b 1
    )
    echo       [OK] ffmpeg instalado
)

REM 2. Entorno virtual
echo [2/4] Creando entorno virtual...
if exist venv (
    echo       Entorno virtual ya existe
) else (
    python -m venv venv
    echo       [OK] Entorno virtual creado
)

REM 3. Dependencias Python
echo [3/4] Instalando dependencias Python...
call venv\Scripts\activate.bat
python -m pip install --upgrade pip -q
python -m pip install openai-whisper sounddevice soundfile gTTS pygame numpy pynput -q
echo       [OK] Dependencias instaladas

REM 4. Carpeta BD
echo [4/4] Preparando carpeta de base de datos...
set "DBDIR=%USERPROFILE%\minka"
if not exist "%DBDIR%" (
    mkdir "%DBDIR%"
    echo       [OK] Carpeta creada: %DBDIR%
) else (
    echo       Carpeta ya existe: %DBDIR%
)

echo.
echo ========================================
echo  Instalacion completada
echo ========================================
echo.
echo Para ejecutar MINKA VOZ:
echo   venv\Scripts\activate.bat
echo   python minka_voz.py
echo.
echo La base de datos se creara en: %DBDIR%\minka.db
echo.
pause