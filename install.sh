#!/usr/bin/env bash
# ==============================================================================
# WorkBuddy Toolkit Installer (One-click Setup)
# https://github.com/FlapPearLabs/workbuddy-toolkit
# ==============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INSTALL_BIN="$HOME/.local/bin"
AUTH_PROFILES_DIR="$HOME/.workbuddy/auth_profiles"
DB_FILE="$HOME/.workbuddy/workbuddy.db"
LAUNCH_AGENTS_DIR="$HOME/Library/LaunchAgents"
SIDECAR_DIR="$HOME/.gemini/config/sidecars/workbuddy-checkin"

echo "========================================================"
echo "    WorkBuddy 多账号管理与自动化工具安装程序"
echo "========================================================"

# 1. 确保必要目录存在
mkdir -p "$INSTALL_BIN"
mkdir -p "$AUTH_PROFILES_DIR"
mkdir -p "$HOME/.workbuddy/logs"

# 2. 安装主脚本及快捷别名
echo "1. 正在安装 CLI 工具至 $INSTALL_BIN ..."
cp "$SCRIPT_DIR/bin/workbuddy" "$INSTALL_BIN/workbuddy"
chmod +x "$INSTALL_BIN/workbuddy"

ln -sf "$INSTALL_BIN/workbuddy" "$INSTALL_BIN/wb-switch"
ln -sf "$INSTALL_BIN/workbuddy" "$INSTALL_BIN/workbuddy-switch"
ln -sf "$INSTALL_BIN/workbuddy" "$INSTALL_BIN/wb-checkin"
ln -sf "$INSTALL_BIN/workbuddy" "$INSTALL_BIN/workbuddy-checkin"
ln -sf "$INSTALL_BIN/workbuddy" "$INSTALL_BIN/wb-chat"
ln -sf "$INSTALL_BIN/workbuddy" "$INSTALL_BIN/workbuddy-chat"
echo "   ✔ 已安装: workbuddy, wb-switch, wb-checkin, wb-chat"

# 3. 检查 PATH
if [[ ":$PATH:" != *":$HOME/.local/bin:"* ]]; then
    echo "   [提示] $HOME/.local/bin 似乎不在您的环境变量 PATH 中。"
    echo "   请在 ~/.zshrc 或 ~/.bashrc 中添加: export PATH=\"\$HOME/.local/bin:\$PATH\""
fi

# 4. 初始化数据库工作区全域互通触发器
if [ -f "$DB_FILE" ]; then
    echo "2. 正在初始化 SQLite 数据库工作区打通补丁..."
    python3 "$INSTALL_BIN/workbuddy" init
else
    echo "2. [跳过] 未检测到 $DB_FILE，首次启动 WorkBuddy 后可运行 'workbuddy init' 打补丁。"
fi

# 5. 配置系统级每日 09:00 定时自动签到
OS="$(uname -s)"
if [ "$OS" = "Darwin" ] && [ -d "$LAUNCH_AGENTS_DIR" ]; then
    echo "3. 正在配置 macOS 系统定时任务 (LaunchAgent)..."
    PLIST_TARGET="$LAUNCH_AGENTS_DIR/com.workbuddy.dailycheckin.plist"
    sed "s|{{HOME}}|$HOME|g" "$SCRIPT_DIR/launchd/com.workbuddy.dailycheckin.plist" > "$PLIST_TARGET"
    launchctl unload "$PLIST_TARGET" 2>/dev/null || true
    launchctl load "$PLIST_TARGET"
    echo "   ✔ LaunchAgent 已激活: 每天早晨 09:00 自动执行后台签到"
elif [ "$OS" = "Linux" ]; then
    echo "3. 正在配置 Linux 系统定时任务..."
    SYSTEMD_USER_DIR="$HOME/.config/systemd/user"
    CONFIGURED=0
    if command -v systemctl >/dev/null 2>&1; then
        mkdir -p "$SYSTEMD_USER_DIR"
        cp "$SCRIPT_DIR/systemd/workbuddy-dailycheckin.service" "$SYSTEMD_USER_DIR/"
        cp "$SCRIPT_DIR/systemd/workbuddy-dailycheckin.timer" "$SYSTEMD_USER_DIR/"
        systemctl --user daemon-reload 2>/dev/null || true
        systemctl --user enable --now workbuddy-dailycheckin.timer 2>/dev/null || true
        if systemctl --user is-active --quiet workbuddy-dailycheckin.timer 2>/dev/null; then
            echo "   ✔ systemd user timer 已激活: 每天早晨 09:00 自动执行后台签到"
            CONFIGURED=1
        fi
    fi
    if [ "$CONFIGURED" -eq 0 ] && command -v crontab >/dev/null 2>&1; then
        CRON_CMD="0 9 * * * $INSTALL_BIN/workbuddy checkin >> $HOME/.workbuddy/logs/checkin.log 2>&1"
        (crontab -l 2>/dev/null | grep -Fv "workbuddy checkin" ; echo "$CRON_CMD") | crontab -
        echo "   ✔ crontab 已配置: 每天早晨 09:00 自动执行后台签到"
    fi
fi

# 6. 配置 Antigravity Scheduled Tasks Sidecar (可选)
if [ -d "$HOME/.gemini" ]; then
    echo "4. 正在配置 Antigravity Scheduled Tasks 侧边栏任务..."
    mkdir -p "$SIDECAR_DIR"
    cp "$SCRIPT_DIR/sidecar/sidecar.json" "$SIDECAR_DIR/sidecar.json"
    echo "   ✔ Sidecar 已配置，可在 Antigravity UI 的 Scheduled Tasks 查看"
fi

echo "========================================================"
echo "🎉 安装完成！"
echo "使用说明:"
echo "  • wb-switch             : 呼出多账号无缝切换菜单"
echo "  • wb-checkin            : 执行所有账号每日签到与每日对话"
echo "  • wb-chat [提示词]      : 直接在终端与模型对话维持连续对话"
echo "  • workbuddy save <别名> : 保存当前登录中的账号"
echo "  • workbuddy status      : 查看所有账号状态与 Token 有效期"
echo "========================================================"
