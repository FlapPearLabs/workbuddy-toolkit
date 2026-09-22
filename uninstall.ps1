# ==============================================================================
# WorkBuddy Toolkit Uninstaller for Windows (PowerShell)
# https://github.com/FlapPearLabs/workbuddy-toolkit
# ==============================================================================

$WorkbuddyHome = Join-Path $env:USERPROFILE ".workbuddy"
$BinDir = Join-Path $WorkbuddyHome "bin"
$TaskName = "WorkBuddyDailyCheckin"
$DbFile = Join-Path $WorkbuddyHome "workbuddy.db"

Write-Host "正在卸载 WorkBuddy Toolkit (Windows)..." -ForegroundColor Yellow

# 1. 注销任务计划程序
try {
    Start-Process -FilePath "schtasks.exe" -ArgumentList @("/delete", "/tn", $TaskName, "/f") -Wait -NoNewWindow -ErrorAction SilentlyContinue
    Write-Host "✔ 已注销并删除 Windows 任务计划: $TaskName" -ForegroundColor Green
} catch {}

# 2. 清理 CLI 脚本及垫片
if (Test-Path $BinDir) {
    Remove-Item -Path $BinDir -Recurse -Force
    Write-Host "✔ 已清理安装的 CLI 脚本与垫片 ($BinDir)" -ForegroundColor Green
}

# 3. 询问回滚数据库
$Rollback = Read-Host "是否需要同时回滚 SQLite 数据库触发器并恢复官方默认数据隔离？(y/N)"
if ($Rollback -match "^[Yy]$" -and (Test-Path $DbFile)) {
    $PythonExe = (Get-Command python -ErrorAction SilentlyContinue).Source
    if ($PythonExe) {
        & $PythonExe -c @"
import sqlite3, os
db = os.path.expanduser('~/.workbuddy/workbuddy.db')
if os.path.exists(db):
    con = sqlite3.connect(db)
    con.execute('DROP TRIGGER IF EXISTS trg_sessions_force_shared_insert;')
    con.execute('DROP TRIGGER IF EXISTS trg_sessions_force_shared_update;')
    con.commit()
    con.close()
    print('✔ 数据库触发器已撤销')
"@
    }
}

Write-Host "卸载完成！已保存的账号凭证仍保留在 ~/.workbuddy/auth_profiles/ 下以防丢失。" -ForegroundColor Green
