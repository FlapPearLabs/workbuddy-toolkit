# ==============================================================================
# WorkBuddy Toolkit Installer for Windows (PowerShell)
# https://github.com/FlapPearLabs/workbuddy-toolkit
# ==============================================================================

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$WorkbuddyHome = Join-Path $env:USERPROFILE ".workbuddy"
$BinDir = Join-Path $WorkbuddyHome "bin"
$ProfilesDir = Join-Path $WorkbuddyHome "auth_profiles"
$LogsDir = Join-Path $WorkbuddyHome "logs"
$DbFile = Join-Path $WorkbuddyHome "workbuddy.db"

Write-Host "========================================================" -ForegroundColor Cyan
Write-Host "    WorkBuddy 多账号管理与自动化工具安装程序 (Windows)" -ForegroundColor Cyan
Write-Host "========================================================" -ForegroundColor Cyan

# 1. 探测 Python 环境
$PythonExe = (Get-Command python -ErrorAction SilentlyContinue).Source
if (-not $PythonExe) {
    $PythonExe = (Get-Command py -ErrorAction SilentlyContinue).Source
}
if (-not $PythonExe) {
    Write-Host "[错误] 未检测到 Python 3，请先安装 Python 并勾选 'Add Python to PATH'。" -ForegroundColor Red
    exit 1
}

# 优先查找用于静默运行的 pythonw.exe (无控制台黑框)
$PythonWExe = $PythonExe -replace "python\.exe$", "pythonw.exe"
if (-not (Test-Path $PythonWExe)) {
    $PythonWExe = $PythonExe
}

# 2. 建立目录
New-Item -ItemType Directory -Force -Path $BinDir | Out-Null
New-Item -ItemType Directory -Force -Path $ProfilesDir | Out-Null
New-Item -ItemType Directory -Force -Path $LogsDir | Out-Null

# 3. 安装主程序与 Windows 命令行垫片
Write-Host "1. 正在安装 CLI 工具至 $BinDir ..." -ForegroundColor Yellow
Copy-Item (Join-Path $ScriptDir "bin\workbuddy") (Join-Path $BinDir "workbuddy") -Force

# 创建 .cmd 垫片
$CmdMain = @"
@echo off
setlocal
where python >nul 2>nul
if %ERRORLEVEL% equ 0 (
    python "%~dp0workbuddy" %*
) else (
    py "%~dp0workbuddy" %*
)
"@
Set-Content -Path (Join-Path $BinDir "workbuddy.cmd") -Value $CmdMain -Encoding ASCII

$CmdSwitch = @"
@echo off
call "%~dp0workbuddy.cmd" switch %*
"@
Set-Content -Path (Join-Path $BinDir "wb-switch.cmd") -Value $CmdSwitch -Encoding ASCII
Set-Content -Path (Join-Path $BinDir "workbuddy-switch.cmd") -Value $CmdSwitch -Encoding ASCII

$CmdCheckin = @"
@echo off
call "%~dp0workbuddy.cmd" checkin %*
"@
Set-Content -Path (Join-Path $BinDir "wb-checkin.cmd") -Value $CmdCheckin -Encoding ASCII
Set-Content -Path (Join-Path $BinDir "workbuddy-checkin.cmd") -Value $CmdCheckin -Encoding ASCII

Write-Host "   ✔ 已安装: workbuddy.cmd, wb-switch.cmd, wb-checkin.cmd" -ForegroundColor Green

# 4. 配置用户 PATH 环境变量
$UserPath = [Environment]::GetEnvironmentVariable("Path", "User")
if ($UserPath -notlike "*$BinDir*") {
    Write-Host "2. 正在将 $BinDir 添加至用户环境变量 PATH ..." -ForegroundColor Yellow
    [Environment]::SetEnvironmentVariable("Path", "$UserPath;$BinDir", "User")
    $env:Path += ";$BinDir"
    Write-Host "   ✔ PATH 环境变量配置成功" -ForegroundColor Green
} else {
    Write-Host "2. [已配置] PATH 环境变量已包含 $BinDir" -ForegroundColor Green
}

# 5. 初始化数据库共享补丁
if (Test-Path $DbFile) {
    Write-Host "3. 正在初始化 SQLite 数据库工作区打通补丁..." -ForegroundColor Yellow
    & $PythonExe (Join-Path $BinDir "workbuddy") init
} else {
    Write-Host "3. [跳过] 未检测到 $DbFile，首次启动 WorkBuddy 后可运行 'workbuddy init' 打补丁。" -ForegroundColor DarkGray
}

# 6. 注册 Windows 任务计划程序 (每日 09:00 静默打卡)
Write-Host "4. 正在配置 Windows 任务计划程序 (Daily 09:00 AM)..." -ForegroundColor Yellow
$TaskName = "WorkBuddyDailyCheckin"
$CheckinLog = Join-Path $LogsDir "checkin.log"
$ActionArg = "`"$BinDir\workbuddy`" checkin"

# 使用 schtasks 注册（系统原生支持，无需管理员权限即可为当前用户注册）
$SchArgs = @(
    "/create",
    "/tn", $TaskName,
    "/tr", "`"$PythonWExe`" `"$BinDir\workbuddy`" checkin",
    "/sc", "daily",
    "/st", "09:00",
    "/f"
)
try {
    Start-Process -FilePath "schtasks.exe" -ArgumentList $SchArgs -Wait -NoNewWindow
    Write-Host "   ✔ Windows 任务计划已激活: 每天早晨 09:00 自动执行后台无窗打卡 ($TaskName)" -ForegroundColor Green
} catch {
    Write-Host "   [警告] 任务计划创建遇到提示，您也可随时使用 wb-checkin 手动打卡。" -ForegroundColor Yellow
}

Write-Host "========================================================" -ForegroundColor Cyan
Write-Host "🎉 安装完成！(请重新打开 PowerShell / CMD 窗口以加载 PATH)" -ForegroundColor Green
Write-Host "使用说明:" -ForegroundColor Cyan
Write-Host "  • wb-switch             : 呼出多账号无缝切换菜单"
Write-Host "  • wb-checkin            : 执行所有账号每日签到"
Write-Host "  • workbuddy save <别名> : 保存当前登录中的账号"
Write-Host "  • workbuddy status      : 查看所有账号状态与 Token 有效期"
Write-Host "========================================================" -ForegroundColor Cyan
