#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
删除已保存账号 Profile 的回归测试 (workbuddy remove / wb-remove)。

覆盖点：
  1. 默认软删除：从 auth_profiles 移入 .trash，可还原
  2. --purge：真正删除，不留回收站副本
  3. 默认拒绝删除当前活跃账号；--force 才允许
  4. 非交互环境不带 --yes 直接拒绝
  5. 未知别名不产生任何文件变动
  6. 同名重复删除不会互相覆盖回收站文件
  7. 删除最后一个账号时仍能正常执行（并给出提示）

所有用例都在临时目录内完成，不会触碰真实 ~/.workbuddy/auth_profiles。
"""

import io
import os
import sys
import json
import stat
import time
import shutil
import tempfile
import unittest
import importlib.util
import importlib.machinery
from contextlib import redirect_stdout
from unittest.mock import patch

if sys.platform == "win32":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

REPO_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BIN_PATH = os.path.join(REPO_DIR, "bin", "workbuddy")
loader = importlib.machinery.SourceFileLoader("workbuddy_remove", BIN_PATH)
spec = importlib.util.spec_from_loader("workbuddy_remove", loader)
workbuddy = importlib.util.module_from_spec(spec)
loader.exec_module(workbuddy)


class _FakeStdin:
    """最小 stdin 替身：只用 isatty() 决定走交互还是非交互分支。"""

    def __init__(self, tty):
        self._tty = tty

    def isatty(self):
        return self._tty


def _write_profile(profiles_dir, alias, uid, nickname="测试账号"):
    data = {
        "account": {"uid": uid, "nickname": nickname, "uin": "1000"},
        "auth": {"accessToken": "x", "refreshToken": "y", "expiresAt": 0},
    }
    path = os.path.join(profiles_dir, "{}.info".format(alias))
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
    return path


def _write_active_account(auth_file, uid, nickname="测试账号"):
    data = {"account": {"uid": uid, "nickname": nickname, "uin": "1000"}}
    os.makedirs(os.path.dirname(auth_file), exist_ok=True)
    with open(auth_file, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)


class TestRemoveProfile(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.orig_profiles_dir = workbuddy.PROFILES_DIR
        self.orig_auth_file = workbuddy.AUTH_FILE
        self.orig_stdin = sys.stdin

        workbuddy.PROFILES_DIR = os.path.join(self.tmp, "auth_profiles")
        workbuddy.AUTH_FILE = os.path.join(self.tmp, "auth", "workbuddy-desktop.info")
        os.makedirs(workbuddy.PROFILES_DIR, exist_ok=True)

        self.trash_dir = os.path.join(workbuddy.PROFILES_DIR, ".trash")

    def tearDown(self):
        workbuddy.PROFILES_DIR = self.orig_profiles_dir
        workbuddy.AUTH_FILE = self.orig_auth_file
        sys.stdin = self.orig_stdin
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _run(self, *args, **kwargs):
        """调用 remove_profile 并吞掉终端输出。"""
        with redirect_stdout(io.StringIO()) as buf:
            result = workbuddy.remove_profile(*args, **kwargs)
        return result, buf.getvalue()

    def _trash_files(self):
        if not os.path.isdir(self.trash_dir):
            return []
        return [f for f in os.listdir(self.trash_dir) if f.endswith(".info")]

    # ---------- 1. 默认软删除 ----------

    def test_soft_delete_moves_file_into_trash(self):
        _write_active_account(workbuddy.AUTH_FILE, "uid-active")
        _write_profile(workbuddy.PROFILES_DIR, "old", "uid-old")
        _write_profile(workbuddy.PROFILES_DIR, "keep", "uid-keep")

        ok, out = self._run("old", assume_yes=True)

        self.assertTrue(ok, out)
        self.assertFalse(os.path.exists(os.path.join(workbuddy.PROFILES_DIR, "old.info")))
        self.assertTrue(os.path.exists(os.path.join(workbuddy.PROFILES_DIR, "keep.info")))
        self.assertEqual(len(self._trash_files()), 1)
        self.assertIn("回收站", out)

    def test_trashed_file_keeps_valid_json_content(self):
        """还原靠的是把文件搬回去，所以内容必须完整可解析。"""
        _write_profile(workbuddy.PROFILES_DIR, "old", "uid-old")
        _write_profile(workbuddy.PROFILES_DIR, "keep", "uid-keep")

        ok, _ = self._run("old", assume_yes=True)
        self.assertTrue(ok)

        trashed = os.path.join(self.trash_dir, self._trash_files()[0])
        with open(trashed, "r", encoding="utf-8") as f:
            restored = json.load(f)
        self.assertEqual(restored["account"]["uid"], "uid-old")

        # 手工还原后应能被 get_profiles() 重新识别
        shutil.move(trashed, os.path.join(workbuddy.PROFILES_DIR, "old.info"))
        with redirect_stdout(io.StringIO()):
            profiles = workbuddy.get_profiles()
        self.assertIn("old", profiles)

    def test_trash_does_not_pollute_profile_list(self):
        """回收站目录不能被 get_profiles() 当成账号读出来。"""
        _write_profile(workbuddy.PROFILES_DIR, "old", "uid-old")
        _write_profile(workbuddy.PROFILES_DIR, "keep", "uid-keep")

        self._run("old", assume_yes=True)
        with redirect_stdout(io.StringIO()):
            profiles = workbuddy.get_profiles()

        self.assertEqual(sorted(profiles.keys()), ["keep"])

    # ---------- 2. --purge ----------

    def test_purge_removes_file_without_trash_copy(self):
        _write_profile(workbuddy.PROFILES_DIR, "old", "uid-old")
        _write_profile(workbuddy.PROFILES_DIR, "keep", "uid-keep")

        ok, out = self._run("old", assume_yes=True, purge=True)

        self.assertTrue(ok, out)
        self.assertFalse(os.path.exists(os.path.join(workbuddy.PROFILES_DIR, "old.info")))
        self.assertEqual(self._trash_files(), [])
        self.assertIn("彻底删除", out)

    # ---------- 3. 活跃账号保护 ----------

    def test_refuses_to_remove_active_account_by_default(self):
        _write_active_account(workbuddy.AUTH_FILE, "uid-active")
        _write_profile(workbuddy.PROFILES_DIR, "me", "uid-active")

        ok, out = self._run("me", assume_yes=True)

        self.assertFalse(ok, out)
        self.assertTrue(os.path.exists(os.path.join(workbuddy.PROFILES_DIR, "me.info")))
        self.assertIn("当前活跃账号", out)
        self.assertIn("--force", out)

    def test_force_allows_removing_active_account(self):
        _write_active_account(workbuddy.AUTH_FILE, "uid-active")
        _write_profile(workbuddy.PROFILES_DIR, "me", "uid-active")
        _write_profile(workbuddy.PROFILES_DIR, "other", "uid-other")

        ok, out = self._run("me", assume_yes=True, force=True)

        self.assertTrue(ok, out)
        self.assertFalse(os.path.exists(os.path.join(workbuddy.PROFILES_DIR, "me.info")))
        # 删掉当前登录态备份后应额外警告
        self.assertIn("没有回滚副本", out)

    def test_active_account_check_by_uid_not_alias(self):
        """活跃账号判定看 UID，别名不同也必须拦住。"""
        _write_active_account(workbuddy.AUTH_FILE, "uid-active")
        _write_profile(workbuddy.PROFILES_DIR, "另一个名字", "uid-active")

        ok, _ = self._run("另一个名字", assume_yes=True)
        self.assertFalse(ok)

    # ---------- 4. 非交互保护 ----------

    def test_non_interactive_without_yes_is_refused(self):
        _write_profile(workbuddy.PROFILES_DIR, "old", "uid-old")
        _write_profile(workbuddy.PROFILES_DIR, "keep", "uid-keep")
        sys.stdin = _FakeStdin(tty=False)

        ok, out = self._run("old")

        self.assertFalse(ok, out)
        self.assertTrue(os.path.exists(os.path.join(workbuddy.PROFILES_DIR, "old.info")))
        self.assertIn("--yes", out)

    def test_interactive_prompt_yes_deletes(self):
        _write_profile(workbuddy.PROFILES_DIR, "old", "uid-old")
        _write_profile(workbuddy.PROFILES_DIR, "keep", "uid-keep")
        sys.stdin = _FakeStdin(tty=True)

        with patch("builtins.input", return_value="y"):
            ok, out = self._run("old")

        self.assertTrue(ok, out)
        self.assertFalse(os.path.exists(os.path.join(workbuddy.PROFILES_DIR, "old.info")))

    def test_interactive_prompt_default_no_keeps_file(self):
        _write_profile(workbuddy.PROFILES_DIR, "old", "uid-old")
        _write_profile(workbuddy.PROFILES_DIR, "keep", "uid-keep")
        sys.stdin = _FakeStdin(tty=True)

        with patch("builtins.input", return_value=""):
            ok, out = self._run("old")

        self.assertFalse(ok, out)
        self.assertTrue(os.path.exists(os.path.join(workbuddy.PROFILES_DIR, "old.info")))
        self.assertIn("已取消", out)

    # ---------- 5. 未知别名 ----------

    def test_unknown_alias_changes_nothing(self):
        _write_profile(workbuddy.PROFILES_DIR, "keep", "uid-keep")

        ok, out = self._run("不存在的账号", assume_yes=True)

        self.assertFalse(ok, out)
        self.assertTrue(os.path.exists(os.path.join(workbuddy.PROFILES_DIR, "keep.info")))
        self.assertEqual(self._trash_files(), [])

    def test_no_profiles_at_all(self):
        ok, out = self._run("anything", assume_yes=True)
        self.assertFalse(ok, out)
        self.assertIn("无需删除", out)

    # ---------- 6. 回收站不覆盖 ----------

    def test_repeated_delete_does_not_overwrite_trash(self):
        _write_profile(workbuddy.PROFILES_DIR, "dup", "uid-1")
        _write_profile(workbuddy.PROFILES_DIR, "keep", "uid-keep")
        self._run("dup", assume_yes=True)

        _write_profile(workbuddy.PROFILES_DIR, "dup", "uid-2")
        self._run("dup", assume_yes=True)

        self.assertEqual(len(self._trash_files()), 2)

    # ---------- 7. 最后一个账号 ----------

    def test_removing_last_profile_warns_but_succeeds(self):
        _write_profile(workbuddy.PROFILES_DIR, "only", "uid-only")

        ok, out = self._run("only", assume_yes=True)

        self.assertTrue(ok, out)
        self.assertIn("最后一个", out)
        self.assertIn("0 个", out)

    # ---------- 8. 命令行参数解析 ----------

    def test_run_remove_cmd_help(self):
        with redirect_stdout(io.StringIO()) as buf:
            ok = workbuddy.run_remove_cmd(["--help"])
        self.assertTrue(ok)
        self.assertIn("--purge", buf.getvalue())

    def test_run_remove_cmd_without_target(self):
        with redirect_stdout(io.StringIO()) as buf:
            ok = workbuddy.run_remove_cmd(["--yes"])
        self.assertFalse(ok)
        self.assertIn("请提供要删除的账号别名", buf.getvalue())

    def test_run_remove_cmd_parses_flags(self):
        _write_profile(workbuddy.PROFILES_DIR, "old", "uid-old")
        _write_profile(workbuddy.PROFILES_DIR, "keep", "uid-keep")

        with redirect_stdout(io.StringIO()):
            ok = workbuddy.run_remove_cmd(["old", "--yes", "--purge"])
        self.assertTrue(ok)
        self.assertFalse(os.path.exists(os.path.join(workbuddy.PROFILES_DIR, "old.info")))

    def test_alias_named_like_command_gets_switch_hint(self):
        """兼容性：removed/delete/rm 过去会走"账号名快捷切换"。

        加了本命令后这些词优先当命令解析，因此裸敲 `workbuddy rm`（不带目标）时
        必须①不删除任何东西 ②在有同名账号时给出 `workbuddy switch rm` 的出口。
        """
        _write_profile(workbuddy.PROFILES_DIR, "rm", "uid-rm")

        with redirect_stdout(io.StringIO()) as buf:
            ok = workbuddy.run_remove_cmd([], invoked="rm")

        self.assertFalse(ok)
        out = buf.getvalue()
        self.assertTrue(os.path.exists(os.path.join(workbuddy.PROFILES_DIR, "rm.info")),
                        "裸敲命令词绝不能删除同名账号")
        self.assertIn("workbuddy switch rm", out)

    def test_alias_named_like_command_still_removable_with_target(self):
        """同名账号仍然可以被正常删除，只是必须显式给出目标。"""
        _write_profile(workbuddy.PROFILES_DIR, "rm", "uid-rm")

        with redirect_stdout(io.StringIO()):
            ok = workbuddy.run_remove_cmd(["rm", "--yes"], invoked="remove")

        self.assertTrue(ok)
        self.assertFalse(os.path.exists(os.path.join(workbuddy.PROFILES_DIR, "rm.info")))


class TestRemoveProfileAdversarial(unittest.TestCase):
    """对抗测试：假设账号文件已损坏、凭据不可读、调用方并发、回收站被占位。

    这些用例来自一次对抗测试（刻意破坏前置条件），覆盖"环境已经不正常时会不会误删"。
    """

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.orig_profiles_dir = workbuddy.PROFILES_DIR
        self.orig_auth_file = workbuddy.AUTH_FILE
        self.orig_stdin = sys.stdin
        workbuddy.PROFILES_DIR = os.path.join(self.tmp, "auth_profiles")
        workbuddy.AUTH_FILE = os.path.join(self.tmp, "auth", "workbuddy-desktop.info")
        os.makedirs(workbuddy.PROFILES_DIR, exist_ok=True)
        os.makedirs(os.path.dirname(workbuddy.AUTH_FILE), exist_ok=True)
        self.trash_dir = os.path.join(workbuddy.PROFILES_DIR, ".trash")

    def tearDown(self):
        workbuddy.PROFILES_DIR = self.orig_profiles_dir
        workbuddy.AUTH_FILE = self.orig_auth_file
        sys.stdin = self.orig_stdin
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _raw_profile(self, alias, content):
        path = os.path.join(workbuddy.PROFILES_DIR, alias + ".info")
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        return path

    def _raw_auth(self, content):
        with open(workbuddy.AUTH_FILE, "w", encoding="utf-8") as f:
            f.write(content)

    def _run(self, *args, **kwargs):
        with redirect_stdout(io.StringIO()) as buf:
            result = workbuddy.remove_profile(*args, **kwargs)
        return result, buf.getvalue()

    def _exists(self, alias):
        return os.path.exists(os.path.join(workbuddy.PROFILES_DIR, alias + ".info"))

    def _trash_count(self):
        return len([f for f in os.listdir(self.trash_dir) if f.endswith(".info")]) if os.path.isdir(self.trash_dir) else 0

    # ---- 活跃账号判定被搞坏 ----

    def test_active_uid_with_spaces_and_case_still_blocked(self):
        """活跃凭据里写成 ' UID-ME ' 也必须认出来，不能靠大小写/空白差异绕过。"""
        _write_profile(workbuddy.PROFILES_DIR, "me", "uid-me")
        self._raw_auth(json.dumps({"account": {"uid": " UID-ME "}}))

        ok, out = self._run("me", assume_yes=True)

        self.assertFalse(ok, out)
        self.assertTrue(self._exists("me"))
        self.assertIn("当前活跃账号", out)

    def test_active_uid_as_userid_field_still_blocked(self):
        _write_profile(workbuddy.PROFILES_DIR, "me", "uid-me")
        self._raw_auth(json.dumps({"account": {"userId": "uid-me"}}))

        ok, _ = self._run("me", assume_yes=True)
        self.assertFalse(ok)
        self.assertTrue(self._exists("me"))

    def test_unreadable_active_credential_blocks_all_deletion(self):
        """活跃凭据文件在但解析不了 → 无法证明目标不活跃，必须拒绝，除非 --force。"""
        _write_profile(workbuddy.PROFILES_DIR, "me", "uid-me")
        _write_profile(workbuddy.PROFILES_DIR, "other", "uid-other")
        self._raw_auth("{broken json")

        ok, out = self._run("me", assume_yes=True)

        self.assertFalse(ok, out)
        self.assertTrue(self._exists("me"))
        self.assertIn("读不到账号 UID", out)

    def test_active_credential_without_uid_blocks_deletion(self):
        """活跃凭据是合法 JSON 但读不出 UID 时，同样属于"无法确认"，不能放行。

        这三种形态都能正常 json.loads，早期实现因此误判为"没有活跃账号"而放行，
        导致活跃账号的备份被无 --force 删除。
        """
        for content in ('{"foo": 1}', '{"account": {}}', '{"account": {"nickname": "x"}}'):
            _write_profile(workbuddy.PROFILES_DIR, "me", "uid-me")
            _write_profile(workbuddy.PROFILES_DIR, "other", "uid-other")
            self._raw_auth(content)

            ok, out = self._run("me", assume_yes=True)

            self.assertFalse(ok, "凭据 %r 下不应放行删除: %s" % (content, out))
            self.assertTrue(self._exists("me"), "活跃账号备份被误删，凭据为 %r" % content)

            # 清理，保证下一轮用例独立
            os.remove(os.path.join(workbuddy.PROFILES_DIR, "me.info"))
            os.remove(os.path.join(workbuddy.PROFILES_DIR, "other.info"))

    def test_active_credential_without_uid_allows_force(self):
        _write_profile(workbuddy.PROFILES_DIR, "other", "uid-other")
        self._raw_auth('{"account": {}}')

        ok, out = self._run("other", assume_yes=True, force=True)
        self.assertTrue(ok, out)
        self.assertFalse(self._exists("other"))

    def test_unreadable_active_credential_allows_force(self):
        _write_profile(workbuddy.PROFILES_DIR, "other", "uid-other")
        self._raw_auth("{broken json")

        ok, out = self._run("other", assume_yes=True, force=True)
        self.assertTrue(ok, out)
        self.assertFalse(self._exists("other"))

    def test_missing_active_credential_does_not_block(self):
        """凭据文件完全不存在（未登录过）时不该拦，否则没法清理。"""
        _write_profile(workbuddy.PROFILES_DIR, "old", "uid-old")
        _write_profile(workbuddy.PROFILES_DIR, "keep", "uid-keep")
        if os.path.exists(workbuddy.AUTH_FILE):
            os.remove(workbuddy.AUTH_FILE)

        ok, out = self._run("old", assume_yes=True)
        self.assertTrue(ok, out)

    # ---- 账号文件本身已损坏 ----

    def test_corrupt_json_profile_is_not_deleted(self):
        """解析失败的账号在列表里根本不可见，不能凭空删掉一个文件。"""
        self._raw_profile("bad", "{not json")
        _write_profile(workbuddy.PROFILES_DIR, "keep", "uid-keep")

        ok, out = self._run("bad", assume_yes=True)

        self.assertFalse(ok, out)
        self.assertTrue(self._exists("bad"))
        self.assertIn("未找到", out)

    def test_profile_dir_named_like_profile_is_skipped(self):
        """.info 后缀但其实是目录时不能被当账号删除。"""
        os.makedirs(os.path.join(workbuddy.PROFILES_DIR, "asdir.info"), exist_ok=True)
        _write_profile(workbuddy.PROFILES_DIR, "keep", "uid-keep")

        ok, out = self._run("asdir", assume_yes=True)
        self.assertFalse(ok, out)
        self.assertTrue(os.path.isdir(os.path.join(workbuddy.PROFILES_DIR, "asdir.info")))

    def test_readonly_profile_file_can_still_be_removed(self):
        """只读属性不应让账号删不掉（会卡住用户），必须能正常移入回收站。"""
        path = _write_profile(workbuddy.PROFILES_DIR, "ro", "uid-ro")
        _write_profile(workbuddy.PROFILES_DIR, "keep", "uid-keep")
        os.chmod(path, stat.S_IREAD)
        try:
            ok, out = self._run("ro", assume_yes=True)
            self.assertTrue(ok, out)
            self.assertFalse(self._exists("ro"))
        finally:
            try:
                os.chmod(path, stat.S_IWRITE)
            except OSError:
                pass

    # ---- 回收站异常 ----

    def test_trash_path_occupied_by_file_fails_gracefully(self):
        """回收站位置被同名普通文件占了 → 报错但绝不能动源文件。"""
        _write_profile(workbuddy.PROFILES_DIR, "old", "uid-old")
        _write_profile(workbuddy.PROFILES_DIR, "keep", "uid-keep")
        with open(os.path.join(workbuddy.PROFILES_DIR, ".trash"), "w", encoding="utf-8") as f:
            f.write("occupied")

        ok, out = self._run("old", assume_yes=True)

        self.assertFalse(ok, out)
        self.assertTrue(self._exists("old"))
        self.assertIn("删除失败", out)

    # ---- 并发 ----

    def test_concurrent_removal_yields_single_trash_copy(self):
        """5 个线程同时删同一账号：只能有一个成功，回收站只能有 1 份副本。

        早期实现用 exists() 选目标名，存在 TOCTOU：多个线程会选中同一目标路径，
        导致回收站副本被覆盖、且多个调用方都报告"删除成功"。
        """
        import threading

        _write_profile(workbuddy.PROFILES_DIR, "race", "uid-race")
        _write_profile(workbuddy.PROFILES_DIR, "keep", "uid-keep")

        results = []
        barrier = threading.Barrier(5)

        def worker():
            barrier.wait()
            results.append(workbuddy.remove_profile("race", assume_yes=True))

        with redirect_stdout(io.StringIO()):
            threads = [threading.Thread(target=worker) for _ in range(5)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()

        self.assertEqual(len(results), 5)
        self.assertEqual(results.count(True), 1, "并发删除应当只有一个赢家，实际: %r" % (results,))
        self.assertEqual(self._trash_count(), 1, "回收站副本数量不对，可能发生了覆盖")
        self.assertTrue(self._exists("keep"))


class TestRemoveCliDispatch(unittest.TestCase):
    """覆盖 main() 的命令分发层：子命令入口、别名入口、退出码。

    之前只有手工 e2e 脚本验过这一层，单元测试没覆盖，改错分发也不会有测试报警。
    """

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.orig_profiles_dir = workbuddy.PROFILES_DIR
        self.orig_auth_file = workbuddy.AUTH_FILE
        self.orig_argv = sys.argv
        workbuddy.PROFILES_DIR = os.path.join(self.tmp, "auth_profiles")
        workbuddy.AUTH_FILE = os.path.join(self.tmp, "auth", "workbuddy-desktop.info")
        os.makedirs(workbuddy.PROFILES_DIR, exist_ok=True)
        os.makedirs(os.path.dirname(workbuddy.AUTH_FILE), exist_ok=True)
        _write_profile(workbuddy.PROFILES_DIR, "keep", "uid-keep")

    def tearDown(self):
        workbuddy.PROFILES_DIR = self.orig_profiles_dir
        workbuddy.AUTH_FILE = self.orig_auth_file
        sys.argv = self.orig_argv
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _main_exit_code(self, argv):
        sys.argv = argv
        with redirect_stdout(io.StringIO()) as buf:
            with self.assertRaises(SystemExit) as cm:
                workbuddy.main()
        return cm.exception.code, buf.getvalue()

    def test_subcommand_success_exits_zero(self):
        _write_profile(workbuddy.PROFILES_DIR, "old", "uid-old")
        code, _ = self._main_exit_code(["workbuddy", "remove", "old", "--yes"])
        self.assertEqual(code, 0)
        self.assertFalse(os.path.exists(os.path.join(workbuddy.PROFILES_DIR, "old.info")))

    def test_subcommand_failure_exits_nonzero(self):
        code, out = self._main_exit_code(["workbuddy", "remove", "nosuch", "--yes"])
        self.assertEqual(code, 1, "找不到账号时必须返回非零退出码，否则脚本会误判成功")
        self.assertIn("未找到", out)

    def test_alias_invocation_routes_to_remove(self):
        """以 wb-remove 名义启动（Unix 符号链接 / Windows 垫片）时也要走删除分支。"""
        _write_profile(workbuddy.PROFILES_DIR, "old", "uid-old")
        code, _ = self._main_exit_code(["wb-remove", "old", "--yes"])
        self.assertEqual(code, 0)
        self.assertFalse(os.path.exists(os.path.join(workbuddy.PROFILES_DIR, "old.info")))

    def test_db_style_command_alias_rm(self):
        """`workbuddy rm <别名>` 与 `delete` 同样可用。"""
        for word in ("rm", "delete", "del"):
            _write_profile(workbuddy.PROFILES_DIR, "old", "uid-old")
            code, _ = self._main_exit_code(["workbuddy", word, "old", "--yes"])
            self.assertEqual(code, 0, "%s 子命令失败" % word)
            self.assertFalse(os.path.exists(os.path.join(workbuddy.PROFILES_DIR, "old.info")))


class _RemoveV2Base(unittest.TestCase):
    """v2 系列用例的公共夹具（隔离目录 + 假凭据）。"""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.orig_profiles_dir = workbuddy.PROFILES_DIR
        self.orig_auth_file = workbuddy.AUTH_FILE
        self.orig_stdin = sys.stdin
        workbuddy.PROFILES_DIR = os.path.join(self.tmp, "auth_profiles")
        workbuddy.AUTH_FILE = os.path.join(self.tmp, "auth", "workbuddy-desktop.info")
        os.makedirs(workbuddy.PROFILES_DIR, exist_ok=True)
        os.makedirs(os.path.dirname(workbuddy.AUTH_FILE), exist_ok=True)

    def tearDown(self):
        workbuddy.PROFILES_DIR = self.orig_profiles_dir
        workbuddy.AUTH_FILE = self.orig_auth_file
        sys.stdin = self.orig_stdin
        shutil.rmtree(self.tmp, ignore_errors=True)

    # --- helpers ---
    def prof(self, alias, uid=None, nick=None):
        data = {"account": {"nickname": nick or alias}, "auth": {}}
        if uid is not None:
            data["account"]["uid"] = uid
        with open(os.path.join(workbuddy.PROFILES_DIR, alias + ".info"), "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)

    def raw_auth(self, content):
        with open(workbuddy.AUTH_FILE, "w", encoding="utf-8") as f:
            f.write(content)

    def active(self, uid, nick="当前"):
        with open(workbuddy.AUTH_FILE, "w", encoding="utf-8") as f:
            json.dump({"account": {"uid": uid, "nickname": nick}}, f, ensure_ascii=False)

    def exists(self, alias):
        return os.path.exists(os.path.join(workbuddy.PROFILES_DIR, alias + ".info"))

    def leftovers(self):
        return sorted(f[:-5] for f in os.listdir(workbuddy.PROFILES_DIR) if f.endswith(".info"))

    def call(self, args, invoked=None):
        with redirect_stdout(io.StringIO()) as buf:
            ok = workbuddy.run_remove_cmd(args, invoked=invoked)
        return ok, buf.getvalue()

    def run_remove(self, *a, **kw):
        with redirect_stdout(io.StringIO()) as buf:
            ok = workbuddy.remove_profile(*a, **kw)
        return ok, buf.getvalue()

    def trash_files(self):
        d = workbuddy.get_profiles_trash_dir()
        if not os.path.isdir(d):
            return []
        return sorted(os.listdir(d))


class TestRemoveCliArgs(_RemoveV2Base):
    """CLI 参数层：未知选项、多目标、-- 分隔符。

    评审实测发现旧实现会把未知选项静默丢弃（`remove alpha --dry-run` 直接删了 alpha），
    这些用例锁住修复后的严格行为。
    """

    def test_unknown_option_rejected_and_nothing_deleted(self):
        self.prof("alpha", "uid-a")
        self.prof("beta", "uid-b")
        self.active("uid-zzz")

        ok, out = self.call(["alpha", "--yes", "--dry-run"])

        self.assertFalse(ok, out)
        self.assertIn("未知选项", out)
        self.assertEqual(self.leftovers(), ["alpha", "beta"], "未知选项绝不能触发删除")

    def test_multiple_targets_rejected(self):
        self.prof("alpha", "uid-a")
        self.prof("beta", "uid-b")
        self.active("uid-zzz")

        ok, out = self.call(["alpha", "beta", "--yes"])

        self.assertFalse(ok, out)
        self.assertIn("一次只能删除一个账号", out)
        self.assertEqual(self.leftovers(), ["alpha", "beta"])

    def test_dash_separator_allows_hyphen_alias(self):
        self.prof("-weird", "uid-w")
        self.prof("keep", "uid-k")
        self.active("uid-k")

        ok, out = self.call(["--yes", "--", "-weird"])

        self.assertTrue(ok, out)
        self.assertEqual(self.leftovers(), ["keep"])

    def test_flags_after_separator_are_treated_as_targets(self):
        """POSIX 语义：`--` 之后一律是操作数，`--yes` 也不例外，应报"多目标"而不是被当开关。"""
        self.prof("alpha", "uid-a")
        self.active("uid-zzz")

        ok, out = self.call(["--", "alpha", "--yes"])

        self.assertFalse(ok, out)
        self.assertIn("一次只能删除一个账号", out)
        self.assertTrue(self.exists("alpha"))

    def test_restore_without_filename_is_rejected(self):
        ok, out = self.call(["--restore"])
        self.assertFalse(ok)
        self.assertIn("需要一个回收站文件名", out)

    def test_list_trash_rejects_targets(self):
        self.prof("alpha", "uid-a")
        ok, out = self.call(["--list-trash", "alpha"])
        self.assertFalse(ok)
        self.assertIn("不接受账号目标", out)

    def test_help_lists_new_options(self):
        ok, out = self.call(["-h"])
        self.assertTrue(ok)
        for token in ("--list-trash", "--restore", "--purge", "--"):
            self.assertIn(token, out)


class TestRemoveIdentitySafety(_RemoveV2Base):
    """身份判定与结构异常：任何异常结构都不能崩溃，且不能放行删除。"""

    def test_account_null_does_not_crash(self):
        self.prof("alpha", "uid-a")
        self.prof("keep", "uid-k")
        self.raw_auth('{"account": null}')

        ok, out = self.run_remove("alpha", assume_yes=True)

        self.assertFalse(ok, out)
        self.assertIn("读不到账号 UID", out)
        self.assertTrue(self.exists("alpha"))

    def test_account_list_does_not_crash(self):
        self.prof("alpha", "uid-a")
        self.prof("keep", "uid-k")
        self.raw_auth('{"account": [1, 2, 3]}')

        ok, out = self.run_remove("alpha", assume_yes=True)

        self.assertFalse(ok, out)
        self.assertTrue(self.exists("alpha"))

    def test_account_string_does_not_crash(self):
        self.prof("alpha", "uid-a")
        self.prof("keep", "uid-k")
        self.raw_auth('{"account": "whoami"}')

        ok, _ = self.run_remove("alpha", assume_yes=True)
        self.assertFalse(ok)
        self.assertTrue(self.exists("alpha"))

    def test_top_level_list_does_not_crash(self):
        self.prof("alpha", "uid-a")
        self.prof("keep", "uid-k")
        self.raw_auth('[1, 2, 3]')

        ok, _ = self.run_remove("alpha", assume_yes=True)
        self.assertFalse(ok)
        self.assertTrue(self.exists("alpha"))

    def test_profile_without_uid_refused_by_default(self):
        """审计报告声称的不变量：无法证明目标不是活跃账号，就不删。

        早期实现这里只是打印警告然后照删，与报告的表述不一致。
        """
        self.prof("broken")           # 无 uid
        self.prof("keep", "uid-k")
        self.active("uid-k")

        ok, out = self.run_remove("broken", assume_yes=True)

        self.assertFalse(ok, out)
        self.assertIn("读不出 UID", out)
        self.assertTrue(self.exists("broken"))

    def test_profile_without_uid_deleted_with_force(self):
        self.prof("broken")
        self.prof("keep", "uid-k")
        self.active("uid-k")

        ok, out = self.run_remove("broken", assume_yes=True, force=True)
        self.assertTrue(ok, out)
        self.assertFalse(self.exists("broken"))

    def test_safe_uid_handles_weird_shapes(self):
        for data in (None, [], "str", 42, {"account": None}, {"account": []}, {}):
            self.assertEqual(workbuddy._safe_uid(data), "", "异常结构应返回空串: %r" % (data,))
        self.assertEqual(workbuddy._safe_uid({"account": {"uid": " UID-X "}}), "uid-x")
        self.assertEqual(workbuddy._safe_uid({"account": {"userId": "U-2"}}), "u-2")


class TestRemoveLock(_RemoveV2Base):
    """锁语义：拿不到锁必须失败，接管过期锁要确认持有者已退出。"""

    def _hold_lock(self, pid, token="holder", age_seconds=0):
        lock = os.path.join(workbuddy.PROFILES_DIR, ".remove.lock")
        with open(lock, "w", encoding="utf-8") as f:
            json.dump({"pid": pid, "token": token, "startedAt": 0}, f)
        if age_seconds:
            old = time.time() - age_seconds
            os.utime(lock, (old, old))
        return lock

    def test_lock_held_by_live_process_blocks_deletion(self):
        self.prof("alpha", "uid-a")
        self.prof("keep", "uid-k")
        self.active("uid-k")
        self._hold_lock(os.getpid())          # 自己这个进程必然存活

        real = workbuddy._acquire_profiles_lock
        with patch.object(workbuddy, "_acquire_profiles_lock",
                          side_effect=lambda *a, **k: real(timeout=0.3)):
            ok, out = self.run_remove("alpha", assume_yes=True)

        self.assertFalse(ok, out)
        self.assertIn("另一个删除进程正在运行", out)
        self.assertTrue(self.exists("alpha"), "锁不可用时绝不能删除")

    def test_stale_lock_with_dead_pid_is_taken_over(self):
        self.prof("alpha", "uid-a")
        self.prof("keep", "uid-k")
        self.active("uid-k")
        self._hold_lock(999999, token="dead-process", age_seconds=3600)

        real = workbuddy._acquire_profiles_lock
        with patch.object(workbuddy, "_acquire_profiles_lock",
                          side_effect=lambda *a, **k: real(timeout=1.0)):
            ok, out = self.run_remove("alpha", assume_yes=True)

        self.assertTrue(ok, out)
        self.assertFalse(self.exists("alpha"))

    def test_fresh_lock_of_live_process_is_not_stolen_even_if_old(self):
        """年龄很大但持有进程还活着 → 不能接管（防止误踢运行慢的进程）。"""
        lock = self._hold_lock(os.getpid(), token="slow-but-alive", age_seconds=3600)
        token, err = workbuddy._acquire_profiles_lock(timeout=0.3)
        self.assertIsNone(token)
        self.assertIn("正在运行", err)
        self.assertTrue(os.path.exists(lock))

    def test_release_does_not_remove_other_owners_lock(self):
        lock = os.path.join(workbuddy.PROFILES_DIR, ".remove.lock")
        token, err = workbuddy._acquire_profiles_lock(timeout=0.2)
        self.assertIsNone(err)
        with open(lock, "w", encoding="utf-8") as f:
            json.dump({"pid": os.getpid(), "token": "someone-else"}, f)

        workbuddy._release_profiles_lock(token)

        self.assertTrue(os.path.exists(lock), "锁已被他人接管时不能替他人释放")


class TestRemoveTombstone(_RemoveV2Base):
    """删除墓碑：删掉的账号不能被 wb-checkin 的自动发现重新加回来。"""

    def test_delete_writes_tombstone(self):
        self.prof("live", "uid-live")
        self.prof("keep", "uid-k")
        self.active("uid-live")

        ok, out = self.run_remove("live", assume_yes=True, force=True)

        self.assertTrue(ok, out)
        self.assertTrue(workbuddy.is_tombstoned("uid-live"))
        self.assertIn("删除标记", out)

    def test_purge_also_writes_tombstone(self):
        self.prof("live", "uid-live")
        self.prof("keep", "uid-k")
        self.active("uid-live")

        ok, _ = self.run_remove("live", assume_yes=True, force=True, purge=True)
        self.assertTrue(ok)
        self.assertTrue(workbuddy.is_tombstoned("uid-live"), "purge 之后同样不能被自动加回")

    def test_auto_import_skips_tombstoned_uid(self):
        """评审实测：删掉活跃账号后跑 checkin，会被自动建回来。这条用例锁住修复。"""
        self.active("uid-gone", "已删除的号")
        workbuddy.add_tombstone("uid-gone", "gone")

        with redirect_stdout(io.StringIO()) as buf:
            created = workbuddy.auto_import_active_profile()

        self.assertIsNone(created, "带墓碑的账号不应被自动入库")
        self.assertEqual(self.leftovers(), [])
        self.assertIn("跳过自动入库", buf.getvalue())

    def test_auto_import_still_works_without_tombstone(self):
        self.active("uid-new", "新号")

        with redirect_stdout(io.StringIO()):
            created = workbuddy.auto_import_active_profile()

        self.assertIsNotNone(created)
        self.assertEqual(self.leftovers(), [created])

    def test_auto_import_skips_already_saved(self):
        self.prof("saved", "uid-new")
        self.active("uid-new")

        with redirect_stdout(io.StringIO()):
            created = workbuddy.auto_import_active_profile()
        self.assertIsNone(created)
        self.assertEqual(self.leftovers(), ["saved"])

    def test_save_current_clears_tombstone(self):
        self.active("uid-live", "live")
        workbuddy.add_tombstone("uid-live", "live")

        with redirect_stdout(io.StringIO()):
            workbuddy.save_current("live")

        self.assertFalse(workbuddy.is_tombstoned("uid-live"),
                         "用户显式 save 后应解除墓碑")

    def test_restore_clears_tombstone(self):
        self.prof("live", "uid-live")
        self.prof("keep", "uid-k")
        self.active("uid-live")
        self.run_remove("live", assume_yes=True, force=True)
        self.assertTrue(workbuddy.is_tombstoned("uid-live"))

        name = [f for f in self.trash_files() if f.startswith("live.")][0]
        ok, out = self.call(["--restore", name])

        self.assertTrue(ok, out)
        self.assertFalse(workbuddy.is_tombstoned("uid-live"))


class TestRemoveTrashCommands(_RemoveV2Base):
    """回收站列表与恢复：否则用户面对一堆带时间戳的文件无法把账号还原回来。"""

    def test_list_trash_when_empty(self):
        ok, out = self.call(["--list-trash"])
        self.assertTrue(ok)
        self.assertIn("回收站为空", out)

    def test_list_trash_shows_entries(self):
        self.prof("trashme", "uid-t", "回收站里的号")
        self.prof("keep", "uid-k")
        self.active("uid-k")
        self.run_remove("trashme", assume_yes=True)

        ok, out = self.call(["--list-trash"])

        self.assertTrue(ok, out)
        self.assertIn("回收站里的号", out)
        self.assertIn("trashme.", out)

    def test_restore_roundtrip(self):
        self.prof("trashme", "uid-t")
        self.prof("keep", "uid-k")
        self.active("uid-k")
        self.run_remove("trashme", assume_yes=True)
        name = self.trash_files()[0]

        ok, out = self.call(["--restore", name])

        self.assertTrue(ok, out)
        self.assertEqual(self.leftovers(), ["keep", "trashme"])
        self.assertEqual(self.trash_files(), [])

    def test_restore_rejects_path_traversal(self):
        self.prof("keep", "uid-k")
        ok, out = self.call(["--restore", "../../etc/passwd"])
        self.assertFalse(ok, out)
        self.assertIn("只接受回收站内的", out)

    def test_restore_refuses_when_alias_exists(self):
        self.prof("dup", "uid-d")
        self.prof("keep", "uid-k")
        self.active("uid-k")
        self.run_remove("dup", assume_yes=True)
        self.prof("dup", "uid-d2")          # 同名账号又被创建出来

        name = [f for f in self.trash_files() if f.startswith("dup.")][0]
        ok, out = self.call(["--restore", name])

        self.assertFalse(ok, out)
        self.assertIn("目标账号已存在", out)


if __name__ == "__main__":
    unittest.main(verbosity=2)
