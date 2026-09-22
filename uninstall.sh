#!/usr/bin/env bash
# ==============================================================================
# WorkBuddy Toolkit Uninstaller
# ==============================================================================

set -e

INSTALL_BIN="$HOME/.local/bin"
PLIST_TARGET="$HOME/Library/LaunchAgents/com.workbuddy.dailycheckin.plist"
SIDECAR_DIR="$HOME/.gemini/config/sidecars/workbuddy-checkin"

echo "正在卸载 WorkBuddy Toolkit..."

# 1. 卸载定时任务 (macOS launchd & Linux systemd/cron)
if [ -f "$PLIST_TARGET" ]; then
    launchctl unload "$PLIST_TARGET" 2>/dev/null || true
    rm -f "$PLIST_TARGET"
    echo "✔ 已注销并删除 macOS LaunchAgent 定时任务"
fi

SYSTEMD_TIMER="$HOME/.config/systemd/user/workbuddy-dailycheckin.timer"
SYSTEMD_SERVICE="$HOME/.config/systemd/user/workbuddy-dailycheckin.service"
if [ -f "$SYSTEMD_TIMER" ]; then
    systemctl --user disable --now workbuddy-dailycheckin.timer 2>/dev/null || true
    rm -f "$SYSTEMD_TIMER" "$SYSTEMD_SERVICE"
    systemctl --user daemon-reload 2>/dev/null || true
    echo "✔ 已注销并删除 Linux systemd user timer"
fi

if command -v crontab >/dev/null 2>&1; then
    crontab -l 2>/dev/null | grep -F "workbuddy checkin" >/dev/null && {
        crontab -l 2>/dev/null | grep -Fv "workbuddy checkin" | crontab -
        echo "✔ 已从 crontab 移除定时任务"
    } || true
fi

# 2. 移除 Sidecar
if [ -d "$SIDECAR_DIR" ]; then
    rm -rf "$SIDECAR_DIR"
    echo "✔ 已清理 Antigravity Sidecar 任务"
fi

# 3. 移除可执行文件
rm -f "$INSTALL_BIN/workbuddy"
rm -f "$INSTALL_BIN/wb-switch"
rm -f "$INSTALL_BIN/workbuddy-switch"
rm -f "$INSTALL_BIN/wb-checkin"
rm -f "$INSTALL_BIN/workbuddy-checkin"
echo "✔ 已清理安装的 CLI 脚本"

echo "是否需要同时回滚 SQLite 数据库触发器并恢复官方默认数据隔离？(y/N)"
read -r answer
if [[ "$answer" =~ ^[Yy]$ ]]; then
    python3 -c "
import sqlite3, os
db = os.path.expanduser('~/.workbuddy/workbuddy.db')
if os.path.exists(db):
    con = sqlite3.connect(db)
    con.execute('DROP TRIGGER IF EXISTS trg_sessions_force_shared_insert;')
    con.execute('DROP TRIGGER IF EXISTS trg_sessions_force_shared_update;')
    con.commit()
    con.close()
    print('✔ 数据库触发器已撤销')
"
fi

echo "卸载完成！已保存的账号凭证仍保留在 ~/.workbuddy/auth_profiles/ 下以防丢失。"
