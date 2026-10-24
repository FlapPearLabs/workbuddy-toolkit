#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
WorkBuddy Toolkit Universal Cross-Platform Uninstaller
Works out-of-the-box on macOS, Linux, and Windows.
https://github.com/FlapPearLabs/workbuddy-toolkit

用法:
    python3 uninstall.py              # 交互式，会询问是否回滚数据库共享
    python3 uninstall.py --yes        # 同时回滚数据库共享（恢复各会话原始归属）
    python3 uninstall.py --no-rollback
    python3 uninstall.py --keep-config  # 保留 failover_router.json / log_guard.json 等配置

始终保留: ~/.workbuddy/auth_profiles/ 下已保存的账号凭证。
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
DB_FILE = os.path.join(WORKBUDDY_DIR, "workbuddy.db")
TOOLKIT_DIR = os.path.join(WORKBUDDY_DIR, "toolkit")
MODELS_JSON = os.path.join(WORKBUDDY_DIR, "models.json")
ROUTER_CONFIG = os.path.join(WORKBUDDY_DIR, "failover_router.json")

_USE_COLOR = sys.stdout.isatty() and "NO_COLOR" not in os.environ
COLOR_GREEN = "\033[92m" if _USE_COLOR else ""
COLOR_YELLOW = "\033[93m" if _USE_COLOR else ""
COLOR_CYAN = "\033[96m" if _USE_COLOR else ""
COLOR_RED = "\033[91m" if _USE_COLOR else ""
COLOR_RESET = "\033[0m" if _USE_COLOR else ""

CLI_NAMES = [
    "workbuddy", "workbuddy-log-guard",
    "wb-help", "workbuddy-help", "wb-login", "workbuddy-login", "wb-audit", "workbuddy-audit",
    "wb-list", "workbuddy-list", "wb-status", "workbuddy-status", "wb-switch", "workbuddy-switch",
    "wb-remove", "workbuddy-remove",
    "wb-checkin", "workbuddy-checkin", "wb-chat", "workbuddy-chat", "wb-doctor", "workbuddy-doctor",
    "wb-models", "workbuddy-models", "wb-usage", "workbuddy-usage", "wb-router", "workbuddy-router",
    "wb-sandbox", "workbuddy-sandbox", "wb-tool", "workbuddy-tool",
]

# Toolkit 自己创建的配置/状态文件（不含账号凭证）
TOOLKIT_OWNED_FILES = [
    "failover_router.json",   # 可能含用户自定义上游 API Key
    "router_token",
    "log_guard.json",
    os.path.join("cache", "audit_cache.json"),
    os.path.join("cache", "heal.lock"),
    os.path.join("logs", "failover_router.log"),
    os.path.join("logs", "checkin.log"),
    os.path.join("logs", "log-guard.log"),
    os.path.join("logs", "log-guard.out"),
    os.path.join("logs", "log-guard.err"),
]


def same_path(a, b):
    try:
        return os.path.realpath(a) == os.path.realpath(b)
    except OSError:
        return False


def _remove(path):
    try:
        if os.path.islink(path) or os.path.isfile(path):
            os.remove(path)
            return True
        if os.path.isdir(path):
            shutil.rmtree(path, ignore_errors=True)
            return True
    except OSError:
        pass
    return False


