#!/usr/bin/env bash
# ==============================================================================
# WorkBuddy Boot & Network-Ready Auto Check-in Gate (macOS & Linux)
# https://github.com/FlapPearLabs/workbuddy-toolkit
#
# 特性：
# 1. 开机/登录后后台自动检测网络，连通后延迟 5 秒执行 wb-checkin 并发送系统通知；
# 2. 单日防重幂等锁：当天已签到则 0 毫秒静默退出，防一天内重启/休眠唤醒重复打扰；
# 3. 双重网络探针（HTTP HEAD + IP Ping fallback），防御 ICMP 过滤与 DNS 刚开机延迟；
# 4. 全局 90 秒超时熔断，超时未联网即优雅记录日志退出，杜绝无限空耗。
# ==============================================================================

set -e

TODAY="$(date +%Y-%m-%d)"
WORKBUDDY_DIR="$HOME/.workbuddy"
FLAG_FILE="$WORKBUDDY_DIR/.last_boot_checkin"
LOG_DIR="$WORKBUDDY_DIR/logs"
LOG_FILE="$LOG_DIR/boot_checkin.log"

mkdir -p "$WORKBUDDY_DIR"
mkdir -p "$LOG_DIR"

# 1. 幂等防护：如果今日已通过开机门禁打过卡，直接静默退出
if [ -f "$FLAG_FILE" ]; then
    LAST_DATE="$(cat "$FLAG_FILE" 2>/dev/null | tr -d '[:space:]')"
    if [ "$LAST_DATE" = "$TODAY" ]; then
        exit 0
    fi
fi

# 2. 网络就绪轮询门禁（最多等待 90 秒，每次间隔 2 秒）
MAX_WAIT_SECONDS=90
START_TIME=$(date +%s)
CONNECTED=0

while true; do
    NOW=$(date +%s)
    if [ $((NOW - START_TIME)) -ge "$MAX_WAIT_SECONDS" ]; then
        break
    fi
    # 双重探针：优先 HTTP HEAD 连通（防 ICMP 拦截），回退公共 DNS 探针
    if curl -I -s --connect-timeout 2 --max-time 3 "https://copilot.tencent.com" >/dev/null 2>&1 || \
       curl -I -s --connect-timeout 2 --max-time 3 "https://www.baidu.com" >/dev/null 2>&1 || \
       ping -c 1 -W 2 223.5.5.5 >/dev/null 2>&1 || \
       ping -c 1 -W 2 119.29.29.29 >/dev/null 2>&1; then
        CONNECTED=1
        break
    fi
    sleep 2
done

if [ "$CONNECTED" -eq 0 ]; then
    echo "[$TODAY $(date +%H:%M:%S)] [WorkBuddy Boot Gate] 超过 ${MAX_WAIT_SECONDS} 秒未检测到网络就绪，退出执行。" >> "$LOG_FILE"
    exit 1
fi

# 3. 连上网后稳定等待 5 秒（规避刚开机时 DHCP 与 DNS 路由表初建震荡）
sleep 5

# 4. 定位并调用 wb-checkin
CHECKIN_CMD=""
if command -v wb-checkin >/dev/null 2>&1; then
    CHECKIN_CMD="wb-checkin"
elif [ -x "$HOME/.local/bin/wb-checkin" ]; then
    CHECKIN_CMD="$HOME/.local/bin/wb-checkin"
elif [ -x "$HOME/.local/bin/workbuddy" ]; then
    CHECKIN_CMD="$HOME/.local/bin/workbuddy checkin"
elif [ -x "$WORKBUDDY_DIR/toolkit/bin/workbuddy" ]; then
    CHECKIN_CMD="$WORKBUDDY_DIR/toolkit/bin/workbuddy checkin"
fi

if [ -z "$CHECKIN_CMD" ]; then
    echo "[$TODAY $(date +%H:%M:%S)] [WorkBuddy Boot Gate] ✖ 未找到可执行的 wb-checkin 命令。" >> "$LOG_FILE"
    exit 1
fi

echo "[$TODAY $(date +%H:%M:%S)] [WorkBuddy Boot Gate] 网络已就绪，正在触发自动签到与保活对话..." >> "$LOG_FILE"

# 执行签到（内部自带 macOS/Linux 原生桌面弹窗与多账号轮询）
if $CHECKIN_CMD >> "$LOG_FILE" 2>&1; then
    echo "$TODAY" > "$FLAG_FILE"
    echo "[$TODAY $(date +%H:%M:%S)] [WorkBuddy Boot Gate] ✔ 今日签到流程执行完成，已写入单日防重标记。" >> "$LOG_FILE"
    exit 0
else
    EXIT_CODE=$?
    echo "[$TODAY $(date +%H:%M:%S)] [WorkBuddy Boot Gate] ▲ 签到命令退出异常 (Exit Code: $EXIT_CODE)。" >> "$LOG_FILE"
    exit "$EXIT_CODE"
fi
