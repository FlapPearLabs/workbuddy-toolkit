"""tests/test_remove_sync_guard.py — 确认期间活跃账号切号的防护。

对抗审查 P0：`remove_profile` 在用户确认后会把"当前活跃凭据"写回待删备份。
如果确认期间客户端切了号（另一终端 switch / 客户端登录页切号），旧实现会把
B 的凭据写进 A 的备份，再连同 A 的原始字节一起移入回收站——A 的凭据永久
丢失，回收站里留下一份"名为 A 实为 B"的文件。

这里用进程内钩子确定性复现：get_active_account 第一次返回 A（判定活跃）、
第二次返回 B（确认后归档），断言回收站里仍是 A 的原始字节。
"""
import importlib.machinery
import importlib.util
import io
import json
import os
import shutil
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

REPO_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BIN_PATH = os.environ.get("WB_BIN") or os.path.join(REPO_DIR, "bin", "workbuddy")
_loader = importlib.machinery.SourceFileLoader("workbuddy_syncguard", BIN_PATH)
_spec = importlib.util.spec_from_loader("workbuddy_syncguard", _loader)
workbuddy = importlib.util.module_from_spec(_spec)
_loader.exec_module(workbuddy)

PROFILE = {"account": {"uid": "uid-a", "nickname": "A"}, "auth": {"accessToken": "TOKEN_OLD_A"}}
ACTIVE_A = {"account": {"uid": "uid-a", "nickname": "A"}, "auth": {"accessToken": "TOKEN_ACTIVE_A"}}
ACTIVE_B = {"account": {"uid": "uid-b", "nickname": "B"}, "auth": {"accessToken": "TOKEN_ACTIVE_B"}}


class TestRemoveSyncGuard(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="wb_syncguard_")
        self._orig = (workbuddy.AUTH_FILE, workbuddy.PROFILES_DIR)
        workbuddy.AUTH_FILE = os.path.join(self.dir, "auth", "workbuddy-desktop.info")
        workbuddy.PROFILES_DIR = os.path.join(self.dir, "auth_profiles")
        os.makedirs(os.path.dirname(workbuddy.AUTH_FILE), exist_ok=True)
        os.makedirs(workbuddy.PROFILES_DIR, exist_ok=True)
        with open(os.path.join(workbuddy.PROFILES_DIR, "alpha.info"), "w", encoding="utf-8") as f:
            json.dump(PROFILE, f, ensure_ascii=False)

    def tearDown(self):
        workbuddy.AUTH_FILE, workbuddy.PROFILES_DIR = self._orig
        shutil.rmtree(self.dir, ignore_errors=True)

    def _run_remove(self, active_side_effect):
        with patch.object(workbuddy, "get_active_account", side_effect=active_side_effect), \
                patch("builtins.input", return_value="y"), \
                redirect_stdout(io.StringIO()) as buf:
            ok = workbuddy.remove_profile("alpha")
        return ok, buf.getvalue()

    def _trash_data(self):
        trash = os.path.join(workbuddy.PROFILES_DIR, ".trash")
        names = [n for n in os.listdir(trash) if n.endswith(".info")]
        self.assertEqual(len(names), 1, names)
        with open(os.path.join(trash, names[0]), "r", encoding="utf-8") as f:
            return json.load(f)

    def test_active_switch_during_confirm_does_not_overwrite_backup(self):
        """确认期间切号：回收站必须保存 A 的原始字节，不能写成 B"""
        ok, out = self._run_remove([ACTIVE_A, ACTIVE_B])
        self.assertTrue(ok)
        self.assertIn("活跃账号在确认期间已切换", out)
        data = self._trash_data()
        self.assertEqual(data["account"]["uid"], "uid-a")
        self.assertEqual(data["auth"]["accessToken"], "TOKEN_OLD_A")

    def test_same_uid_still_syncs_latest_token(self):
        """未切号时仍要归档最新 token——不能把修复做成"干脆不同步" """
        ok, _out = self._run_remove([ACTIVE_A, ACTIVE_A])
        self.assertTrue(ok)
        data = self._trash_data()
        self.assertEqual(data["account"]["uid"], "uid-a")
        self.assertEqual(data["auth"]["accessToken"], "TOKEN_ACTIVE_A")


if __name__ == "__main__":
    unittest.main()