def unregister_services():
    if sys.platform == "darwin":
        for label in ("com.workbuddy.dailycheckin", "com.workbuddy.failover-router", "com.workbuddy.log-guard"):
            plist = os.path.join(HOME, "Library", "LaunchAgents", f"{label}.plist")
            if os.path.exists(plist):
                subprocess.run(["launchctl", "unload", plist], stderr=subprocess.DEVNULL, stdout=subprocess.DEVNULL)
                _remove(plist)
                print(f"{COLOR_GREEN}✔ 已注销并删除 LaunchAgent: {label}{COLOR_RESET}")
    elif sys.platform == "win32":
        for task in ("WorkBuddyDailyCheckin", "WorkBuddyLogGuard"):
            try:
                res = subprocess.run(["schtasks", "/delete", "/tn", task, "/f"], stderr=subprocess.DEVNULL, stdout=subprocess.DEVNULL)
                if res.returncode == 0:
                    print(f"{COLOR_GREEN}✔ 已注销 Windows 任务计划: {task}{COLOR_RESET}")
            except Exception:
                pass
        # 任务计划不可用时安装器会退回登录启动项，这里一并清理。
        # 路径拼接与 install.py 的 _startup_fallback_path 保持一致，改动时两边同步。
        appdata = os.environ.get("APPDATA")
        if appdata:
            fallback_vbs = os.path.join(appdata, "Microsoft", "Windows", "Start Menu",
                                        "Programs", "Startup", "WorkBuddyDailyCheckin.vbs")
            if os.path.exists(fallback_vbs):
                _remove(fallback_vbs)
                print(f"{COLOR_GREEN}✔ 已删除登录启动项兜底: WorkBuddyDailyCheckin.vbs{COLOR_RESET}")
    else:  # Linux
        unit_dir = os.path.join(HOME, ".config", "systemd", "user")
        removed_any = False
        for base in ("workbuddy-dailycheckin", "workbuddy-log-guard"):
            tmr = os.path.join(unit_dir, f"{base}.timer")
            svc = os.path.join(unit_dir, f"{base}.service")
            if os.path.exists(tmr) or os.path.exists(svc):
                if shutil.which("systemctl"):
                    subprocess.run(["systemctl", "--user", "disable", "--now", f"{base}.timer"], stderr=subprocess.DEVNULL, stdout=subprocess.DEVNULL)
                _remove(tmr)
                _remove(svc)
                removed_any = True
        if removed_any:
            if shutil.which("systemctl"):
                subprocess.run(["systemctl", "--user", "daemon-reload"], stderr=subprocess.DEVNULL)
            print(f"{COLOR_GREEN}✔ 已清理 Linux systemd user timer{COLOR_RESET}")
        if shutil.which("crontab"):
            try:
                proc = subprocess.run(["crontab", "-l"], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
                if proc.returncode == 0:
                    lines = proc.stdout.splitlines()
                    kept = [l for l in lines if "workbuddy checkin" not in l and "workbuddy-log-guard" not in l]
                    if len(kept) != len(lines):
                        set_proc = subprocess.Popen(["crontab", "-"], stdin=subprocess.PIPE, text=True)
                        set_proc.communicate("\n".join(kept) + "\n")
                        print(f"{COLOR_GREEN}✔ 已从 crontab 移除定时任务{COLOR_RESET}")
            except Exception:
                pass

    # 手动启动的 router（非 launchd）也一并停止
    if sys.platform != "win32" and shutil.which("pkill"):
        subprocess.run(["pkill", "-f", "toolkit/sidecar/router_engine.py"], stderr=subprocess.DEVNULL, stdout=subprocess.DEVNULL)


def restore_models_json():
    """还原 wb-models 对 WorkBuddy models.json 的改写，否则卸载后这些模型会指向已不存在的 127.0.0.1:8047。"""
    sidecar_candidates = [os.path.join(SCRIPT_DIR, "sidecar"), os.path.join(TOOLKIT_DIR, "sidecar")]
    for cand in sidecar_candidates:
        if os.path.exists(os.path.join(cand, "models_inventory.py")):
            sys.path.insert(0, cand)
            break
    else:
        return
    try:
        import models_inventory
        summary = models_inventory.restore_models_json(
            models_json_path=MODELS_JSON, router_config_path=ROUTER_CONFIG,
            port=_router_port(models_inventory),
        )
        if summary.get("restored") or summary.get("removed"):
            print(f"{COLOR_GREEN}✔ 已还原 models.json: 恢复 {summary['restored']} 个模型的原始上游，移除 {summary['removed']} 个 Toolkit 注册的条目{COLOR_RESET}")
        if summary.get("left"):
            print(f"{COLOR_YELLOW}▲ models.json 中仍有 {summary['left']} 个条目指向本地路由且无法确定原值，请在 WorkBuddy 中手动调整{COLOR_RESET}")
    except Exception as e:
        print(f"{COLOR_YELLOW}▲ 还原 models.json 失败: {e}{COLOR_RESET}")


def _router_port(models_inventory):
    try:
        return int(models_inventory.load_failover_config(ROUTER_CONFIG).get("port", 8047))
    except Exception:
        return 8047


def rollback_database(argv):
    if "--yes" in argv or "-y" in argv:
        ans = "y"
    elif "--no-rollback" in argv or not sys.stdin.isatty():
        ans = "n"
    else:
        try:
            ans = input("是否同时回滚多账号工作区共享，并恢复各会话原始账号归属？(y/N): ").strip()
        except (EOFError, KeyboardInterrupt):
            ans = "n"
    if ans.lower() != "y" or not os.path.exists(DB_FILE):
        return
    cli = os.path.join(SCRIPT_DIR, "bin", "workbuddy")
    if not os.path.exists(cli):
        cli = os.path.join(HOME, ".local", "bin", "workbuddy")
    if os.path.exists(cli):
        # 复用 CLI 实现：按备份表恢复每个会话与自动化任务的原始归属
        subprocess.run([sys.executable, cli, "rollback"])
    else:
        import sqlite3
        con = sqlite3.connect(DB_FILE)
        con.execute("DROP TRIGGER IF EXISTS trg_sessions_force_shared_insert;")
        con.execute("DROP TRIGGER IF EXISTS trg_sessions_force_shared_update;")
        con.commit()
        con.close()
        print(f"{COLOR_GREEN}✔ 数据库共享触发器已撤销{COLOR_RESET}")


def remove_cli():
    if sys.platform == "win32":
        bin_dir = os.path.join(WORKBUDDY_DIR, "bin")
        if os.path.exists(bin_dir):
            shutil.rmtree(bin_dir, ignore_errors=True)
            print(f"{COLOR_GREEN}✔ 已删除 Windows CLI 安装目录及垫片 ({bin_dir}){COLOR_RESET}")
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Environment", 0, winreg.KEY_READ | winreg.KEY_WRITE) as key:
                try:
                    cur_path, _ = winreg.QueryValueEx(key, "Path")
                    paths = [p for p in cur_path.split(";") if p and p.lower() != bin_dir.lower()]
                    winreg.SetValueEx(key, "Path", 0, winreg.REG_EXPAND_SZ, ";".join(paths))
                    print(f"{COLOR_GREEN}✔ 已从用户 PATH 环境变量移除 {bin_dir}{COLOR_RESET}")
                except FileNotFoundError:
                    pass
        except Exception:
            pass
        return
    bin_dir = os.path.join(HOME, ".local", "bin")
    for name in CLI_NAMES:
        _remove(os.path.join(bin_dir, name))
    print(f"{COLOR_GREEN}✔ 已清理安装的 CLI 脚本与软链接{COLOR_RESET}")


def remove_toolkit_files(argv):
    sidecar_dir = os.path.join(HOME, ".gemini", "config", "sidecars", "workbuddy-checkin")
    if _remove(sidecar_dir):
        print(f"{COLOR_GREEN}✔ 已清理 Antigravity Sidecar 任务{COLOR_RESET}")

    # README 推荐把仓库直接 clone 到 ~/.workbuddy/toolkit：那是用户的源码检出，不能整目录删除
    if os.path.isdir(TOOLKIT_DIR):
        is_checkout = os.path.isdir(os.path.join(TOOLKIT_DIR, ".git")) or same_path(TOOLKIT_DIR, SCRIPT_DIR)
        if is_checkout:
            print(f"{COLOR_CYAN}ℹ {TOOLKIT_DIR} 是 Toolkit 源码仓库，已保留；如不再需要可手动删除。{COLOR_RESET}")
        else:
            shutil.rmtree(TOOLKIT_DIR, ignore_errors=True)
            print(f"{COLOR_GREEN}✔ 已清理 Toolkit 伴随组件目录 ({TOOLKIT_DIR}){COLOR_RESET}")

    _remove(os.path.join(WORKBUDDY_DIR, "toolkit-state"))
    if "--keep-config" in argv:
        return
    removed = [rel for rel in TOOLKIT_OWNED_FILES if _remove(os.path.join(WORKBUDDY_DIR, rel))]
    if removed:
        print(f"{COLOR_GREEN}✔ 已清理 Toolkit 配置与日志: {', '.join(removed)}{COLOR_RESET}")


def uninstall(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    print(f"\n{COLOR_YELLOW}正在卸载 WorkBuddy Toolkit ({sys.platform})...{COLOR_RESET}")
    unregister_services()
    restore_models_json()
    rollback_database(argv)
    remove_cli()
    remove_toolkit_files(argv)
    print(f"\n{COLOR_GREEN}卸载完成！已保存的账号凭证仍安全保留在 ~/.workbuddy/auth_profiles/ 下。{COLOR_RESET}\n")


if __name__ == "__main__":
    uninstall()
