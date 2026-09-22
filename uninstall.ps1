# ==============================================================================
# WorkBuddy Toolkit Uninstaller for Windows (PowerShell)
# https://github.com/FlapPearLabs/workbuddy-toolkit
# ==============================================================================

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path

$Python = Get-Command python -ErrorAction SilentlyContinue
if (-not $Python) {
    $Python = Get-Command py -ErrorAction SilentlyContinue
}

if (-not $Python) {
    Write-Host "[ERROR] Python 3 not found in PATH." -ForegroundColor Red
    exit 1
}

$UninstallPy = Join-Path $ScriptDir "uninstall.py"
& $Python.Source $UninstallPy
