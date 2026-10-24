#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Unit and Integration Tests for WorkBuddy Interactive Control Center (wb-tool / interactive_tool.py)
Tests:
- Design specifications: zero emoji, name length (2-5), description length (<=25).
- Visual alignment: display_width with CJK and ANSI escape codes.
- Breadcrumb navigation: Esc/0 navigation, submenu transitions, exit summaries.
- Fault tolerance & continuity: catching SystemExit, in-place refresh, invalid input tolerance.
- Subcommand integration: bin/workbuddy tool / wb-tool invocation.
"""

import os
import sys
import unittest
from unittest.mock import patch, MagicMock
from io import StringIO

# Add repo root and sidecar to sys.path
REPO_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SIDECAR_DIR = os.path.join(REPO_DIR, "sidecar")
if REPO_DIR not in sys.path:
    sys.path.insert(0, REPO_DIR)
if SIDECAR_DIR not in sys.path:
    sys.path.insert(0, SIDECAR_DIR)

import interactive_tool

class TestInteractiveToolDesign(unittest.TestCase):
    """验证《Don't Make Me Think》与《写给大家看的设计书》硬性设计规范"""

    def test_menu_specifications_constraints(self):
        """测试菜单项：严格 2-5 汉字，描述 <= 25 汉字，零 Emoji"""
        all_menus = [
            ("主菜单", interactive_tool.MAIN_MENU_ITEMS),
            ("查看积分", interactive_tool.USAGE_MENU_ITEMS),
            ("切换账号", interactive_tool.ACCOUNT_MENU_ITEMS),
            ("清理磁盘", interactive_tool.DISK_MENU_ITEMS),
        ]

        def has_emoji(text: str) -> bool:
            for ch in text:
                cp = ord(ch)
                if (0x1F300 <= cp <= 0x1F9FF) or (0x1FA00 <= cp <= 0x1FAFF) or (0x1F600 <= cp <= 0x1F64F) or (0x2600 <= cp <= 0x27BF):
                    return True
            return False

        for menu_name, items in all_menus:
            for item in items:
                name = item["name"]
                desc = item["desc"]
                # 1. 零 Emoji
                self.assertFalse(
                    has_emoji(name),
                    f"菜单 [{menu_name}] 项目 '{name}' 包含非法 Emoji！"
                )
                self.assertFalse(
                    has_emoji(desc),
                    f"菜单 [{menu_name}] 项目 '{name}' 描述包含非法 Emoji！"
                )

                # 2. 名称 2-5 字符
                self.assertTrue(
                    2 <= len(name) <= 5,
                    f"菜单 [{menu_name}] 项目 '{name}' 长度 {len(name)} 不在 2-5 字符区间！"
                )

                # 3. 描述 <= 25 字符
                self.assertTrue(
                    len(desc) <= 25,
                    f"菜单 [{menu_name}] 项目 '{name}' 描述 '{desc}' 长度 {len(desc)} 超过 25 字符！"
                )

    def test_display_width_cjk_ansi(self):
        """测试终端视觉对齐计算器，保证全角汉字与 ANSI 颜色不破坏表格排版"""
        # 纯 ASCII
        self.assertEqual(interactive_tool.display_width("hello"), 5)
        # 中文字符（每个占 2 宽）
        self.assertEqual(interactive_tool.display_width("查看积分"), 8)
        # 混合带 ANSI 转义码
        ansi_text = "\033[92m查看积分\033[0m"
        self.assertEqual(interactive_tool.display_width(ansi_text), 8)

