#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
WorkBuddy 交互式控制中心 (wb-tool / workbuddy-tool)
遵循 Steve Krug《Don't Make Me Think》与 Robin Williams《写给大家看的设计书》(CRAP) 原则设计。
特点:
- 极致纯净: 零 Emoji、零晦涩技术黑话。
- 严谨规范: 功能名称 2-5 汉字，功能描述不超过 25 汉字。
- 面包屑状态机: 支持多级菜单 Esc/0 逐级返回，原地刷新与会话聚合审计报告。
- 高内聚低耦合: 复用现有底层模块，捕获 SystemExit 保证连续操作体验。
"""

import os
import sys
import unicodedata
from typing import Dict, Any, List, Optional, Tuple

# 只在交互式终端输出 ANSI 颜色；管道、cron/launchd 日志与 NO_COLOR 环境下输出纯文本
HAS_COLOR = bool(getattr(sys.stdout, "isatty", lambda: False)()) and "NO_COLOR" not in os.environ
COLOR_GREEN = "\033[92m" if HAS_COLOR else ""
COLOR_YELLOW = "\033[93m" if HAS_COLOR else ""
COLOR_CYAN = "\033[96m" if HAS_COLOR else ""
COLOR_RED = "\033[91m" if HAS_COLOR else ""
COLOR_BOLD = "\033[1m" if HAS_COLOR else ""
COLOR_DIM = "\033[2m" if HAS_COLOR else ""
COLOR_RESET = "\033[0m" if HAS_COLOR else ""

TOOL_VERSION = "0.7.0"

def display_width(text: str) -> int:
    """计算包含中文字符与 ANSI 控制码的终端视觉宽度"""
    w = 0
    in_escape = False
    for char in text:
        if char == "\033":
            in_escape = True
            continue
        if in_escape:
            if char == "m":
                in_escape = False
            continue
        if unicodedata.east_asian_width(char) in ("F", "W"):
            w += 2
        else:
            w += 1
    return w

def pad_to_width(text: str, target_width: int) -> str:
    current = display_width(text)
    if current < target_width:
        return text + " " * (target_width - current)
    return text

# 菜单配置项：严格执行 名称 2-5 字，描述 <= 25 字，零 Emoji
MAIN_MENU_ITEMS = [
    {
        "id": "1",
        "name": "查看积分",
        "desc": "查看今日与历史消耗，支持实时刷新和明细下钻",
        "action": "submenu_usage",
    },
    {
        "id": "2",
        "name": "切换账号",
        "desc": "免扫码一键切号，支持查看已存账号并录入新号",
        "action": "submenu_account",
    },
    {
        "id": "3",
        "name": "每日签到",
        "desc": "一键领取每日积分奖励，自动发送保活打卡对话",
        "action": "do_checkin",
    },
    {
        "id": "4",
        "name": "模型切换",
        "desc": "查看可用模型列表与费率，切换常用默认模型",
        "action": "do_models",
    },
    {
        "id": "5",
        "name": "清理磁盘",
        "desc": "清理后台残留临时缓存，释放被占用的电脑空间",
        "action": "submenu_disk",
    },
    {
        "id": "6",
        "name": "重启软件",
        "desc": "一键关闭并重新打开客户端，使新配置即时生效",
        "action": "do_restart",
    },
    {
        "id": "0",
        "name": "退出",
        "desc": "关闭工具箱，返回命令行终端",
        "action": "exit",
    },
]

USAGE_MENU_ITEMS = [
    {
        "id": "1",
        "name": "今日概览",
        "desc": "查看今天已消耗积分总量与实时计费明细",
        "action": "usage_today",
    },
    {
        "id": "2",
        "name": "会话明细",
        "desc": "按会话查看积分消耗分布与详细对话开销",
        "action": "usage_drilldown",
    },
    {
        "id": "3",
        "name": "实时盯盘",
        "desc": "启动实时动态刷新界面，监测每秒消耗流速",
        "action": "usage_watch",
    },
    {
        "id": "4",
        "name": "历史全量",
        "desc": "查看自使用以来的全部历史累计消耗与统计",
        "action": "usage_all",
    },
    {
        "id": "0",
        "name": "返回上级",
        "desc": "返回工具箱主菜单",
        "action": "back",
    },
]

ACCOUNT_MENU_ITEMS = [
    {
        "id": "1",
        "name": "立即切号",
        "desc": "选择已有账号免扫码即时切换，永久免密生效",
        "action": "account_switch",
    },
    {
        "id": "2",
        "name": "扫码新号",
        "desc": "扫描二维码录入并保存新的账号凭证",
        "action": "account_login",
    },
    {
        "id": "3",
        "name": "账号体检",
        "desc": "检查所有已存账号的有效期与凭证健康状态",
        "action": "account_audit",
    },
    {
        "id": "4",
        "name": "账号清单",
        "desc": "查看本地已保存的所有账号别名与配置路径",
        "action": "account_list",
    },
    {
        "id": "5",
        "name": "删除账号",
        "desc": "将账号移入本地回收站，客户端登录不受影响",
        "action": "account_remove",
    },
    {
        "id": "0",
        "name": "返回上级",
        "desc": "返回工具箱主菜单",
        "action": "back",
    },
]

DISK_MENU_ITEMS = [
    {
        "id": "1",
        "name": "推荐清理",
        "desc": "清理过期会话快照与临时日志，释放磁盘空间",
        "action": "disk_clean",
    },
    {
        "id": "2",
        "name": "深度清理",
        "desc": "深度回收孤儿后台进程并修复沙盒异常规则",
        "action": "disk_heal_clean",
    },
    {
        "id": "3",
        "name": "空间体检",
        "desc": "检查当前沙盒状态、规则总量与快照占用详情",
        "action": "disk_status",
    },
    {
        "id": "0",
        "name": "返回上级",
        "desc": "返回工具箱主菜单",
        "action": "back",
    },
]

class InteractiveToolController:
    def __init__(self, context: Dict[str, Any], pause_after_action: bool = True):
        self.context = context
        self.pause_after_action = pause_after_action
        self.action_history: List[str] = []
        self.nav_stack: List[Tuple[str, List[Dict[str, Any]]]] = [("主菜单", MAIN_MENU_ITEMS)]

    def get_status_info(self) -> Dict[str, Any]:
        """获取当前活跃账号、健康度、积分消耗及已存账号数"""
        get_active_account = self.context.get("get_active_account")
        get_profiles = self.context.get("get_profiles")
        check_profile_health = self.context.get("check_profile_health")

        active_data = get_active_account() if get_active_account else None
        active_acc = active_data.get("account", {}) if isinstance(active_data, dict) else {}
        active_uid = active_acc.get("uid", "")

        profiles = get_profiles() if get_profiles else {}
        profile_count = len(profiles)

        active_name = "未登录"
        active_status = "未就绪"
        active_alias = ""

        if active_uid and profiles:
            for name, p in profiles.items():
                if p.get("uid") == active_uid:
                    active_alias = name
                    nick = p.get("nickname") or active_acc.get("nickname") or name
                    active_name = f"{name} ({nick})"
                    if check_profile_health:
                        h = check_profile_health(p, force=False)
                        st = h.get("status")
                        if st == "OK":
                            active_status = "正常"
                        elif st == "REFRESHED":
                            active_status = "已续期"
                        elif st == "EXPIRED":
                            active_status = "已失效"
                        else:
                            active_status = "正常"
                    else:
                        active_status = "正常"
                    break
        elif active_uid:
            nick = active_acc.get("nickname") or "当前用户"
            active_name = f"{nick}"
            active_status = "正常"

        # 获取今日积分消耗
        credits_str = "0.0 积分"
        try:
            try:
                from . import credit_meter
            except (ImportError, ValueError):
                import credit_meter
            db_file = self.context.get("db_file")
            profiles_dir = self.context.get("profiles_dir")
            auth_file = self.context.get("auth_file")
            cm = credit_meter.CreditMeter(
                db_path=db_file,
                profiles_dir=profiles_dir,
                active_info_path=auth_file,
            )
            w = cm.parse_time_window(today=True)
            u = cm.query_usage(w)
            pts = u.get("total_credits", 0.0)
            burn = u.get("burn_rate_per_sec")
            if burn and burn > 0.001:
                credits_str = f"{pts:.1f} 积分 ({burn:.1f}/秒)"
            else:
                credits_str = f"{pts:.1f} 积分"
        except Exception:
            pass

        return {
            "active_name": active_name,
            "active_status": active_status,
            "active_alias": active_alias,
            "credits_str": credits_str,
            "profile_count": profile_count,
        }

    def render_header(self, info: Dict[str, Any]):
        """渲染紧凑、高对比的顶栏状态卡片 (CRAP Alignment & Contrast)"""
        tool_ver = self.context.get("version", TOOL_VERSION)
        title_segment = f" WorkBuddy 工具箱 (wb-tool v{tool_ver}) "
        total_width = 80
        bar_len = total_width - display_width(title_segment) - 4
        top_border = f"╭─{title_segment}{'─' * max(bar_len, 2)}╮"

        status_color = COLOR_GREEN if info["active_status"] in ("正常", "已续期") else (COLOR_RED if info["active_status"] == "已失效" else COLOR_YELLOW)
        act_str = f"当前账号: {info['active_name']} ({status_color}{info['active_status']}{COLOR_RESET})"
        use_str = f"今日消耗: {COLOR_CYAN}{info['credits_str']}{COLOR_RESET}"
        cnt_str = f"已存账号: {COLOR_BOLD}{info['profile_count']}{COLOR_RESET} 个"

        content_raw = f"  {act_str} │ {use_str} │ {cnt_str}"
        # 补齐右边距
        pad_spaces = total_width - display_width(content_raw) - 2
        content_line = f"│{content_raw}{' ' * max(pad_spaces, 1)}│"
        bottom_border = f"╰{'─' * (total_width - 2)}╯"

        print(f"\n{COLOR_CYAN}{top_border}{COLOR_RESET}")
        print(content_line)
        print(f"{COLOR_CYAN}{bottom_border}{COLOR_RESET}\n")

    def render_menu(self, menu_title: str, items: List[Dict[str, Any]]):
        """渲染符合 CRAP 原则的菜单结构：对比清晰、对齐工整、描述自明"""
        current_path = " > ".join([name for name, _ in self.nav_stack])
        print(f"{COLOR_BOLD}[ {current_path} ]{COLOR_RESET}")
        print(f"{COLOR_DIM}{'─' * 60}{COLOR_RESET}")

        for item in items:
            item_id = item["id"]
            name = item["name"]
            desc = item["desc"]
            # 强化序号与名称视觉重量，弱化描述色彩
            id_str = f"{COLOR_BOLD}[{item_id}]{COLOR_RESET}"
            name_str = f"{COLOR_BOLD}{name:<5}{COLOR_RESET}"
            print(f"  {id_str} {name_str} ── {COLOR_DIM}{desc}{COLOR_RESET}")

        print(f"{COLOR_DIM}{'─' * 60}{COLOR_RESET}")

    def prompt_action(self, items: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """获取用户输入，支持序号、返回上级(0/q/Esc)、容错拦截"""
        valid_ids = {item["id"]: item for item in items}
        try:
            choice = input(f"{COLOR_BOLD}请选择操作编号 [0-{len(items)-1}]: {COLOR_RESET}").strip()
        except (KeyboardInterrupt, EOFError):
            return {"action": "back"}

        if not choice:
            return None

        # 支持 q、exit、esc 控制键
        if choice.lower() in ("q", "quit", "exit"):
            return {"action": "back" if len(self.nav_stack) > 1 else "exit"}
        if choice in ("\x1b", "esc"):
            return {"action": "back"}

        if choice in valid_ids:
            return valid_ids[choice]

        print(f"{COLOR_RED}无效的编号 '{choice}'，请输入正确的操作数字。{COLOR_RESET}")
        return None

    def execute_action(self, action_key: str) -> bool:
        """
        分发执行操作。返回 True 表示继续循环，False 表示退出工具箱。
        核心铁律: 捕获 SystemExit 绝不因单个子命令退出而中断交互工作流。
        """
        if action_key == "exit":
            return False
        if action_key == "back":
            if len(self.nav_stack) > 1:
                self.nav_stack.pop()
            else:
                return False
            return True

        # 子菜单路由
        if action_key == "submenu_usage":
            self.nav_stack.append(("查看积分", USAGE_MENU_ITEMS))
            return True
        elif action_key == "submenu_account":
            self.nav_stack.append(("切换账号", ACCOUNT_MENU_ITEMS))
            return True
        elif action_key == "submenu_disk":
            self.nav_stack.append(("清理磁盘", DISK_MENU_ITEMS))
            return True

        # 执行动作前打印分隔
        print(f"\n{COLOR_CYAN}{'═' * 60}{COLOR_RESET}")

        try:
            if action_key == "usage_today":
                self.action_history.append("查看今日积分")
                run_usage = self.context.get("run_usage_cmd")
                if run_usage:
                    run_usage(["--today"])
            elif action_key == "usage_drilldown":
                self.action_history.append("查看会话明细")
                run_usage = self.context.get("run_usage_cmd")
                info = self.get_status_info()
                alias = info.get("active_alias")
                if run_usage:
                    if alias:
                        run_usage(["-a", alias])
                    else:
                        run_usage(["-v"])
            elif action_key == "usage_watch":
                self.action_history.append("实时盯盘监控")
                run_usage = self.context.get("run_usage_cmd")
                if run_usage:
                    run_usage(["--watch"])
            elif action_key == "usage_all":
                self.action_history.append("查看历史全量积分")
                run_usage = self.context.get("run_usage_cmd")
                if run_usage:
                    run_usage(["--all"])
            elif action_key == "account_switch":
                self.action_history.append("切换账号")
                self._handle_account_switch()
            elif action_key == "account_login":
                self.action_history.append("扫码录入新号")
                self._handle_account_login()
            elif action_key == "account_audit":
                self.action_history.append("账号体检")
                run_audit = self.context.get("run_audit")
                if run_audit:
                    run_audit(force=True, notify_on_expired=True)
            elif action_key == "account_list":
                self.action_history.append("查看账号清单")
                show_status = self.context.get("show_status")
                if show_status:
                    show_status(as_json=False)
            elif action_key == "account_remove":
                self.action_history.append("删除账号")
                self._handle_account_remove()
            elif action_key == "do_checkin":
                self.action_history.append("每日签到")
                run_checkin = self.context.get("run_checkin")
                if run_checkin:
                    run_checkin(with_chat=True)
            elif action_key == "do_models":
                self.action_history.append("模型切换")
                run_models = self.context.get("run_models_cmd")
                if run_models:
                    run_models([])
            elif action_key == "disk_clean":
                self.action_history.append("推荐清理磁盘")
                run_sandbox = self.context.get("run_sandbox_cmd")
                if run_sandbox:
                    run_sandbox(["clean"])
            elif action_key == "disk_heal_clean":
                self.action_history.append("深度清理与自愈")
                run_sandbox = self.context.get("run_sandbox_cmd")
                if run_sandbox:
                    run_sandbox(["heal"])
                    run_sandbox(["clean"])
            elif action_key == "disk_status":
                self.action_history.append("磁盘空间体检")
                run_sandbox = self.context.get("run_sandbox_cmd")
                if run_sandbox:
                    run_sandbox(["status"])
            elif action_key == "do_restart":
                self.action_history.append("重启软件客户端")
                restart_fn = self.context.get("restart_workbuddy")
                if restart_fn:
                    restart_fn()
            else:
                print(f"{COLOR_YELLOW}未实现的功能动作: {action_key}{COLOR_RESET}")
        except SystemExit:
            # 隔离子命令的退出代码，保持控制中心常驻
            pass
        except Exception as e:
            print(f"{COLOR_RED}执行出错: {e}{COLOR_RESET}")

        print(f"{COLOR_CYAN}{'═' * 60}{COLOR_RESET}")
        self._wait_for_user()
        return True

    def _wait_for_user(self):
        """非自动化环境下等待用户回车继续"""
        if self.pause_after_action and sys.stdin.isatty():
            try:
                input(f"{COLOR_DIM}按回车键返回菜单...{COLOR_RESET}")
            except (KeyboardInterrupt, EOFError):
                pass

    def _handle_account_switch(self):
        """交互式账号切换列表"""
        get_profiles = self.context.get("get_profiles")
        switch_to_profile = self.context.get("switch_to_profile")
        get_active_account = self.context.get("get_active_account")

        profiles = get_profiles() if get_profiles else {}
        if not profiles:
            print(f"{COLOR_RED}未在本地发现任何已保存的账号凭证。请先通过扫码录入新账号。{COLOR_RESET}")
            return

        active_data = get_active_account() if get_active_account else None
        active_uid = active_data.get("account", {}).get("uid") if active_data else None

        keys = list(profiles.keys())
        print(f"\n{COLOR_BOLD}请选择要切换的目标账号:{COLOR_RESET}")
        for idx, name in enumerate(keys, 1):
            p = profiles[name]
            is_cur = (p.get("uid") == active_uid)
            cur_mark = f" {COLOR_GREEN}(当前使用中){COLOR_RESET}" if is_cur else ""
            print(f"  [{idx}] {name:<12} (昵称: {p.get('nickname')}){cur_mark}")
        print("  [0] 返回上级")

        try:
            choice = input(f"{COLOR_BOLD}请输入账号序号 [1-{len(keys)}]: {COLOR_RESET}").strip()
            if choice in ("0", "q", "exit", ""):
                return
            idx = int(choice)
            if 1 <= idx <= len(keys):
                target_alias = keys[idx - 1]
                if switch_to_profile:
                    switch_to_profile(target_alias, auto_restart=True)
            else:
                print(f"{COLOR_RED}无效的序号。{COLOR_RESET}")
        except ValueError:
            print(f"{COLOR_RED}请输入正确的数字。{COLOR_RESET}")
        except (KeyboardInterrupt, EOFError):
            pass

    def _handle_account_remove(self):
        """交互式删除账号：移入本地回收站，可手工移回恢复"""
        get_profiles = self.context.get("get_profiles")
        remove_profile = self.context.get("remove_profile")
        get_active_account = self.context.get("get_active_account")

        profiles = get_profiles() if get_profiles else {}
        if not profiles:
            print(f"{COLOR_RED}本地没有已保存的账号凭证，无需删除。{COLOR_RESET}")
            return

        active_data = get_active_account() if get_active_account else None
        active_uid = active_data.get("account", {}).get("uid") if active_data else None

        keys = list(profiles.keys())
        print(f"\n{COLOR_BOLD}请选择要删除的账号 (将移入本地回收站，客户端当前登录不受影响):{COLOR_RESET}")
        for idx, name in enumerate(keys, 1):
            p = profiles[name]
            is_cur = (p.get("uid") == active_uid)
            cur_mark = f" {COLOR_YELLOW}(当前使用中){COLOR_RESET}" if is_cur else ""
            print(f"  [{idx}] {name:<12} (昵称: {p.get('nickname')}){cur_mark}")
        print("  [0] 返回上级")

        try:
            choice = input(f"{COLOR_BOLD}请输入账号序号 [1-{len(keys)}]: {COLOR_RESET}").strip()
            if choice in ("0", "q", "exit", ""):
                return
            idx = int(choice)
            if 1 <= idx <= len(keys):
                if remove_profile:
                    remove_profile(keys[idx - 1])
            else:
                print(f"{COLOR_RED}无效的序号: {choice}{COLOR_RESET}")
        except ValueError:
            print(f"{COLOR_RED}请输入正确的数字序号。{COLOR_RESET}")
        except (KeyboardInterrupt, EOFError):
            print("\n已取消。")

    def _handle_account_login(self):
        """扫码录入新账号"""
        run_login = self.context.get("run_login")
        if not run_login:
            print(f"{COLOR_RED}未挂载 login 引擎。{COLOR_RESET}")
            return
        try:
            alias = input(f"{COLOR_BOLD}请输入新账号别名 (直接回车使用自动命名): {COLOR_RESET}").strip()
            alias = alias if alias else None
            run_login(alias=alias, auto_switch=True, force=False)
        except (KeyboardInterrupt, EOFError):
            print("\n已取消录入。")

    def render_exit_summary(self):
        """退出时打印会话聚合审计报告 (Rule 13)"""
        info = self.get_status_info()
        act_count = len(self.action_history)
        total_width = 80
        title = " WorkBuddy 工具箱会话摘要 "
        bar_len = total_width - display_width(title) - 4
        top_border = f"╭─{title}{'─' * max(bar_len, 2)}╮"

        line1 = f"  本次操作记录: 共完成 {act_count} 项操作"
        line2 = f"  当前生效账号: {info['active_name']}"
        line3 = "  工具状态    : 已安全退出"

        print(f"\n{COLOR_CYAN}{top_border}{COLOR_RESET}")
        print(f"│{pad_to_width(line1, total_width - 2)}│")
        print(f"│{pad_to_width(line2, total_width - 2)}│")
        print(f"│{pad_to_width(line3, total_width - 2)}│")
        print(f"{COLOR_CYAN}╰{'─' * (total_width - 2)}╯{COLOR_RESET}\n")

    def run(self) -> int:
        """主运行循环"""
        while True:
            # 顶部卡片
            info = self.get_status_info()
            self.render_header(info)

            # 当前层级菜单
            current_name, current_items = self.nav_stack[-1]
            self.render_menu(current_name, current_items)

            # 等待输入
            selected = self.prompt_action(current_items)
            if selected is None:
                continue

            should_continue = self.execute_action(selected["action"])
            if not should_continue:
                break

        self.render_exit_summary()
        return 0

def run_interactive_tool(context: Dict[str, Any], args: Optional[List[str]] = None) -> int:
    controller = InteractiveToolController(context)
    return controller.run()
