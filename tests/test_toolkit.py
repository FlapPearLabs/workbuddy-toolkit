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
import base64
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
        self.orig_audit_cache_file = getattr(workbuddy, "AUDIT_CACHE_FILE", None)

        workbuddy.AUTH_FILE = os.path.join(self.test_dir, "auth", "workbuddy-desktop.info")
        workbuddy.PROFILES_DIR = os.path.join(self.test_dir, "auth_profiles")
        workbuddy.DB_FILE = os.path.join(self.test_dir, "workbuddy.db")
        workbuddy.AUDIT_CACHE_FILE = os.path.join(self.test_dir, "cache", "audit_cache.json")

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
        if self.orig_audit_cache_file:
            workbuddy.AUDIT_CACHE_FILE = self.orig_audit_cache_file
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
        self.assertIn("workbuddy doctor", res.stdout)
        self.assertIn("免重新扫码", res.stdout)

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

        chat_resp = MagicMock()
        chat_resp.__iter__.return_value = [
            b'data: {"choices": [{"delta": {"content": "\xe4\xbd\xa0\xe5\xa5\xbd"}}]}\n\n',
            b'data: [DONE]\n\n'
        ]
        chat_resp.__enter__.return_value = chat_resp

        with patch("urllib.request.urlopen", side_effect=[status_resp, claim_resp, chat_resp]) as mock_urlopen:
            workbuddy.run_checkin("testuser")
            self.assertEqual(mock_urlopen.call_count, 3)
            # 验证请求头包含 Bearer token 和 X-User-Id
            req1 = mock_urlopen.call_args_list[0][0][0]
            self.assertEqual(req1.headers.get("Authorization"), "Bearer mock_token_999")
            self.assertEqual(req1.headers.get("X-user-id"), "mock-uid-999")
            # 验证第 3 个请求为 chat completions 且使用了流式
            req3 = mock_urlopen.call_args_list[2][0][0]
            self.assertIn("/v2/chat/completions", req3.full_url)
            self.assertEqual(req3.headers.get("Accept"), "text/event-stream")

    def test_06_direct_chat_completion_mock(self):
        """测试 CLI 直接调用模型对话与 SSE 流式解析"""
        chat_resp = MagicMock()
        chat_resp.__iter__.return_value = [
            b'data: {"choices": [{"delta": {"content": "\xe6\xb5\x8b\xe8\xaf\x95"}}]}\n\n',
            b'data: {"choices": [{"delta": {"content": "\xe6\x88\x90\xe5\x8a\x9f"}}]}\n\n',
            b'data: [DONE]\n\n'
        ]
        chat_resp.__enter__.return_value = chat_resp

        with patch("urllib.request.urlopen", return_value=chat_resp) as mock_urlopen:
            res = workbuddy.send_chat_message("token_123", "uid_123", prompt="你好")
            self.assertTrue(res.get("success"))
            self.assertEqual(res.get("reply"), "测试成功")
            self.assertEqual(res.get("model"), workbuddy.PREFERRED_CHAT_MODELS[0])

    def test_07_chat_model_fallback_mock(self):
        """测试首选模型失败时自动向下 fallback 至下一个低倍率/免费模型"""
        import urllib.error
        err_fp = MagicMock()
        err_fp.read.return_value = b'{"code":11102,"msg":"model error"}'
        http_err = urllib.error.HTTPError("url", 400, "Bad Request", {}, err_fp)

        fallback_resp = MagicMock()
        fallback_resp.__iter__.return_value = [
            b'data: {"choices": [{"delta": {"content": "fallback_ok"}}]}\n\n',
            b'data: [DONE]\n\n'
        ]
        fallback_resp.__enter__.return_value = fallback_resp

        with patch("urllib.request.urlopen", side_effect=[http_err, fallback_resp]) as mock_urlopen:
            res = workbuddy.send_chat_message("token_123", "uid_123", prompt="你好")
            self.assertTrue(res.get("success"))
            self.assertEqual(res.get("reply"), "fallback_ok")
            self.assertEqual(res.get("model"), workbuddy.PREFERRED_CHAT_MODELS[1])
            self.assertEqual(mock_urlopen.call_count, 2)

    def test_08_parse_and_run_chat_flags(self):
        """测试 parse_and_run_chat 准确解析 -p, -m, --all 以及位置参数"""
        with patch.object(workbuddy, "run_chat") as mock_run_chat:
            # 1. 验证 -p flag
            workbuddy.parse_and_run_chat(["-p", "测试提示词"])
            mock_run_chat.assert_called_with(target_name=None, prompt="测试提示词", model=None, send_all=False)

            # 2. 验证 -m 与 -p 组合
            workbuddy.parse_and_run_chat(["-m", "hy3", "-p", "你好世界"])
            mock_run_chat.assert_called_with(target_name=None, prompt="你好世界", model="hy3", send_all=False)

            # 3. 验证 --all
            workbuddy.parse_and_run_chat(["--all", "-p", "全员打卡"])
            mock_run_chat.assert_called_with(target_name=None, prompt="全员打卡", model=None, send_all=True)

            # 4. 验证直接纯文本传参
            workbuddy.parse_and_run_chat(["直接说你好"])
            mock_run_chat.assert_called_with(target_name=None, prompt="直接说你好", model=None, send_all=False)

    @staticmethod
    def _create_mock_envelope(suite=1, key_id="0123456789abcdef", nonce_len=12, tag_len=16, ciphertext=b"sample_cipher_bytes"):
        raw_nonce = b"N" * nonce_len
        raw_tag = b"T" * tag_len
        inner = {
            "suite": suite,
            "keyId": key_id,
            "nonce": base64.b64encode(raw_nonce).decode("ascii"),
            "authTag": base64.b64encode(raw_tag).decode("ascii"),
            "ciphertext": base64.b64encode(ciphertext).decode("ascii")
        }
        outer = base64.b64encode(json.dumps(inner).encode("utf-8")).decode("ascii")
        return {"$wbEncrypted": 1, "envelope": outer}

    def test_t01_legacy_plaintext_resolution(self):
        """T1: legacy plaintext accessToken -> resolves directly without invoking resolver subprocess"""
        plain_token = "mock_legacy_plain_token_12345"
        with patch.object(workbuddy, "run_native_resolver") as mock_resolver:
            res = workbuddy.resolve_credential_field(plain_token)
            self.assertEqual(res, plain_token)
            mock_resolver.assert_not_called()

    def test_t02_encrypted_credential_detection(self):
        """T2: encrypted credential detection -> correctly identifies format"""
        env = self._create_mock_envelope()
        self.assertTrue(workbuddy.is_encrypted_credential(env))
        self.assertEqual(workbuddy.check_token_format(env), "sym-v1")
        self.assertEqual(workbuddy.check_token_format("normal_string_token"), "plaintext")
        self.assertEqual(workbuddy.check_token_format(None), "missing")

    def test_t03_malformed_envelope_fail_closed(self):
        """T3: malformed $wbEncrypted -> fail closed"""
        # 1. 非法 suite
        bad_suite = self._create_mock_envelope(suite=99)
        self.assertEqual(workbuddy.check_token_format(bad_suite), "unsupported")
        with self.assertRaises(workbuddy.CredentialError):
            workbuddy.resolve_credential_field(bad_suite)

        # 2. 损坏 base64
        corrupted = {"$wbEncrypted": 1, "envelope": "!!!not_base64!!!"}
        self.assertEqual(workbuddy.check_token_format(corrupted), "malformed")
        with self.assertRaises(workbuddy.CredentialError):
            workbuddy.resolve_credential_field(corrupted)

        # 3. 缺少必要字段
        missing_fields = {"$wbEncrypted": 1, "envelope": base64.b64encode(b'{"suite": 1}').decode("ascii")}
        self.assertEqual(workbuddy.check_token_format(missing_fields), "malformed")
        with self.assertRaises(workbuddy.CredentialError):
            workbuddy.resolve_credential_field(missing_fields)

    def test_t04_encrypted_credential_runtime_unavailable(self):
        """T4: encrypted credential + runtime unavailable -> fail closed with clear error, no API request"""
        env = self._create_mock_envelope()
        with patch.object(workbuddy, "find_workbuddy_runtime", side_effect=workbuddy.CredentialError("RUNTIME_NOT_FOUND")):
            with patch("urllib.request.urlopen") as mock_urlopen:
                with self.assertRaises(workbuddy.CredentialError):
                    workbuddy.resolve_credential_field(env)
                mock_urlopen.assert_not_called()

    def test_t05_dict_access_token_never_sent_in_header(self):
        """T5: accessToken is dict -> never enters Authorization header"""
        env = self._create_mock_envelope()
        with patch("urllib.request.urlopen") as mock_urlopen:
            res = workbuddy.send_chat_message(env, "uid_mock")
            self.assertFalse(res.get("success"))
            self.assertIn("AUTH_CREDENTIAL_UNRESOLVED", res.get("error", ""))
            mock_urlopen.assert_not_called()

    def test_t06_encrypted_nickname_no_crash(self):
        """T6: encrypted nickname -> no .lower() crash, falls back safely"""
        env_nick = self._create_mock_envelope()
        account_with_enc_nick = {
            "account": {"uid": "uid_enc_12345", "nickname": env_nick, "uin": "987654321"},
            "auth": {"accessToken": "valid_token_xyz"}
        }
        prof_file = os.path.join(workbuddy.PROFILES_DIR, "enc_nick_acc.info")
        with open(prof_file, "w", encoding="utf-8") as f:
            json.dump(account_with_enc_nick, f)

        profiles = workbuddy.get_profiles()
        self.assertIn("enc_nick_acc", profiles)
        self.assertIsInstance(profiles["enc_nick_acc"]["nickname"], str)
        self.assertTrue(profiles["enc_nick_acc"]["nickname"].lower().isalnum())

        with patch.object(workbuddy, "restart_workbuddy"):
            ok = workbuddy.switch_to_profile("enc_nick_acc", auto_restart=False)
            self.assertTrue(ok)

    def test_t07_profile_save_preserves_encrypted_envelope(self):
        """T7: profile save -> keeps encrypted envelope unchanged (opaque copy)"""
        env_token = self._create_mock_envelope()
        active_payload = {
            "account": {"uid": "uid_save_1", "nickname": "SaveEnc"},
            "auth": {"accessToken": env_token, "expiresAt": 1900000000000}
        }
        with open(workbuddy.AUTH_FILE, "w", encoding="utf-8") as f:
            json.dump(active_payload, f)

        workbuddy.save_current("saved_enc_prof")
        target_path = os.path.join(workbuddy.PROFILES_DIR, "saved_enc_prof.info")
        self.assertTrue(os.path.exists(target_path))
        with open(target_path, "r", encoding="utf-8") as f:
            saved_data = json.load(f)

        self.assertEqual(saved_data["auth"]["accessToken"], env_token)

    def test_t08_profile_switch_preserves_encrypted_envelope(self):
        """T8: profile switch -> keeps encrypted envelope unchanged in AUTH_FILE"""
        env_token = self._create_mock_envelope()
        prof_payload = {
            "account": {"uid": "uid_switch_1", "nickname": "SwitchEnc"},
            "auth": {"accessToken": env_token, "expiresAt": 1900000000000}
        }
        prof_path = os.path.join(workbuddy.PROFILES_DIR, "switch_enc.info")
        with open(prof_path, "w", encoding="utf-8") as f:
            json.dump(prof_payload, f)

        with patch.object(workbuddy, "restart_workbuddy"):
            ok = workbuddy.switch_to_profile("switch_enc", auto_restart=False)
            self.assertTrue(ok)

        with open(workbuddy.AUTH_FILE, "r", encoding="utf-8") as f:
            active_written = json.load(f)
        self.assertEqual(active_written["auth"]["accessToken"], env_token)

    def test_t09_sync_active_token_to_profiles_preserves_envelope(self):
        """T9: sync_active_token_to_profiles -> keeps encrypted document unchanged in profile file"""
        env_token = self._create_mock_envelope()
        active_payload = {
            "account": {"uid": "uid_sync_1", "nickname": "SyncEnc"},
            "auth": {"accessToken": env_token, "expiresAt": 1900000000000}
        }
        with open(workbuddy.AUTH_FILE, "w", encoding="utf-8") as f:
            json.dump(active_payload, f)

        prof_path = os.path.join(workbuddy.PROFILES_DIR, "sync_enc.info")
        with open(prof_path, "w", encoding="utf-8") as f:
            json.dump({"account": {"uid": "uid_sync_1"}, "auth": {}}, f)

        workbuddy.sync_active_token_to_profiles()
        with open(prof_path, "r", encoding="utf-8") as f:
            synced = json.load(f)
        self.assertEqual(synced["auth"]["accessToken"], env_token)

    def test_t10_plaintext_legacy_parity(self):
        """T10: plaintext legacy profile -> does not regress in save, switch, and sync"""
        plain_payload = {
            "account": {"uid": "uid_legacy_1", "nickname": "LegacyPlain"},
            "auth": {"accessToken": "legacy_plain_token_string", "expiresAt": 1900000000000}
        }
        with open(workbuddy.AUTH_FILE, "w", encoding="utf-8") as f:
            json.dump(plain_payload, f)

        workbuddy.save_current("legacy_test")
        profiles = workbuddy.get_profiles()
        self.assertIn("legacy_test", profiles)
        self.assertEqual(profiles["legacy_test"]["nickname"], "LegacyPlain")

        with patch.object(workbuddy, "restart_workbuddy"):
            ok = workbuddy.switch_to_profile("legacy_test", auto_restart=False)
            self.assertTrue(ok)

    def test_t11_doctor_plaintext_format(self):
        """T11: doctor plaintext format -> reports correctly and returns COMPATIBLE (True)"""
        plain_payload = {
            "account": {"uid": "uid_doc_plain", "nickname": "DocPlain"},
            "auth": {"accessToken": "plain_test_token_abc"}
        }
        with open(workbuddy.AUTH_FILE, "w", encoding="utf-8") as f:
            json.dump(plain_payload, f)

        with patch.object(workbuddy, "find_workbuddy_runtime", return_value="/mock/WorkBuddy"):
            with patch.object(workbuddy, "run_native_resolver", return_value={"ok": True, "electron": "37.10.3"}):
                res = workbuddy.run_doctor()
                self.assertTrue(res)

    def test_t12_doctor_encrypted_resolver_available(self):
        """T12: doctor encrypted + resolver available -> reports correctly and returns COMPATIBLE (True)"""
        env_token = self._create_mock_envelope()
        enc_payload = {
            "account": {"uid": "uid_doc_enc", "nickname": "DocEnc"},
            "auth": {"accessToken": env_token}
        }
        with open(workbuddy.AUTH_FILE, "w", encoding="utf-8") as f:
            json.dump(enc_payload, f)

        with patch.object(workbuddy, "find_workbuddy_runtime", return_value="/mock/WorkBuddy"):
            with patch.object(workbuddy, "run_native_resolver", return_value={"ok": True, "electron": "37.10.3"}):
                res = workbuddy.run_doctor()
                self.assertTrue(res)

    def test_t13_doctor_encrypted_resolver_unavailable(self):
        """T13: doctor encrypted + resolver unavailable -> reports BLOCKED / INCOMPATIBLE (False)"""
        env_token = self._create_mock_envelope()
        enc_payload = {
            "account": {"uid": "uid_doc_enc_fail", "nickname": "DocEncFail"},
            "auth": {"accessToken": env_token}
        }
        with open(workbuddy.AUTH_FILE, "w", encoding="utf-8") as f:
            json.dump(enc_payload, f)

        with patch.object(workbuddy, "find_workbuddy_runtime", side_effect=workbuddy.CredentialError("RUNTIME_NOT_FOUND")):
            res = workbuddy.run_doctor()
            self.assertFalse(res)

    def test_t14_secret_leakage_regression(self):
        """T14: secret leakage regression -> stdout/stderr do not contain test token in doctor/error logs"""
        secret_token = "secret_canary_token_do_not_leak"
        env_token = self._create_mock_envelope()

        import io
        fake_stdout = io.StringIO()
        with patch.object(workbuddy, "find_workbuddy_runtime", return_value="/mock/WorkBuddy"):
            with patch.object(workbuddy, "run_native_resolver", return_value={"ok": True, "accessToken": secret_token}):
                with patch("sys.stdout", fake_stdout):
                    resolved = workbuddy.resolve_credential_field(env_token)
                    self.assertEqual(resolved, secret_token)
                    workbuddy.run_doctor()

        output_text = fake_stdout.getvalue()
        self.assertNotIn(secret_token, output_text, "敏感明文 Token 绝对不能泄漏到控制台输出或日志中")

    def test_t15_api_layer_bearer_string_guarantee(self):
        """T15: API layer -> only sends Bearer header if accessToken is successfully resolved to str"""
        env_token = self._create_mock_envelope()
        prof_payload = {
            "account": {"uid": "uid_t15", "nickname": "T15Account"},
            "auth": {"accessToken": env_token}
        }
        with open(os.path.join(workbuddy.PROFILES_DIR, "t15.info"), "w", encoding="utf-8") as f:
            json.dump(prof_payload, f)

        # 1. 模拟解密失败场景：确保完全不发起网络请求
        with patch.object(workbuddy, "resolve_credential_field", side_effect=workbuddy.CredentialError("DECRYPT_FAILED")):
            with patch("urllib.request.urlopen") as mock_urlopen:
                workbuddy.run_checkin(target_name="t15", with_chat=False)
                mock_urlopen.assert_not_called()

        # 2. 模拟解密成功场景：验证 Authorization header 使用解析后的明文字符串
        resolved_str = "resolved_plain_token_string"
        dummy_resp = MagicMock()
        dummy_resp.read.return_value = b'{"code": 0, "data": {"today_checked_in": true, "streak_days": 5, "total_credits": 500}}'
        dummy_resp.__enter__.return_value = dummy_resp

        with patch.object(workbuddy, "resolve_credential_field", return_value=resolved_str):
            with patch("urllib.request.urlopen", return_value=dummy_resp) as mock_urlopen:
                workbuddy.run_checkin(target_name="t15", with_chat=False)
                self.assertEqual(mock_urlopen.call_count, 1)
                req_obj = mock_urlopen.call_args[0][0]
                auth_header = req_obj.get_header("Authorization")
                self.assertEqual(auth_header, f"Bearer {resolved_str}")

    def test_t16_encrypted_nickname_unicode_and_control_chars(self):
        """T16: encrypted nickname -> resolves Unicode/spaces, rejects NUL/controls, falls back safely"""
        env_nick = self._create_mock_envelope()
        account_data = {
            "nickname": env_nick,
            "uin": "123456",
            "uid": "wb_user_test_long_id"
        }

        # 1. 验证解密为中文 "测试账号" 正常通过，get_display_nickname 必须返回 "测试账号"
        with patch.object(workbuddy, "find_workbuddy_runtime", return_value="/mock/WorkBuddy"):
            with patch.object(workbuddy, "run_native_resolver", return_value={"ok": True, "version": 1, "value": "测试账号"}):
                nick = workbuddy.get_display_nickname(account_data)
                self.assertEqual(nick, "测试账号")
                resolved = workbuddy.resolve_credential_field(env_nick, field_name="nickname")
                self.assertEqual(resolved, "测试账号")

        # 2. 验证包含空格与合规 Unicode (Emoji/标点) 正常合法通过
        with patch.object(workbuddy, "find_workbuddy_runtime", return_value="/mock/WorkBuddy"):
            with patch.object(workbuddy, "run_native_resolver", return_value={"ok": True, "version": 1, "value": "开发 组长 🚀"}):
                nick = workbuddy.get_display_nickname(account_data)
                self.assertEqual(nick, "开发 组长 🚀")
                resolved = workbuddy.resolve_credential_field(env_nick, field_name="nickname")
                self.assertEqual(resolved, "开发 组长 🚀")

        # 3. 验证包含 NUL (\x00) 或控制字符时 fail closed，get_display_nickname 安全 fallback 至 uin
        with patch.object(workbuddy, "find_workbuddy_runtime", return_value="/mock/WorkBuddy"):
            for bad_nick in ("bad\x00nick", "bad\x1fnick", "bad\x7fnick", "   ", ""):
                with patch.object(workbuddy, "run_native_resolver", return_value={"ok": True, "version": 1, "value": bad_nick}):
                    with self.assertRaises(workbuddy.CredentialError):
                        workbuddy.resolve_credential_field(env_nick, field_name="nickname")
                    nick = workbuddy.get_display_nickname(account_data)
                    self.assertEqual(nick, "123456", f"遇到非法昵称 {repr(bad_nick)} 应安全回退到 uin")

    def test_t17_access_token_validator_strictness_not_relaxed(self):
        """T17: accessToken validator strictness -> Chinese/spaces/controls strictly rejected for accessToken"""
        env_token = self._create_mock_envelope()

        # 1. 明文 accessToken 传入非 Token 字符集时必须抛出 INVALID_FORMAT
        for invalid_plain in ("测试账号", "token with spaces", "token\x00nul", "token\nnewline"):
            with self.assertRaises(workbuddy.CredentialError):
                workbuddy.resolve_credential_field(invalid_plain, field_name="accessToken")

        # 2. 加密信封解密后若返回中文或带空格字符串，accessToken 校验必须 fail closed
        with patch.object(workbuddy, "find_workbuddy_runtime", return_value="/mock/WorkBuddy"):
            with patch.object(workbuddy, "run_native_resolver", return_value={"ok": True, "version": 1, "value": "测试账号"}):
                with self.assertRaises(workbuddy.CredentialError):
                    workbuddy.resolve_credential_field(env_token, field_name="accessToken")

            with patch.object(workbuddy, "run_native_resolver", return_value={"ok": True, "version": 1, "value": "token with space"}):
                with self.assertRaises(workbuddy.CredentialError):
                    workbuddy.resolve_credential_field(env_token, field_name="accessToken")

            # 3. 唯有符合严格 Token 正则的 ASCII 字符串才允许通过
            valid_token = "mock_valid_token_ascii_string_12345"
            with patch.object(workbuddy, "run_native_resolver", return_value={"ok": True, "version": 1, "value": valid_token}):
                resolved = workbuddy.resolve_credential_field(env_token, field_name="accessToken")
                self.assertEqual(resolved, valid_token)

    def test_t18_generate_qr_terminal(self):
        """T18: pure python terminal QR code generation produces correct half-block characters"""
        url = "https://copilot.tencent.com/v2/plugin/auth/state?state=mock_test_123"
        qr_str = workbuddy.generate_qr_terminal(url)
        self.assertIsInstance(qr_str, str)
        self.assertGreater(len(qr_str), 50)
        has_block_chars = any(c in qr_str for c in ("▀", "▄", "█", " "))
        self.assertTrue(has_block_chars)
        lines = qr_str.strip().split("\n")
        self.assertGreaterEqual(len(lines), 10)
        self.assertLessEqual(len(lines), 40)

    def test_t19_check_profile_health_unexpired_zero_network(self):
        """T19: check_profile_health -> unexpired token (> 10min) returns HEALTHY with 0 network calls"""
        prof_info = {
            "name": "healthy_acc",
            "uid": "uid_healthy_1",
            "nickname": "HealthyAcc",
            "expiresAt": 1900000000000,
            "data": {
                "account": {"uid": "uid_healthy_1", "nickname": "HealthyAcc"},
                "auth": {"accessToken": "valid_token_string", "expiresAt": 1900000000000}
            }
        }
        with patch("urllib.request.urlopen") as mock_url:
            mock_url.side_effect = AssertionError("Should never call network when expiresAt > 10m")
            res = workbuddy.check_profile_health(prof_info, force=False)
            self.assertEqual(res["status"], "HEALTHY")
            self.assertIn("剩余大于10分钟", res["detail"])
            mock_url.assert_not_called()

        res2 = workbuddy.check_profile_health(prof_info, force=False)
        self.assertEqual(res2["status"], "HEALTHY")
        self.assertTrue(res2.get("cached"))

    def test_t20_check_profile_health_expired_auto_refresh(self):
        """T20: check_profile_health -> expired token with valid refresh token triggers silent refresh and updates file"""
        import time
        prof_path = os.path.join(workbuddy.PROFILES_DIR, "refresh_acc.info")
        prof_payload = {
            "account": {"uid": "uid_refresh_1", "nickname": "RefreshAcc"},
            "auth": {
                "accessToken": "old_expired_token",
                "refreshToken": "valid_refresh_token_string",
                "expiresAt": 1000,
                "refreshExpiresAt": 1900000000000
            }
        }
        with open(prof_path, "w", encoding="utf-8") as f:
            json.dump(prof_payload, f)

        prof_info = {
            "name": "refresh_acc",
            "path": prof_path,
            "uid": "uid_refresh_1",
            "nickname": "RefreshAcc",
            "expiresAt": 1000,
            "data": prof_payload
        }

        mock_resp_data = {
            "code": 0,
            "data": {
                "accessToken": "new_refreshed_access_token_123",
                "refreshToken": "new_refresh_token_456",
                "expiresIn": 7200,
                "refreshExpiresIn": 2592000
            }
        }

        mock_cm = MagicMock()
        mock_cm.__enter__.return_value.read.return_value = json.dumps(mock_resp_data).encode("utf-8")

        with patch("urllib.request.urlopen", return_value=mock_cm):
            res = workbuddy.check_profile_health(prof_info, force=True)
            self.assertEqual(res["status"], "REFRESHED")

        with open(prof_path, "r", encoding="utf-8") as f:
            updated_data = json.load(f)
        self.assertIn("accessToken", updated_data["auth"])
        self.assertGreater(updated_data["auth"]["expiresAt"], int(time.time() * 1000))

    def test_t21_check_profile_health_expired_refresh_failed(self):
        """T21: check_profile_health -> expired token and expired refresh token returns EXPIRED without crash"""
        prof_info = {
            "name": "dead_acc",
            "uid": "uid_dead_1",
            "nickname": "DeadAcc",
            "expiresAt": 1000,
            "data": {
                "account": {"uid": "uid_dead_1", "nickname": "DeadAcc"},
                "auth": {
                    "accessToken": "old_token",
                    "refreshToken": "old_refresh",
                    "expiresAt": 1000,
                    "refreshExpiresAt": 1000
                }
            }
        }
        res = workbuddy.check_profile_health(prof_info, force=True)
        self.assertEqual(res["status"], "EXPIRED")

    def test_t22_run_audit_detection(self):
        """T22: run_audit detects healthy and expired profiles accurately"""
        healthy_path = os.path.join(workbuddy.PROFILES_DIR, "aud_healthy.info")
        with open(healthy_path, "w", encoding="utf-8") as f:
            json.dump({
                "account": {"uid": "uid_aud_1", "nickname": "AudHealthy"},
                "auth": {"accessToken": "valid_token", "expiresAt": 1900000000000}
            }, f)

        ok = workbuddy.run_audit(force=False)
        self.assertTrue(ok)

        dead_path = os.path.join(workbuddy.PROFILES_DIR, "aud_dead.info")
        with open(dead_path, "w", encoding="utf-8") as f:
            json.dump({
                "account": {"uid": "uid_aud_2", "nickname": "AudDead"},
                "auth": {"accessToken": "dead_token", "expiresAt": 1000, "refreshExpiresAt": 1000}
            }, f)

        ok2 = workbuddy.run_audit(force=False)
        self.assertFalse(ok2)

    def test_t23_switch_to_profile_expired_protection(self):
        """T23: switch_to_profile guards against switching to expired profile"""
        dead_path = os.path.join(workbuddy.PROFILES_DIR, "dead_prof.info")
        with open(dead_path, "w", encoding="utf-8") as f:
            json.dump({
                "account": {"uid": "uid_dead_switch", "nickname": "DeadSwitch"},
                "auth": {"accessToken": "dead_token", "expiresAt": 1000, "refreshExpiresAt": 1000}
            }, f)

        # 1. 非交互式终端环境，自动阻止切号
        with patch("sys.stdin.isatty", return_value=False):
            switched = workbuddy.switch_to_profile("dead_prof", auto_restart=False, check_health=True)
            self.assertFalse(switched)

        # 2. 交互式终端环境下用户取消切号
        with patch("sys.stdin.isatty", return_value=True):
            with patch("builtins.input", side_effect=EOFError):
                switched = workbuddy.switch_to_profile("dead_prof", auto_restart=False, check_health=True)
                self.assertFalse(switched)

            with patch("builtins.input", return_value="n"):
                switched = workbuddy.switch_to_profile("dead_prof", auto_restart=False, check_health=True)
                self.assertFalse(switched)

            # 3. 交互式终端环境下用户明确输入 y 强制切号
            with patch("builtins.input", return_value="y"):
                with patch.object(workbuddy, "restart_workbuddy"):
                    switched = workbuddy.switch_to_profile("dead_prof", auto_restart=False, check_health=True)
                    self.assertTrue(switched)

    def test_t24_run_login_flow(self):
        """T24: run_login mocks state, polling, token resolution, and profile writing"""
        state_resp = json.dumps({
            "code": 0,
            "data": {
                "state": "mock_state_xyz",
                "authUrl": "https://auth.example.com/qr?state=mock_state_xyz"
            }
        }).encode("utf-8")

        poll_ing = json.dumps({"code": 11217, "msg": "login ing..."}).encode("utf-8")
        poll_ok = json.dumps({
            "code": 0,
            "data": {
                "accessToken": "mock_login_token_abc_123",
                "refreshToken": "mock_login_ref_token_xyz",
                "userId": "wb_user_login_test",
                "expiresIn": 7200,
                "refreshExpiresIn": 2592000
            }
        }).encode("utf-8")

        acc_resp = json.dumps({
            "code": 0,
            "data": {
                "uid": "wb_user_login_test",
                "nickname": "MockLoginUser",
                "uin": "100099"
            }
        }).encode("utf-8")

        call_count = [0]
        def mock_urlopen(req, timeout=None):
            url = req.full_url if hasattr(req, "full_url") else str(req)
            cm = MagicMock()
            if "state" in url and "token" not in url:
                cm.__enter__.return_value.read.return_value = state_resp
            elif "token" in url and "state=" in url:
                call_count[0] += 1
                if call_count[0] == 1:
                    cm.__enter__.return_value.read.return_value = poll_ing
                else:
                    cm.__enter__.return_value.read.return_value = poll_ok
            elif "account" in url:
                cm.__enter__.return_value.read.return_value = acc_resp
            else:
                cm.__enter__.return_value.read.return_value = b"{}"
            return cm

        with patch("urllib.request.urlopen", side_effect=mock_urlopen):
            with patch("time.sleep", return_value=None):
                with patch("webbrowser.open", return_value=True):
                    ok = workbuddy.run_login(alias="new_logged_acc", auto_switch=False)
                    self.assertTrue(ok)

        saved_file = os.path.join(workbuddy.PROFILES_DIR, "new_logged_acc.info")
        self.assertTrue(os.path.exists(saved_file))
        with open(saved_file, "r", encoding="utf-8") as f:
            saved_json = json.load(f)
        self.assertEqual(saved_json["account"]["uid"], "wb_user_login_test")
        self.assertIn("accounts", saved_json)
        self.assertEqual(saved_json["accounts"][0]["uid"], "wb_user_login_test")

    def test_t25_switch_to_profile_reloads_refreshed_credentials(self):
        """T25: switch_to_profile reloads newly refreshed credentials instead of writing stale in-memory data"""
        prof_path = os.path.join(workbuddy.PROFILES_DIR, "stale_switch.info")
        initial_data = {
            "account": {"uid": "uid_stale_switch", "nickname": "StaleSwitch"},
            "auth": {
                "accessToken": "expired_old_token",
                "refreshToken": "valid_refresh_token_xyz",
                "expiresAt": 1000,
                "refreshExpiresAt": 1900000000000
            }
        }
        with open(prof_path, "w", encoding="utf-8") as f:
            json.dump(initial_data, f)

        mock_refresh_resp = {
            "code": 0,
            "data": {
                "accessToken": "brand_new_refreshed_access_token_999",
                "refreshToken": "brand_new_refresh_token_999",
                "expiresIn": 7200,
                "refreshExpiresIn": 2592000
            }
        }
        mock_cm = MagicMock()
        mock_cm.__enter__.return_value.read.return_value = json.dumps(mock_refresh_resp).encode("utf-8")

        with patch("urllib.request.urlopen", return_value=mock_cm):
            with patch.object(workbuddy, "restart_workbuddy"):
                switched = workbuddy.switch_to_profile("stale_switch", auto_restart=False, check_health=True)
                self.assertTrue(switched)

        with open(workbuddy.AUTH_FILE, "r", encoding="utf-8") as f:
            active_auth = json.load(f)
        resolved_tok = workbuddy.resolve_credential_field(active_auth["auth"]["accessToken"], "accessToken")
        self.assertEqual(resolved_tok, "brand_new_refreshed_access_token_999")

    def test_t26_qr_format_bits_conformance(self):
        """T26: QR code generator uses correct Level L Mask 0 format bits (0b111011111000100)"""
        url = "https://www.workbuddy.cn/login?platform=workbuddy&state=test_state_123"
        qr_output = workbuddy.generate_qr_terminal(url)
        self.assertIsInstance(qr_output, str)
        self.assertGreater(len(qr_output), 50)

    def test_t27_show_status_active_profile_timestamps(self):
        """T27: show_status correctly detects unexpired active account timestamp"""
        with open(workbuddy.AUTH_FILE, "w", encoding="utf-8") as f:
            json.dump({
                "account": {"uid": "uid_status_test", "nickname": "StatusUser"},
                "auth": {
                    "accessToken": "status_test_token_valid",
                    "expiresAt": 1900000000000,
                    "refreshExpiresAt": 1900000000000
                }
            }, f)
        import io
        buf = io.StringIO()
        with patch("sys.stdout", buf):
            workbuddy.show_status()
        out = buf.getvalue()
        self.assertIn("当前活跃账号", out)
        self.assertIn("StatusUser", out)
        self.assertIn("正常", out)
        self.assertNotIn("未设置过期时间", out)

    def test_t28_login_command_flags(self):
        """T28: CLI handles --help and --no-switch properly"""
        import io
        buf = io.StringIO()
        with patch("sys.stdout", buf):
            with patch("sys.argv", ["workbuddy", "login", "--help"]):
                workbuddy.main()
        self.assertIn("用法: workbuddy login", buf.getvalue())

    def test_t29_resolve_profile_alias_conflict_same_uid_inplace_update(self):
        """T29: 同账号扫码/保存时，若别名存在且 UID 相同，直接执行在位平滑更新"""
        prof_path = os.path.join(workbuddy.PROFILES_DIR, "same_user.info")
        with open(prof_path, "w", encoding="utf-8") as f:
            json.dump({
                "account": {"uid": "user_uid_100", "nickname": "SameUser"},
                "auth": {"accessToken": "tok_old"}
            }, f)

        final_alias, is_inplace = workbuddy.resolve_profile_alias_conflict("same_user", "user_uid_100", force=False)
        self.assertEqual(final_alias, "same_user")
        self.assertTrue(is_inplace)

    def test_t30_resolve_profile_alias_conflict_diff_uid_auto_increment(self):
        """T30: 异账号别名冲突时，自动生成自增候选别名 (<alias>_1, <alias>_2) 避免卡死或无意覆盖"""
        prof1 = os.path.join(workbuddy.PROFILES_DIR, "collision.info")
        with open(prof1, "w", encoding="utf-8") as f:
            json.dump({"account": {"uid": "user_uid_aaa"}}, f)

        prof2 = os.path.join(workbuddy.PROFILES_DIR, "collision_1.info")
        with open(prof2, "w", encoding="utf-8") as f:
            json.dump({"account": {"uid": "user_uid_bbb"}}, f)

        # 非交互式环境下，自动递增为 collision_2
        with patch("sys.stdin.isatty", return_value=False):
            final_alias, is_inplace = workbuddy.resolve_profile_alias_conflict("collision", "user_uid_ccc", force=False)
            self.assertEqual(final_alias, "collision_2")
            self.assertFalse(is_inplace)

        # 验证原先的文件均完好无损
        with open(prof1, "r", encoding="utf-8") as f:
            self.assertEqual(json.load(f)["account"]["uid"], "user_uid_aaa")
        with open(prof2, "r", encoding="utf-8") as f:
            self.assertEqual(json.load(f)["account"]["uid"], "user_uid_bbb")

    def test_t31_resolve_profile_alias_conflict_diff_uid_force_overwrite(self):
        """T31: 异账号别名冲突但指定 --force 时，允许执行显式覆盖"""
        prof1 = os.path.join(workbuddy.PROFILES_DIR, "force_test.info")
        with open(prof1, "w", encoding="utf-8") as f:
            json.dump({"account": {"uid": "user_uid_old"}}, f)

        final_alias, is_inplace = workbuddy.resolve_profile_alias_conflict("force_test", "user_uid_new", force=True)
        self.assertEqual(final_alias, "force_test")
        self.assertTrue(is_inplace)

    def test_t32_save_current_conflict_resolution(self):
        """T32: save_current 支持异账号自动自愈重命名与 --force 强制覆盖"""
        with open(workbuddy.AUTH_FILE, "w", encoding="utf-8") as f:
            json.dump({
                "account": {"uid": "user_active_999", "nickname": "ActiveUser"},
                "auth": {"accessToken": "active_tok"}
            }, f)

        existing_path = os.path.join(workbuddy.PROFILES_DIR, "mysave.info")
        with open(existing_path, "w", encoding="utf-8") as f:
            json.dump({
                "account": {"uid": "user_existing_888", "nickname": "ExistingUser"},
                "auth": {"accessToken": "existing_tok"}
            }, f)

        with patch("sys.stdin.isatty", return_value=False):
            workbuddy.save_current("mysave", force=False)

        # 检查是否自动生成了 mysave_1.info 且不破坏 mysave.info
        cand_path = os.path.join(workbuddy.PROFILES_DIR, "mysave_1.info")
        self.assertTrue(os.path.exists(cand_path))
        with open(cand_path, "r", encoding="utf-8") as f:
            self.assertEqual(json.load(f)["account"]["uid"], "user_active_999")
        with open(existing_path, "r", encoding="utf-8") as f:
            self.assertEqual(json.load(f)["account"]["uid"], "user_existing_888")

        # 使用 force=True 时，覆盖 mysave.info
        workbuddy.save_current("mysave", force=True)
        with open(existing_path, "r", encoding="utf-8") as f:
            self.assertEqual(json.load(f)["account"]["uid"], "user_active_999")

    def test_t33_notify_desktop_cross_platform(self):
        """T33: notify_desktop 支持 macOS, Windows, Linux 双端/跨平台原生通知与安全容错"""
        # 1. macOS (osascript)
        with patch("sys.platform", "darwin"):
            with patch("subprocess.run") as mock_sub:
                ok = workbuddy.notify_desktop("测试标题", "测试内容")
                self.assertTrue(ok)
                mock_sub.assert_called_once()
                cmd = mock_sub.call_args[0][0]
                self.assertEqual(cmd[0], "osascript")
                self.assertIn("display notification", cmd[2])

        # 2. Windows (PowerShell Toast)
        with patch("sys.platform", "win32"):
            with patch("subprocess.run") as mock_sub:
                ok = workbuddy.notify_desktop("WinTitle", "WinMsg")
                self.assertTrue(ok)
                mock_sub.assert_called_once()
                cmd = mock_sub.call_args[0][0]
                self.assertEqual(cmd[0], "powershell")
                self.assertIn("ToastNotificationManager", cmd[-1])

        # 3. 容错测试：子进程异常时不崩溃主程序，优雅返回 False
        with patch("sys.platform", "darwin"):
            with patch("subprocess.run", side_effect=RuntimeError("Subprocess failed")):
                ok = workbuddy.notify_desktop("FailTitle", "FailMsg")
                self.assertFalse(ok)

    def test_t34_run_audit_triggers_desktop_notification_on_expired(self):
        """T34: run_audit 校验发现失效账号时，自动触发系统级桌面通知；健康时不打扰"""
        dead_path = os.path.join(workbuddy.PROFILES_DIR, "aud_expired.info")
        with open(dead_path, "w", encoding="utf-8") as f:
            json.dump({
                "account": {"uid": "uid_dead_audit", "nickname": "DeadAudit"},
                "auth": {"accessToken": "dead_tok", "expiresAt": 1000, "refreshExpiresAt": 1000}
            }, f)

        with patch.object(workbuddy, "notify_desktop") as mock_notify:
            ok = workbuddy.run_audit(force=True, notify_on_expired=True)
            self.assertFalse(ok)
            mock_notify.assert_called_once()
            args = mock_notify.call_args[0]
            self.assertIn("WorkBuddy", args[0])
            self.assertIn("DeadAudit", args[1])

        # 移除失效账号，仅保留健康账号
        os.remove(dead_path)
        healthy_path = os.path.join(workbuddy.PROFILES_DIR, "aud_ok.info")
        with open(healthy_path, "w", encoding="utf-8") as f:
            json.dump({
                "account": {"uid": "uid_ok_audit", "nickname": "OkAudit"},
                "auth": {"accessToken": "ok_tok", "expiresAt": 1900000000000}
            }, f)

        with patch.object(workbuddy, "notify_desktop") as mock_notify2:
            ok2 = workbuddy.run_audit(force=False, notify_on_expired=True)
            self.assertTrue(ok2)
            mock_notify2.assert_not_called()

    def test_t35_parse_audit_cli_flags_and_daemon(self):
        """T35: CLI audit 参数解析支持 --interval, --daemon, --force 及其变体"""
        f1, d1, i1 = workbuddy._parse_audit_cli_args(["--daemon", "12"])
        self.assertFalse(f1)
        self.assertTrue(d1)
        self.assertEqual(i1, 12.0)

        f2, d2, i2 = workbuddy._parse_audit_cli_args(["--interval=3.5", "--force"])
        self.assertTrue(f2)
        self.assertTrue(d2)
        self.assertEqual(i2, 3.5)

        f3, d3, i3 = workbuddy._parse_audit_cli_args(["--daemon"])
        self.assertFalse(f3)
        self.assertTrue(d3)
        self.assertEqual(i3, 6.0)

        f4, d4, i4 = workbuddy._parse_audit_cli_args([])
        self.assertFalse(f4)
        self.assertFalse(d4)
        self.assertEqual(i4, 6.0)

    def test_t36_run_audit_daemon_iteration_and_exit(self):
        """T36: run_audit_daemon 在休眠中响应 KeyboardInterrupt 优雅退出"""
        with patch.object(workbuddy, "run_audit") as mock_audit:
            with patch("time.sleep", side_effect=KeyboardInterrupt):
                # 守护进程应当捕获 KeyboardInterrupt 并正常返回，绝不向上抛出
                workbuddy.run_audit_daemon(interval_hours=0.1, force=False)
                mock_audit.assert_called_once()

    def test_t37_resolve_profile_alias_conflict_interactive_responses(self):
        """T37: 交互式终端下，用户输入 'y' 确认覆盖，输入 'n' 自动分配候选名"""
        prof_path = os.path.join(workbuddy.PROFILES_DIR, "inter_acc.info")
        with open(prof_path, "w", encoding="utf-8") as f:
            json.dump({"account": {"uid": "user_old_111"}}, f)

        # 1. 用户输入 y 覆盖
        with patch("sys.stdin.isatty", return_value=True):
            with patch("builtins.input", return_value="y"):
                alias, is_inplace = workbuddy.resolve_profile_alias_conflict("inter_acc", "user_new_222", force=False)
                self.assertEqual(alias, "inter_acc")
                self.assertTrue(is_inplace)

        # 2. 用户输入 n 取消覆盖，自动递增
        with patch("sys.stdin.isatty", return_value=True):
            with patch("builtins.input", return_value="n"):
                alias, is_inplace = workbuddy.resolve_profile_alias_conflict("inter_acc", "user_new_222", force=False)
                self.assertEqual(alias, "inter_acc_1")
                self.assertFalse(is_inplace)

    def test_t38_run_login_with_force_overwrite_diff_uid(self):
        """T38: run_login 携带 force=True 时，若别名已被其他 UID 占用，强制覆盖原有 Profile"""
        prof_path = os.path.join(workbuddy.PROFILES_DIR, "force_login_acc.info")
        with open(prof_path, "w", encoding="utf-8") as f:
            json.dump({
                "account": {"uid": "old_uid_before_login", "nickname": "OldUser"},
                "auth": {"accessToken": "old_token"}
            }, f)

        state_resp = json.dumps({"code": 0, "data": {"state": "st1", "authUrl": "https://auth.example.com/qr"}}).encode("utf-8")
        poll_ok = json.dumps({"code": 0, "data": {"accessToken": "new_tok", "userId": "new_uid_after_login"}}).encode("utf-8")
        acc_resp = json.dumps({"code": 0, "data": {"uid": "new_uid_after_login", "nickname": "NewUser"}}).encode("utf-8")

        def mock_urlopen(req, timeout=None):
            url = req.full_url if hasattr(req, "full_url") else str(req)
            cm = MagicMock()
            if "state" in url and "token" not in url:
                cm.__enter__.return_value.read.return_value = state_resp
            elif "token" in url and "state=" in url:
                cm.__enter__.return_value.read.return_value = poll_ok
            elif "account" in url:
                cm.__enter__.return_value.read.return_value = acc_resp
            return cm

        with patch("urllib.request.urlopen", side_effect=mock_urlopen):
            with patch("time.sleep", return_value=None):
                with patch("webbrowser.open", return_value=True):
                    ok = workbuddy.run_login(alias="force_login_acc", auto_switch=False, force=True)
                    self.assertTrue(ok)

        with open(prof_path, "r", encoding="utf-8") as f:
            saved = json.load(f)
        self.assertEqual(saved["account"]["uid"], "new_uid_after_login")

    def test_t39_run_login_without_force_diff_uid_auto_renames(self):
        """T39: run_login 不带 force 且环境非交互时，若别名已被其他 UID 占用，自愈重命名为 <alias>_1 保存"""
        prof_path = os.path.join(workbuddy.PROFILES_DIR, "auto_ren_acc.info")
        with open(prof_path, "w", encoding="utf-8") as f:
            json.dump({
                "account": {"uid": "preserved_old_uid", "nickname": "PreservedUser"},
                "auth": {"accessToken": "preserved_token"}
            }, f)

        state_resp = json.dumps({"code": 0, "data": {"state": "st2", "authUrl": "https://auth.example.com/qr"}}).encode("utf-8")
        poll_ok = json.dumps({"code": 0, "data": {"accessToken": "new_tok_2", "userId": "brand_new_uid"}}).encode("utf-8")
        acc_resp = json.dumps({"code": 0, "data": {"uid": "brand_new_uid", "nickname": "BrandNewUser"}}).encode("utf-8")

        def mock_urlopen(req, timeout=None):
            url = req.full_url if hasattr(req, "full_url") else str(req)
            cm = MagicMock()
            if "state" in url and "token" not in url:
                cm.__enter__.return_value.read.return_value = state_resp
            elif "token" in url and "state=" in url:
                cm.__enter__.return_value.read.return_value = poll_ok
            elif "account" in url:
                cm.__enter__.return_value.read.return_value = acc_resp
            return cm

        with patch("sys.stdin.isatty", return_value=False):
            with patch("urllib.request.urlopen", side_effect=mock_urlopen):
                with patch("time.sleep", return_value=None):
                    with patch("webbrowser.open", return_value=True):
                        ok = workbuddy.run_login(alias="auto_ren_acc", auto_switch=False, force=False)
                        self.assertTrue(ok)

        # 验证原文件未被覆盖
        with open(prof_path, "r", encoding="utf-8") as f:
            self.assertEqual(json.load(f)["account"]["uid"], "preserved_old_uid")

        # 验证新文件已成功落盘为 auto_ren_acc_1.info
        cand_path = os.path.join(workbuddy.PROFILES_DIR, "auto_ren_acc_1.info")
        self.assertTrue(os.path.exists(cand_path))
        with open(cand_path, "r", encoding="utf-8") as f:
            self.assertEqual(json.load(f)["account"]["uid"], "brand_new_uid")

    def test_t40_run_audit_daemon_handles_exception_gracefully(self):
        """T40: run_audit_daemon 单轮巡检抛出异常时自动容错，不导致守护进程崩溃退出"""
        call_count = [0]

        def mock_audit(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                raise RuntimeError("Transient network timeout in audit")
            return True

        curr_time = [1000.0]
        def fake_time():
            return curr_time[0]

        def mock_sleep(sec):
            curr_time[0] += (sec or 1.0)
            if call_count[0] >= 2:
                raise KeyboardInterrupt

        with patch.object(workbuddy, "run_audit", side_effect=mock_audit):
            with patch("time.time", side_effect=fake_time):
                with patch("time.sleep", side_effect=mock_sleep):
                    workbuddy.run_audit_daemon(interval_hours=0.001, force=False)
                    # 确认执行了至少 2 轮巡检（第一轮异常未打崩守护进程）
                    self.assertGreaterEqual(call_count[0], 2)

    def test_t41_notify_desktop_newline_and_windows_toast_handling(self):
        """T41: notify_desktop 在 macOS 下过滤换行符防语法错误，在 Windows 下包含 System.Drawing 与 AUMID 容错"""
        # 1. macOS 下换行符与双引号过滤
        with patch("sys.platform", "darwin"):
            with patch("subprocess.run") as mock_sub:
                ok = workbuddy.notify_desktop("标题\n第二行", "消息内容\r\n多行文字")
                self.assertTrue(ok)
                mock_sub.assert_called_once()
                cmd = mock_sub.call_args[0][0]
                self.assertEqual(cmd[0], "osascript")
                self.assertNotIn("\n", cmd[2])
                self.assertNotIn("\r", cmd[2])

        # 2. Windows 下 WinRT Toast 包含 PowerShell 容错 AUMID 与 System.Drawing
        with patch("sys.platform", "win32"):
            with patch("subprocess.run") as mock_sub:
                ok = workbuddy.notify_desktop("WinTitle", "WinMsg")
                self.assertTrue(ok)
                cmd = mock_sub.call_args[0][0]
                ps_script = cmd[-1]
                self.assertIn("System.Drawing", ps_script)
                self.assertIn("WindowsPowerShell", ps_script)

    def test_t42_github_workflow_yaml_secrets_not_in_if_condition(self):
        """T42: 静态断言 .github/workflows/workbuddy-monitor.yml 中严禁在 if: 中直接使用 secrets.*"""
        repo_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        wf_path = os.path.join(repo_dir, ".github", "workflows", "workbuddy-monitor.yml")
        self.assertTrue(os.path.exists(wf_path))
        with open(wf_path, "r", encoding="utf-8") as f:
            lines = f.readlines()

        for idx, line in enumerate(lines, 1):
            stripped = line.strip()
            if stripped.startswith("if:"):
                self.assertNotIn(
                    "secrets.",
                    stripped,
                    f"Line {idx} in {wf_path} contains 'secrets.' in if: condition! "
                    f"GitHub Actions rejects secrets in if expressions; map to env: instead."
                )

    def test_t43_resolve_profile_alias_conflict_with_userid_field(self):
        """T43: resolve_profile_alias_conflict 兼容已有 Profile 中仅存在 userId 字段的情况"""
        prof_path = os.path.join(workbuddy.PROFILES_DIR, "legacy_user.info")
        with open(prof_path, "w", encoding="utf-8") as f:
            json.dump({"account": {"userId": "legacy_uid_123"}}, f)

        # 相同 UID (由 userId 提供) -> 在位平滑更新
        alias, is_inplace = workbuddy.resolve_profile_alias_conflict("legacy_user", "legacy_uid_123", force=False)
        self.assertEqual(alias, "legacy_user")
        self.assertTrue(is_inplace)

        # 不同 UID -> 自增消解
        with patch("sys.stdin.isatty", return_value=False):
            alias_diff, is_inplace_diff = workbuddy.resolve_profile_alias_conflict("legacy_user", "other_uid_456", force=False)
            self.assertEqual(alias_diff, "legacy_user_1")
            self.assertFalse(is_inplace_diff)

    def test_t44_show_status_json_format_active_and_profiles(self):
        """T44: show_status(as_json=True) 输出完整的程序化 JSON 结构且字段完备"""
        active_payload = {
            "account": {"uid": "uid_json_act", "nickname": "JsonActive"},
            "auth": {
                "accessToken": "plain_act_token",
                "expiresAt": 1900000000000,
                "refreshExpiresAt": 1900000000000
            }
        }
        with open(workbuddy.AUTH_FILE, "w", encoding="utf-8") as f:
            json.dump(active_payload, f)

        prof_act = os.path.join(workbuddy.PROFILES_DIR, "act_profile.info")
        with open(prof_act, "w", encoding="utf-8") as f:
            json.dump(active_payload, f)

        prof_other = os.path.join(workbuddy.PROFILES_DIR, "other_profile.info")
        with open(prof_other, "w", encoding="utf-8") as f:
            json.dump({
                "account": {"uid": "uid_json_other", "nickname": "OtherUser"},
                "auth": {
                    "accessToken": "plain_other_token",
                    "expiresAt": 1900000000000,
                    "refreshExpiresAt": 1900000000000
                }
            }, f)

        import io
        buf = io.StringIO()
        with patch("sys.stdout", buf):
            workbuddy.show_status(as_json=True)

        raw = buf.getvalue().strip()
        data = json.loads(raw)

        self.assertEqual(data["platform"], sys.platform)
        self.assertEqual(data["total_profiles"], 2)

        # 检查 active_account 字段完备性
        act = data["active_account"]
        self.assertIsNotNone(act)
        self.assertEqual(act["uid"], "uid_json_act")
        self.assertEqual(act["nickname"], "JsonActive")
        self.assertEqual(act["profile_name"], "act_profile")
        self.assertEqual(act["storage_format"], "plaintext")
        self.assertEqual(act["expires_at"], 1900000000000)
        self.assertEqual(act["health"]["status"], "HEALTHY")

        # 检查 profiles 列表字段完备性
        profs = data["profiles"]
        self.assertEqual(len(profs), 2)
        names = [p["name"] for p in profs]
        self.assertIn("act_profile", names)
        self.assertIn("other_profile", names)

        act_p = next(p for p in profs if p["name"] == "act_profile")
        self.assertTrue(act_p["is_active"])
        self.assertEqual(act_p["uid"], "uid_json_act")
        self.assertEqual(act_p["storage_format"], "plaintext")

        other_p = next(p for p in profs if p["name"] == "other_profile")
        self.assertFalse(other_p["is_active"])
        self.assertEqual(other_p["uid"], "uid_json_other")
        self.assertEqual(other_p["storage_format"], "plaintext")

    def test_t45_cli_list_and_status_aliases_and_json_flag(self):
        """T45: CLI 命令 (list/status/wb-list/wb-status) 及 --json / --help 正确分发"""
        import io

        # 1. workbuddy list --json
        buf1 = io.StringIO()
        with patch("sys.stdout", buf1):
            with patch("sys.argv", ["workbuddy", "list", "--json"]):
                workbuddy.main()
        json_out1 = json.loads(buf1.getvalue().strip())
        self.assertIn("profiles", json_out1)

        # 2. wb-list --json
        buf2 = io.StringIO()
        with patch("sys.stdout", buf2):
            with patch("sys.argv", ["wb-list", "--json"]):
                workbuddy.main()
        json_out2 = json.loads(buf2.getvalue().strip())
        self.assertIn("active_account", json_out2)

        # 3. wb-status --help
        buf3 = io.StringIO()
        with patch("sys.stdout", buf3):
            with patch("sys.argv", ["wb-status", "--help"]):
                workbuddy.main()
        self.assertIn("用法:", buf3.getvalue())

        # 4. workbuddy list --help
        buf4 = io.StringIO()
        with patch("sys.stdout", buf4):
            with patch("sys.argv", ["workbuddy", "list", "--help"]):
                workbuddy.main()
        self.assertIn("用法:", buf4.getvalue())

    def test_t46_show_status_zero_token_leak(self):
        """T46: show_status 在文本与 JSON 模式下均严禁输出任何敏感 Token 明文或私密字段"""
        secret_canary = "super_secret_canary_token_strictly_prohibited_98765"
        active_payload = {
            "account": {"uid": "uid_canary", "nickname": "CanaryUser"},
            "auth": {
                "accessToken": secret_canary,
                "refreshToken": "refresh_canary_54321",
                "expiresAt": 1900000000000
            }
        }
        with open(workbuddy.AUTH_FILE, "w", encoding="utf-8") as f:
            json.dump(active_payload, f)

        prof_file = os.path.join(workbuddy.PROFILES_DIR, "canary.info")
        with open(prof_file, "w", encoding="utf-8") as f:
            json.dump(active_payload, f)

        import io
        # 1. 验证 JSON 模式零泄漏
        buf_json = io.StringIO()
        with patch("sys.stdout", buf_json):
            workbuddy.show_status(as_json=True)
        json_text = buf_json.getvalue()
        self.assertNotIn(secret_canary, json_text)
        self.assertNotIn("refresh_canary_54321", json_text)

        # 2. 验证文本模式零泄漏
        buf_text = io.StringIO()
        with patch("sys.stdout", buf_text):
            workbuddy.show_status(as_json=False)
        plain_text = buf_text.getvalue()
        self.assertNotIn(secret_canary, plain_text)
        self.assertNotIn("refresh_canary_54321", plain_text)

    def test_t47_show_status_and_health_edge_cases_and_null_timestamps(self):
        """T47: 校验 null 时间戳、null UID、损坏或空配置下 show_status 与 check_profile_health 的安全兜底"""
        import io

        # 1. 验证 check_profile_health 对 null 时间戳及非字典输入不崩溃
        self.assertEqual(workbuddy.check_profile_health(None)["status"], "EXPIRED")
        self.assertEqual(workbuddy.check_profile_health("not_a_dict")["status"], "EXPIRED")

        null_ts_prof = {
            "data": {
                "account": {"uid": "uid_null_ts", "nickname": "NullTsUser"},
                "auth": {"accessToken": "some_tok", "expiresAt": None, "refreshExpiresAt": None}
            }
        }
        res_null = workbuddy.check_profile_health(null_ts_prof)
        self.assertIn("status", res_null)

        # 2. 验证 format_timestamp 边界与异常入参
        self.assertEqual(workbuddy.format_timestamp(None), "未知")
        self.assertEqual(workbuddy.format_timestamp(0), "未知")
        self.assertEqual(workbuddy.format_timestamp(-1000), "未知")
        self.assertEqual(workbuddy.format_timestamp("invalid_non_numeric"), "未知")
        formatted = workbuddy.format_timestamp(1900000000000)
        self.assertRegex(formatted, r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$")
        formatted_str = workbuddy.format_timestamp("1900000000000")
        self.assertEqual(formatted, formatted_str)

        # 3. 构造包含 null 时间戳与 null UID 的异常活跃账号与 Profile
        bad_active = {
            "account": {"uid": None, "nickname": "NullUidActive"},
            "auth": {"accessToken": "act_tok", "expiresAt": None, "refreshExpiresAt": None}
        }
        with open(workbuddy.AUTH_FILE, "w", encoding="utf-8") as f:
            json.dump(bad_active, f)

        prof_bad = os.path.join(workbuddy.PROFILES_DIR, "bad_acc.info")
        with open(prof_bad, "w", encoding="utf-8") as f:
            json.dump({
                "account": {"uid": None, "nickname": "BadAcc"},
                "auth": {"accessToken": "bad_tok", "expiresAt": None, "refreshExpiresAt": None}
            }, f)

        # 验证 JSON 输出不崩溃且结构完整
        buf_json = io.StringIO()
        with patch("sys.stdout", buf_json):
            workbuddy.show_status(as_json=True)
        j_data = json.loads(buf_json.getvalue().strip())
        self.assertIn("active_account", j_data)
        self.assertEqual(j_data["total_profiles"], 1)
        self.assertEqual(j_data["profiles"][0]["expires_at_formatted"], "未知")

        # 验证文本输出不崩溃
        buf_text = io.StringIO()
        with patch("sys.stdout", buf_text):
            workbuddy.show_status(as_json=False)
        self.assertIn("=== WorkBuddy 账号状态", buf_text.getvalue())

        # 4. 验证完全空的 auth.json
        with open(workbuddy.AUTH_FILE, "w", encoding="utf-8") as f:
            json.dump({}, f)

        buf_empty = io.StringIO()
        with patch("sys.stdout", buf_empty):
            workbuddy.show_status(as_json=True)
        j_empty = json.loads(buf_empty.getvalue().strip())
        self.assertIsNone(j_empty["active_account"])

        # 5. 验证 CLI 命令 workbuddy --json 直接支持
        buf_cli = io.StringIO()
        with patch("sys.stdout", buf_cli):
            with patch("sys.argv", ["workbuddy", "--json"]):
                workbuddy.main()
        j_cli = json.loads(buf_cli.getvalue().strip())
        self.assertIn("platform", j_cli)

        # 6. 验证 CLI 命令 workbuddy-list --json 别名支持
        buf_wb_list = io.StringIO()
        with patch("sys.stdout", buf_wb_list):
            with patch("sys.argv", ["workbuddy-list", "--json"]):
                workbuddy.main()
        j_wb_list = json.loads(buf_wb_list.getvalue().strip())
        self.assertIn("platform", j_wb_list)

    def test_t48_cli_help_aliases_and_subcommand(self):
        """T48: CLI 命令 wb-help / workbuddy-help / workbuddy help 输出精简操作提示与功能清单"""
        import io
        bin_script = os.path.join(REPO_DIR, "bin", "workbuddy")

        # 1. 验证 sys.argv[0] == "wb-help"
        buf_wb_help = io.StringIO()
        with patch("sys.stdout", buf_wb_help):
            with patch("sys.argv", ["wb-help"]):
                workbuddy.main()
        out1 = buf_wb_help.getvalue()
        self.assertIn("WorkBuddy CLI", out1)
        self.assertIn("常用命令:", out1)
        self.assertIn("wb-help", out1)
        self.assertIn("workbuddy-help", out1)
        self.assertIn("README.md", out1)

        # 2. 验证 sys.argv[0] == "workbuddy-help"
        buf_wb_full_help = io.StringIO()
        with patch("sys.stdout", buf_wb_full_help):
            with patch("sys.argv", ["workbuddy-help"]):
                workbuddy.main()
        out2 = buf_wb_full_help.getvalue()
        self.assertIn("WorkBuddy CLI", out2)
        self.assertIn("wb-help", out2)

        # 3. 验证 Windows 风格垫片程序名 "wb-help.cmd"
        buf_cmd = io.StringIO()
        with patch("sys.stdout", buf_cmd):
            with patch("sys.argv", ["wb-help.cmd"]):
                workbuddy.main()
        out3 = buf_cmd.getvalue()
        self.assertIn("WorkBuddy CLI", out3)

        # 4. 验证 workbuddy help 子命令
        buf_sub = io.StringIO()
        with patch("sys.stdout", buf_sub):
            with patch("sys.argv", ["workbuddy", "help"]):
                workbuddy.main()
        out4 = buf_sub.getvalue()
        self.assertIn("WorkBuddy CLI", out4)

        # 5. 验证 workbuddy --help 与 -h 标志
        buf_flag = io.StringIO()
        with patch("sys.stdout", buf_flag):
            with patch("sys.argv", ["workbuddy", "--help"]):
                workbuddy.main()
        self.assertIn("WorkBuddy CLI", buf_flag.getvalue())

        # 6. 真实外部进程执行 Smoke Test
        res = subprocess.run([sys.executable, bin_script, "help"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        self.assertEqual(res.returncode, 0)
        self.assertIn("WorkBuddy CLI", res.stdout)
        self.assertIn("wb-help", res.stdout)

if __name__ == "__main__":
    unittest.main()



