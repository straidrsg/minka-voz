#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Instalador de MINKA VOZ para Windows
.DESCRIPTION
    Instala dependencias del sistema (ffmpeg), crea entorno virtual,
    instala paquetes Python y prepara la base de datos.
#>

param(
    [switch]$SaltarFFmpeg,
    [switch]$SaltarVenv,
    [switch]$SaltarPip
)

$ErrorActionPreference = "Stop"

function Write-Step($msg) {
    Write-Host "`n🌿 $msg`n" -ForegroundColor Green
}

function Write-Warn($msg) {
    Write-Host "⚠ $msg" -ForegroundColor Yellow
}

function Write-Err($msg) {
    Write-Host "✗ $msg" -ForegroundColor Red
    exit 1
}

# Verificar admin (para winget)
if (-NOT ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Write-Warn "Se recomienda ejecutar PowerShell como Administrador para winget install ffmpeg"
}

# 1. ffmpeg
if (-not $SaltarFFmpeg) {
    Write-Step "Instalando ffmpeg (requerido por Whisper)..."
    if (Get-Command ffmpeg -ErrorAction SilentlyContinue) {
        Write-Host "  ffmpeg ya está instalado" -ForegroundColor Gray
   } else {
        try {
            winget install --id Gyan.FFmpeg --silent --accept-source-agreements --accept-package-agreements
            $env:PATH = [System.Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path","User")
            Write-Host "  ✓ ffmpeg instalado" -ForegroundColor Green
        } catch {
            Write-Err "No se pudo instalar ffmpeg automáticamente. Instálalo manualmente: https://ffmpeg.org/download.html"
        }
    }
}

# 2. Entorno virtual
$venvPath = ".\venv"
if (-not $SaltarVenv) {
    Write-Step "Creando entorno virtual en $venvPath..."
    if (Test-Path $venvPath) {
        Write-Host "  Entorno virtual ya existe" -ForegroundColor Gray
    } else {
        python -m venv $venvPath
        Write-Host "  ✓ Entorno virtual creado" -ForegroundColor Green
    }
}

# 3. Activar venv e instalar deps Python
if (-not $SaltarPip) {
    Write-Step "Instalando dependencias Python..."
    & "$venvPath\Scripts\Activate.ps1"
    python -m pip install --upgrade pip -q
    $paquetes = @(
        "openai-whisper",
        "sounddevice",
        "soundfile",
        "gTTS",
        "pygame",
        "numpy",
        "pynput"
    )
    foreach ($pkg in $paquetes) {
        Write-Host "  Instalando $pkg..." -NoNewline
        python -m pip install $pkg -q
        Write-Host " ✓" -ForegroundColor Green
    }
}

# 4. Carpeta de base de datos
Write-Step "Preparando carpeta de base de datos..."
$dbDir = Join-Path $env:USERPROFILE "minka"
if (-not (Test-Path $dbDir)) {
    New-Item -ItemType Directory -Path $dbDir | Out-Null
    Write-Host "  ✓ Carpeta creada: $dbDir" -ForegroundColor Green
} else {
    Write-Host "  Carpeta ya existe: $dbDir" -ForegroundColor Gray
}

# 5. Resumen
Write-Host "`n🎉  ¡Instalación completada!`n" -ForegroundColor Cyan
Write-Host "Para ejecutar MINKA VOZ:" -ForegroundColor White
Write-Host "  .\venv\Scripts\Activate.ps1" -ForegroundColor Gray
Write-Host "  python minka_voz.py" -ForegroundColor Gray
Write-Host "`nLa base de datos se creará automáticamente en: $dbDir\minka.db`n"