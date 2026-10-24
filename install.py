#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
WorkBuddy Toolkit Universal Cross-Platform Installer
Works out-of-the-box on macOS, Linux, and Windows with zero dependencies.
https://github.com/FlapPearLabs/workbuddy-toolkit

默认只安装命令行工具与 sidecar 模块，不会修改 WorkBuddy 数据库，也不会注册任何后台任务。
需要的能力请显式开启（交互式终端中会逐项询问，默认为否）:

    python3 install.py                     # 仅安装 CLI
    python3 install.py --init-workspace    # 同时开启多账号工作区共享 (等同 workbuddy init)
    python3 install.py --with-checkin      # 注册每日签到 (09:00；任务计划不可用时降级为登录时)
    python3 install.py --with-log-guard    # 注册日志/沙盒看门狗 (每 30 分钟)
    python3 install.py --with-router       # 注册容灾路由常驻服务 (macOS LaunchAgent)
    python3 install.py --with-services     # 以上三项后台任务全部开启
    python3 install.py --no-input          # 不询问，未显式开启的一律跳过
"""

import os
import sys
import shutil
import subprocess

if sys.platform == "win32":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
HOME = os.path.expanduser("~")
WORKBUDDY_DIR = os.path.join(HOME, ".workbuddy")
AUTH_PROFILES_DIR = os.path.join(WORKBUDDY_DIR, "auth_profiles")
LOGS_DIR = os.path.join(WORKBUDDY_DIR, "logs")
DB_FILE = os.path.join(WORKBUDDY_DIR, "workbuddy.db")
TOOLKIT_DIR = os.path.join(WORKBUDDY_DIR, "toolkit")

_USE_COLOR = sys.stdout.isatty() and "NO_COLOR" not in os.environ
COLOR_GREEN = "\033[92m" if _USE_COLOR else ""
COLOR_YELLOW = "\033[93m" if _USE_COLOR else ""
COLOR_CYAN = "\033[96m" if _USE_COLOR else ""
COLOR_RED = "\033[91m" if _USE_COLOR else ""
COLOR_BOLD = "\033[1m" if _USE_COLOR else ""
COLOR_RESET = "\033[0m" if _USE_COLOR else ""

CLI_ALIASES = [
    "wb-help", "workbuddy-help",
    "wb-login", "workbuddy-login",
    "wb-audit", "workbuddy-audit",
    "wb-list", "workbuddy-list",
    "wb-status", "workbuddy-status",
    "wb-switch", "workbuddy-switch",
    "wb-memory", "workbuddy-memory",
    "wb-checkin", "workbuddy-checkin",
    "wb-chat", "workbuddy-chat",
    "wb-doctor", "workbuddy-doctor",
    "wb-models", "workbuddy-models",
    "wb-usage", "workbuddy-usage",
    "wb-router", "workbuddy-router",
    "wb-sandbox", "workbuddy-sandbox",
    "wb-tool", "workbuddy-tool",
]

# Windows 垫片: 别名 -> 子命令
WINDOWS_SUBCOMMAND_SHIMS = {
    "switch": ["wb-switch", "workbuddy-switch"],
    "memory": ["wb-memory", "workbuddy-memory"],
    "checkin": ["wb-checkin", "workbuddy-checkin"],
    "chat": ["wb-chat", "workbuddy-chat"],
    "doctor": ["wb-doctor", "workbuddy-doctor"],
    "login": ["wb-login", "workbuddy-login"],
    "audit": ["wb-audit", "workbuddy-audit"],
    "list": ["wb-list", "workbuddy-list"],
    "status": ["wb-status", "workbuddy-status"],
    "models": ["wb-models", "workbuddy-models"],
    "router": ["wb-router", "workbuddy-router"],
    "sandbox": ["wb-sandbox", "workbuddy-sandbox"],
    "help": ["wb-help", "workbuddy-help"],
    "usage": ["wb-usage", "workbuddy-usage"],
    "tool": ["wb-tool", "workbuddy-tool"],
}

OPTIONAL_FEATURES = [
    ("init_workspace", "--init-workspace", "开启多账号工作区/历史会话共享 (修改 WorkBuddy 数据库，可用 workbuddy rollback 恢复)"),
    ("checkin", "--with-checkin", "注册每日 09:00 自动签到 (会为每个已保存账号发送一次保活对话)"),
    ("log_guard", "--with-log-guard", "注册日志/沙盒看门狗 (每 30 分钟清理 WorkBuddy 日志与快照)"),
    ("router", "--with-router", "注册容灾路由常驻服务 127.0.0.1:8047 (仅 macOS LaunchAgent)"),
]


def print_banner():
    print(f"\n{COLOR_BOLD}{COLOR_CYAN}========================================================{COLOR_RESET}")
    print(f"{COLOR_BOLD}{COLOR_CYAN}    WorkBuddy Toolkit 全平台通用安装程序 ({sys.platform}){COLOR_RESET}")
    print(f"{COLOR_BOLD}{COLOR_CYAN}========================================================{COLOR_RESET}")


def parse_options(argv):
    """解析可选能力开关。返回 {feature_key: bool}。"""
    if any(a in ("-h", "--help") for a in argv):
        print(__doc__)
        sys.exit(0)
    opts = {key: False for key, _, _ in OPTIONAL_FEATURES}
    explicit = set()
    for key, flag, _ in OPTIONAL_FEATURES:
        if flag in argv:
            opts[key] = True
            explicit.add(key)
    if "--with-services" in argv:
        for key in ("checkin", "log_guard", "router"):
            opts[key] = True
            explicit.add(key)
    if "--no-services" in argv:
        for key in ("checkin", "log_guard", "router"):
            opts[key] = False
            explicit.add(key)

    interactive = sys.stdin.isatty() and "--no-input" not in argv
    if interactive:
        print(f"\n{COLOR_BOLD}以下能力默认关闭，可按需开启 (直接回车 = 否):{COLOR_RESET}")
        for key, _flag, desc in OPTIONAL_FEATURES:
            if key in explicit:
                continue
            try:
                ans = input(f"  • {desc}\n    是否开启？[y/N]: ").strip().lower()
            except (EOFError, KeyboardInterrupt):
                print()
                ans = ""
            opts[key] = ans in ("y", "yes")
    return opts


def same_path(a, b):
    try:
        return os.path.realpath(a) == os.path.realpath(b)
    except OSError:
        return False


def deploy_sidecar():
    """把 sidecar 模块部署到 ~/.workbuddy/toolkit/sidecar。

    若仓库本身就 clone 在 ~/.workbuddy/toolkit（README 推荐位置），源与目标是同一目录，
    此时必须跳过复制，否则 rmtree 会删掉仓库里的 sidecar 源码。
    """
    src_sidecar = os.path.join(SCRIPT_DIR, "sidecar")
    dest_sidecar = os.path.join(TOOLKIT_DIR, "sidecar")
    if not os.path.isdir(src_sidecar):
        print(f"{COLOR_RED}错误: 未找到 sidecar 目录 ({src_sidecar})，安装包不完整。{COLOR_RESET}")
        sys.exit(1)
    if same_path(src_sidecar, dest_sidecar):
        return dest_sidecar
    os.makedirs(TOOLKIT_DIR, exist_ok=True)
    staging = dest_sidecar + ".staging"
    if os.path.exists(staging):
        shutil.rmtree(staging)
    shutil.copytree(src_sidecar, staging, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    if os.path.exists(dest_sidecar):
        shutil.rmtree(dest_sidecar)
    os.replace(staging, dest_sidecar)
    return dest_sidecar


def setup_dirs():
    os.makedirs(AUTH_PROFILES_DIR, exist_ok=True)
    os.makedirs(LOGS_DIR, exist_ok=True)


def _write_cmd(path, content):
    # newline="" 阻止 Python 把内容里已有的 \r\n 再翻译成 \r\r\n
    with open(path, "w", encoding="ascii", newline="") as f:
        f.write(content)


# 启动器报错提示：优先中文；英文 Windows 的 ANSI 代码页编码不了中文，回退英文。
LAUNCHER_HINT_MISSING_ZH = "未找到可用的 Python 3（需要 3.8 及以上）"
LAUNCHER_HINT_FIX_ZH = "请安装 Python 或将其加入 PATH，然后重试"
LAUNCHER_HINT_MISSING_EN = "No usable Python 3 found (3.8+ required)."
LAUNCHER_HINT_FIX_EN = "Install Python or add it to PATH, then re-run the installer."
LAUNCHER_HINT_STORE_ZH = "不支持 Microsoft Store 版 Python，请改用官方安装包"
LAUNCHER_HINT_STORE_EN = "Store-installed Python is not supported; use the official installer."


def _escape_batch_text(text):
    """转义 echo 参数里的 cmd 控制符。

    `^` 必须最先处理，否则会把后面新加进去的 `^` 再转一遍。括号在 goto 结构下
    已经没有语法意义，仍然一并转义——将来有人往文案里加括号时不会再咬人。

    注意：`%` 故意不在名单里——它不是控制符，但会触发 cmd 变量展开，转义方式
    （翻倍 `%%`）依赖上下文（批处理内 vs 命令行）。现有六条 hint 都不含 `%`；
    将来要在文案里用字面 `%`，请先单独验证展开行为，而不是顺手加进这个循环。
    """
    for ch in ("^", "&", "|", "<", ">", "(", ")"):
        text = text.replace(ch, "^" + ch)
    return text


def _render_launcher(template, target):
    """返回 (中文文本, 英文文本)，由 _write_cmd_native 决定实际落盘哪一份。"""
    zh = template.format(target=target,
                         hint_missing=_escape_batch_text(LAUNCHER_HINT_MISSING_ZH),
                         hint_fix=_escape_batch_text(LAUNCHER_HINT_FIX_ZH),
                         hint_store=_escape_batch_text(LAUNCHER_HINT_STORE_ZH))
    en = template.format(target=target,
                         hint_missing=_escape_batch_text(LAUNCHER_HINT_MISSING_EN),
                         hint_fix=_escape_batch_text(LAUNCHER_HINT_FIX_EN),
                         hint_store=_escape_batch_text(LAUNCHER_HINT_STORE_EN))
    return zh, en


def _write_cmd_native(path, text_zh, text_en):
    """按系统 ANSI 代码页写 .cmd，编码不了中文就退回纯 ASCII 版本。

    cmd 按系统代码页解码批处理文件：UTF-8 在中文 Windows 上会乱码，而英文
    Windows 的代码页又编码不了中文，所以准备两份文本做一次降级。
    返回实际使用的编码。
    """
    for text, encoding in ((text_zh, "mbcs"), (text_en, "ascii")):
        try:
            with open(path, "w", encoding=encoding, newline="") as f:
                f.write(text)
            return encoding
        except (LookupError, UnicodeEncodeError):
            continue
    raise OSError(f"无法写入启动器: {path}")


def install_cli():
    src_bin = os.path.join(SCRIPT_DIR, "bin", "workbuddy")
    if not os.path.exists(src_bin):
        print(f"{COLOR_RED}错误: 未在 {src_bin} 找到主程序。{COLOR_RESET}")
        sys.exit(1)
    src_log_guard = os.path.join(SCRIPT_DIR, "bin", "workbuddy-log-guard")

    deploy_sidecar()

    if sys.platform == "win32":
        bin_dir = os.path.join(WORKBUDDY_DIR, "bin")
        os.makedirs(bin_dir, exist_ok=True)
        dest_bin = os.path.join(bin_dir, "workbuddy")
        shutil.copy2(src_bin, dest_bin)

        # 解释器探测顺序：WorkBuddy 自带 Python > PATH 里的 python（排除 Windows
        # Store 的 0 字节占位符，它会拉起应用商店）> py launcher。都找不到时明确
        # 报错并返回 9009（本脚本登记的「无可用解释器」退出码）。
        #
        # 这里只能用 ASCII：_write_cmd() 以 encoding="ascii" 落盘。
        # WindowsApps 过滤必须放进 for /f 的命令串里做：cmd 中管道两侧各起一个
        # 子进程，写成 `if ... echo | findstr ... || set` 时 || 只看 findstr 的
        # 退出码，会覆盖已经选好的解释器。
        py_launcher = (
            "@echo off\r\n"
            "setlocal\r\n"
            "set \"WBPY=\"\r\n"
            "rem Bundled interpreters are probed by directory mtime (newest install first);\r\n"
            "rem the first one passing the 3.8 check wins, so no version-string comparison\r\n"
            "for /f \"delims=\" %%d in ('dir /b /ad /o-d \"%USERPROFILE%\\.workbuddy\\binaries\\python\\versions\" 2^>nul') do (\r\n"
            "    if not defined WBPY call :wb_probe_bundled \"%%d\"\r\n"
            ")\r\n"
            "if not defined WBPY (\r\n"
            "    for /f \"delims=\" %%i in ('where python 2^>nul ^| findstr /v /i /c:\"WindowsApps\"') do (\r\n"
            "        if not defined WBPY set \"WBPY=%%i\"\r\n"
            "    )\r\n"
            ")\r\n"
            "if not defined WBPY (\r\n"
            "    for /f \"delims=\" %%i in ('where py 2^>nul') do if not defined WBPY set \"WBPY=%%i\"\r\n"
            ")\r\n"
            "if defined WBPY goto :wb_run\r\n"
            "echo [workbuddy] {hint_missing} 1>&2\r\n"
            "echo [workbuddy] {hint_fix} 1>&2\r\n"
            "echo [workbuddy] {hint_store} 1>&2\r\n"
            "exit /b 9009\r\n"
            "\r\n"
            ":wb_run\r\n"
            "\"%WBPY%\" \"%~dp0{target}\" %*\r\n"
            "goto :eof\r\n"
            "\r\n"
            ":wb_probe_bundled\r\n"
            "set \"WBCAND=%USERPROFILE%\\.workbuddy\\binaries\\python\\versions\\%~1\\python.exe\"\r\n"
            "if not exist \"%WBCAND%\" goto :eof\r\n"
            "\"%WBCAND%\" -c \"import sys;sys.exit(0 if sys.version_info>=(3,8) else 1)\" >nul 2>nul\r\n"
            "if errorlevel 1 goto :eof\r\n"
            "if defined WBPY goto :eof\r\n"
            "set \"WBPY=%WBCAND%\"\r\n"
            "goto :eof\r\n"
        )
        launcher_zh, launcher_en = _render_launcher(py_launcher, "workbuddy")
        for name in ["workbuddy.cmd", "wb.cmd"]:
            _write_cmd_native(os.path.join(bin_dir, name), launcher_zh, launcher_en)
        for subcmd, names in WINDOWS_SUBCOMMAND_SHIMS.items():
            shim = f"@echo off\r\ncall \"%~dp0workbuddy.cmd\" {subcmd} %*\r\n"
            for name in names:
                _write_cmd(os.path.join(bin_dir, f"{name}.cmd"), shim)

        if os.path.exists(src_log_guard):
            shutil.copy2(src_log_guard, os.path.join(bin_dir, "workbuddy-log-guard"))
            guard_zh, guard_en = _render_launcher(py_launcher, "workbuddy-log-guard")
            _write_cmd_native(os.path.join(bin_dir, "workbuddy-log-guard.cmd"), guard_zh, guard_en)

        # 配置 Windows 用户 PATH 环境变量
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Environment", 0, winreg.KEY_READ | winreg.KEY_WRITE) as key:
                try:
                    cur_path, _ = winreg.QueryValueEx(key, "Path")
                except FileNotFoundError:
                    cur_path = ""
                if bin_dir.lower() not in cur_path.lower():
                    new_path = f"{cur_path};{bin_dir}" if cur_path else bin_dir
                    winreg.SetValueEx(key, "Path", 0, winreg.REG_EXPAND_SZ, new_path)
                    print(f"{COLOR_GREEN}✔ 已将 {bin_dir} 添加至用户 PATH 环境变量{COLOR_RESET}")
        except Exception:
            pass

        print(f"{COLOR_GREEN}1. ✔ CLI 工具及 Windows 命令垫片已安装至: {bin_dir}{COLOR_RESET}")
        return dest_bin, bin_dir

    bin_dir = os.path.join(HOME, ".local", "bin")
    os.makedirs(bin_dir, exist_ok=True)
    dest_bin = os.path.join(bin_dir, "workbuddy")
    shutil.copy2(src_bin, dest_bin)
    os.chmod(dest_bin, 0o755)

    if os.path.exists(src_log_guard):
        dest_log_guard = os.path.join(bin_dir, "workbuddy-log-guard")
        shutil.copy2(src_log_guard, dest_log_guard)
        os.chmod(dest_log_guard, 0o755)

    for alias in CLI_ALIASES:
        link_path = os.path.join(bin_dir, alias)
        if os.path.islink(link_path) or os.path.exists(link_path):
            try:
                os.remove(link_path)
            except Exception:
                pass
        try:
            os.symlink(dest_bin, link_path)
        except Exception:
            shutil.copy2(dest_bin, link_path)

    path_env = os.environ.get("PATH", "")
    if bin_dir not in path_env.split(os.pathsep):
        print(f"{COLOR_YELLOW}   [提示] {bin_dir} 暂不在当前 PATH 中，建议将其加入 ~/.bashrc 或 ~/.zshrc{COLOR_RESET}")

    print(f"{COLOR_GREEN}1. ✔ CLI 工具已安装至: {bin_dir} (workbuddy, wb-help, wb-models, wb-router, wb-switch, wb-checkin){COLOR_RESET}")
    return dest_bin, bin_dir


def init_workspace(dest_bin, enabled):
    if not enabled:
        print(f"2. [跳过] 未开启多账号工作区共享。需要时运行: {COLOR_BOLD}workbuddy init{COLOR_RESET}")
        return
    if not os.path.exists(DB_FILE):
        print(f"2. {COLOR_YELLOW}[跳过] 未检测到 {DB_FILE}，首次启动 WorkBuddy 后可运行 'workbuddy init'。{COLOR_RESET}")
        return
    print("2. 正在开启多账号工作区共享 (workbuddy init)...")
    # 复用 CLI 的实现，保证与 `workbuddy init` 完全一致（含会话归属备份）
    subprocess.run([sys.executable, dest_bin, "init"])


def _render_template(src, dest, replacements):
    with open(src, "r", encoding="utf-8") as f:
        content = f.read()
    for k, v in replacements.items():
        content = content.replace(k, v)
    with open(dest, "w", encoding="utf-8") as f:
        f.write(content)


def _load_launch_agent(name):
    launch_dir = os.path.join(HOME, "Library", "LaunchAgents")
    os.makedirs(launch_dir, exist_ok=True)
    src = os.path.join(SCRIPT_DIR, "launchd", f"{name}.plist")
    dest = os.path.join(launch_dir, f"{name}.plist")
    if not os.path.exists(src):
        return False
    _render_template(src, dest, {"{{HOME}}": HOME})
    subprocess.run(["launchctl", "unload", dest], stderr=subprocess.DEVNULL, stdout=subprocess.DEVNULL)
    subprocess.run(["launchctl", "load", "-w", dest], stderr=subprocess.DEVNULL, stdout=subprocess.DEVNULL)
    return True


def _install_systemd_unit(base):
    systemd_user_dir = os.path.join(HOME, ".config", "systemd", "user")
    svc_src = os.path.join(SCRIPT_DIR, "systemd", f"{base}.service")
    tmr_src = os.path.join(SCRIPT_DIR, "systemd", f"{base}.timer")
    if not (os.path.exists(svc_src) and os.path.exists(tmr_src)):
        return False
    os.makedirs(systemd_user_dir, exist_ok=True)
    shutil.copy2(svc_src, os.path.join(systemd_user_dir, f"{base}.service"))
    shutil.copy2(tmr_src, os.path.join(systemd_user_dir, f"{base}.timer"))
    subprocess.run(["systemctl", "--user", "daemon-reload"], stderr=subprocess.DEVNULL)
    res = subprocess.run(["systemctl", "--user", "enable", "--now", f"{base}.timer"], stderr=subprocess.DEVNULL)
    return res.returncode == 0


def _startup_fallback_path(task_name="WorkBuddyDailyCheckin"):
    """登录启动项兜底的固定路径；写入与清理共用，避免两处各拼一遍。"""
    appdata = os.environ.get("APPDATA")
    if not appdata:
        return None
    return os.path.join(appdata, "Microsoft", "Windows", "Start Menu",
                        "Programs", "Startup", f"{task_name}.vbs")


def _remove_windows_startup_fallback(task_name="WorkBuddyDailyCheckin"):
    """删除登录启动项兜底，返回是否真的删掉了文件。"""
    path = _startup_fallback_path(task_name)
    if path and os.path.exists(path):
        try:
            os.remove(path)
            return True
        except OSError:
            return False
    return False


def _install_windows_startup_fallback(task_name, cmd):
    """任务计划程序不可用时的降级路径：写入当前用户的启动文件夹。

    与 Linux 分支 systemd→cron 的降级思路一致，语义会从「每天 09:00」退化为
    「登录时执行一次」，但总好过 --with-checkin 静默失效。

    WSH 按系统 ANSI 代码页解码脚本，中文用户名下的路径会读成乱码，因此必须写
    UTF-16LE + BOM。用二进制写入顺带避免了 newline 翻译产生 \r\r\n。
    """
    path = _startup_fallback_path(task_name)
    if not path or not os.path.isdir(os.path.dirname(path)):
        return None

    lines = [
        "' Auto-generated by WorkBuddy Toolkit: check-in fallback "
        "when Task Scheduler is unavailable",
        f'CreateObject("WScript.Shell").Run "{cmd.replace(chr(34), chr(34) * 2)}", 0, False',
        "",
    ]
    try:
        with open(path, "wb") as f:
            f.write(b"\xff\xfe")
            f.write("\r\n".join(lines).encode("utf-16-le"))
    except OSError:
        return None
    return path


def _add_cron_lines(new_lines):
    proc = subprocess.run(["crontab", "-l"], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
    existing = proc.stdout if proc.returncode == 0 else ""
    markers = [m for m, _ in new_lines]
    lines = [l for l in existing.splitlines() if not any(m in l for m in markers)]
    lines.extend(line for _, line in new_lines)
    set_proc = subprocess.Popen(["crontab", "-"], stdin=subprocess.PIPE, text=True)
    set_proc.communicate("\n".join(lines) + "\n")
    return set_proc.returncode == 0


def setup_scheduler(bin_path, bin_dir, opts):
    wanted = [k for k in ("checkin", "log_guard", "router") if opts.get(k)]
    if not wanted:
        print("3. [跳过] 未注册任何后台任务。需要时重新运行: python3 install.py --with-checkin / --with-log-guard / --with-router")
        return
    print("3. 正在注册已开启的后台任务...")

    if sys.platform == "darwin":
        if opts.get("checkin") and _load_launch_agent("com.workbuddy.dailycheckin"):
            print(f"{COLOR_GREEN}   ✔ LaunchAgent 已激活: 每天 09:00 签到{COLOR_RESET}")
        if opts.get("router") and _load_launch_agent("com.workbuddy.failover-router"):
            print(f"{COLOR_GREEN}   ✔ LaunchAgent 已激活: Failover Router 容灾路由 (127.0.0.1:8047){COLOR_RESET}")
        if opts.get("log_guard") and _load_launch_agent("com.workbuddy.log-guard"):
            print(f"{COLOR_GREEN}   ✔ LaunchAgent 已激活: Log Guard 看门狗 (每 30 分钟){COLOR_RESET}")
        return

    if opts.get("router"):
        print(f"{COLOR_YELLOW}   [提示] 容灾路由常驻服务目前只提供 macOS LaunchAgent；其他平台请按需运行: wb-router start{COLOR_RESET}")

    if sys.platform == "win32":
        python_exe = sys.executable
        pythonw_exe = python_exe.replace("python.exe", "pythonw.exe")
        runner = pythonw_exe if os.path.exists(pythonw_exe) else python_exe
        if opts.get("checkin"):
            # 每日任务保持原样（含保活对话，与文档一致）；只有降级路径关掉对话，
            # 避免登录相关事件多次触发时重复发送
            cmd = f'"{runner}" "{bin_path}" checkin'
            log_path = os.path.join(LOGS_DIR, "checkin.log")
            # 降级路径与 Linux 的 cron 分支对齐：把输出落到 checkin.log，
            # 否则 pythonw + 隐藏窗口会让失败完全无声。
            fallback_cmd = f'cmd /c ""{runner}" "{bin_path}" checkin --no-chat >> "{log_path}" 2>&1"'
            res = subprocess.run(["schtasks", "/create", "/tn", "WorkBuddyDailyCheckin", "/tr", cmd, "/sc", "daily", "/st", "09:00", "/f"],
                                 stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            if res.returncode == 0:
                # 两个触发器互斥：任务计划恢复后必须删掉旧启动项，否则会一天跑两次
                stale = _startup_fallback_path()
                if stale and os.path.exists(stale) and not _remove_windows_startup_fallback():
                    print(f"{COLOR_YELLOW}   [警告] 旧的登录启动项删除失败，请手工删除: {stale}{COLOR_RESET}")
                print(f"{COLOR_GREEN}   ✔ Windows 任务计划已激活: 每天 09:00 签到 (WorkBuddyDailyCheckin){COLOR_RESET}")
            else:
                # 上一次可能注册成功过；这次被策略拒绝时那条任务仍然有效，
                # 不删就会和登录触发并存，同一天签到两次
                subprocess.run(["schtasks", "/delete", "/tn", "WorkBuddyDailyCheckin", "/f"],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                fallback_path = _install_windows_startup_fallback("WorkBuddyDailyCheckin", fallback_cmd)
                if fallback_path:
                    print(f"{COLOR_YELLOW}   [降级] 任务计划不可用，已改为登录时签到（仅签到，不含保活对话）: {fallback_path}{COLOR_RESET}")
                    print(f"{COLOR_YELLOW}          输出日志: {log_path}{COLOR_RESET}")
                else:
                    detail = res.stderr.strip() or res.stdout.strip() or "unknown"
                    print(f"{COLOR_YELLOW}   [提示] 任务计划注册失败，且无法写入启动项: {detail}{COLOR_RESET}")
        if opts.get("log_guard"):
            guard_cmd = f'"{runner}" "{os.path.join(bin_dir, "workbuddy-log-guard")}"'
            res = subprocess.run(["schtasks", "/create", "/tn", "WorkBuddyLogGuard", "/tr", guard_cmd, "/sc", "minute", "/mo", "30", "/f"],
                                 stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            if res.returncode == 0:
                print(f"{COLOR_GREEN}   ✔ Windows 任务计划已激活: 每 30 分钟日志治理 (WorkBuddyLogGuard){COLOR_RESET}")
            else:
                print(f"{COLOR_YELLOW}   [提示] Log Guard 任务计划注册返回: {res.stderr.strip()}{COLOR_RESET}")
        return

    # Linux: 优先 systemd --user，失败再降级 cron
    cron_lines = []
    has_systemd = shutil.which("systemctl") is not None
    if opts.get("checkin"):
        if has_systemd and _install_systemd_unit("workbuddy-dailycheckin"):
            print(f"{COLOR_GREEN}   ✔ systemd user timer 已激活: 每天 09:00 签到{COLOR_RESET}")
        else:
            cron_lines.append(("workbuddy checkin", f"0 9 * * * {bin_path} checkin >> {LOGS_DIR}/checkin.log 2>&1"))
    if opts.get("log_guard"):
        if has_systemd and _install_systemd_unit("workbuddy-log-guard"):
            print(f"{COLOR_GREEN}   ✔ systemd user timer 已激活: 每 30 分钟日志治理{COLOR_RESET}")
        else:
            cron_lines.append(("workbuddy-log-guard", f"0,30 * * * * {bin_dir}/workbuddy-log-guard >> {LOGS_DIR}/log-guard.log 2>&1"))
    if cron_lines:
        if shutil.which("crontab"):
            try:
                if _add_cron_lines(cron_lines):
                    print(f"{COLOR_GREEN}   ✔ crontab 定时任务已配置 ({len(cron_lines)} 项){COLOR_RESET}")
            except Exception as e:
                print(f"{COLOR_YELLOW}   [提示] crontab 配置失败: {e}{COLOR_RESET}")
        else:
            print(f"{COLOR_YELLOW}   [提示] 未找到 systemd/crontab，后台任务未注册，可随时手动运行。{COLOR_RESET}")


def setup_antigravity_sidecar(dest_bin, opts):
    """Antigravity Scheduled Tasks 伴随体本质上也是一个每日签到计划任务，跟随 checkin 开关。"""
    if not opts.get("checkin"):
        return
    gemini_dir = os.path.join(HOME, ".gemini")
    if not os.path.exists(gemini_dir):
        return
    sidecar_dest = os.path.join(gemini_dir, "config", "sidecars", "workbuddy-checkin")
    sidecar_src = os.path.join(SCRIPT_DIR, "sidecar", "sidecar.json")
    if os.path.exists(sidecar_src):
        os.makedirs(sidecar_dest, exist_ok=True)
        _render_template(sidecar_src, os.path.join(sidecar_dest, "sidecar.json"), {"{{BIN_PATH}}": dest_bin, "{{HOME}}": HOME})
        print(f"{COLOR_GREEN}4. ✔ Antigravity 侧边栏签到任务已配置{COLOR_RESET}")


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    print_banner()
    opts = parse_options(argv)
    setup_dirs()
    dest_bin, bin_dir = install_cli()
    init_workspace(dest_bin, opts.get("init_workspace"))
    setup_scheduler(dest_bin, bin_dir, opts)
    setup_antigravity_sidecar(dest_bin, opts)
    print(f"\n{COLOR_BOLD}{COLOR_GREEN}========================================================{COLOR_RESET}")
    print(f"{COLOR_BOLD}{COLOR_GREEN}🎉 安装部署全部完成！{COLOR_RESET}")
    print(f"{COLOR_CYAN}下一步:{COLOR_RESET}")
    print(f"  • {COLOR_BOLD}workbuddy doctor{COLOR_RESET}      : 检查凭据与运行时兼容性")
    print(f"  • {COLOR_BOLD}wb-login{COLOR_RESET}              : 添加账号")
    print(f"  • {COLOR_BOLD}wb-switch{COLOR_RESET}             : 多账号切换菜单")
    print(f"  • {COLOR_BOLD}wb-checkin{COLOR_RESET}            : 手动执行签到")
    print(f"  • {COLOR_BOLD}workbuddy init{COLOR_RESET}        : 开启多账号工作区共享 (可用 workbuddy rollback 恢复)")
    print(f"{COLOR_BOLD}{COLOR_GREEN}========================================================{COLOR_RESET}\n")


if __name__ == "__main__":
    main()
