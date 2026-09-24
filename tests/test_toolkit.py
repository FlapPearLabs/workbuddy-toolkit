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

if __name__ == "__main__":
    unittest.main()
