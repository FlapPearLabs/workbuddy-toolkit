# ==============================================================================
# WorkBuddy Toolkit Installer for Windows (PowerShell)
# https://github.com/FlapPearLabs/workbuddy-toolkit
# ==============================================================================

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path

$Python = Get-Command python -ErrorAction SilentlyContinue
if (-not $Python) {
    $Python = Get-Command py -ErrorAction SilentlyContinue
}

if (-not $Python) {
    Write-Host "[ERROR] Python 3 is required but not found in PATH. Please install Python." -ForegroundColor Red
    exit 1
}

$InstallPy = Join-Path $ScriptDir "install.py"
& $Python.Source $InstallPy
