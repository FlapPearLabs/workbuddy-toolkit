#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Tests for WorkBuddy Sandbox Guard, Seatbelt Healing, and Snapshot Lifecycle Governance.
"""

import os
import sys
import time
import json
import socket
import shutil
import tempfile
import threading
import unittest
import importlib.util
import importlib.machinery

def load_module(name, path):
    loader = importlib.machinery.SourceFileLoader(name, path)
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module

REPO_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOG_GUARD_PATH = os.path.join(REPO_DIR, "bin", "workbuddy-log-guard")
WORKBUDDY_CLI_PATH = os.path.join(REPO_DIR, "bin", "workbuddy")

class TestSandboxGuard(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.guard = load_module("workbuddy_log_guard", LOG_GUARD_PATH)
        self.cli = load_module("workbuddy_cli", WORKBUDDY_CLI_PATH)

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_clean_session_snapshots(self):
        sessions_dir = os.path.join(self.temp_dir, "sessions")
        os.makedirs(sessions_dir, exist_ok=True)

        # 1. Old session (> 72 hours) with modify_backup
        old_sess = os.path.join(sessions_dir, "old_session_1")
        old_backup = os.path.join(old_sess, "modify_backup")
        os.makedirs(old_backup, exist_ok=True)
        dummy_file = os.path.join(old_backup, "file.txt")
        with open(dummy_file, "w") as f:
            f.write("hello" * 100)
        old_time = time.time() - (3600 * 100)
        os.utime(old_sess, (old_time, old_time))

        # 2. Fresh session (< 1 hour) with modify_backup
        fresh_sess = os.path.join(sessions_dir, "fresh_session_2")
        fresh_backup = os.path.join(fresh_sess, "modify_backup")
        os.makedirs(fresh_backup, exist_ok=True)
        fresh_file = os.path.join(fresh_backup, "file.txt")
        with open(fresh_file, "w") as f:
            f.write("fresh" * 100)

        # 3. Old session with active lockfile held open
        locked_sess = os.path.join(sessions_dir, "locked_session_3")
        locked_backup = os.path.join(locked_sess, "modify_backup")
        os.makedirs(locked_backup, exist_ok=True)
        lock_file = os.path.join(locked_sess, "center.backup.lock")
        with open(lock_file, "w") as f:
            f.write("locked")
        os.utime(locked_sess, (old_time, old_time))

        open_files = {os.path.realpath(lock_file)}

        cleaned, freed = self.guard.clean_session_snapshots(sessions_dir, open_files, ttl_hours=72, max_keep=10)

        # Old non-locked session's modify_backup should be purged
        self.assertFalse(os.path.exists(old_backup))
        # Fresh session must be preserved
        self.assertTrue(os.path.exists(fresh_backup))
        # Locked session must be preserved
        self.assertTrue(os.path.exists(locked_backup))
        self.assertGreater(freed, 0)

    def test_clean_shell_snapshots(self):
        snapshots_dir = os.path.join(self.temp_dir, "shell-snapshots")
        os.makedirs(snapshots_dir, exist_ok=True)

        old_snap = os.path.join(snapshots_dir, "old_snap.bin")
        with open(old_snap, "w") as f:
            f.write("snapshot")
        old_time = time.time() - (3600 * 100)
        os.utime(old_snap, (old_time, old_time))

        fresh_snap = os.path.join(snapshots_dir, "fresh_snap.bin")
        with open(fresh_snap, "w") as f:
            f.write("fresh snapshot")

        cleaned = self.guard.clean_shell_snapshots(snapshots_dir, ttl_hours=72)
        self.assertEqual(cleaned, 1)
        self.assertFalse(os.path.exists(old_snap))
        self.assertTrue(os.path.exists(fresh_snap))

    def test_mock_sandbox_ipc_and_healing(self):
        if os.name == "nt":
            self.skipTest("Unix domain sockets not applicable to Windows test runner")

        sock_path = os.path.join(self.temp_dir, "mock_center.sock")
        server_sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        server_sock.bind(sock_path)
        server_sock.listen(5)

        received_commands = []
        injected_rules = []

        def server_loop():
            while True:
                try:
                    conn, _ = server_sock.accept()
                except Exception:
                    break
                data = b""
                while True:
                    chunk = conn.recv(4096)
                    if not chunk:
                        break
                    data += chunk
                    if b"\n" in chunk:
                        break
                if data:
                    req = json.loads(data.decode("utf-8").strip())
                    cmd = req.get("command")
                    received_commands.append(cmd)
                    if cmd == "sandbox.rules.get_rules":
                        resp = {
                            "success": True,
                            "data": {
                                "fileRules": [
                                    {"path": "/Applications/WorkBuddy.app/**", "action": "read=allow"}
                                ]
                            }
                        }
                    elif cmd == "sandbox.rules.add_file_rule":
                        rules = req.get("data", {}).get("rules", [])
                        injected_rules.extend(rules)
                        resp = {"success": True, "addedCount": len(rules)}
                    elif cmd == "sandbox.rules.set_file_rules":
                        resp = {"success": True}
                    else:
                        resp = {"success": True}
                    conn.sendall(json.dumps(resp).encode("utf-8") + b"\n")
                conn.close()

        th = threading.Thread(target=server_loop, daemon=True)
        th.start()

        try:
            # 1. Test send_sandbox_ipc directly
            ping_resp = self.guard.send_sandbox_ipc(sock_path, "sandbox.rules.get_rules", {}, uid="test-uid")
            self.assertIsNotNone(ping_resp)
            self.assertTrue(ping_resp.get("success"))

            # 2. Test heal_sandbox_center_rules
            heal_result = self.guard.heal_sandbox_center_rules(socket_path=sock_path, uid="test-uid")
            self.assertEqual(heal_result.get("status"), "ok")
            self.assertGreater(heal_result.get("added_temp_rules"), 0)
            self.assertIn("sandbox.rules.add_file_rule", received_commands)

            injected_paths = [r["path"] for r in injected_rules]
            self.assertIn("/var/folders/**", injected_paths)
            self.assertIn("/tmp/**", injected_paths)
        finally:
            server_sock.close()

if __name__ == "__main__":
    unittest.main()
