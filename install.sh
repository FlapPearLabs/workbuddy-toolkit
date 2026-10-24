#!/usr/bin/env bash
# ==============================================================================
# WorkBuddy Toolkit Installer (macOS / Linux)
# https://github.com/FlapPearLabs/workbuddy-toolkit
#
# 默认只安装 CLI 与 sidecar 模块，不修改 WorkBuddy 数据库、不注册后台任务。
# 可选能力（交互式终端中逐项询问，默认否；也可用参数显式开启）:
#   --init-workspace   开启多账号工作区共享 (等同 workbuddy init)
#   --with-checkin     注册每日 09:00 签到
#   --with-log-guard   注册日志/沙盒看门狗 (每 30 分钟)
#   --with-router      注册容灾路由常驻服务 (仅 macOS)
#   --with-services    以上三项后台任务全部开启
#   --no-input         不询问，未显式开启的一律跳过
# ==============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INSTALL_BIN="$HOME/.local/bin"
AUTH_PROFILES_DIR="$HOME/.workbuddy/auth_profiles"
DB_FILE="$HOME/.workbuddy/workbuddy.db"
TOOLKIT_DIR="$HOME/.workbuddy/toolkit"
LAUNCH_AGENTS_DIR="$HOME/Library/LaunchAgents"
SIDECAR_DIR="$HOME/.gemini/config/sidecars/workbuddy-checkin"

OPT_INIT=0; OPT_CHECKIN=0; OPT_GUARD=0; OPT_ROUTER=0
SET_INIT=0; SET_CHECKIN=0; SET_GUARD=0; SET_ROUTER=0
NO_INPUT=0
for arg in "$@"; do
    case "$arg" in
        --init-workspace) OPT_INIT=1; SET_INIT=1 ;;
        --with-checkin)   OPT_CHECKIN=1; SET_CHECKIN=1 ;;
        --with-log-guard) OPT_GUARD=1; SET_GUARD=1 ;;
        --with-router)    OPT_ROUTER=1; SET_ROUTER=1 ;;
        --with-services)  OPT_CHECKIN=1; OPT_GUARD=1; OPT_ROUTER=1; SET_CHECKIN=1; SET_GUARD=1; SET_ROUTER=1 ;;
        --no-services)    OPT_CHECKIN=0; OPT_GUARD=0; OPT_ROUTER=0; SET_CHECKIN=1; SET_GUARD=1; SET_ROUTER=1 ;;
        --no-input)       NO_INPUT=1 ;;
        -h|--help)        sed -n '2,15p' "$0"; exit 0 ;;
    esac
done

ask() {
    # ask <描述>  -> 返回 0 表示用户同意
    local answer
    read -r -p "  • $1
    是否开启？[y/N]: " answer || answer=""
    [[ "$answer" =~ ^[Yy]([Ee][Ss])?$ ]]
}

echo "========================================================"
echo "    WorkBuddy 多账号管理与自动化工具安装程序"
echo "========================================================"

if [ -t 0 ] && [ "$NO_INPUT" -eq 0 ]; then
    echo "以下能力默认关闭，可按需开启 (直接回车 = 否):"
    [ "$SET_INIT" -eq 1 ]    || { ask "开启多账号工作区/历史会话共享 (修改 WorkBuddy 数据库，可用 workbuddy rollback 恢复)" && OPT_INIT=1 || true; }
    [ "$SET_CHECKIN" -eq 1 ] || { ask "注册每日 09:00 自动签到 (会为每个已保存账号发送一次保活对话)" && OPT_CHECKIN=1 || true; }
    [ "$SET_GUARD" -eq 1 ]   || { ask "注册日志/沙盒看门狗 (每 30 分钟清理 WorkBuddy 日志与快照)" && OPT_GUARD=1 || true; }
    [ "$SET_ROUTER" -eq 1 ]  || { ask "注册容灾路由常驻服务 127.0.0.1:8047 (仅 macOS)" && OPT_ROUTER=1 || true; }
fi

# 1. 确保必要目录存在
mkdir -p "$INSTALL_BIN" "$AUTH_PROFILES_DIR" "$HOME/.workbuddy/logs"

