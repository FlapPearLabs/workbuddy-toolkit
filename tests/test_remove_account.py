#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
"删账号不会把本地搞坏"的回归测试。

覆盖的真实故障:
- 删掉正在使用的账号：本地没有凭证备份，想再用只能重新扫码；
- 直接物理删除不可恢复，手滑一次就得重新登录；
- 回收站里的文件又被 get_profiles() 扫成"账号"，删了等于没删；
- 删账号顺手动了本地库里别的账号的会话/自动化归属。
"""

import io
import os
import sys
import json
import shutil
import sqlite3
import subprocess
import tempfile
import time
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

import importlib.util
import importlib.machinery

REPO_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_loader = importlib.machinery.SourceFileLoader("workbuddy_rm", os.path.join(REPO_DIR, "bin", "workbuddy"))
_spec = importlib.util.spec_from_loader("workbuddy_rm", _loader)
workbuddy = importlib.util.module_from_spec(_spec)
_loader.exec_module(workbuddy)


class _SandboxMixin:
    def _setup_sandbox(self):
        self.tmp = tempfile.mkdtemp()
        self._orig = (workbuddy.AUTH_FILE, workbuddy.PROFILES_DIR, workbuddy.DB_FILE, workbuddy.AUDIT_CACHE_FILE)
        workbuddy.AUTH_FILE = os.path.join(self.tmp, "auth", "workbuddy-desktop.info")
        workbuddy.PROFILES_DIR = os.path.join(self.tmp, "auth_profiles")
        workbuddy.DB_FILE = os.path.join(self.tmp, "workbuddy.db")
        workbuddy.AUDIT_CACHE_FILE = os.path.join(self.tmp, "cache", "audit_cache.json")
        os.makedirs(os.path.dirname(workbuddy.AUTH_FILE))
        os.makedirs(workbuddy.PROFILES_DIR)
        con = sqlite3.connect(workbuddy.DB_FILE)
        con.execute("CREATE TABLE sessions (id TEXT PRIMARY KEY, cwd TEXT NOT NULL, user_id TEXT NOT NULL, title TEXT)")
        con.execute("CREATE TABLE automations (id TEXT PRIMARY KEY, name TEXT NOT NULL, owner_user_id TEXT, deleted_at INTEGER)")
        con.commit()
        con.close()

    def _teardown_sandbox(self):
        (workbuddy.AUTH_FILE, workbuddy.PROFILES_DIR, workbuddy.DB_FILE, workbuddy.AUDIT_CACHE_FILE) = self._orig
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _db(self):
        return sqlite3.connect(workbuddy.DB_FILE)

    def _save_profile(self, alias, uid, nickname=None, token=None):
        data = {
            "account": {"uid": uid, "nickname": nickname or alias},
            "auth": {"accessToken": token or f"tok_{alias}"},
        }
        path = os.path.join(workbuddy.PROFILES_DIR, f"{alias}.info")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f)
        return data

    def _set_active(self, uid, nickname="active"):
        data = {"account": {"uid": uid, "nickname": nickname}, "auth": {"accessToken": f"tok_active_{uid}"}}
        os.makedirs(os.path.dirname(workbuddy.AUTH_FILE), exist_ok=True)
        with open(workbuddy.AUTH_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f)
        return data

    def _profile_exists(self, alias):
        return os.path.exists(os.path.join(workbuddy.PROFILES_DIR, f"{alias}.info"))

    def _trash_files(self):
        d = os.path.join(workbuddy.PROFILES_DIR, ".trash")
        if not os.path.isdir(d):
            return []
        # 回收站里还有 removed 标记文件（deleted.json），只数账号备份
        return sorted(f for f in os.listdir(d) if f.endswith(".info"))

    def _run(self, func, *args, **kwargs):
        buf = io.StringIO()
        with redirect_stdout(buf):
            result = func(*args, **kwargs)
        return result, buf.getvalue()


class TestRemoveAccount(_SandboxMixin, unittest.TestCase):
    def setUp(self):
        self._setup_sandbox()

    def tearDown(self):
        self._teardown_sandbox()

    # ---------- 正常删除 ----------

    def test_remove_moves_to_trash(self):
        self._save_profile("alice", "uid_alice")
        self._save_profile("bob", "uid_bob")
        self._set_active("uid_bob")

        ok, out = self._run(workbuddy.remove_profile, "alice", yes=True)

        self.assertTrue(ok)
        self.assertFalse(self._profile_exists("alice"), "原文件应已移走")
        self.assertEqual(len(self._trash_files()), 1, "应有一个文件进回收站")
        self.assertTrue(self._trash_files()[0].endswith(".info"))
        self.assertTrue(self._profile_exists("bob"), "别的账号不能被连带删掉")
        self.assertIn("回收站", out)

    def test_trash_entries_not_rescanned_as_profiles(self):
        """回收站里的文件不能被 get_profiles() 重新扫出来 —— 否则删了等于没删。"""
        self._save_profile("alice", "uid_alice")
        self._save_profile("bob", "uid_bob")
        self._set_active("uid_bob")

        workbuddy.remove_profile("alice", yes=True)

        self.assertEqual(sorted(workbuddy.get_profiles().keys()), ["bob"])

    def test_remove_by_nickname(self):
        self._save_profile("a1", "uid_alice", nickname="老王")
        self._save_profile("bob", "uid_bob")
        self._set_active("uid_bob")

        ok, _ = self._run(workbuddy.remove_profile, "老王", yes=True)

        self.assertTrue(ok)
        self.assertFalse(self._profile_exists("a1"))

    def test_remove_unknown_target_changes_nothing(self):
        self._save_profile("alice", "uid_alice")
        self._set_active("uid_alice")

        ok, out = self._run(workbuddy.remove_profile, "ghost", yes=True)

        self.assertFalse(ok)
        self.assertTrue(self._profile_exists("alice"))
        self.assertEqual(self._trash_files(), [])
        self.assertIn("没有唯一匹配", out)

    # ---------- 活跃账号保护 ----------

    def test_active_account_blocked_when_not_interactive(self):
        self._save_profile("alice", "uid_alice")
        self._save_profile("bob", "uid_bob")
        self._set_active("uid_alice")

        with patch.object(sys.stdin, "isatty", return_value=False):
            ok, out = self._run(workbuddy.remove_profile, "alice")

        self.assertFalse(ok, "非交互环境不许删当前账号")
        self.assertTrue(self._profile_exists("alice"))
        self.assertIn("非交互", out)

    def test_active_account_refused_when_only_yes(self):
        """脚本加 -y 不等于"同意删当前账号"，必须再显式 --force-active。"""
        self._save_profile("alice", "uid_alice")
        self._save_profile("bob", "uid_bob")
        self._set_active("uid_alice")

        with patch.object(sys.stdin, "isatty", return_value=False):
            ok, out = self._run(workbuddy.remove_profile, "alice", yes=True)

        self.assertFalse(ok)
        self.assertTrue(self._profile_exists("alice"))
        self.assertIn("已拒绝", out)

    def test_active_account_detected_via_legacy_userid_field(self):
        """老数据把 UID 写在 account.userId 里，也必须认出它是当前账号。"""
        legacy = {"account": {"userId": "uid_legacy", "nickname": "老数据"}, "auth": {"accessToken": "t"}}
        with open(os.path.join(workbuddy.PROFILES_DIR, "legacy.info"), "w", encoding="utf-8") as f:
            json.dump(legacy, f)
        os.makedirs(os.path.dirname(workbuddy.AUTH_FILE), exist_ok=True)
        with open(workbuddy.AUTH_FILE, "w", encoding="utf-8") as f:
            json.dump(legacy, f)

        with patch.object(sys.stdin, "isatty", return_value=False):
            ok, out = self._run(workbuddy.remove_profile, "legacy", yes=True)

        self.assertFalse(ok, "userId 形态的当前账号也不能被 -y 静默删掉")
        self.assertTrue(self._profile_exists("legacy"))

    def test_active_account_detected_via_shared_uin(self):
        """一边只有 uin、一边有 uid + uin 时，靠共有的 uin 也要认出是同一个账号。"""
        self._save_profile("alice", "uid_alice", nickname="小A")
        # profile 里补上 uin
        path = os.path.join(workbuddy.PROFILES_DIR, "alice.info")
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        data["account"]["uin"] = "998877"
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f)
        # 登录态只有 uin
        os.makedirs(os.path.dirname(workbuddy.AUTH_FILE), exist_ok=True)
        with open(workbuddy.AUTH_FILE, "w", encoding="utf-8") as f:
            json.dump({"account": {"uin": "998877", "nickname": "小A"}, "auth": {"accessToken": "t"}}, f)

        with patch.object(sys.stdin, "isatty", return_value=False):
            ok, _ = self._run(workbuddy.remove_profile, "alice", yes=True)

        self.assertFalse(ok)
        self.assertTrue(self._profile_exists("alice"))

    def test_survives_missing_stdin(self):
        """stdin 为 None（无控制台句柄）时不能抛 traceback，按非交互拒绝处理。"""
        self._save_profile("alice", "uid_alice")
        self._save_profile("bob", "uid_bob")
        self._set_active("uid_alice")

        with patch.object(sys, "stdin", None):
            ok, _ = self._run(workbuddy.remove_profile, "alice")

        self.assertFalse(ok)
        self.assertTrue(self._profile_exists("alice"))

    # ---------- 同一账号多个别名 ----------

    def test_uid_query_refused_when_multiple_aliases(self):
        """按 UID 删但该 UID 有两个别名时，只删一个等于没删 —— 必须拒绝并让人按别名删。"""
        self._save_profile("dup1", "uid_dup")
        self._save_profile("dup2", "uid_dup")
        self._save_profile("other", "uid_other")
        self._set_active("uid_other")

        ok, out = self._run(workbuddy.remove_profile, "uid_dup", yes=True)

        self.assertFalse(ok)
        self.assertTrue(self._profile_exists("dup1"))
        self.assertTrue(self._profile_exists("dup2"))
        self.assertIn("别名", out)

    def test_alias_delete_warns_about_twin_alias(self):
        self._save_profile("dup1", "uid_dup")
        self._save_profile("dup2", "uid_dup")
        self._set_active("uid_other")

        ok, out = self._run(workbuddy.remove_profile, "dup1", yes=True)

        self.assertTrue(ok)
        self.assertFalse(self._profile_exists("dup1"))
        self.assertTrue(self._profile_exists("dup2"))
        self.assertIn("别的别名", out)

    def test_active_account_needs_force_active_with_yes(self):
        self._save_profile("alice", "uid_alice")
        self._save_profile("bob", "uid_bob")
        self._set_active("uid_alice")

        ok, _ = self._run(workbuddy.remove_profile, "alice", yes=True, force_active=True)

        self.assertTrue(ok)
        self.assertFalse(self._profile_exists("alice"))

    def test_active_account_declined_interactively(self):
        self._save_profile("alice", "uid_alice")
        self._set_active("uid_alice")

        with patch.object(sys.stdin, "isatty", return_value=True), \
                patch("builtins.input", return_value="n"):
            ok, out = self._run(workbuddy.remove_profile, "alice")

        self.assertFalse(ok)
        self.assertTrue(self._profile_exists("alice"))
        self.assertIn("已取消", out)

    def test_active_account_confirmed_interactively(self):
        self._save_profile("alice", "uid_alice")
        self._save_profile("bob", "uid_bob")
        self._set_active("uid_alice")

        with patch.object(sys.stdin, "isatty", return_value=True), \
                patch("builtins.input", return_value="yes"):
            ok, _ = self._run(workbuddy.remove_profile, "alice")

        self.assertTrue(ok)
        self.assertFalse(self._profile_exists("alice"))
        self.assertEqual(len(self._trash_files()), 1)

    def test_normal_account_declined_interactively(self):
        self._save_profile("alice", "uid_alice")
        self._save_profile("bob", "uid_bob")
        self._set_active("uid_bob")

        with patch.object(sys.stdin, "isatty", return_value=True), \
                patch("builtins.input", return_value="n"):
            ok, out = self._run(workbuddy.remove_profile, "alice")

        self.assertFalse(ok)
        self.assertTrue(self._profile_exists("alice"))
        self.assertIn("已取消", out)

    # ---------- 永久删除 / 预览 ----------

    def test_purge_deletes_without_trash(self):
        self._save_profile("alice", "uid_alice")
        self._save_profile("bob", "uid_bob")
        self._set_active("uid_bob")

        ok, out = self._run(workbuddy.remove_profile, "alice", yes=True, purge=True)

        self.assertTrue(ok)
        self.assertFalse(self._profile_exists("alice"))
        self.assertEqual(self._trash_files(), [], "purge 不应留回收站文件")
        self.assertIn("永久删除", out)

    def test_dry_run_touches_nothing(self):
        self._save_profile("alice", "uid_alice")
        self._save_profile("bob", "uid_bob")
        self._set_active("uid_alice")

        ok, out = self._run(workbuddy.remove_profile, "alice", dry_run=True)

        self.assertTrue(ok)
        self.assertTrue(self._profile_exists("alice"))
        self.assertEqual(self._trash_files(), [])
        self.assertIn("dry-run", out)

    # ---------- 回收站 / 恢复 ----------

    def test_restore_roundtrip_keeps_content(self):
        original = self._save_profile("alice", "uid_alice")
        self._save_profile("bob", "uid_bob")
        self._set_active("uid_bob")

        workbuddy.remove_profile("alice", yes=True)
        ok, _ = self._run(workbuddy.restore_profile, "alice")

        self.assertTrue(ok)
        self.assertTrue(self._profile_exists("alice"))
        self.assertEqual(self._trash_files(), [])
        with open(os.path.join(workbuddy.PROFILES_DIR, "alice.info"), "r", encoding="utf-8") as f:
            self.assertEqual(json.load(f), original, "恢复后内容要一模一样")

    def test_restore_refuses_to_overwrite_existing(self):
        self._save_profile("alice", "uid_alice")
        self._save_profile("bob", "uid_bob")
        self._set_active("uid_bob")

        workbuddy.remove_profile("alice", yes=True)
        self._save_profile("alice", "uid_other", nickname="新人")

        ok, out = self._run(workbuddy.restore_profile, "alice")

        self.assertFalse(ok, "同名账号已存在时不许覆盖")
        with open(os.path.join(workbuddy.PROFILES_DIR, "alice.info"), "r", encoding="utf-8") as f:
            self.assertEqual(json.load(f)["account"]["uid"], "uid_other")
        self.assertEqual(len(self._trash_files()), 1, "回收站里的备份要留着")
        self.assertIn("已经存在", out)

    def test_restore_unknown_alias(self):
        ok, out = self._run(workbuddy.restore_profile, "nobody")
        self.assertFalse(ok)
        self.assertIn("找不到", out)

    def test_empty_trash(self):
        self._save_profile("alice", "uid_alice")
        self._save_profile("bob", "uid_bob")
        self._set_active("uid_bob")
        workbuddy.remove_profile("alice", yes=True)

        ok, _ = self._run(workbuddy.empty_trash, yes=True)

        self.assertTrue(ok)
        self.assertEqual(self._trash_files(), [])

    def test_empty_trash_declined(self):
        self._save_profile("alice", "uid_alice")
        self._save_profile("bob", "uid_bob")
        self._set_active("uid_bob")
        workbuddy.remove_profile("alice", yes=True)

        with patch.object(sys.stdin, "isatty", return_value=True), \
                patch("builtins.input", return_value="n"):
            ok, _ = self._run(workbuddy.empty_trash)

        self.assertFalse(ok)
        self.assertEqual(len(self._trash_files()), 1)

    # ---------- 不碰别人的历史 ----------

    def test_audit_cache_entry_cleared_only_for_target(self):
        self._save_profile("alice", "uid_alice")
        self._save_profile("bob", "uid_bob")
        self._set_active("uid_bob")
        os.makedirs(os.path.dirname(workbuddy.AUDIT_CACHE_FILE), exist_ok=True)
        with open(workbuddy.AUDIT_CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump({"uid_alice": {"status": "HEALTHY"}, "uid_bob": {"status": "HEALTHY"}}, f)

        workbuddy.remove_profile("alice", yes=True)

        with open(workbuddy.AUDIT_CACHE_FILE, "r", encoding="utf-8") as f:
            cache = json.load(f)
        self.assertNotIn("uid_alice", cache)
        self.assertIn("uid_bob", cache, "别的账号的缓存不许动")

    def test_ownership_tables_untouched(self):
        self._save_profile("alice", "uid_alice")
        self._save_profile("bob", "uid_bob")
        self._set_active("uid_bob")
        con = self._db()
        con.execute(f"CREATE TABLE {workbuddy.SESSION_OWNER_BACKUP_TABLE} "
                    f"(session_id TEXT PRIMARY KEY, user_id TEXT NOT NULL, saved_at INTEGER NOT NULL)")
        con.execute(f"INSERT INTO {workbuddy.SESSION_OWNER_BACKUP_TABLE} VALUES ('s1', 'uid_alice', 1)")
        con.execute(f"CREATE TABLE {workbuddy.AUTOMATION_OWNER_BACKUP_TABLE} "
                    f"(automation_id TEXT PRIMARY KEY, owner_user_id TEXT, saved_at INTEGER NOT NULL)")
        con.execute(f"INSERT INTO {workbuddy.AUTOMATION_OWNER_BACKUP_TABLE} VALUES ('a1', 'uid_alice', 1)")
        con.execute("INSERT INTO sessions VALUES ('s1', '/tmp', 'uid_bob', 't')")
        con.commit()
        con.close()

        ok, out = self._run(workbuddy.remove_profile, "alice", yes=True)

        self.assertTrue(ok)
        con = self._db()
        self.assertEqual(con.execute(f"SELECT COUNT(*) FROM {workbuddy.SESSION_OWNER_BACKUP_TABLE}").fetchone()[0], 1)
        self.assertEqual(con.execute(f"SELECT COUNT(*) FROM {workbuddy.AUTOMATION_OWNER_BACKUP_TABLE}").fetchone()[0], 1)
        self.assertEqual(con.execute("SELECT user_id FROM sessions WHERE id='s1'").fetchone()[0], "uid_bob")
        con.close()
        self.assertIn("归属", out)

    def test_ownership_count_reads_rows(self):
        con = self._db()
        con.execute(f"CREATE TABLE {workbuddy.SESSION_OWNER_BACKUP_TABLE} "
                    f"(session_id TEXT PRIMARY KEY, user_id TEXT NOT NULL, saved_at INTEGER NOT NULL)")
        con.execute(f"INSERT INTO {workbuddy.SESSION_OWNER_BACKUP_TABLE} VALUES ('s1', 'uid_alice', 1)")
        con.execute(f"INSERT INTO {workbuddy.SESSION_OWNER_BACKUP_TABLE} VALUES ('s2', 'uid_bob', 1)")
        con.execute(f"CREATE TABLE {workbuddy.AUTOMATION_OWNER_BACKUP_TABLE} "
                    f"(automation_id TEXT PRIMARY KEY, owner_user_id TEXT, saved_at INTEGER NOT NULL)")
        con.execute(f"INSERT INTO {workbuddy.AUTOMATION_OWNER_BACKUP_TABLE} VALUES ('a1', 'uid_alice', 1)")
        con.commit()
        con.close()

        counts = workbuddy._count_ownership_rows("uid_alice")

        self.assertEqual(counts[workbuddy.SESSION_OWNER_BACKUP_TABLE], 1)
        self.assertEqual(counts[workbuddy.AUTOMATION_OWNER_BACKUP_TABLE], 1)

    def test_ownership_count_with_space_in_path(self):
        """库路径里有空格 / 中文时，只读 URI 也要能连上，否则统计会静默变成"没有记录"。"""
        spaced_dir = os.path.join(self.tmp, "带 空格 的目录")
        os.makedirs(spaced_dir, exist_ok=True)
        spaced_db = os.path.join(spaced_dir, "workbuddy.db")
        con = sqlite3.connect(spaced_db)
        con.execute(f"CREATE TABLE {workbuddy.SESSION_OWNER_BACKUP_TABLE} "
                    f"(session_id TEXT PRIMARY KEY, user_id TEXT NOT NULL, saved_at INTEGER NOT NULL)")
        con.execute(f"INSERT INTO {workbuddy.SESSION_OWNER_BACKUP_TABLE} VALUES ('s1', 'uid_alice', 1)")
        con.commit()
        con.close()

        original_db = workbuddy.DB_FILE
        workbuddy.DB_FILE = spaced_db
        try:
            counts = workbuddy._count_ownership_rows("uid_alice")
        finally:
            workbuddy.DB_FILE = original_db

        self.assertEqual(counts[workbuddy.SESSION_OWNER_BACKUP_TABLE], 1)

    def test_ownership_count_without_db(self):
        workbuddy.DB_FILE = os.path.join(self.tmp, "no-such.db")
        self.assertEqual(workbuddy._count_ownership_rows("uid_alice"), {})

    def test_no_token_leaked_to_output(self):
        self._save_profile("alice", "uid_alice", token="super-secret-token")
        self._save_profile("bob", "uid_bob")
        self._set_active("uid_bob")

        ok, out = self._run(workbuddy.remove_profile, "alice", yes=True)

        self.assertTrue(ok, "删的是非活跃账号，应当成功")
        self.assertNotIn("super-secret-token", out)

    def test_active_auth_file_untouched(self):
        self._save_profile("alice", "uid_alice")
        self._save_profile("bob", "uid_bob")
        active = self._set_active("uid_alice")
        with open(workbuddy.AUTH_FILE, "r", encoding="utf-8") as f:
            before = json.load(f)

        workbuddy.remove_profile("alice", yes=True, force_active=True)

        with open(workbuddy.AUTH_FILE, "r", encoding="utf-8") as f:
            self.assertEqual(json.load(f), before, "客户端的登录态不该被删号动作改写")
        self.assertEqual(before, active)


class TestRemoveCommandCli(_SandboxMixin, unittest.TestCase):
    def setUp(self):
        self._setup_sandbox()

    def tearDown(self):
        self._teardown_sandbox()

    def test_list_trash_exit_zero(self):
        code, out = self._run(workbuddy.run_remove_cmd, ["--list-trash"])
        self.assertEqual(code, 0)
        self.assertIn("回收站", out)

    def test_no_target_exit_one(self):
        code, out = self._run(workbuddy.run_remove_cmd, [])
        self.assertEqual(code, 1)
        self.assertIn("请指定", out)

    def test_unknown_option_rejected(self):
        code, out = self._run(workbuddy.run_remove_cmd, ["alice", "--purgee"])
        self.assertEqual(code, 1)
        self.assertIn("未知选项", out)

    def test_two_targets_rejected(self):
        code, out = self._run(workbuddy.run_remove_cmd, ["alice", "bob"])
        self.assertEqual(code, 1)
        self.assertIn("一次只能删一个", out)

    def test_dry_run_via_cli(self):
        self._save_profile("alice", "uid_alice")
        self._save_profile("bob", "uid_bob")
        self._set_active("uid_bob")

        code, out = self._run(workbuddy.run_remove_cmd, ["alice", "--dry-run"])

        self.assertEqual(code, 0)
        self.assertTrue(self._profile_exists("alice"))
        self.assertIn("dry-run", out)

    def test_yes_via_cli_removes(self):
        self._save_profile("alice", "uid_alice")
        self._save_profile("bob", "uid_bob")
        self._set_active("uid_bob")

        code, _ = self._run(workbuddy.run_remove_cmd, ["alice", "-y"])

        self.assertEqual(code, 0)
        self.assertFalse(self._profile_exists("alice"))

    def test_restore_via_cli(self):
        self._save_profile("alice", "uid_alice")
        self._save_profile("bob", "uid_bob")
        self._set_active("uid_bob")
        workbuddy.run_remove_cmd(["alice", "-y"])

        code, _ = self._run(workbuddy.run_remove_cmd, ["--restore", "alice"])

        self.assertEqual(code, 0)
        self.assertTrue(self._profile_exists("alice"))


    def test_purge_missing_file_is_not_reported_as_deleted(self):
        """真走到 purge 的 FileNotFoundError 分支（解析完到删除之间文件被外部删掉）。"""
        self._save_profile("alice", "uid_alice")
        self._save_profile("bob", "uid_bob")
        self._set_active("uid_bob")

        with patch.object(workbuddy.os, "remove", side_effect=FileNotFoundError("gone")):
            ok, out = self._run(workbuddy.remove_profile, "alice", yes=True, purge=True)

        self.assertFalse(ok, "文件本来就不在，不该报成功")
        self.assertIn("没有可删的凭证", out)

    def test_profile_with_null_account_still_listed(self):
        """account 字段是 null 的历史文件不能被整份跳过（否则列表里凭空少一个账号）。"""
        with open(os.path.join(workbuddy.PROFILES_DIR, "nullacc.info"), "w", encoding="utf-8") as f:
            json.dump({"account": None, "auth": {"accessToken": "T-null"}}, f)
        self._save_profile("bob", "uid_bob")
        self._set_active("uid_bob")

        self.assertIn("nullacc", workbuddy.get_profiles())
        ok, _ = self._run(workbuddy.remove_profile, "nullacc", yes=True, force_active=True)  # 读不出 ID，按"拿不准"需显式强制
        self.assertTrue(ok)
        self.assertFalse(self._profile_exists("nullacc"))

    def test_nickname_uid_collision_refused(self):
        """昵称恰好等于另一个账号的 UID 时，不能按"昵称优先"删错对象。"""
        self._save_profile("nick_acc", "uid_nick", nickname="123456789")
        self._save_profile("uid_acc", "123456789", nickname="真主人")
        self._save_profile("keep", "uid_keep")
        self._set_active("uid_keep")

        ok, out = self._run(workbuddy.remove_profile, "123456789", yes=True)

        self.assertFalse(ok)
        self.assertTrue(self._profile_exists("nick_acc"))
        self.assertTrue(self._profile_exists("uid_acc"))
        self.assertIn("同时是", out)

    def test_remove_by_full_uin(self):
        """只有 uin 的老账号文件，按完整 uin 也要能定位并删掉。"""
        with open(os.path.join(workbuddy.PROFILES_DIR, "uinonly.info"), "w", encoding="utf-8") as f:
            json.dump({"account": {"uin": "998877", "nickname": "老张"},
                       "auth": {"accessToken": "T-uin"}}, f)
        self._save_profile("bob", "uid_bob")
        self._set_active("uid_bob")

        ok, _ = self._run(workbuddy.remove_profile, "998877", yes=True, force_active=True)  # 只有 uin，和登录态无法比 → 拿不准

        self.assertTrue(ok)
        self.assertFalse(self._profile_exists("uinonly"))

    def test_restore_picks_latest_deletion(self):
        """同别名删两次，恢复要拿到后删的那份（不能按文件 mtime 排）。"""
        self._save_profile("tw", "uid_v1")
        self._save_profile("bob", "uid_bob")
        self._set_active("uid_bob")
        workbuddy.remove_profile("tw", yes=True)

        # 把第一份备份的 mtime 推后，模拟"账号最后被写的时间很晚"——按 mtime 排就会挑错
        trash = os.path.join(workbuddy.PROFILES_DIR, ".trash")
        first = [f for f in os.listdir(trash) if f.endswith(".info")][0]
        future = time.time() + 3600
        os.utime(os.path.join(trash, first), (future, future))

        self._save_profile("tw", "uid_v2")
        workbuddy.remove_profile("tw", yes=True)
        workbuddy.restore_profile("tw")

        with open(os.path.join(workbuddy.PROFILES_DIR, "tw.info"), "r", encoding="utf-8") as f:
            self.assertEqual(json.load(f)["account"]["uid"], "uid_v2", "应恢复最近删除的那份")

    def test_alias_named_help_can_still_be_removed(self):
        self._save_profile("help", "uid_help")
        self._save_profile("bob", "uid_bob")
        self._set_active("uid_bob")

        code, _ = self._run(workbuddy.run_remove_cmd, ["help", "-y"])

        self.assertEqual(code, 0)
        self.assertFalse(self._profile_exists("help"), "叫 help 的账号也要能删")

    def test_help_keyword_still_works_without_such_alias(self):
        self._save_profile("alice", "uid_alice")

        code, out = self._run(workbuddy.run_remove_cmd, ["help"])

        self.assertEqual(code, 0)
        self.assertIn("用法", out)
        self.assertTrue(self._profile_exists("alice"))

    def test_active_detected_when_fields_named_differently(self):
        """一边写 userId、一边写 uid，是同一个账号，必须认出来。"""
        os.makedirs(os.path.dirname(workbuddy.AUTH_FILE), exist_ok=True)
        with open(os.path.join(workbuddy.PROFILES_DIR, "legacy.info"), "w", encoding="utf-8") as f:
            json.dump({"account": {"userId": "U1", "nickname": "老"}, "auth": {"accessToken": "T1"}}, f)
        with open(workbuddy.AUTH_FILE, "w", encoding="utf-8") as f:
            json.dump({"account": {"uid": "U1", "nickname": "老"}, "auth": {"accessToken": "T2"}}, f)

        with patch.object(sys.stdin, "isatty", return_value=False):
            ok, _ = self._run(workbuddy.remove_profile, "legacy", yes=True)

        self.assertFalse(ok, "profile 用 userId、登录态用 uid 时也必须认出是当前账号")
        self.assertTrue(self._profile_exists("legacy"))

    def test_active_detected_without_any_id_field(self):
        """两边都没有 ID 字段时，靠同一个 accessToken 兜底。"""
        body = {"account": {"nickname": "无ID"}, "auth": {"accessToken": "TOK-SAME"}}
        os.makedirs(os.path.dirname(workbuddy.AUTH_FILE), exist_ok=True)
        with open(os.path.join(workbuddy.PROFILES_DIR, "noid.info"), "w", encoding="utf-8") as f:
            json.dump(body, f)
        with open(workbuddy.AUTH_FILE, "w", encoding="utf-8") as f:
            json.dump(body, f)

        with patch.object(sys.stdin, "isatty", return_value=False):
            ok, _ = self._run(workbuddy.remove_profile, "noid", yes=True)

        self.assertFalse(ok, "同一个 accessToken 说明是同一个登录态")
        self.assertTrue(self._profile_exists("noid"))

    def test_duplicate_aliases_with_mixed_fields(self):
        """同一账号的两个别名分别写 uid / userId 时，按 UID 删也必须判成多别名。"""
        self._save_profile("dup1", "u1")
        with open(os.path.join(workbuddy.PROFILES_DIR, "dup2.info"), "w", encoding="utf-8") as f:
            json.dump({"account": {"userId": "u1", "nickname": "dup2"}, "auth": {"accessToken": "T2"}}, f)
        self._save_profile("other", "u2")
        self._set_active("u2")

        ok, out = self._run(workbuddy.remove_profile, "u1", yes=True)

        self.assertFalse(ok)
        self.assertTrue(self._profile_exists("dup1"))
        self.assertTrue(self._profile_exists("dup2"))
        self.assertIn("别名", out)

    def test_uid_prefix_does_not_delete(self):
        """删号不接受 UID 前缀猜测：打错一半不能变成误删。"""
        self._save_profile("alice", "abcdef123456")
        self._save_profile("bob", "uid_bob")
        self._set_active("uid_bob")

        ok, out = self._run(workbuddy.remove_profile, "abcd", yes=True)

        self.assertFalse(ok)
        self.assertTrue(self._profile_exists("alice"))
        self.assertIn("前缀", out)

    def test_full_uid_deletes(self):
        self._save_profile("alice", "abcdef123456")
        self._save_profile("bob", "uid_bob")
        self._set_active("uid_bob")

        ok, _ = self._run(workbuddy.remove_profile, "abcdef123456", yes=True)

        self.assertTrue(ok)
        self.assertFalse(self._profile_exists("alice"))

    def test_restore_rejects_broken_backup(self):
        trash = os.path.join(workbuddy.PROFILES_DIR, ".trash")
        os.makedirs(trash, exist_ok=True)
        with open(os.path.join(trash, "broken.20260101-000000.info"), "w", encoding="utf-8") as f:
            f.write("{not json")

        ok, out = self._run(workbuddy.restore_profile, "broken")

        self.assertFalse(ok)
        self.assertFalse(self._profile_exists("broken"), "坏备份不能被塞进账号目录")
        self.assertIn("不像是账号凭证", out)

    def test_empty_trash_with_target_rejected(self):
        """--purge 写成 --empty-trash 还带账号名时，不能默默清空整个回收站。"""
        self._save_profile("alice", "uid_alice")
        self._save_profile("bob", "uid_bob")
        self._set_active("uid_bob")
        workbuddy.remove_profile("alice", yes=True)

        code, out = self._run(workbuddy.run_remove_cmd, ["--empty-trash", "bob", "-y"])

        self.assertEqual(code, 1)
        self.assertEqual(len(self._trash_files()), 1, "回收站不该被清空")
        self.assertIn("不接受账号名", out)

    def test_active_detected_when_uid_and_uin_are_the_fields(self):
        """一侧只有 uid、另一侧只有 uin，值相同就该认成同一个账号（删号宁严勿松）。"""
        self._save_profile("alice", "123456")
        os.makedirs(os.path.dirname(workbuddy.AUTH_FILE), exist_ok=True)
        with open(workbuddy.AUTH_FILE, "w", encoding="utf-8") as f:
            json.dump({"account": {"uin": "123456", "nickname": "alice"}, "auth": {"accessToken": "T9"}}, f)

        with patch.object(sys.stdin, "isatty", return_value=False):
            ok, _ = self._run(workbuddy.remove_profile, "alice", yes=True)

        self.assertFalse(ok, "uid 与 uin 值相同时应判为当前账号")
        self.assertTrue(self._profile_exists("alice"))

    def test_uid_lookup_works_on_legacy_userid_profile(self):
        """老账号文件把 UID 写在 account.userId，按这个 UID 也要能删。"""
        with open(os.path.join(workbuddy.PROFILES_DIR, "legacy.info"), "w", encoding="utf-8") as f:
            json.dump({"account": {"userId": "U-LEGACY-1", "nickname": "老数据"},
                       "auth": {"accessToken": "T1"}}, f)
        self._save_profile("bob", "uid_bob")
        self._set_active("uid_bob")

        ok, _ = self._run(workbuddy.remove_profile, "U-LEGACY-1", yes=True)

        self.assertTrue(ok)
        self.assertFalse(self._profile_exists("legacy"))

    def test_uid_is_masked_in_output(self):
        long_uid = "abcdef1234567890"
        self._save_profile("alice", long_uid)
        self._save_profile("bob", "uid_bob")
        self._set_active("uid_bob")

        _, out = self._run(workbuddy.remove_profile, "alice", yes=True)

        self.assertNotIn(long_uid, out, "输出里的 UID 应与 status 一样做掩码")
        self.assertIn(long_uid[:8], out)

    def test_broken_profile_can_be_removed_by_alias(self):
        """坏 JSON 的账号文件列表里看不到，但也得能被删掉，不能变成清不掉的死文件。"""
        broken = os.path.join(workbuddy.PROFILES_DIR, "broken.info")
        with open(broken, "w", encoding="utf-8") as f:
            f.write("{not json")

        ok, out = self._run(workbuddy.remove_profile, "broken", yes=True)

        self.assertTrue(ok)
        self.assertFalse(os.path.exists(broken))
        self.assertEqual(len(self._trash_files()), 1)
        self.assertIn("损坏", out)

    def test_restore_rejects_non_credential_json(self):
        trash = os.path.join(workbuddy.PROFILES_DIR, ".trash")
        os.makedirs(trash, exist_ok=True)
        with open(os.path.join(trash, "junk.20260101-000000.info"), "w", encoding="utf-8") as f:
            json.dump({"hello": "world"}, f)

        ok, out = self._run(workbuddy.restore_profile, "junk")

        self.assertFalse(ok)
        self.assertFalse(self._profile_exists("junk"))
        self.assertIn("不像是账号凭证", out)

    def test_restore_rejects_empty_shell_account(self):
        """`{"account": {}}` 不是账号，不能恢复成一个空壳 profile。"""
        trash = os.path.join(workbuddy.PROFILES_DIR, ".trash")
        os.makedirs(trash, exist_ok=True)
        with open(os.path.join(trash, "fake.20260101-000000.info"), "w", encoding="utf-8") as f:
            json.dump({"account": {}}, f)

        ok, _ = self._run(workbuddy.restore_profile, "fake")

        self.assertFalse(ok)
        self.assertFalse(self._profile_exists("fake"))

    # ---------- 签到不能把删掉的号存回来 ----------

    def test_checkin_does_not_reimport_deleted_active_account(self):
        self._save_profile("alice", "uid_alice")
        self._save_profile("bob", "uid_bob")
        self._set_active("uid_bob")

        ok, _ = self._run(workbuddy.remove_profile, "bob", yes=True, force_active=True)
        self.assertTrue(ok)

        profiles = workbuddy.get_profiles()
        _, out = self._run(workbuddy._auto_import_active_profile, workbuddy.get_active_account(), profiles)

        self.assertEqual(sorted(workbuddy.get_profiles().keys()), ["alice"], "签到不能把刚删掉的号自动存回来")
        self.assertIn("跳过自动收录", out)

    def test_tombstone_survives_client_token_refresh(self):
        """客户端每 2 小时刷 token 会改登录态文件的 mtime，这不等于用户想要这个账号回来。"""
        self._save_profile("alice", "uid_alice")
        self._save_profile("bob", "uid_bob")
        self._set_active("uid_bob")
        workbuddy.remove_profile("bob", yes=True, force_active=True)

        # 模拟客户端刷新 token 回写登录态：内容/时间都变了，但用户没说要这个账号
        future = time.time() + 7200
        os.utime(workbuddy.AUTH_FILE, (future, future))
        workbuddy._auto_import_active_profile(workbuddy.get_active_account(), workbuddy.get_profiles())

        self.assertEqual(sorted(workbuddy.get_profiles().keys()), ["alice"],
                         "token 刷新不能让删掉的账号自己回来")

    def test_relogin_clears_tombstone(self):
        """用户主动 workbuddy login 之后，才允许重新收录。"""
        self._save_profile("alice", "uid_alice")
        self._save_profile("bob", "uid_bob")
        self._set_active("uid_bob")
        workbuddy.remove_profile("bob", yes=True, force_active=True)

        workbuddy._clear_tombstone("uid_bob")   # 等价于 login / save 成功后的动作
        workbuddy._auto_import_active_profile(workbuddy.get_active_account(), workbuddy.get_profiles())

        uids = [p["uid"] for p in workbuddy.get_profiles().values()]
        self.assertIn("uid_bob", uids, "主动重新登录后应恢复正常收录")

    def test_uin_only_active_account_not_reimported(self):
        """只有 uin 的老文件删完也要记墓碑，否则第二天签到把号存回来（第六轮审查的 P1）。"""
        with open(os.path.join(workbuddy.PROFILES_DIR, "old.info"), "w", encoding="utf-8") as f:
            json.dump({"account": {"uin": "111222", "nickname": "老账号"}}, f)
        os.makedirs(os.path.dirname(workbuddy.AUTH_FILE), exist_ok=True)
        with open(workbuddy.AUTH_FILE, "w", encoding="utf-8") as f:
            json.dump({"account": {"uid": "U-real-777", "uin": "111222"}, "auth": {"accessToken": "T-old"}}, f)
        self._save_profile("keep", "uid_keep")

        ok, _ = self._run(workbuddy.remove_profile, "old", yes=True, force_active=True)
        self.assertTrue(ok)

        workbuddy._auto_import_active_profile(workbuddy.get_active_account(), workbuddy.get_profiles())

        self.assertNotIn("老账号", workbuddy.get_profiles(), "只有 uin 的账号也不能被签到存回来")
        self.assertEqual(sorted(workbuddy.get_profiles().keys()), ["keep"])

    def test_no_id_active_account_not_reimported(self):
        """连 ID 都没有的当前账号，靠 token 指纹记墓碑，签到同样不能存回来。"""
        body = {"account": {"nickname": "无名"}, "auth": {"accessToken": "TOK-NOID"}}
        with open(os.path.join(workbuddy.PROFILES_DIR, "noid.info"), "w", encoding="utf-8") as f:
            json.dump(body, f)
        self._save_profile("keep", "uid_keep")
        os.makedirs(os.path.dirname(workbuddy.AUTH_FILE), exist_ok=True)
        with open(workbuddy.AUTH_FILE, "w", encoding="utf-8") as f:
            json.dump(body, f)

        ok, _ = self._run(workbuddy.remove_profile, "noid", yes=True, force_active=True)
        self.assertTrue(ok)

        workbuddy._auto_import_active_profile(workbuddy.get_active_account(), workbuddy.get_profiles())

        self.assertNotIn("无名", workbuddy.get_profiles())

    def test_tombstone_write_failure_is_reported(self):
        """墓碑写不进去时不能假装"签到不会再存回来"。"""
        self._save_profile("alice", "uid_alice")
        self._save_profile("bob", "uid_bob")
        self._set_active("uid_bob")

        with patch.object(workbuddy, "_save_tombstones", return_value=False):
            ok, out = self._run(workbuddy.remove_profile, "bob", yes=True, force_active=True)

        self.assertTrue(ok)
        self.assertIn("没能", out)
        self.assertNotIn("不会再把它自动存回列表", out)

    def test_restore_clears_tombstone(self):
        self._save_profile("alice", "uid_alice")
        self._save_profile("bob", "uid_bob")
        self._set_active("uid_bob")
        workbuddy.remove_profile("bob", yes=True, force_active=True)
        self.assertTrue(workbuddy._is_tombstoned("uid_bob"))

        ok, _ = self._run(workbuddy.restore_profile, "bob")

        self.assertTrue(ok)
        self.assertFalse(workbuddy._is_tombstoned("uid_bob"), "恢复就是'我要这个账号回来'，标记要解掉")

    def test_concurrent_tombstones_are_not_lost(self):
        """多进程/多线程同时删号时，墓碑读改写要串行，不能互相覆盖。"""
        from concurrent.futures import ThreadPoolExecutor

        keys = [f"U-conc-{i}" for i in range(8)]
        with ThreadPoolExecutor(max_workers=8) as pool:
            list(pool.map(lambda k: workbuddy._record_tombstones({k}), keys))

        marks = workbuddy._load_tombstones()
        for k in keys:
            self.assertIn(k, marks, f"{k} 的墓碑被并发覆盖丢了")

    def test_dirty_tombstone_file_does_not_crash(self):
        """deleted.json 里混进非数字时间戳、且超过上限时，删除不能崩。"""
        trash = os.path.join(workbuddy.PROFILES_DIR, ".trash")
        os.makedirs(trash, exist_ok=True)
        dirty = {f"old-{i}": 1700000000 + i for i in range(200)}
        dirty["legacy-key"] = "not-a-number"
        with open(os.path.join(trash, "deleted.json"), "w", encoding="utf-8") as f:
            json.dump(dirty, f)
        self._save_profile("alice", "uid_alice")
        self._save_profile("bob", "uid_bob")
        self._set_active("uid_bob")

        ok, _ = self._run(workbuddy.remove_profile, "alice", yes=True)

        self.assertTrue(ok)
        self.assertFalse(self._profile_exists("alice"))
        self.assertLessEqual(len(workbuddy._load_tombstones()), workbuddy.TOMBSTONE_LIMIT)

    def test_active_detected_when_ids_differ_but_token_same(self):
        """profile 只有 uin、登录态只有 uid，两个值还不同，但 token 相同 → 同一个账号。"""
        with open(os.path.join(workbuddy.PROFILES_DIR, "old.info"), "w", encoding="utf-8") as f:
            json.dump({"account": {"uin": "999888777", "nickname": "OldUser"},
                       "auth": {"accessToken": "SAME-TOKEN"}}, f)
        os.makedirs(os.path.dirname(workbuddy.AUTH_FILE), exist_ok=True)
        with open(workbuddy.AUTH_FILE, "w", encoding="utf-8") as f:
            json.dump({"account": {"uid": "U-real-777", "nickname": "OldUser"},
                       "auth": {"accessToken": "SAME-TOKEN"}}, f)

        with patch.object(sys.stdin, "isatty", return_value=False):
            ok, out = self._run(workbuddy.remove_profile, "old", yes=True)

        self.assertFalse(ok, "token 相同就说明是同一个登录态，不能当普通账号删")
        self.assertTrue(self._profile_exists("old"))

    def test_undecidable_identity_requires_explicit_force(self):
        """ID 对不上、token 也不同、昵称一样 → 昵称不算证据，按"无法确认"处理，必须显式强制。"""
        with open(os.path.join(workbuddy.PROFILES_DIR, "old.info"), "w", encoding="utf-8") as f:
            json.dump({"account": {"uin": "999888777", "nickname": "OldUser"},
                       "auth": {"accessToken": "T-profile"}}, f)
        os.makedirs(os.path.dirname(workbuddy.AUTH_FILE), exist_ok=True)
        with open(workbuddy.AUTH_FILE, "w", encoding="utf-8") as f:
            json.dump({"account": {"uid": "U-real-777", "nickname": "OldUser"},
                       "auth": {"accessToken": "T-live"}}, f)

        with patch.object(sys.stdin, "isatty", return_value=False):
            ok, out = self._run(workbuddy.remove_profile, "old", yes=True)

        self.assertFalse(ok, "拿不准的时候不许脚本静默删")
        self.assertIn("无法确认", out)
        self.assertTrue(self._profile_exists("old"))

    def test_siblings_detected_across_different_id_fields(self):
        """两个别名一个写 uin、一个写 uid（值还不同）但 token 相同 → 要提示还剩哪个别名。"""
        with open(os.path.join(workbuddy.PROFILES_DIR, "dup_uin.info"), "w", encoding="utf-8") as f:
            json.dump({"account": {"uin": "999888777", "nickname": "OldUser"},
                       "auth": {"accessToken": "SAME-TOKEN"}}, f)
        with open(os.path.join(workbuddy.PROFILES_DIR, "dup_uid.info"), "w", encoding="utf-8") as f:
            json.dump({"account": {"uid": "U-real-777", "nickname": "OldUser"},
                       "auth": {"accessToken": "SAME-TOKEN"}}, f)
        self._save_profile("keep", "uid_keep")
        self._set_active("uid_keep")

        ok, out = self._run(workbuddy.remove_profile, "dup_uin", yes=True, force_active=True)  # 与登录态不可比 → 拿不准

        self.assertTrue(ok)
        self.assertFalse(self._profile_exists("dup_uin"))
        self.assertTrue(self._profile_exists("dup_uid"))
        self.assertIn("dup_uid", out, "另一个别名也要被点名")
        self.assertIn("还挂在别的别名下", out)

    def test_numeric_uid_is_kept(self):
        """数字型 uid 也不能丢（别让 status 显示"无UID"、switch 失效）。"""
        with open(os.path.join(workbuddy.PROFILES_DIR, "numuid.info"), "w", encoding="utf-8") as f:
            json.dump({"account": {"uid": 123456789, "nickname": "Num"},
                       "auth": {"accessToken": "T-num"}}, f)

        self.assertEqual(workbuddy.get_profiles()["numuid"]["uid"], "123456789")

    def test_non_object_profile_file_can_be_removed(self):
        """合法 JSON 但不是账号对象（[] / null）的 .info，也得能按别名删掉。"""
        for alias, body in (("listfile", "[]"), ("nullfile", "null")):
            with open(os.path.join(workbuddy.PROFILES_DIR, f"{alias}.info"), "w", encoding="utf-8") as f:
                f.write(body)
        self._save_profile("keep", "uid_keep")
        self._set_active("uid_keep")

        ok, _ = self._run(workbuddy.remove_profile, "listfile", yes=True, force_active=True)
        self.assertTrue(ok)
        self.assertFalse(self._profile_exists("listfile"))

        ok, _ = self._run(workbuddy.remove_profile, "nullfile", yes=True, force_active=True)
        self.assertTrue(ok)
        self.assertFalse(self._profile_exists("nullfile"))

    def test_tombstone_write_failure_warns_for_normal_account_too(self):
        """非当前账号删掉后墓碑写失败，也要告警（否则哪天它变成当前账号就会被签到存回来）。"""
        self._save_profile("alice", "uid_alice")
        self._save_profile("bob", "uid_bob")
        self._set_active("uid_bob")

        with patch.object(workbuddy, "_save_tombstones", return_value=False):
            ok, out = self._run(workbuddy.remove_profile, "alice", yes=True)

        self.assertTrue(ok)
        self.assertIn("没能", out)

    # ---------- 同名昵称不是同一个账号（第六/七轮审查的 P1 原样复现） ----------

    def test_same_nickname_different_accounts_are_not_confused(self):
        """两个不相干账号都叫"微信用户"时：按完整 UID 必须能删，且不能把另一个说成同一账号。"""
        self._save_profile("acc1", "U-A", nickname="微信用户")
        self._save_profile("acc2", "U-B", nickname="微信用户")
        self._save_profile("keep", "U-C")
        self._set_active("U-C")

        ok, out = self._run(workbuddy.remove_profile, "U-A", yes=True)

        self.assertTrue(ok, "完整 UID 只对应 acc1，不该被判成多别名")
        self.assertFalse(self._profile_exists("acc1"))
        self.assertTrue(self._profile_exists("acc2"), "另一个账号不能被牵连")
        self.assertNotIn("还挂在别的别名下", out)

    def test_same_nickname_alias_delete_does_not_claim_twin(self):
        """按别名删时，不能把同昵称的另一个账号说成"账号本体仍在它下面"。"""
        self._save_profile("acc1", "U-A", nickname="微信用户")
        self._save_profile("acc2", "U-B", nickname="微信用户")
        self._set_active("U-OTHER")

        ok, out = self._run(workbuddy.remove_profile, "acc1", yes=True)

        self.assertTrue(ok)
        self.assertNotIn("acc2", out, "同昵称不同 UID 的账号不该出现在提示里")

    def test_unknown_relation_requires_force_even_with_yes(self):
        """证据不足时，-y 不够；--force-active --yes 才放行。"""
        with open(os.path.join(workbuddy.PROFILES_DIR, "old.info"), "w", encoding="utf-8") as f:
            json.dump({"account": {"uin": "999888777"}, "auth": {"accessToken": "T-p"}}, f)
        os.makedirs(os.path.dirname(workbuddy.AUTH_FILE), exist_ok=True)
        with open(workbuddy.AUTH_FILE, "w", encoding="utf-8") as f:
            json.dump({"account": {"uid": "U-real"}, "auth": {"accessToken": "T-l"}}, f)

        with patch.object(sys.stdin, "isatty", return_value=False):
            ok, _ = self._run(workbuddy.remove_profile, "old", yes=True)
        self.assertFalse(ok)
        self.assertTrue(self._profile_exists("old"))

        with patch.object(sys.stdin, "isatty", return_value=False):
            ok, _ = self._run(workbuddy.remove_profile, "old", yes=True, force_active=True)
        self.assertTrue(ok, "显式 --force-active --yes 应当放行")
        self.assertFalse(self._profile_exists("old"))

    def test_alias_wins_over_other_account_uid_case_insensitively(self):
        """`Alice` 存在、另一个账号的 uid 恰好是 `alice`：敲小写别名不能删到别人头上。"""
        self._save_profile("Alice", "uid_alice_owner")
        self._save_profile("bob", "alice")
        self._set_active("uid_other")

        ok, out = self._run(workbuddy.remove_profile, "alice", yes=True)

        self.assertTrue(ok)
        self.assertFalse(self._profile_exists("Alice"), "应当删的是别名 Alice")
        self.assertTrue(self._profile_exists("bob"), "bob 不能被误删")

    def test_clearing_tombstone_removes_all_keys(self):
        """登录/保存要把 uid、uin、token 指纹一起解掉，只解 uid 会留下"仍算已删除"。"""
        data = {"account": {"uid": "U-1", "uin": "888888"}, "auth": {"accessToken": "TOK-X"}}
        keys = workbuddy._tombstone_keys(data)
        self.assertGreaterEqual(len(keys), 3)

        workbuddy._record_tombstones(keys)
        self.assertTrue(workbuddy._is_tombstoned(data))

        workbuddy._clear_tombstones(keys)
        self.assertFalse(workbuddy._is_tombstoned(data))

    def test_broken_file_does_not_claim_tombstone_write_failure(self):
        """坏文件没有身份值可记，不能假报"墓碑写不进去"。"""
        broken = os.path.join(workbuddy.PROFILES_DIR, "dead.info")
        with open(broken, "w", encoding="utf-8") as f:
            f.write("{broken")
        self._save_profile("bob", "uid_bob")
        self._set_active("uid_bob")

        ok, out = self._run(workbuddy.remove_profile, "dead", yes=True, force_active=True)

        self.assertTrue(ok)
        self.assertNotIn("没能", out)

    def test_switch_still_works_after_removal(self):
        """验收 B：删完号，剩下的账号还得能正常切。"""
        self._save_profile("alice", "uid_alice")
        self._save_profile("keep", "uid_keep")
        self._set_active("uid_alice")

        workbuddy.remove_profile("alice", yes=True, force_active=True)

        with patch.object(workbuddy, "restart_workbuddy", lambda *a, **k: None):
            ok = workbuddy.switch_to_profile("keep", auto_restart=False, check_health=False)

        self.assertTrue(ok)
        with open(workbuddy.AUTH_FILE, "r", encoding="utf-8") as f:
            self.assertEqual(json.load(f)["account"]["uid"], "uid_keep")

    # ---------- 真实进程：main() 分发 ----------

    def _make_home_layout(self):
        """按子进程自己解析路径的方式铺一份 home（~/.workbuddy 下）。"""
        home = os.path.join(self.tmp, "home")
        profiles = os.path.join(home, ".workbuddy", "auth_profiles")
        auth_dir = os.path.join(home, ".workbuddy", "auth")
        os.makedirs(profiles, exist_ok=True)
        os.makedirs(auth_dir, exist_ok=True)
        for alias, uid in (("alice", "uid_alice"), ("bob", "uid_bob")):
            with open(os.path.join(profiles, f"{alias}.info"), "w", encoding="utf-8") as f:
                json.dump({"account": {"uid": uid, "nickname": alias},
                           "auth": {"accessToken": f"t-{alias}"}}, f)
        with open(os.path.join(auth_dir, "workbuddy-desktop.info"), "w", encoding="utf-8") as f:
            json.dump({"account": {"uid": "uid_bob", "nickname": "bob"},
                       "auth": {"accessToken": "t-bob"}}, f)
        env = os.environ.copy()
        env.update({
            "HOME": home,
            "USERPROFILE": home,
            "APPDATA": os.path.join(home, "appdata"),
            "LOCALAPPDATA": os.path.join(home, "localappdata"),
            "XDG_CONFIG_HOME": os.path.join(home, "xdg"),
            "NO_COLOR": "1",
        })
        return home, profiles, env

    def test_main_dispatch_removes_account(self):
        home, profiles, env = self._make_home_layout()
        script = os.path.join(REPO_DIR, "bin", "workbuddy")

        proc = subprocess.run([sys.executable, script, "rm", "alice", "-y"],
                              capture_output=True, text=True, env=env, timeout=120)

        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertFalse(os.path.exists(os.path.join(profiles, "alice.info")))
        self.assertTrue(os.path.exists(os.path.join(profiles, "bob.info")))
        trash = os.path.join(profiles, ".trash")
        self.assertEqual(len([f for f in os.listdir(trash) if f.endswith(".info")]), 1)

    def test_main_dispatch_blocks_active_account(self):
        home, profiles, env = self._make_home_layout()
        script = os.path.join(REPO_DIR, "bin", "workbuddy")

        proc = subprocess.run([sys.executable, script, "rm", "bob", "-y"],
                              capture_output=True, text=True, env=env, stdin=subprocess.DEVNULL, timeout=120)

        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertTrue(os.path.exists(os.path.join(profiles, "bob.info")))

    def test_prog_name_alias_dispatch(self):
        """wb-rm 这个入口文件名的分发要真的生效（install.py 装的就是这个别名）。"""
        home, profiles, env = self._make_home_layout()
        alias_script = os.path.join(home, "wb-rm")
        shutil.copy(os.path.join(REPO_DIR, "bin", "workbuddy"), alias_script)

        proc = subprocess.run([sys.executable, alias_script, "alice", "-y"],
                              capture_output=True, text=True, env=env, timeout=120)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertFalse(os.path.exists(os.path.join(profiles, "alice.info")))

        # 多敲一次 "rm" 也要认（wb-rm rm bob 这种手滑）
        proc = subprocess.run([sys.executable, alias_script, "rm", "bob", "-y", "--force-active"],
                              capture_output=True, text=True, env=env, timeout=120)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertFalse(os.path.exists(os.path.join(profiles, "bob.info")))

        proc = subprocess.run([sys.executable, alias_script, "--list-trash"],
                              capture_output=True, text=True, env=env, timeout=120)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("回收站", proc.stdout)


if __name__ == "__main__":
    unittest.main(verbosity=2)