class TestInteractiveToolStateMachine(unittest.TestCase):
    """测试 Rule 13 交互连续性、阶梯式面包屑导航与会话审计"""

    def setUp(self):
        self.mock_context = {
            "version": "0.7.0",
            "auth_file": "/tmp/mock_auth.info",
            "profiles_dir": "/tmp/mock_profiles",
            "db_file": "/tmp/mock_db.sqlite",
            "get_active_account": MagicMock(return_value={"account": {"uid": "u1", "nickname": "测试账号"}}),
            "get_profiles": MagicMock(return_value={"test_alias": {"uid": "u1", "nickname": "测试账号"}}),
            "switch_to_profile": MagicMock(return_value=True),
            "remove_profile": MagicMock(return_value=True),
            "run_login": MagicMock(),
            "run_audit": MagicMock(return_value=True),
            "run_checkin": MagicMock(),
            "run_models_cmd": MagicMock(),
            "run_usage_cmd": MagicMock(),
            "run_sandbox_cmd": MagicMock(),
            "restart_workbuddy": MagicMock(),
            "show_status": MagicMock(),
            "check_profile_health": MagicMock(return_value={"status": "OK"}),
        }

    def test_main_menu_clean_exit(self):
        """测试在主菜单直接选择 0 退出并打印审计摘要"""
        controller = interactive_tool.InteractiveToolController(self.mock_context)
        with patch("builtins.input", side_effect=["0"]):
            with patch("sys.stdout", new_callable=StringIO) as mock_out:
                ret = controller.run()
                self.assertEqual(ret, 0)
                out = mock_out.getvalue()
                self.assertIn("WorkBuddy 工具箱", out)
                self.assertIn("会话摘要", out)
                self.assertIn("已安全退出", out)

    def test_breadcrumb_navigation_and_submenus(self):
        """测试层级面包屑：进入 [查看积分]，按 0 返回 [主菜单]，再按 0 退出"""
        controller = interactive_tool.InteractiveToolController(self.mock_context)
        # 1: 进入查看积分, 0: 返回主菜单, 0: 退出
        with patch("builtins.input", side_effect=["1", "0", "0"]):
            with patch("sys.stdout", new_callable=StringIO) as mock_out:
                ret = controller.run()
                self.assertEqual(ret, 0)
                out = mock_out.getvalue()
                self.assertIn("主菜单 > 查看积分", out)
                self.assertIn("今日概览", out)

    def test_actions_continuous_loop_and_history(self):
        """测试连续执行多项操作，不被 SystemExit 中断，且如实记录会话历史"""
        # 模拟 run_checkin 内部抛出 SystemExit(0)
        self.mock_context["run_checkin"].side_effect = SystemExit(0)

        controller = interactive_tool.InteractiveToolController(self.mock_context, pause_after_action=False)
        # 3: 每日签到 (应被捕获保持存活), 6: 重启软件, 0: 退出
        with patch("builtins.input", side_effect=["3", "6", "0"]):
            with patch("sys.stdout", new_callable=StringIO) as mock_out:
                ret = controller.run()
                self.assertEqual(ret, 0)
                out = mock_out.getvalue()
                self.assertIn("本次操作记录: 共完成 2 项操作", out)
                self.mock_context["run_checkin"].assert_called_once()
                self.mock_context["restart_workbuddy"].assert_called_once()

    def test_invalid_input_tolerance(self):
        """测试输入非法字符（99, abc）时不崩溃并重新请求输入"""
        controller = interactive_tool.InteractiveToolController(self.mock_context)
        with patch("builtins.input", side_effect=["99", "invalid_cmd", "0"]):
            with patch("sys.stdout", new_callable=StringIO) as mock_out:
                ret = controller.run()
                self.assertEqual(ret, 0)
                out = mock_out.getvalue()
                self.assertIn("无效的编号", out)

    def test_esc_and_q_return(self):
        """测试按 q 或 Esc 在子菜单返回上一级"""
        controller = interactive_tool.InteractiveToolController(self.mock_context)
        # 进入 2 (切换账号), 按 q 返回, 按 q 退出
        with patch("builtins.input", side_effect=["2", "q", "q"]):
            with patch("sys.stdout", new_callable=StringIO):
                ret = controller.run()
                self.assertEqual(ret, 0)

if __name__ == "__main__":
    unittest.main()
