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

    def test_clean_session_snapshots_auto_detection(self):
        """Test clean_session_snapshots when open_files_set is None (auto-detect) and open files in session."""
        sessions_dir = os.path.join(self.temp_dir, "auto_sessions")
        os.makedirs(sessions_dir, exist_ok=True)

        old_sess = os.path.join(sessions_dir, "sess_open_file")
        old_backup = os.path.join(old_sess, "modify_backup")
        os.makedirs(old_backup, exist_ok=True)
        active_file = os.path.join(old_backup, "active_doc.py")
        with open(active_file, "w") as f:
            f.write("in-flight work")

        old_time = time.time() - (3600 * 100)
        os.utime(old_sess, (old_time, old_time))

        # Mock get_open_files to return active_file
        orig_get_open_files = self.guard.get_open_files
        self.guard.get_open_files = lambda d: {os.path.realpath(active_file)}

        try:
            cleaned, freed = self.guard.clean_session_snapshots(sessions_dir, open_files_set=None, ttl_hours=72)
            # The session has an open file in its directory, so it should NOT be touched
            self.assertTrue(os.path.exists(old_backup))
            self.assertEqual(cleaned, 0)
        finally:
            self.guard.get_open_files = orig_get_open_files

    def test_is_workbuddy_gui_running_live(self):
        """Verify is_workbuddy_gui_running runs safely and returns a bool."""
        res = self.guard.is_workbuddy_gui_running()
        self.assertIsInstance(res, bool)

    def test_reap_orphaned_daemons_protection(self):
        """Test reap_orphaned_daemons guardrails: gui_running, user_workload_active, sandbox_cli_active."""
        # 1. When GUI is running, must skip
        orig_gui = self.guard.is_workbuddy_gui_running
        self.guard.is_workbuddy_gui_running = lambda: True
        try:
            res = self.guard.reap_orphaned_daemons()
            self.assertFalse(res.get("reaped"))
            self.assertEqual(res.get("reason"), "gui_running")
        finally:
            self.guard.is_workbuddy_gui_running = orig_gui

    def test_run_sandbox_cmd_status_json(self):
        """Test workbuddy sandbox status --json CLI output format."""
        import io
        from contextlib import redirect_stdout

        buf = io.StringIO()
        with redirect_stdout(buf):
            self.cli.run_sandbox_cmd(["status", "--json"])

        output = buf.getvalue().strip()
        data = json.loads(output)
        self.assertIn("sandbox_daemon", data)
        self.assertIn("gui_running", data)
        self.assertIn("sessions_count", data)

    def test_doctor_check5_sandbox_audit(self):
        """Test wb-doctor Check 5 (Sandbox & Seatbelt) reports HEALTHY when temp wildcards active, RISK when bloated."""
        import io
        from unittest.mock import patch, MagicMock
        from contextlib import redirect_stdout

        # 1. Test HEALTHY when temp wildcards present
        mock_guard_healthy = MagicMock()
        mock_guard_healthy.find_sandbox_center_socket.return_value = "/mock/center.sock"
        mock_guard_healthy.find_active_uid.return_value = "uid-test"
        mock_guard_healthy.send_sandbox_ipc.return_value = {
            "success": True,
            "data": {
                "fileRules": [
                    {"path": "/var/folders/**", "action": "read=allow"},
                    {"path": "/tmp/**", "action": "read=allow"}
                ]
            }
        }
        with patch.object(self.cli, "get_log_guard_module", return_value=mock_guard_healthy):
            buf = io.StringIO()
            with redirect_stdout(buf):
                self.cli.run_doctor()
            output = buf.getvalue()
            self.assertIn("Sandbox & Seatbelt", output)
            self.assertIn("HEALTHY", output)

        # 2. Test RISK when > 2000 rules and no temp wildcard
        mock_guard_risk = MagicMock()
        mock_guard_risk.find_sandbox_center_socket.return_value = "/mock/center.sock"
        mock_guard_risk.find_active_uid.return_value = "uid-test"
        bloated_rules = [{"path": f"/some/single/file_{i}", "action": "read=allow"} for i in range(2500)]
        mock_guard_risk.send_sandbox_ipc.return_value = {
            "success": True,
            "data": {"fileRules": bloated_rules}
        }
        with patch.object(self.cli, "get_log_guard_module", return_value=mock_guard_risk):
            buf = io.StringIO()
            with redirect_stdout(buf):
                self.cli.run_doctor()
            output = buf.getvalue()
            self.assertIn("RISK", output)

    def test_doctor_check6_sccache_audit(self):
        """Test wb-doctor Check 6 (Cargo sccache reuse) audit logic."""
        import io
        from unittest.mock import patch, mock_open
        from contextlib import redirect_stdout

        cargo_cfg_content = '[build]\nrustc-wrapper = "/opt/homebrew/bin/sccache"\n'
        orig_exists = os.path.exists
        with patch("os.path.exists", side_effect=lambda p: True if "config.toml" in str(p) else orig_exists(p)), \
             patch("builtins.open", mock_open(read_data=cargo_cfg_content)):
            buf = io.StringIO()
            with redirect_stdout(buf):
                self.cli.run_doctor()
            output = buf.getvalue()
            self.assertIn("Cargo sccache reuse", output)
            self.assertIn("CONFIGURED", output)

    def test_doctor_upstream_spec_and_conflict_warnings(self):
        """Test wb-doctor detects upstream spec natively patched vs vulnerable, and warns on IPC mismatch / unresponsive."""
        import io
        from unittest.mock import patch, MagicMock
        from contextlib import redirect_stdout

        # 1. Test NATIVELY_PATCHED upstream spec
        mock_spec_patched = {
            "version": "5.7.0",
            "has_temp_unix": True,
            "total_rules": 48
        }
        with patch.object(self.cli, "get_upstream_rules_spec", return_value=mock_spec_patched):
            buf = io.StringIO()
            with redirect_stdout(buf):
                self.cli.run_doctor()
            output = buf.getvalue()
            self.assertIn("Upstream sandbox spec", output)
            self.assertIn("NATIVELY_PATCHED", output)
            self.assertIn("ZERO CONFLICTS DETECTED", output)

        # 2. Test IPC_MISMATCH when upstream changed protocol or returned error
        mock_guard_mismatch = MagicMock()
        mock_guard_mismatch.find_sandbox_center_socket.return_value = "/mock/center.sock"
        mock_guard_mismatch.find_active_uid.return_value = "uid-test"
        mock_guard_mismatch.send_sandbox_ipc.return_value = {
            "success": False,
            "error": "command not found"
        }
        with patch.object(self.cli, "get_log_guard_module", return_value=mock_guard_mismatch):
            buf = io.StringIO()
            with redirect_stdout(buf):
                self.cli.run_doctor()
            output = buf.getvalue()
            self.assertIn("IPC_MISMATCH", output)
            self.assertIn("POTENTIAL DRIFT DETECTED", output)
            self.assertIn("uninstall.py", output)

        # 3. Test IPC_UNRESPONSIVE when socket exists but IPC times out (resp is None)
        mock_guard_unresponsive = MagicMock()
        mock_guard_unresponsive.find_sandbox_center_socket.return_value = "/mock/center.sock"
        mock_guard_unresponsive.find_active_uid.return_value = "uid-test"
        mock_guard_unresponsive.send_sandbox_ipc.return_value = None
        with patch.object(self.cli, "get_log_guard_module", return_value=mock_guard_unresponsive):
            buf = io.StringIO()
            with redirect_stdout(buf):
                self.cli.run_doctor()
            output = buf.getvalue()
            self.assertIn("IPC_UNRESPONSIVE", output)
            self.assertIn("POTENTIAL DRIFT DETECTED", output)

        # 4. Test DAEMON_NOT_FOUND when GUI is running but no socket in /tmp
        mock_guard_nogui = MagicMock()
        mock_guard_nogui.find_sandbox_center_socket.return_value = None
        mock_guard_nogui.is_workbuddy_gui_running.return_value = True
        with patch.object(self.cli, "get_log_guard_module", return_value=mock_guard_nogui):
            buf = io.StringIO()
            with redirect_stdout(buf):
                self.cli.run_doctor()
            output = buf.getvalue()
            self.assertIn("DAEMON_NOT_FOUND", output)
            self.assertIn("POTENTIAL DRIFT DETECTED", output)

if __name__ == "__main__":
    unittest.main()
