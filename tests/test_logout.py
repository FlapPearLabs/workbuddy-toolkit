#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
WorkBuddy Toolkit 登出功能测试

覆盖：标记路径规则、预览零写入、写标记后删凭据的顺序、备份生成、
进程占用保护、重复登出、--deep 的清理边界。

全部在 tempfile 沙箱内执行，不读取也不写入真实凭据。
"""

import os
import sys
import json
import shutil
import tempfile
import threading
import unittest
from unittest.mock import patch

if sys.platform == "win32":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

import importlib.util
import importlib.machinery

REPO_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
bin_path = os.path.join(REPO_DIR, "bin", "workbuddy")
loader = importlib.machinery.SourceFileLoader("workbuddy_logout_under_test", bin_path)
spec = importlib.util.spec_from_loader("workbuddy_logout_under_test", loader)
workbuddy = importlib.util.module_from_spec(spec)
loader.exec_module(workbuddy)


class LogoutSandbox(unittest.TestCase):
    """沙箱基类：把登出涉及的路径全部重定向到临时目录。"""
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self._orig = {
            "AUTH_FILE": workbuddy.AUTH_FILE,
            "PROFILES_DIR": workbuddy.PROFILES_DIR,
            "LOGOUT_BACKUP_ROOT": workbuddy.LOGOUT_BACKUP_ROOT,
            "ACCOUNT_SNAPSHOT_FILE": workbuddy.ACCOUNT_SNAPSHOT_FILE,
            "SIDEBAR_SNAPSHOT_TEMPLATE": workbuddy.SIDEBAR_SNAPSHOT_TEMPLATE,
        }
        workbuddy.AUTH_FILE = os.path.join(self.test_dir, "auth", "workbuddy-desktop.info")
        # 联测 switch_to_profile 会读账号库，必须一起重定向，否则会碰真实账号
        workbuddy.PROFILES_DIR = os.path.join(self.test_dir, "auth_profiles")
        workbuddy.LOGOUT_BACKUP_ROOT = os.path.join(self.test_dir, "logout_backup")
        workbuddy.ACCOUNT_SNAPSHOT_FILE = os.path.join(
            self.test_dir, "storage", "skeleton", "account-snapshot.json")
        workbuddy.SIDEBAR_SNAPSHOT_TEMPLATE = os.path.join(
            self.test_dir, "{uid}", "sidebar-list-snapshot.json")
        os.makedirs(os.path.dirname(workbuddy.AUTH_FILE), exist_ok=True)

    def tearDown(self):
        for key, value in self._orig.items():
            setattr(workbuddy, key, value)
        shutil.rmtree(self.test_dir, ignore_errors=True)

    # ---------------- helpers

    def write_auth(self, payload=None):
        with open(workbuddy.AUTH_FILE, "w", encoding="utf-8") as f:
            json.dump(payload or {"auth": {"accessToken": "fake-token"}}, f)

    def make_uid_cache(self, uid="uid-1"):
        os.makedirs(os.path.dirname(workbuddy.ACCOUNT_SNAPSHOT_FILE), exist_ok=True)
        with open(workbuddy.ACCOUNT_SNAPSHOT_FILE, "w", encoding="utf-8") as f:
            json.dump({"primary": {"uid": uid, "nickname": "sandbox"}}, f)
        uid_dir = os.path.join(self.test_dir, uid)
        os.makedirs(uid_dir, exist_ok=True)
        sidebar = os.path.join(uid_dir, "sidebar-list-snapshot.json")
        startup = os.path.join(uid_dir, "startup-route.json")
        for path in (sidebar, startup):
            with open(path, "w", encoding="utf-8") as f:
                f.write("{}")
        return sidebar, startup


class TestLogout(LogoutSandbox):
    # ---------------- 用例

    def test_01_marker_path_appends_suffix(self):
        """标记路径必须严格是凭据路径追加 .logged-out，与主程序 getLogoutMarkerPath 对齐。"""
        self.assertEqual(
            workbuddy.get_logout_marker_path("/tmp/x/a.info"),
            "/tmp/x/a.info.logged-out",
        )

    def test_02_preview_writes_nothing(self):
        self.write_auth()
        with patch.object(workbuddy, "is_workbuddy_running", return_value=False):
            workbuddy.run_logout([])
        self.assertTrue(os.path.exists(workbuddy.AUTH_FILE), "预览不得删除凭据")
        self.assertFalse(os.path.exists(workbuddy.get_logout_marker_path()))
        self.assertFalse(os.path.exists(workbuddy.LOGOUT_BACKUP_ROOT), "预览不得产生备份")

    def test_03_logout_writes_marker_and_removes_credential(self):
        self.write_auth()
        with patch.object(workbuddy, "is_workbuddy_running", return_value=False):
            workbuddy.run_logout(["--yes"])

        marker = workbuddy.get_logout_marker_path()
        self.assertFalse(os.path.exists(workbuddy.AUTH_FILE), "凭据应被删除")
        self.assertTrue(os.path.exists(marker), "登出标记应存在")
        with open(marker, "r", encoding="utf-8") as f:
            content = f.read().strip()
        self.assertRegex(
            content, r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$",
            "标记内容应为 ISO 8601 UTC 时间（与 JS toISOString 一致）")

    def test_04_backup_copied_before_removal(self):
        self.write_auth({"auth": {"accessToken": "secret-value"}})
        with patch.object(workbuddy, "is_workbuddy_running", return_value=False):
            workbuddy.run_logout(["--yes"])

        self.assertTrue(os.path.isdir(workbuddy.LOGOUT_BACKUP_ROOT))
        stamps = os.listdir(workbuddy.LOGOUT_BACKUP_ROOT)
        self.assertEqual(len(stamps), 1)
        backup_file = os.path.join(
            workbuddy.LOGOUT_BACKUP_ROOT, stamps[0], "workbuddy-desktop.info")
        self.assertTrue(os.path.exists(backup_file), "删除前必须留下凭据副本")

    def test_05_refuses_while_client_running(self):
        self.write_auth()
        with patch.object(workbuddy, "is_workbuddy_running", return_value=True):
            ok = workbuddy.run_logout(["--yes"])
        self.assertFalse(ok, "客户端运行时应返回失败，由 main 转成非零退出码")
        self.assertTrue(os.path.exists(workbuddy.AUTH_FILE), "被拒时不得删除凭据")

    def test_06_allow_running_overrides(self):
        self.write_auth()
        with patch.object(workbuddy, "is_workbuddy_running", return_value=True):
            workbuddy.run_logout(["--yes", "--allow-running"])
        self.assertFalse(os.path.exists(workbuddy.AUTH_FILE))

    def test_07_idempotent_when_already_logged_out(self):
        with patch.object(workbuddy, "is_workbuddy_running", return_value=False):
            workbuddy.run_logout(["--yes"])
        self.assertFalse(os.path.exists(workbuddy.get_logout_marker_path()),
                         "无凭据时不应凭空创建标记")

    def test_08_deep_clears_account_cache_only(self):
        self.write_auth()
        sidebar, startup = self.make_uid_cache()

        with patch.object(workbuddy, "is_workbuddy_running", return_value=False):
            workbuddy.run_logout(["--yes", "--deep"])

        self.assertFalse(os.path.exists(workbuddy.ACCOUNT_SNAPSHOT_FILE), "账号快照应清理")
        self.assertFalse(os.path.exists(sidebar), "侧栏快照应清理")
        self.assertTrue(os.path.exists(startup),
                        "startup-route.json 与账号无关，不该被顺手删掉")

    def test_09_without_deep_keeps_cache(self):
        self.write_auth()
        self.make_uid_cache()
        with patch.object(workbuddy, "is_workbuddy_running", return_value=False):
            workbuddy.run_logout(["--yes"])
        self.assertTrue(os.path.exists(workbuddy.ACCOUNT_SNAPSHOT_FILE),
                        "不带 --deep 时不应清理账号缓存")

    def test_10_force_is_not_accepted_as_confirm(self):
        """-f / --force 不再等同于 --yes：误触不能跳过预览直接删凭据。"""
        self.write_auth()
        with patch.object(workbuddy, "is_workbuddy_running", return_value=False):
            workbuddy.run_logout(["--force"])
            workbuddy.run_logout(["-f"])
        self.assertTrue(os.path.exists(workbuddy.AUTH_FILE),
                        "带 --force / -f 时不得删除凭据")
        self.assertFalse(os.path.exists(workbuddy.get_logout_marker_path()))

    def test_11_uid_traversal_ignored_in_deep(self):
        """uid 含路径穿越字符时，--deep 不得越界清理。"""
        self.write_auth()
        sentinel = os.path.join(os.path.dirname(self.test_dir),
                                "sidebar-list-snapshot.json")
        with open(sentinel, "w", encoding="utf-8") as f:
            f.write("sentinel")

        def _cleanup():
            if os.path.exists(sentinel):
                os.remove(sentinel)
        self.addCleanup(_cleanup)

        os.makedirs(os.path.dirname(workbuddy.ACCOUNT_SNAPSHOT_FILE), exist_ok=True)
        with open(workbuddy.ACCOUNT_SNAPSHOT_FILE, "w", encoding="utf-8") as f:
            json.dump({"primary": {"uid": "../"}}, f)

        with patch.object(workbuddy, "is_workbuddy_running", return_value=False):
            workbuddy.run_logout(["--yes", "--deep"])

        self.assertTrue(os.path.exists(sentinel),
                        "uid 越界时不得删除 ~/.workbuddy 之外的同名文件")

    def test_12_logout_then_switch_clears_all_markers(self):
        """登出后切号：新凭据必须可用，全部残留标记必须清除。

        客户端只认 `<凭证>.logged-out`，而 switch_to_profile 历史上只清
        `workbuddy-desktop.logout-marker`。任一残留都会让新凭据被忽略，
        表现为"切号返回成功但客户端仍按未登录处理"。
        """
        self.write_auth({"account": {"uid": "uid-1", "nickname": "acc1"},
                         "auth": {"accessToken": "tok1"}})

        with patch.object(workbuddy, "is_workbuddy_running", return_value=False):
            self.assertTrue(workbuddy.run_logout(["--yes"]))

        markers = workbuddy.get_all_logout_markers()
        self.assertTrue(len(markers) >= 2, "应同时覆盖客户端标记与 toolkit 历史标记")
        for m in markers:
            self.assertTrue(os.path.exists(m),
                            "登出后应写入 {}".format(os.path.basename(m)))

        os.makedirs(workbuddy.PROFILES_DIR, exist_ok=True)
        target = {"account": {"uid": "uid-2", "nickname": "acc2"},
                  "auth": {"accessToken": "tok2"}}
        with open(os.path.join(workbuddy.PROFILES_DIR, "acc2.info"), "w",
                  encoding="utf-8") as f:
            json.dump(target, f)

        with patch.object(workbuddy, "sync_active_token_to_profiles", return_value=None), \
                patch.object(workbuddy, "reassign_automations_owner", return_value=None):
            switched = workbuddy.switch_to_profile("acc2", auto_restart=False)

        self.assertTrue(switched, "切号应成功")
        self.assertTrue(os.path.exists(workbuddy.AUTH_FILE), "切号后凭据应已写入")
        for m in markers:
            self.assertFalse(
                os.path.exists(m),
                "切号后残留 {}，新凭据会被客户端忽略".format(os.path.basename(m)))

    def test_13_backups_do_not_overwrite_in_same_second(self):
        """同一秒内连续登出两次，两份凭据副本都必须保留。"""
        self.write_auth({"auth": {"accessToken": "first"}})
        with patch.object(workbuddy, "is_workbuddy_running", return_value=False):
            self.assertTrue(workbuddy.run_logout(["--yes"]))

        self.write_auth({"auth": {"accessToken": "second"}})
        with patch.object(workbuddy, "is_workbuddy_running", return_value=False):
            self.assertTrue(workbuddy.run_logout(["--yes"]))

        dirs = [d for d in os.listdir(workbuddy.LOGOUT_BACKUP_ROOT)
                if os.path.isdir(os.path.join(workbuddy.LOGOUT_BACKUP_ROOT, d))]
        self.assertEqual(len(dirs), 2, "两次登出应产生两个独立备份目录")

        contents = set()
        for d in dirs:
            path = os.path.join(workbuddy.LOGOUT_BACKUP_ROOT, d, "workbuddy-desktop.info")
            with open(path, encoding="utf-8") as f:
                contents.add(json.load(f)["auth"]["accessToken"])
        self.assertEqual(contents, {"first", "second"},
                         "两份副本内容都必须在，不能互相覆盖")

    def test_14_unknown_process_state_blocks_without_flag(self):
        """进程探测返回 None（未知）时默认拦截，不得当作"未运行"。"""
        self.write_auth()
        with patch.object(workbuddy, "is_workbuddy_running", return_value=None):
            ok = workbuddy.run_logout(["--yes"])
        self.assertFalse(ok, "未知状态应返回失败")
        self.assertTrue(os.path.exists(workbuddy.AUTH_FILE), "未知状态不得删除凭据")

    def test_15_unknown_state_allowed_with_flag(self):
        self.write_auth()
        with patch.object(workbuddy, "is_workbuddy_running", return_value=None):
            ok = workbuddy.run_logout(["--yes", "--allow-running"])
        self.assertTrue(ok)
        self.assertFalse(os.path.exists(workbuddy.AUTH_FILE))

    def test_16_delete_failure_returns_false(self):
        """凭据删除失败时 run_logout 必须返回 False，让 main 能转成非零退出码。"""
        self.write_auth()
        real_remove = os.remove

        def fake_remove(path, *args, **kwargs):
            if str(path).endswith("workbuddy-desktop.info"):
                raise PermissionError("locked by client")
            return real_remove(path, *args, **kwargs)

        with patch.object(workbuddy, "is_workbuddy_running", return_value=False), \
                patch("os.remove", side_effect=fake_remove):
            ok = workbuddy.run_logout(["--yes"])

        self.assertFalse(ok, "删除失败必须返回 False")
        self.assertTrue(os.path.exists(workbuddy.AUTH_FILE))

    def test_17_linux_branch_uses_proc_scan_not_pgrep(self):
        """Linux 分支必须复用 _linux_app_pids，不得用 pgrep -f 做命令行模糊匹配。"""
        with patch("sys.platform", "linux"), \
                patch.object(workbuddy, "_linux_app_pids", return_value=[4321]) as scan:
            self.assertTrue(workbuddy.is_workbuddy_running())
            scan.assert_called_once()

        with patch("sys.platform", "linux"), \
                patch.object(workbuddy, "_linux_app_pids", return_value=[]):
            self.assertFalse(workbuddy.is_workbuddy_running())


class TestLogoutAdversarial(LogoutSandbox):
    """刻意破坏前置条件，验证环境异常时不会误删、不会崩溃。"""

    def test_a1_corrupt_credential_still_logs_out(self):
        """凭据文件是非法二进制：登出不依赖解析它，应照常完成。"""
        with open(workbuddy.AUTH_FILE, "wb") as f:
            f.write(b"\x00\x01\x02 not json at all")
        with patch.object(workbuddy, "is_workbuddy_running", return_value=False):
            self.assertTrue(workbuddy.run_logout(["--yes"]))
        self.assertFalse(os.path.exists(workbuddy.AUTH_FILE))
        self.assertTrue(os.path.exists(workbuddy.get_logout_marker_path()))

    def test_a2_empty_credential_file(self):
        """0 字节凭据也应能登出。"""
        open(workbuddy.AUTH_FILE, "wb").close()
        with patch.object(workbuddy, "is_workbuddy_running", return_value=False):
            self.assertTrue(workbuddy.run_logout(["--yes"]))
        self.assertFalse(os.path.exists(workbuddy.AUTH_FILE))

    def test_a3_corrupt_snapshot_does_not_crash_deep(self):
        """account-snapshot 损坏时 --deep 不得崩溃，凭据与快照都应被清掉。"""
        self.write_auth()
        os.makedirs(os.path.dirname(workbuddy.ACCOUNT_SNAPSHOT_FILE), exist_ok=True)
        with open(workbuddy.ACCOUNT_SNAPSHOT_FILE, "w", encoding="utf-8") as f:
            f.write("{ broken json")
        with patch.object(workbuddy, "is_workbuddy_running", return_value=False):
            self.assertTrue(workbuddy.run_logout(["--yes", "--deep"]))
        self.assertFalse(os.path.exists(workbuddy.AUTH_FILE))
        self.assertFalse(os.path.exists(workbuddy.ACCOUNT_SNAPSHOT_FILE),
                         "损坏的账号快照仍应被清理")

    def test_a4_overlong_uid_does_not_escape(self):
        """uid 超长（超出白名单上限）时不得拼出越界路径。"""
        self.write_auth()
        os.makedirs(os.path.dirname(workbuddy.ACCOUNT_SNAPSHOT_FILE), exist_ok=True)
        outside = os.path.join(os.path.dirname(self.test_dir),
                               "sidebar-list-snapshot.json")
        with open(outside, "w", encoding="utf-8") as f:
            f.write("sentinel")

        def cleanup():
            if os.path.exists(outside):
                os.remove(outside)
        self.addCleanup(cleanup)

        with open(workbuddy.ACCOUNT_SNAPSHOT_FILE, "w", encoding="utf-8") as f:
            json.dump({"primary": {"uid": "a" * 500}}, f)

        with patch.object(workbuddy, "is_workbuddy_running", return_value=False):
            self.assertTrue(workbuddy.run_logout(["--yes", "--deep"]))
        self.assertTrue(os.path.exists(outside), "超长 uid 不得越界删除")

    def test_a5_backup_root_blocked_by_file(self):
        """备份根路径被同名普通文件占位时中止，且不删凭据、不写标记。"""
        self.write_auth()
        with open(workbuddy.LOGOUT_BACKUP_ROOT, "w", encoding="utf-8") as f:
            f.write("blocked")
        with patch.object(workbuddy, "is_workbuddy_running", return_value=False):
            ok = workbuddy.run_logout(["--yes"])
        self.assertFalse(ok, "无法创建备份目录时必须返回失败")
        self.assertTrue(os.path.exists(workbuddy.AUTH_FILE), "备份失败不得删除凭据")
        self.assertFalse(os.path.exists(workbuddy.get_logout_marker_path()),
                         "备份失败时不应写入标记")

    def test_a6_marker_path_occupied_by_directory(self):
        """标记路径被目录占位时写入失败，应中止且不删凭据。"""
        self.write_auth()
        os.makedirs(workbuddy.get_logout_marker_path(), exist_ok=True)
        with patch.object(workbuddy, "is_workbuddy_running", return_value=False):
            ok = workbuddy.run_logout(["--yes"])
        self.assertFalse(ok, "标记写入失败必须返回失败")
        self.assertTrue(os.path.exists(workbuddy.AUTH_FILE), "标记失败不得删除凭据")

    def test_a7_concurrent_logout_is_safe(self):
        """多线程同时登出：不得抛未捕获异常，最终状态必须一致。"""
        self.write_auth()
        results = []

        def worker():
            try:
                results.append(workbuddy.run_logout(["--yes"]))
            except Exception as exc:  # noqa: BLE001 - 显式收集任何未捕获异常
                results.append(exc)

        with patch.object(workbuddy, "is_workbuddy_running", return_value=False):
            threads = [threading.Thread(target=worker) for _ in range(5)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()

        errors = [r for r in results if isinstance(r, Exception)]
        self.assertFalse(errors, "并发登出不应抛出未捕获异常: {}".format(errors))
        self.assertFalse(os.path.exists(workbuddy.AUTH_FILE), "凭据最终应被删除")
        self.assertTrue(os.path.exists(workbuddy.get_logout_marker_path()), "标记应存在")

    def test_a8_repeated_logout_keeps_every_backup(self):
        """连续多次登出，每一份凭据副本都必须保留，不得互相覆盖。"""
        created = []
        for i in range(3):
            token = "tok-%d" % i
            self.write_auth({"auth": {"accessToken": token}})
            with patch.object(workbuddy, "is_workbuddy_running", return_value=False):
                self.assertTrue(workbuddy.run_logout(["--yes"]))
            created.append(token)

        dirs = [d for d in os.listdir(workbuddy.LOGOUT_BACKUP_ROOT)
                if os.path.isdir(os.path.join(workbuddy.LOGOUT_BACKUP_ROOT, d))]
        self.assertEqual(len(dirs), 3, "三次登出应产生三个独立备份目录")

        seen = set()
        for d in dirs:
            path = os.path.join(workbuddy.LOGOUT_BACKUP_ROOT, d,
                                "workbuddy-desktop.info")
            with open(path, encoding="utf-8") as f:
                seen.add(json.load(f)["auth"]["accessToken"])
        self.assertEqual(seen, set(created), "三份凭据副本都必须保留")


if __name__ == "__main__":
    unittest.main(verbosity=2)
