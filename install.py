#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
WorkBuddy Toolkit Universal Cross-Platform Installer
Works out-of-the-box on macOS, Linux, and Windows with zero dependencies.
https://github.com/FlapPearLabs/workbuddy-toolkit
"""

import os
import sys
import shutil
import sqlite3
import subprocess

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
HOME = os.path.expanduser("~")
WORKBUDDY_DIR = os.path.join(HOME, ".workbuddy")
AUTH_PROFILES_DIR = os.path.join(WORKBUDDY_DIR, "auth_profiles")
LOGS_DIR = os.path.join(WORKBUDDY_DIR, "logs")
DB_FILE = os.path.join(WORKBUDDY_DIR, "workbuddy.db")

COLOR_GREEN = "\033[92m" if sys.platform != "win32" or "WT_SESSION" in os.environ or os.environ.get("TERM_PROGRAM") else ""
COLOR_YELLOW = "\033[93m" if sys.platform != "win32" or "WT_SESSION" in os.environ or os.environ.get("TERM_PROGRAM") else ""
COLOR_CYAN = "\033[96m" if sys.platform != "win32" or "WT_SESSION" in os.environ or os.environ.get("TERM_PROGRAM") else ""
COLOR_RED = "\033[91m" if sys.platform != "win32" or "WT_SESSION" in os.environ or os.environ.get("TERM_PROGRAM") else ""
COLOR_BOLD = "\033[1m" if sys.platform != "win32" or "WT_SESSION" in os.environ or os.environ.get("TERM_PROGRAM") else ""
COLOR_RESET = "\033[0m" if sys.platform != "win32" or "WT_SESSION" in os.environ or os.environ.get("TERM_PROGRAM") else ""

def print_banner():
    print(f"\n{COLOR_BOLD}{COLOR_CYAN}========================================================{COLOR_RESET}")
    print(f"{COLOR_BOLD}{COLOR_CYAN}    WorkBuddy Toolkit 全平台通用安装程序 ({sys.platform}){COLOR_RESET}")
    print(f"{COLOR_BOLD}{COLOR_CYAN}========================================================{COLOR_RESET}")

def setup_dirs():
    os.makedirs(AUTH_PROFILES_DIR, exist_ok=True)
    os.makedirs(LOGS_DIR, exist_ok=True)

def install_cli():
    src_bin = os.path.join(SCRIPT_DIR, "bin", "workbuddy")
    if not os.path.exists(src_bin):
        print(f"{COLOR_RED}错误: 未在 {src_bin} 找到主程序。{COLOR_RESET}")
        sys.exit(1)

    if sys.platform == "win32":
        bin_dir = os.path.join(WORKBUDDY_DIR, "bin")
        os.makedirs(bin_dir, exist_ok=True)
        dest_bin = os.path.join(bin_dir, "workbuddy")
        shutil.copy2(src_bin, dest_bin)

        # 写入 Windows CMD 垫片
        cmd_wrapper = (
            "@echo off\r\n"
            "setlocal\r\n"
            "where python >nul 2>nul\r\n"
            "if %ERRORLEVEL% equ 0 (\r\n"
            "    python \"%~dp0workbuddy\" %*\r\n"
            ") else (\r\n"
            "    py \"%~dp0workbuddy\" %*\r\n"
            ")\r\n"
        )
        for name in ["workbuddy.cmd", "wb.cmd"]:
            with open(os.path.join(bin_dir, name), "w", encoding="ascii") as f:
                f.write(cmd_wrapper)

        cmd_switch = "@echo off\r\ncall \"%~dp0workbuddy.cmd\" switch %*\r\n"
        for name in ["wb-switch.cmd", "workbuddy-switch.cmd"]:
            with open(os.path.join(bin_dir, name), "w", encoding="ascii") as f:
                f.write(cmd_switch)

        cmd_checkin = "@echo off\r\ncall \"%~dp0workbuddy.cmd\" checkin %*\r\n"
        for name in ["wb-checkin.cmd", "workbuddy-checkin.cmd"]:
            with open(os.path.join(bin_dir, name), "w", encoding="ascii") as f:
                f.write(cmd_checkin)

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
    else:
        bin_dir = os.path.join(HOME, ".local", "bin")
        os.makedirs(bin_dir, exist_ok=True)
        dest_bin = os.path.join(bin_dir, "workbuddy")
        shutil.copy2(src_bin, dest_bin)
        os.chmod(dest_bin, 0o755)

        for alias in ["wb-switch", "workbuddy-switch", "wb-checkin", "workbuddy-checkin"]:
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
        if bin_dir not in path_env:
            print(f"{COLOR_YELLOW}   [提示] {bin_dir} 暂不在当前 PATH 中，建议将其加入 ~/.bashrc 或 ~/.zshrc{COLOR_RESET}")

        print(f"{COLOR_GREEN}1. ✔ CLI 工具已安装至: {bin_dir} (workbuddy, wb-switch, wb-checkin){COLOR_RESET}")
        return dest_bin, bin_dir

def init_db():
    if os.path.exists(DB_FILE):
        print(f"2. 正在初始化 SQLite 数据库工作区打通补丁...")
        try:
            con = sqlite3.connect(DB_FILE)
            cur = con.cursor()
            cur.execute("UPDATE sessions SET user_id = '' WHERE user_id IS NOT NULL AND user_id != '';")
            cur.execute("""
            CREATE TRIGGER IF NOT EXISTS trg_sessions_force_shared_insert
            AFTER INSERT ON sessions
            BEGIN
                UPDATE sessions SET user_id = '' WHERE id = NEW.id;
            END;
            """)
            cur.execute("""
            CREATE TRIGGER IF NOT EXISTS trg_sessions_force_shared_update
            AFTER UPDATE OF user_id ON sessions
            WHEN NEW.user_id != '' AND NEW.user_id IS NOT NULL
            BEGIN
                UPDATE sessions SET user_id = '' WHERE id = NEW.id;
            END;
            """)
            con.commit()
            con.close()
            print(f"{COLOR_GREEN}   ✔ 全域会话打通触发器已激活{COLOR_RESET}")
        except Exception as e:
            print(f"{COLOR_RED}   ✖ 数据库配置异常: {e}{COLOR_RESET}")
    else:
        print(f"2. {COLOR_YELLOW}[跳过] 未检测到 {DB_FILE}，首次启动 WorkBuddy 后可运行 'workbuddy init' 打补丁。{COLOR_RESET}")

def setup_scheduler(bin_path, bin_dir):
    print(f"3. 正在配置系统级每日 09:00 定时自动打卡...")
    if sys.platform == "darwin":
        launch_dir = os.path.join(HOME, "Library", "LaunchAgents")
        os.makedirs(launch_dir, exist_ok=True)
        plist_src = os.path.join(SCRIPT_DIR, "launchd", "com.workbuddy.dailycheckin.plist")
        plist_dest = os.path.join(launch_dir, "com.workbuddy.dailycheckin.plist")
        if os.path.exists(plist_src):
            with open(plist_src, "r", encoding="utf-8") as f:
                content = f.read().replace("{{HOME}}", HOME)
            with open(plist_dest, "w", encoding="utf-8") as f:
                f.write(content)
            subprocess.run(["launchctl", "unload", plist_dest], stderr=subprocess.DEVNULL, stdout=subprocess.DEVNULL)
            subprocess.run(["launchctl", "load", plist_dest], stderr=subprocess.DEVNULL, stdout=subprocess.DEVNULL)
            print(f"{COLOR_GREEN}   ✔ macOS LaunchAgent 已激活 (每天 09:00 静默签到){COLOR_RESET}")
    elif sys.platform == "win32":
        task_name = "WorkBuddyDailyCheckin"
        python_exe = sys.executable
        pythonw_exe = python_exe.replace("python.exe", "pythonw.exe")
        runner = pythonw_exe if os.path.exists(pythonw_exe) else python_exe
        cmd = f'"{runner}" "{bin_path}" checkin'
        sch_cmd = ["schtasks", "/create", "/tn", task_name, "/tr", cmd, "/sc", "daily", "/st", "09:00", "/f"]
        res = subprocess.run(sch_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if res.returncode == 0:
            print(f"{COLOR_GREEN}   ✔ Windows 任务计划已激活: 每天 09:00 后台无窗打卡 ({task_name}){COLOR_RESET}")
        else:
            print(f"{COLOR_YELLOW}   [提示] 任务计划注册返回: {res.stderr.strip()}{COLOR_RESET}")
    else:  # Linux
        systemd_user_dir = os.path.join(HOME, ".config", "systemd", "user")
        has_systemd = shutil.which("systemctl") is not None
        configured = False
        if has_systemd:
            try:
                os.makedirs(systemd_user_dir, exist_ok=True)
                svc_src = os.path.join(SCRIPT_DIR, "systemd", "workbuddy-dailycheckin.service")
                tmr_src = os.path.join(SCRIPT_DIR, "systemd", "workbuddy-dailycheckin.timer")
                if os.path.exists(svc_src) and os.path.exists(tmr_src):
                    shutil.copy2(svc_src, os.path.join(systemd_user_dir, "workbuddy-dailycheckin.service"))
                    shutil.copy2(tmr_src, os.path.join(systemd_user_dir, "workbuddy-dailycheckin.timer"))
                    subprocess.run(["systemctl", "--user", "daemon-reload"], stderr=subprocess.DEVNULL)
                    subprocess.run(["systemctl", "--user", "enable", "--now", "workbuddy-dailycheckin.timer"], stderr=subprocess.DEVNULL)
                    print(f"{COLOR_GREEN}   ✔ Linux systemd user timer 已激活: 每天 09:00 自动打卡{COLOR_RESET}")
                    configured = True
            except Exception:
                configured = False

        if not configured and shutil.which("crontab"):
            try:
                cron_cmd = f"0 9 * * * {bin_path} checkin >> {LOGS_DIR}/checkin.log 2>&1"
                proc = subprocess.run(["crontab", "-l"], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
                existing = proc.stdout if proc.returncode == 0 else ""
                lines = [l for l in existing.splitlines() if "workbuddy checkin" not in l]
                lines.append(cron_cmd)
                new_cron = "\n".join(lines) + "\n"
                set_proc = subprocess.Popen(["crontab", "-"], stdin=subprocess.PIPE, text=True)
                set_proc.communicate(new_cron)
                print(f"{COLOR_GREEN}   ✔ crontab 定时任务已配置: 每天 09:00 自动打卡{COLOR_RESET}")
            except Exception as e:
                print(f"{COLOR_YELLOW}   [提示] 未配置系统定时器，您可随时运行 wb-checkin 手动打卡。{COLOR_RESET}")

def setup_sidecar():
    gemini_dir = os.path.join(HOME, ".gemini")
    if os.path.exists(gemini_dir):
        sidecar_dest = os.path.join(gemini_dir, "config", "sidecars", "workbuddy-checkin")
        sidecar_src = os.path.join(SCRIPT_DIR, "sidecar", "sidecar.json")
        if os.path.exists(sidecar_src):
            os.makedirs(sidecar_dest, exist_ok=True)
            shutil.copy2(sidecar_src, os.path.join(sidecar_dest, "sidecar.json"))
            print(f"{COLOR_GREEN}4. ✔ Antigravity 侧边栏任务伴随体已配置{COLOR_RESET}")

def main():
    print_banner()
    setup_dirs()
    dest_bin, bin_dir = install_cli()
    init_db()
    setup_scheduler(dest_bin, bin_dir)
    setup_sidecar()
    print(f"\n{COLOR_BOLD}{COLOR_GREEN}========================================================{COLOR_RESET}")
    print(f"{COLOR_BOLD}{COLOR_GREEN}🎉 安装部署全部完成！{COLOR_RESET}")
    print(f"{COLOR_CYAN}常用命令指南:{COLOR_RESET}")
    print(f"  • {COLOR_BOLD}wb-switch{COLOR_RESET}             : 呼出多账号无缝切换菜单 (永久免扫码)")
    print(f"  • {COLOR_BOLD}wb-checkin{COLOR_RESET}            : 一键批量执行所有已存账号每日签到")
    print(f"  • {COLOR_BOLD}workbuddy save <别名>{COLOR_RESET} : 将当前登录账号保存入库")
    print(f"  • {COLOR_BOLD}workbuddy status{COLOR_RESET}      : 查看所有账号状态及 Token 有效期")
    print(f"{COLOR_BOLD}{COLOR_GREEN}========================================================{COLOR_RESET}\n")

if __name__ == "__main__":
    main()