# 2. 部署 sidecar 模块 (wb-usage / wb-models / wb-tool / wb-router 依赖)
#    若仓库本身就 clone 在 ~/.workbuddy/toolkit，源与目标相同，跳过复制以免删掉源码。
SRC_SIDECAR="$SCRIPT_DIR/sidecar"
DEST_SIDECAR="$TOOLKIT_DIR/sidecar"
if [ ! -d "$SRC_SIDECAR" ]; then
    echo "错误: 未找到 $SRC_SIDECAR，安装包不完整。" >&2
    exit 1
fi
SRC_REAL="$(cd "$SRC_SIDECAR" && pwd -P)"
DEST_REAL=""
[ -d "$DEST_SIDECAR" ] && DEST_REAL="$(cd "$DEST_SIDECAR" && pwd -P)"
if [ "$SRC_REAL" != "$DEST_REAL" ]; then
    mkdir -p "$TOOLKIT_DIR"
    rm -rf "$DEST_SIDECAR.staging"
    cp -R "$SRC_SIDECAR" "$DEST_SIDECAR.staging"
    rm -rf "$DEST_SIDECAR.staging/__pycache__"
    rm -rf "$DEST_SIDECAR"
    mv "$DEST_SIDECAR.staging" "$DEST_SIDECAR"
fi

# 3. 安装主脚本及快捷别名
echo "1. 正在安装 CLI 工具至 $INSTALL_BIN ..."
cp "$SCRIPT_DIR/bin/workbuddy" "$INSTALL_BIN/workbuddy"
chmod +x "$INSTALL_BIN/workbuddy"

if [ -f "$SCRIPT_DIR/bin/workbuddy-log-guard" ]; then
    cp "$SCRIPT_DIR/bin/workbuddy-log-guard" "$INSTALL_BIN/workbuddy-log-guard"
    chmod +x "$INSTALL_BIN/workbuddy-log-guard"
fi

for alias in wb-help workbuddy-help wb-login workbuddy-login wb-audit workbuddy-audit \
             wb-list workbuddy-list wb-status workbuddy-status wb-switch workbuddy-switch \
             wb-remove workbuddy-remove \
             wb-checkin workbuddy-checkin wb-chat workbuddy-chat wb-doctor workbuddy-doctor \
             wb-models workbuddy-models wb-usage workbuddy-usage wb-router workbuddy-router \
             wb-sandbox workbuddy-sandbox wb-tool workbuddy-tool; do
    ln -sf "$INSTALL_BIN/workbuddy" "$INSTALL_BIN/$alias"
done
echo "   ✔ 已安装: workbuddy, workbuddy-log-guard, wb-tool, wb-help, wb-login, wb-audit, wb-list, wb-status, wb-switch, wb-remove, wb-checkin, wb-chat, wb-doctor, wb-models, wb-usage, wb-router, wb-sandbox"

if [[ ":$PATH:" != *":$HOME/.local/bin:"* ]]; then
    echo "   [提示] $HOME/.local/bin 似乎不在您的环境变量 PATH 中。"
    echo "   请在 ~/.zshrc 或 ~/.bashrc 中添加: export PATH=\"\$HOME/.local/bin:\$PATH\""
fi

# 4. 多账号工作区共享 (可选)
if [ "$OPT_INIT" -eq 1 ]; then
    if [ -f "$DB_FILE" ]; then
        echo "2. 正在开启多账号工作区共享 (workbuddy init)..."
        python3 "$INSTALL_BIN/workbuddy" init
    else
        echo "2. [跳过] 未检测到 $DB_FILE，首次启动 WorkBuddy 后可运行 'workbuddy init'。"
    fi
else
    echo "2. [跳过] 未开启多账号工作区共享。需要时运行: workbuddy init"
fi

# 5. 后台任务 (可选)
load_agent() {
    local name="$1"
    local src="$SCRIPT_DIR/launchd/$name.plist"
    local dest="$LAUNCH_AGENTS_DIR/$name.plist"
    [ -f "$src" ] || return 1
    mkdir -p "$LAUNCH_AGENTS_DIR"
    sed "s|{{HOME}}|$HOME|g" "$src" > "$dest"
    launchctl unload "$dest" 2>/dev/null || true
    launchctl load -w "$dest" 2>/dev/null || true
}

