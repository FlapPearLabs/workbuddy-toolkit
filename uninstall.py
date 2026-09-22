#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
WorkBuddy Toolkit Universal Cross-Platform Uninstaller
Works out-of-the-box on macOS, Linux, and Windows.
https://github.com/FlapPearLabs/workbuddy-toolkit
"""

import os
import sys
import shutil
import sqlite3
import subprocess

if sys.platform == "win32":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

HOME = os.path.expanduser("~")
WORKBUDDY_DIR = os.path.join(HOME, ".workbuddy")
DB_FILE = os.path.join(WORKBUDDY_DIR, "workbuddy.db")

COLOR_GREEN = "\033[92m" if sys.platform != "win32" or "WT_SESSION" in os.environ or os.environ.get("TERM_PROGRAM") else ""
COLOR_YELLOW = "\033[93m" if sys.platform != "win32" or "WT_SESSION" in os.environ or os.environ.get("TERM_PROGRAM") else ""
COLOR_CYAN = "\033[96m" if sys.platform != "win32" or "WT_SESSION" in os.environ or os.environ.get("TERM_PROGRAM") else ""
COLOR_RED = "\033[91m" if sys.platform != "win32" or "WT_SESSION" in os.environ or os.environ.get("TERM_PROGRAM") else ""
COLOR_RESET = "\033[0m" if sys.platform != "win32" or "WT_SESSION" in os.environ or os.environ.get("TERM_PROGRAM") else ""

def uninstall():
    print(f"\n{COLOR_YELLOW}正在卸载 WorkBuddy Toolkit ({sys.platform})...{COLOR_RESET}")

    # 1. 卸载定时任务
    if sys.platform == "darwin":
        plist_path = os.path.join(HOME, "Library", "LaunchAgents", "com.workbuddy.dailycheckin.plist")
        if os.path.exists(plist_path):
            subprocess.run(["launchctl", "unload", plist_path], stderr=subprocess.DEVNULL, stdout=subprocess.DEVNULL)
            try:
                os.remove(plist_path)
            except Exception:
                pass
            print(f"{COLOR_GREEN}✔ 已注销并删除 macOS LaunchAgent 定时任务{COLOR_RESET}")
    elif sys.platform == "win32":
        try:
            subprocess.run(["schtasks", "/delete", "/tn", "WorkBuddyDailyCheckin", "/f"], stderr=subprocess.DEVNULL, stdout=subprocess.DEVNULL)
            print(f"{COLOR_GREEN}✔ 已注销 Windows 任务计划: WorkBuddyDailyCheckin{COLOR_RESET}")
        except Exception:
            pass
    else:  # Linux
        # systemd
        svc = os.path.join(HOME, ".config", "systemd", "user", "workbuddy-dailycheckin.service")
        tmr = os.path.join(HOME, ".config", "systemd", "user", "workbuddy-dailycheckin.timer")
        if os.path.exists(tmr):
            subprocess.run(["systemctl", "--user", "disable", "--now", "workbuddy-dailycheckin.timer"], stderr=subprocess.DEVNULL)
            for f in [svc, tmr]:
                if os.path.exists(f):
                    os.remove(f)
            subprocess.run(["systemctl", "--user", "daemon-reload"], stderr=subprocess.DEVNULL)
            print(f"{COLOR_GREEN}✔ 已清理 Linux systemd user timer 任务{COLOR_RESET}")
        # crontab
        if shutil.which("crontab"):
            try:
                proc = subprocess.run(["crontab", "-l"], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
                if proc.returncode == 0 and "workbuddy checkin" in proc.stdout:
                    lines = [l for l in proc.stdout.splitlines() if "workbuddy checkin" not in l]
                    new_cron = "\n".join(lines) + "\n"
                    set_proc = subprocess.Popen(["crontab", "-"], stdin=subprocess.PIPE, text=True)
                    set_proc.communicate(new_cron)
                    print(f"{COLOR_GREEN}✔ 已从 crontab 移除定时任务{COLOR_RESET}")
            except Exception:
                pass

    # 2. 清理 Sidecar
    sidecar_dir = os.path.join(HOME, ".gemini", "config", "sidecars", "workbuddy-checkin")
    if os.path.exists(sidecar_dir):
        shutil.rmtree(sidecar_dir, ignore_errors=True)
        print(f"{COLOR_GREEN}✔ 已清理 Antigravity Sidecar 任务{COLOR_RESET}")

    # 3. 移除可执行文件
    if sys.platform == "win32":
        bin_dir = os.path.join(WORKBUDDY_DIR, "bin")
        if os.path.exists(bin_dir):
            shutil.rmtree(bin_dir, ignore_errors=True)
            print(f"{COLOR_GREEN}✔ 已删除 Windows CLI 安装目录及垫片 ({bin_dir}){COLOR_RESET}")
    else:
        bin_dir = os.path.join(HOME, ".local", "bin")
        for name in ["workbuddy", "wb-switch", "workbuddy-switch", "wb-checkin", "workbuddy-checkin"]:
            fpath = os.path.join(bin_dir, name)
            if os.path.islink(fpath) or os.path.exists(fpath):
                try:
                    os.remove(fpath)
                except Exception:
                    pass
        print(f"{COLOR_GREEN}✔ 已清理安装的 CLI 脚本与软链接{COLOR_RESET}")

    # 4. 询问回滚数据库触发器
    try:
        if "--yes" in sys.argv or "-y" in sys.argv:
            ans = "y"
        elif "--no-rollback" in sys.argv or not sys.stdin.isatty():
            ans = "n"
        else:
            ans = input("是否需要同时回滚 SQLite 数据库触发器并恢复官方默认数据隔离？(y/N): ").strip()

        if ans.lower() == "y" and os.path.exists(DB_FILE):
            con = sqlite3.connect(DB_FILE)
            con.execute("DROP TRIGGER IF EXISTS trg_sessions_force_shared_insert;")
            con.execute("DROP TRIGGER IF EXISTS trg_sessions_force_shared_update;")
            con.commit()
            con.close()
            print(f"{COLOR_GREEN}✔ 数据库共享触发器已成功撤销{COLOR_RESET}")
    except (EOFError, KeyboardInterrupt):
        pass

    print(f"\n{COLOR_GREEN}卸载完成！已保存的账号凭证仍安全保留在 ~/.workbuddy/auth_profiles/ 下。{COLOR_RESET}\n")

if __name__ == "__main__":
    uninstall()
