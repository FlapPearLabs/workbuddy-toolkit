#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Automated Cross-Platform Test Suite for WorkBuddy Toolkit
Runs on macOS, Linux, and Windows in GitHub Actions CI.
"""

import os
import sys
import json
import shutil
import sqlite3
import tempfile
import unittest
import subprocess
from unittest.mock import patch, MagicMock

if sys.platform == "win32":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

import importlib.util
import importlib.machinery

REPO_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
bin_path = os.path.join(REPO_DIR, "bin", "workbuddy")
loader = importlib.machinery.SourceFileLoader("workbuddy", bin_path)
spec = importlib.util.spec_from_loader("workbuddy", loader)
workbuddy = importlib.util.module_from_spec(spec)
loader.exec_module(workbuddy)

class TestWorkBuddyCore(unittest.TestCase):
    def setUp(self):
        # 创建沙箱隔离目录，避免干扰本地真实配置
        self.test_dir = tempfile.mkdtemp()
        self.orig_auth_file = workbuddy.AUTH_FILE
        self.orig_profiles_dir = workbuddy.PROFILES_DIR
        self.orig_db_file = workbuddy.DB_FILE

        workbuddy.AUTH_FILE = os.path.join(self.test_dir, "auth", "workbuddy-desktop.info")
        workbuddy.PROFILES_DIR = os.path.join(self.test_dir, "auth_profiles")
        workbuddy.DB_FILE = os.path.join(self.test_dir, "workbuddy.db")

        os.makedirs(os.path.dirname(workbuddy.AUTH_FILE), exist_ok=True)
        os.makedirs(workbuddy.PROFILES_DIR, exist_ok=True)

        # 创建沙箱 SQLite 数据库
        self.con = sqlite3.connect(workbuddy.DB_FILE)
        self.con.execute("""
        CREATE TABLE sessions (
            id TEXT PRIMARY KEY,
            cwd TEXT NOT NULL,
            user_id TEXT NOT NULL,
            title TEXT
        );
        """)
        self.con.execute("""
        CREATE TABLE automations (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            owner_user_id TEXT,
            deleted_at INTEGER
        );
        """)
        self.con.commit()

    def tearDown(self):
        self.con.close()
        workbuddy.AUTH_FILE = self.orig_auth_file
        workbuddy.PROFILES_DIR = self.orig_profiles_dir
        workbuddy.DB_FILE = self.orig_db_file
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_01_paths_and_colors(self):
        """测试各平台路径解析逻辑与 ANSI 颜色配置"""
        auth_file = workbuddy.get_auth_file()
        self.assertTrue(isinstance(auth_file, str))
        self.assertTrue(len(auth_file) > 0)
        self.assertTrue(workbuddy.get_db_file().endswith("workbuddy.db"))
        self.assertTrue(workbuddy.get_profiles_dir().endswith("auth_profiles"))

    def test_02_sqlite_trigger_shared_workspace(self):
        """测试 SQLite 触发器对 user_id 过滤的穿透与防篡改效果"""
        # 1. 插入带有独立 user_id 的旧会话
        self.con.execute("INSERT INTO sessions VALUES ('s1', '/path/a', 'user_old_1', 'Session 1');")
        self.con.commit()

        # 2. 注入触发器
        ok = workbuddy.init_shared_workspace()
        self.assertTrue(ok)

        # 3. 验证旧会话已统一为 ''
        cur = self.con.cursor()
        cur.execute("SELECT user_id FROM sessions WHERE id = 's1';")
        self.assertEqual(cur.fetchone()[0], '')

        # 4. 插入新会话（带特定 user_id），验证触发器强制置空
        cur.execute("INSERT INTO sessions VALUES ('s2', '/path/b', 'user_new_2', 'Session 2');")
        self.con.commit()
        cur.execute("SELECT user_id FROM sessions WHERE id = 's2';")
        self.assertEqual(cur.fetchone()[0], '', "触发器必须拦截 INSERT 并自动将 user_id 置空")

        # 5. 试图将 user_id 修改为特定账号，验证 UPDATE 触发器防篡改
        cur.execute("UPDATE sessions SET user_id = 'user_hijack' WHERE id = 's2';")
        self.con.commit()
        cur.execute("SELECT user_id FROM sessions WHERE id = 's2';")
        self.assertEqual(cur.fetchone()[0], '', "触发器必须拦截 UPDATE 并强制恢复 user_id 为空")

        # 6. 测试回滚触发器
        rollback_ok = workbuddy.rollback_shared_workspace(restore_uid='user_restored')
        self.assertTrue(rollback_ok)
        cur.execute("SELECT user_id FROM sessions WHERE id = 's1';")
        self.assertEqual(cur.fetchone()[0], 'user_restored')

    def test_03_profile_management_and_switch(self):
        """测试 Profile 保存、读取、免扫码切换及 Token 同步机制"""
        fake_account_1 = {
            "account": {"uid": "mock-uid-111", "nickname": "AccountOne", "uin": "10001"},
            "auth": {"accessToken": "tok_111", "expiresAt": 1800000000000, "refreshExpiresAt": 1900000000000}
        }
        fake_account_2 = {
            "account": {"uid": "mock-uid-222", "nickname": "AccountTwo", "uin": "10002"},
            "auth": {"accessToken": "tok_222", "expiresAt": 1800000000000, "refreshExpiresAt": 1900000000000}
        }

        # 1. 模拟当前处于 Account 1
        with open(workbuddy.AUTH_FILE, "w", encoding="utf-8") as f:
            json.dump(fake_account_1, f)

        # 2. 保存 Account 1
        workbuddy.save_current("acc1")
        profiles = workbuddy.get_profiles()
        self.assertIn("acc1", profiles)
        self.assertEqual(profiles["acc1"]["uid"], "mock-uid-111")

        # 3. 写入 Account 2 Profile
        acc2_path = os.path.join(workbuddy.PROFILES_DIR, "acc2.info")
        with open(acc2_path, "w", encoding="utf-8") as f:
            json.dump(fake_account_2, f)

        # 4. 执行免扫码切号 (不实际重启客户端)
        switched = workbuddy.switch_to_profile("acc2", auto_restart=False)
        self.assertTrue(switched)

        # 验证当前 AUTH_FILE 已变为 Account 2
        active = workbuddy.get_active_account()
        self.assertEqual(active["account"]["uid"], "mock-uid-222")

    def test_04_cli_command_execution(self):
        """测试 CLI 命令行入口能否通过子进程正常执行并返回预期状态"""
        cmd_bin = os.path.join(REPO_DIR, "bin", "workbuddy")
        res = subprocess.run([sys.executable, cmd_bin, "help"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        self.assertEqual(res.returncode, 0)
        self.assertIn("workbuddy switch", res.stdout)
        self.assertIn("永久免扫码", res.stdout)

    def test_05_checkin_protocol_mock(self):
        """测试签到协议两段式探测与领取（通过 Mock HTTP 端点）"""
        fake_account = {
            "account": {"uid": "mock-uid-999", "nickname": "CheckinUser", "uin": "99999"},
            "auth": {"accessToken": "mock_token_999", "expiresAt": 1800000000000, "refreshExpiresAt": 1900000000000}
        }
        with open(os.path.join(workbuddy.PROFILES_DIR, "testuser.info"), "w", encoding="utf-8") as f:
            json.dump(fake_account, f)

        # 模拟响应数据
        status_resp = MagicMock()
        status_resp.read.return_value = json.dumps({
            "code": 0,
            "msg": "ok",
            "data": {"today_checked_in": False, "streak_days": 5, "total_credits": 500}
        }).encode("utf-8")
        status_resp.__enter__.return_value = status_resp

        claim_resp = MagicMock()
        claim_resp.read.return_value = json.dumps({
            "code": 0,
            "msg": "ok",
            "data": {"credit": 100, "streak_days": 6}
        }).encode("utf-8")
        claim_resp.__enter__.return_value = claim_resp

        with patch("urllib.request.urlopen", side_effect=[status_resp, claim_resp]) as mock_urlopen:
            workbuddy.run_checkin("testuser")
            self.assertEqual(mock_urlopen.call_count, 2)
            # 验证请求头包含 Bearer token 和 X-User-Id
            req1 = mock_urlopen.call_args_list[0][0][0]
            self.assertEqual(req1.headers.get("Authorization"), "Bearer mock_token_999")
            self.assertEqual(req1.headers.get("X-user-id"), "mock-uid-999")

if __name__ == "__main__":
    unittest.main()