install_systemd_unit() {
    local base="$1"
    local dir="$HOME/.config/systemd/user"
    [ -f "$SCRIPT_DIR/systemd/$base.service" ] && [ -f "$SCRIPT_DIR/systemd/$base.timer" ] || return 1
    command -v systemctl >/dev/null 2>&1 || return 1
    mkdir -p "$dir"
    cp "$SCRIPT_DIR/systemd/$base.service" "$SCRIPT_DIR/systemd/$base.timer" "$dir/"
    systemctl --user daemon-reload 2>/dev/null || true
    systemctl --user enable --now "$base.timer" 2>/dev/null || true
    systemctl --user is-active --quiet "$base.timer" 2>/dev/null
}

OS="$(uname -s)"
if [ "$OPT_CHECKIN" -eq 0 ] && [ "$OPT_GUARD" -eq 0 ] && [ "$OPT_ROUTER" -eq 0 ]; then
    echo "3. [跳过] 未注册任何后台任务。需要时重新运行: ./install.sh --with-checkin / --with-log-guard / --with-router"
elif [ "$OS" = "Darwin" ]; then
    echo "3. 正在注册已开启的后台任务 (LaunchAgent)..."
    [ "$OPT_CHECKIN" -eq 1 ] && load_agent com.workbuddy.dailycheckin && echo "   ✔ 每天 09:00 签到"
    [ "$OPT_ROUTER" -eq 1 ]  && load_agent com.workbuddy.failover-router && echo "   ✔ Failover Router 容灾路由 (127.0.0.1:8047)"
    [ "$OPT_GUARD" -eq 1 ]   && load_agent com.workbuddy.log-guard && echo "   ✔ Log Guard 看门狗 (每 30 分钟)"
elif [ "$OS" = "Linux" ]; then
    echo "3. 正在注册已开启的后台任务..."
    [ "$OPT_ROUTER" -eq 1 ] && echo "   [提示] 容灾路由常驻服务目前只提供 macOS LaunchAgent；Linux 请按需运行: wb-router start"
    CRON_ADD=()
    if [ "$OPT_CHECKIN" -eq 1 ]; then
        if install_systemd_unit workbuddy-dailycheckin; then
            echo "   ✔ systemd user timer: 每天 09:00 签到"
        else
            CRON_ADD+=("0 9 * * * $INSTALL_BIN/workbuddy checkin >> $HOME/.workbuddy/logs/checkin.log 2>&1")
        fi
    fi
    if [ "$OPT_GUARD" -eq 1 ]; then
        if install_systemd_unit workbuddy-log-guard; then
            echo "   ✔ systemd user timer: 每 30 分钟日志治理"
        else
            CRON_ADD+=("0,30 * * * * $INSTALL_BIN/workbuddy-log-guard >> $HOME/.workbuddy/logs/log-guard.log 2>&1")
        fi
    fi
    if [ "${#CRON_ADD[@]}" -gt 0 ]; then
        if command -v crontab >/dev/null 2>&1; then
            { crontab -l 2>/dev/null | grep -Fv "workbuddy checkin" | grep -Fv "workbuddy-log-guard" || true
              printf '%s\n' "${CRON_ADD[@]}"; } | crontab -
            echo "   ✔ crontab 已配置 ${#CRON_ADD[@]} 项"
        else
            echo "   [提示] 未找到 systemd/crontab，后台任务未注册，可随时手动运行。"
        fi
    fi
fi

# 6. Antigravity Scheduled Tasks Sidecar (跟随签到开关)
if [ "$OPT_CHECKIN" -eq 1 ] && [ -d "$HOME/.gemini" ]; then
    echo "4. 正在配置 Antigravity Scheduled Tasks 侧边栏签到任务..."
    mkdir -p "$SIDECAR_DIR"
    sed -e "s|{{BIN_PATH}}|$INSTALL_BIN/workbuddy|g" -e "s|{{HOME}}|$HOME|g" "$SCRIPT_DIR/sidecar/sidecar.json" > "$SIDECAR_DIR/sidecar.json"
    echo "   ✔ Sidecar 已配置"
fi

echo "========================================================"
echo "🎉 安装完成！"
echo "下一步:"
echo "  • workbuddy doctor      : 检查凭据与运行时兼容性"
echo "  • wb-login              : 添加账号"
echo "  • wb-switch             : 多账号切换菜单"
echo "  • wb-remove             : 删除本地已保存账号 (默认移入回收站)"
echo "  • wb-checkin            : 手动执行签到"
echo "  • workbuddy init        : 开启多账号工作区共享 (可用 workbuddy rollback 恢复)"
echo "========================================================"
