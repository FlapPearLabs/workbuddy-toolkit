#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
"可回退"承诺与账号匹配的回归测试。

覆盖的真实故障:
- init 清空 sessions.user_id 不留备份，rollback 只能把全部会话挂到同一个 UID；
- 切号改写 automations.owner_user_id 不可恢复；
- 卸载不还原 models.json，模型指向已不存在的 127.0.0.1:8047；
- 卸载会删除 README 推荐位置 ~/.workbuddy/toolkit 下的源码仓库；
- `workbuddy switch bob` 切到了昵称为 bob 的另一个账号。
"""

import io
import os
import sys
import json
import shutil
import sqlite3
import tempfile
import unittest
import subprocess
from unittest.mock import patch

import importlib.util
import importlib.machinery

REPO_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_loader = importlib.machinery.SourceFileLoader("workbuddy_rev", os.path.join(REPO_DIR, "bin", "workbuddy"))
_spec = importlib.util.spec_from_loader("workbuddy_rev", _loader)
workbuddy = importlib.util.module_from_spec(_spec)
_loader.exec_module(workbuddy)

sys.path.insert(0, os.path.join(REPO_DIR, "sidecar"))
import models_inventory  # noqa: E402


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

    def _save_profile(self, alias, uid, nickname):
        data = {"account": {"uid": uid, "nickname": nickname}, "auth": {"accessToken": f"tok_{alias}"}}
        with open(os.path.join(workbuddy.PROFILES_DIR, f"{alias}.info"), "w", encoding="utf-8") as f:
            json.dump(data, f)
        return data


class TestWorkspaceRollback(_SandboxMixin, unittest.TestCase):
    def setUp(self):
        self._setup_sandbox()

    def tearDown(self):
        self._teardown_sandbox()

    def test_rollback_restores_each_sessions_original_owner(self):
        con = self._db()
        con.executemany("INSERT INTO sessions VALUES (?, '/w', ?, 't')", [("s1", "alice"), ("s2", "bob"), ("s3", "alice")])
        con.commit()
        con.close()

        with patch("sys.stdout", new_callable=io.StringIO):
            self.assertTrue(workbuddy.init_shared_workspace())
        con = self._db()
        con.execute("INSERT INTO sessions VALUES ('s4', '/w', 'carol', 't')")  # 共享期间新建，触发器置空并备份
        con.commit()
        self.assertEqual({r[0] for r in con.execute("SELECT user_id FROM sessions")}, {""})
        con.close()

        with patch("sys.stdout", new_callable=io.StringIO):
            self.assertTrue(workbuddy.rollback_shared_workspace())
        con = self._db()
        self.assertEqual(dict(con.execute("SELECT id, user_id FROM sessions")),
                         {"s1": "alice", "s2": "bob", "s3": "alice", "s4": "carol"})
        names = {r[0] for r in con.execute("SELECT name FROM sqlite_master")}
        self.assertNotIn("trg_sessions_force_shared_insert", names)
        self.assertNotIn(workbuddy.SESSION_OWNER_BACKUP_TABLE, names)
        con.close()

    def test_init_upgrades_legacy_triggers_that_did_not_back_up(self):
        con = self._db()
        con.executescript("""
        CREATE TRIGGER trg_sessions_force_shared_insert AFTER INSERT ON sessions
        WHEN NEW.user_id != '' AND NEW.user_id IS NOT NULL
        BEGIN UPDATE sessions SET user_id = '' WHERE id = NEW.id; END;
        """)
        con.close()
        with patch("sys.stdout", new_callable=io.StringIO):
            workbuddy.init_shared_workspace()
        con = self._db()
        con.execute("INSERT INTO sessions VALUES ('n1', '/w', 'dave', 't')")
        con.commit()
        backed = dict(con.execute(f"SELECT session_id, user_id FROM {workbuddy.SESSION_OWNER_BACKUP_TABLE}"))
        con.close()
        self.assertEqual(backed, {"n1": "dave"})

    def test_switch_backs_up_automation_owners_and_rollback_restores_them(self):
        con = self._db()
        con.executemany("INSERT INTO automations VALUES (?, ?, ?, NULL)", [("a1", "daily", "alice"), ("a2", "weekly", "bob")])
        con.commit()
        con.close()
        self.assertTrue(workbuddy.reassign_automations_owner("carol"))
        self.assertTrue(workbuddy.reassign_automations_owner("dave"))  # 第二次切换不得覆盖最初的备份
        con = self._db()
        self.assertEqual({r[0] for r in con.execute("SELECT owner_user_id FROM automations")}, {"dave"})
        con.close()
        with patch("sys.stdout", new_callable=io.StringIO):
            workbuddy.rollback_shared_workspace()
        con = self._db()
        self.assertEqual(dict(con.execute("SELECT id, owner_user_id FROM automations")), {"a1": "alice", "a2": "bob"})
        con.close()


class TestProfileResolution(_SandboxMixin, unittest.TestCase):
    def setUp(self):
        self._setup_sandbox()

    def tearDown(self):
        self._teardown_sandbox()

    def test_exact_alias_beats_other_profiles_nickname(self):
        self._save_profile("alice", "uid-alice-0001", "bob")
        self._save_profile("bob", "uid-bob-0002", "Bobby")
        with patch("sys.stdout", new_callable=io.StringIO):
            self.assertTrue(workbuddy.switch_to_profile("bob", auto_restart=False, check_health=False))
        with open(workbuddy.AUTH_FILE, "r", encoding="utf-8") as f:
            self.assertEqual(json.load(f)["account"]["uid"], "uid-bob-0002")

    def test_ambiguous_nickname_is_refused(self):
        self._save_profile("work", "uid-1111", "Cat")
        self._save_profile("home", "uid-2222", "cat")
        with patch("sys.stdout", new_callable=io.StringIO) as out:
            self.assertFalse(workbuddy.switch_to_profile("CAT", auto_restart=False, check_health=False))
        self.assertIn("多个账号", out.getvalue())
        self.assertFalse(os.path.exists(workbuddy.AUTH_FILE))

    def test_uid_prefix_requires_unique_match_and_min_length(self):
        self._save_profile("one", "123456-aaaa", "One")
        self._save_profile("two", "123499-bbbb", "Two")
        profiles = workbuddy.get_profiles()
        with patch("sys.stdout", new_callable=io.StringIO):
            self.assertEqual(workbuddy.resolve_profile_target(profiles, "1")[0], None, "过短的前缀不得匹配")
            self.assertEqual(workbuddy.resolve_profile_target(profiles, "1234")[0], None, "歧义前缀不得猜测")
            self.assertEqual(workbuddy.resolve_profile_target(profiles, "123456")[0], "one")
            self.assertEqual(workbuddy.resolve_profile_target(profiles, "123456", allow_uid_prefix=False)[0], None)

    def test_same_account_saved_twice_is_not_ambiguous(self):
        self._save_profile("acc", "uid-same-9999", "Same")
        self._save_profile("acc_1", "uid-same-9999", "Same")
        name, prof = workbuddy.resolve_profile_target(workbuddy.get_profiles(), "Same")
        self.assertIsNotNone(prof)
        self.assertEqual(prof["uid"], "uid-same-9999")


class TestModelsJsonRestore(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.mj = os.path.join(self.tmp, "models.json")
        self.router_cfg = os.path.join(self.tmp, "failover_router.json")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_register_then_restore_round_trips(self):
        original = [
            {"id": "space-bunny-free", "url": "https://upstream.example/v1", "apiKey": "user-own-key", "name": "Space Bunny"},
            {"id": "my-model", "url": "https://other.example/v1", "apiKey": "k2"},
        ]
        with open(self.mj, "w", encoding="utf-8") as f:
            json.dump(original, f)
        models_inventory.register_virtual_model_in_models_json(models_json_path=self.mj, port=8047, token="tok")
        with open(self.mj, "r", encoding="utf-8") as f:
            changed = json.load(f)
        self.assertIn("workbuddy-autopilot", [m["id"] for m in changed])

        summary = models_inventory.restore_models_json(models_json_path=self.mj, router_config_path=self.router_cfg, port=8047)
        with open(self.mj, "r", encoding="utf-8") as f:
            restored = json.load(f)
        self.assertEqual(restored, original)
        self.assertEqual(summary["removed"], 2)  # autopilot + deepseek 原本不存在
        self.assertFalse(os.path.exists(models_inventory._default_models_backup_path(self.mj)))

    def test_restore_without_backup_uses_router_upstreams(self):
        """旧版本安装（没有备份）：用 failover_router.json 中记录的真实上游还原。"""
        with open(self.mj, "w", encoding="utf-8") as f:
            json.dump([
                {"id": "workbuddy-autopilot", "url": "http://127.0.0.1:8047/v1", "apiKey": "sk-workbuddy-router-local"},
                {"id": "space-bunny-free", "url": "http://127.0.0.1:8047/v1", "apiKey": "sk-workbuddy-router-local"},
            ], f)
        with open(self.router_cfg, "w", encoding="utf-8") as f:
            json.dump({"upstreams": {"space-bunny-free": {"url": "https://upstream.example/v1", "apiKey": "user-own-key"}}}, f)
        models_inventory.restore_models_json(models_json_path=self.mj, router_config_path=self.router_cfg, port=8047)
        with open(self.mj, "r", encoding="utf-8") as f:
            restored = json.load(f)
        self.assertEqual(len(restored), 1)
        self.assertEqual(restored[0]["url"], "https://upstream.example/v1")
        self.assertEqual(restored[0]["apiKey"], "user-own-key")

    def test_backup_records_pre_toolkit_state_only_once(self):
        with open(self.mj, "w", encoding="utf-8") as f:
            json.dump([], f)
        models_inventory.register_virtual_model_in_models_json(models_json_path=self.mj, port=8047, token="tok")
        models_inventory.register_virtual_model_in_models_json(models_json_path=self.mj, port=8047, token="tok")
        with open(models_inventory._default_models_backup_path(self.mj), "r", encoding="utf-8") as f:
            entries = json.load(f)["entries"]
        self.assertIsNone(entries["workbuddy-autopilot"], "第二次注册不得把已改写的状态当作原始状态")


class TestUninstallKeepsCheckout(unittest.TestCase):
    def setUp(self):
        self.home = tempfile.mkdtemp()
        self.env = os.environ.copy()
        self.env.update({"HOME": self.home, "USERPROFILE": self.home, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8",
                         "APPDATA": os.path.join(self.home, "AppData", "Roaming"),
                         "LOCALAPPDATA": os.path.join(self.home, "AppData", "Local")})

    def tearDown(self):
        shutil.rmtree(self.home, ignore_errors=True)

    def test_uninstall_restores_models_json_and_keeps_source_checkout(self):
        clone = os.path.join(self.home, ".workbuddy", "toolkit")
        # .codegraph 是本机代码索引（含 unix socket），copytree 复制 socket 会直接失败
        shutil.copytree(REPO_DIR, clone, ignore=shutil.ignore_patterns(
            "__pycache__", ".ruff_cache", ".codegraph"))
        os.makedirs(os.path.join(clone, ".git"), exist_ok=True)
        wb = os.path.join(self.home, ".workbuddy")
        original = [{"id": "space-bunny-free", "url": "https://upstream.example/v1", "apiKey": "user-own-key"}]
        with open(os.path.join(wb, "models.json"), "w", encoding="utf-8") as f:
            json.dump(original, f)
        models_inventory.register_virtual_model_in_models_json(models_json_path=os.path.join(wb, "models.json"), port=8047)
        self.assertTrue(os.path.exists(os.path.join(wb, "router_token")))

        res = subprocess.run([sys.executable, os.path.join(clone, "uninstall.py"), "--no-rollback"],
                             cwd=clone, env=self.env, stdin=subprocess.DEVNULL,
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        self.assertEqual(res.returncode, 0, res.stderr + res.stdout)
        self.assertTrue(os.path.exists(os.path.join(clone, "sidecar", "credit_meter.py")), "源码仓库不得被删除")
        with open(os.path.join(wb, "models.json"), "r", encoding="utf-8") as f:
            self.assertEqual(json.load(f), original)
        self.assertFalse(os.path.exists(os.path.join(wb, "router_token")))
        self.assertFalse(os.path.exists(os.path.join(wb, "toolkit-state")))


class TestCreditMeterUsesOwnerBackup(unittest.TestCase):
    def test_session_owner_map_reads_backup_table(self):
        import credit_meter
        tmp = tempfile.mkdtemp()
        try:
            db = os.path.join(tmp, "workbuddy.db")
            con = sqlite3.connect(db)
            con.execute("CREATE TABLE sessions (id TEXT PRIMARY KEY, user_id TEXT)")
            con.execute("INSERT INTO sessions VALUES ('s1', '')")
            con.execute(f"CREATE TABLE {credit_meter.SESSION_OWNER_BACKUP_TABLE} (session_id TEXT PRIMARY KEY, user_id TEXT, saved_at INTEGER)")
            con.execute(f"INSERT INTO {credit_meter.SESSION_OWNER_BACKUP_TABLE} VALUES ('s1', 'uid-owner', 0)")
            con.commit()
            con.close()
            meter = credit_meter.CreditMeter(db_path=db, profiles_dir=os.path.join(tmp, "p"),
                                             active_info_path=os.path.join(tmp, "none.info"), workbuddy_dir=tmp)
            self.assertEqual(meter.build_session_owner_map({}).get("s1"), "uid-owner")
            self.assertEqual(credit_meter.SESSION_OWNER_BACKUP_TABLE, workbuddy.SESSION_OWNER_BACKUP_TABLE)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
