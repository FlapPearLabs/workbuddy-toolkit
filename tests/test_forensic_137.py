#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Forensic Regression Tests for Bash Channel / Shell Execution Failures and Exit 137.
Tests negative controls (exit 137 != rule explosion), failure families (A~H),
UDS top-level sessionId wire protocol, and per-session rule pruning.
"""

import os
import sys
import json
import time
import socket
import shutil
import tempfile
import threading
import unittest
from unittest.mock import patch, MagicMock

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


class TestForensic137(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.guard = load_module("workbuddy_log_guard_forensic", LOG_GUARD_PATH)
        self.cli = load_module("workbuddy_cli_forensic", WORKBUDDY_CLI_PATH)

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    @unittest.skipUnless(hasattr(socket, "AF_UNIX") and sys.platform != "win32",
                         "Unix Domain Sockets (AF_UNIX) transport not supported on Windows runners; tested on macOS/Linux")
    def test_uds_wire_protocol_top_level_session_id(self):
        """
        Verify that send_sandbox_ipc places sessionId at the top-level
        envelope of CenterIpcMessage, matching upstream Rust wire format.
        """
        sock_path = os.path.join(self.temp_dir, "test_wire.sock")
        received_payloads = []

        server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        server.bind(sock_path)
        server.listen(1)

        def server_thread():
            conn, _ = server.accept()
            data = b""
            while b"\n" not in data:
                chunk = conn.recv(1024)
                if not chunk:
                    break
                data += chunk
            if data:
                received_payloads.append(json.loads(data.decode("utf-8").strip()))
                conn.sendall(json.dumps({"success": True, "data": {}}).encode("utf-8") + b"\n")
            conn.close()

        th = threading.Thread(target=server_thread, daemon=True)
        th.start()

        resp = self.guard.send_sandbox_ipc(
            sock_path,
            "sandbox.rules.get_rules",
            {"category": "auto_grant"},
            uid="user-test-42",
            timeout=2.0,
            session_id="sess-xyz-987"
        )

        th.join(timeout=2.0)
        server.close()

        self.assertIsNotNone(resp)
        self.assertTrue(resp.get("success"))
        self.assertEqual(len(received_payloads), 1)

        wire_msg = received_payloads[0]
        # Upstream CenterIpcMessage requirements:
        self.assertEqual(wire_msg.get("command"), "sandbox.rules.get_rules")
        self.assertEqual(wire_msg.get("uid"), "user-test-42")
        self.assertEqual(wire_msg.get("sessionId"), "sess-xyz-987", "sessionId must be at top-level envelope")
        self.assertNotIn("sessionId", wire_msg.get("data", {}), "sessionId must not be polluted into data payload")

    def test_send_sandbox_ipc_with_diag_socket_not_found_portable(self):
        """
        PORTABLE TEST (Windows, macOS, Linux):
        Verify that send_sandbox_ipc_with_diag exposes concrete SOCKET_NOT_FOUND error code
        when socket path is missing, instead of hiding under fail-open.
        """
        non_existent_sock = os.path.join(self.temp_dir, "non_existent.sock")
        resp1, diag1 = self.guard.send_sandbox_ipc_with_diag(
            non_existent_sock, "sandbox.rules.get_rules", {}, timeout=0.5
        )
        self.assertIsNone(resp1)
        self.assertEqual(diag1.get("status"), "error")
        self.assertEqual(diag1.get("error_code"), "SOCKET_NOT_FOUND")

        if sys.platform == "win32":
            dummy_file = os.path.join(self.temp_dir, "dummy_win.sock")
            with open(dummy_file, "w") as f:
                f.write("placeholder")
            resp_w, diag_w = self.guard.send_sandbox_ipc_with_diag(
                dummy_file, "sandbox.rules.get_rules", {}, timeout=0.5
            )
            self.assertIsNone(resp_w)
            self.assertEqual(diag_w.get("error_code"), "UNSUPPORTED_PLATFORM")

    @unittest.skipUnless(hasattr(socket, "AF_UNIX") and sys.platform != "win32",
                         "Unix Domain Sockets (AF_UNIX) transport not supported on Windows runners; tested on macOS/Linux")
    def test_send_sandbox_ipc_with_diag_unix_transport_errors(self):
        """
        UNIX TRANSPORT CAPABILITY TEST (macOS, Linux):
        Verify CONNECTION_REFUSED and DEADLINE_EXCEEDED with real local AF_UNIX sockets.
        """
        # 1. Connection Refused test (socket file exists, but nothing is listening)
        refused_sock = os.path.join(self.temp_dir, "refused.sock")
        dummy_s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        dummy_s.bind(refused_sock)
        dummy_s.close()

        resp2, diag2 = self.guard.send_sandbox_ipc_with_diag(
            refused_sock, "sandbox.rules.get_rules", {}, timeout=0.5
        )
        self.assertIsNone(resp2)
        self.assertEqual(diag2.get("status"), "error")
        self.assertEqual(diag2.get("error_code"), "CONNECTION_REFUSED")

        # 2. Timeout (DEADLINE_EXCEEDED) test
        hang_sock = os.path.join(self.temp_dir, "hang.sock")
        server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        server.bind(hang_sock)
        server.listen(1)

        def hang_worker():
            conn, _ = server.accept()
            time.sleep(1.0)
            conn.close()

        th = threading.Thread(target=hang_worker, daemon=True)
        th.start()

        resp3, diag3 = self.guard.send_sandbox_ipc_with_diag(
            hang_sock, "sandbox.rules.get_rules", {}, timeout=0.2
        )
        th.join(timeout=2.0)
        server.close()

        self.assertIsNone(resp3)
        self.assertEqual(diag3.get("status"), "error")
        self.assertEqual(diag3.get("error_code"), "DEADLINE_EXCEEDED")

    def test_heal_sandbox_center_rules_per_session_pruning(self):
        """
        Verify that heal_sandbox_center_rules detects bloated per-session rules
        and issues set_file_rules with the correct session_id.
        """
        ipc_calls = []

        def mock_send(sock, cmd, data, uid="default", timeout=2.0, session_id=None):
            ipc_calls.append({"cmd": cmd, "data": data, "session_id": session_id})
            if cmd == "sandbox.rules.get_rules" and session_id is None:
                # Global rules are normal (48 rules)
                return {
                    "success": True,
                    "data": {
                        "fileRules": [
                            {"path": "/var/folders/**", "action": "read=allow"},
                            {"path": "/tmp/**", "action": "read=allow"}
                        ]
                    }
                }
            elif cmd == "sandbox.monitor.query":
                return {
                    "success": True,
                    "data": {
                        "decideBucketsTop": [{"sessionId": "session-bloated-123"}]
                    }
                }
            elif cmd == "sandbox.rules.get_rules" and session_id == "session-bloated-123":
                # Session has 1500 bloated auto_grant rules
                return {
                    "success": True,
                    "data": {
                        "fileRules": [{"path": f"/tmp/file_{i}", "category": "auto_grant"} for i in range(1500)]
                    }
                }
            elif cmd == "sandbox.rules.set_file_rules":
                return {"success": True, "data": {"removedCount": 1500}}
            return {"success": True, "data": {}}

        with patch.object(self.guard, "find_sandbox_center_socket", return_value="/mock.sock"), \
             patch.object(self.guard, "find_active_uid", return_value="uid-mock"), \
             patch.object(self.guard, "send_sandbox_ipc", side_effect=mock_send), \
             patch.dict(os.environ, {"WORKBUDDY_HEAL_LOCK": os.path.join(self.temp_dir, "heal.lock")}):

            result = self.guard.heal_sandbox_center_rules()

            self.assertEqual(result.get("status"), "ok")
            self.assertTrue(result.get("cleared_auto_grant"))
            pruned_sessions = result.get("pruned_sessions", [])
            self.assertEqual(len(pruned_sessions), 1)
            self.assertEqual(pruned_sessions[0]["sessionId"], "session-bloated-123")
            self.assertTrue(pruned_sessions[0]["success"])

            # Verify that set_file_rules was invoked with session_id="session-bloated-123"
            session_prune_calls = [
                c for c in ipc_calls
                if c["cmd"] == "sandbox.rules.set_file_rules" and c["session_id"] == "session-bloated-123"
            ]
            self.assertGreaterEqual(len(session_prune_calls), 1)

    def test_inspect_137_negative_control_unknown(self):
        """
        NEGATIVE CONTROL:
        When exit 137 is encountered in logs, but:
        1. Sandbox rules are normal (<= 500 rules, temp wildcards present)
        2. No 120s timeout log evidence
        3. No PTY 5002ms delay evidence
        4. No memory pressure
        The fingerprint MUST classify as UNKNOWN (Family H), NEVER as RULE_EXPLOSION_LIKELY.
        """
        log_file = os.path.join(self.temp_dir, "sandbox_100.log")
        with open(log_file, "w") as f:
            f.write("2026-10-08 12:00:00 waitpid returned exit_code=137, killed=true\n")

        mock_guard = MagicMock()
        mock_guard.find_sandbox_center_socket.return_value = "/mock/center.sock"
        mock_guard.find_active_uid.return_value = "uid-test"
        mock_guard.send_sandbox_ipc.return_value = {
            "success": True,
            "data": {
                "fileRules": [
                    {"path": "/var/folders/**", "action": "read=allow"},
                    {"path": "/tmp/**", "action": "read=allow"}
                ]
            }
        }

        with patch.object(self.cli, "get_log_guard_module", return_value=mock_guard):
            fp = self.cli.inspect_137_failure(target_log_dir=self.temp_dir)

            self.assertEqual(fp["classification"], "UNKNOWN",
                             "Negative Control Failed: bare exit 137 must not be attributed to rule explosion")
            self.assertEqual(fp["root_cause_family"], "H")
            self.assertEqual(fp["confidence"], "LOW")
            self.assertIn("需保留下一次现场", fp["reason"])

    def test_inspect_137_positive_rule_explosion_family_a(self):
        """
        POSITIVE CONTROL:
        When rules exceed 2000 or session rules exceed 1000 without temp wildcards,
        the fingerprint MUST classify as RULE_EXPLOSION_LIKELY (Family A).
        """
        log_file = os.path.join(self.temp_dir, "sandbox_200.log")
        with open(log_file, "w") as f:
            f.write("2026-10-08 12:00:00 sandbox.rules.fetch_profile 超时 3000ms\n"
                    "rules_json_len=6985694\nexit_code=137\n")

        mock_guard = MagicMock()
        mock_guard.find_sandbox_center_socket.return_value = "/mock/center.sock"
        mock_guard.find_active_uid.return_value = "uid-test"
        mock_guard.send_sandbox_ipc.return_value = {
            "success": True,
            "data": {
                "fileRules": [{"path": f"/tmp/unique_{i}"} for i in range(2500)]
            }
        }

        with patch.object(self.cli, "get_log_guard_module", return_value=mock_guard):
            fp = self.cli.inspect_137_failure(target_log_dir=self.temp_dir)

            self.assertEqual(fp["classification"], "RULE_EXPLOSION_LIKELY")
            self.assertEqual(fp["root_cause_family"], "A")
            self.assertEqual(fp["confidence"], "HIGH")

    def test_inspect_137_positive_pty_lifecycle_family_b(self):
        """
        POSITIVE CONTROL:
        When log shows PTY 5002ms teardown hangs without rule explosion,
        the fingerprint MUST classify as PTY_LIFECYCLE_LIKELY (Family B).
        """
        log_file = os.path.join(self.temp_dir, "sandbox_300.log")
        with open(log_file, "w") as f:
            f.write("2026-10-08 12:00:00 InteractiveProcess::drop join 超时 5000ms\n")

        mock_guard = MagicMock()
        mock_guard.find_sandbox_center_socket.return_value = "/mock/center.sock"
        mock_guard.find_active_uid.return_value = "uid-test"
        mock_guard.send_sandbox_ipc.return_value = {
            "success": True,
            "data": {"fileRules": [{"path": "/var/folders/**"}]}
        }

        with patch.object(self.cli, "get_log_guard_module", return_value=mock_guard):
            fp = self.cli.inspect_137_failure(target_log_dir=self.temp_dir)

            self.assertEqual(fp["classification"], "PTY_LIFECYCLE_LIKELY")
            self.assertEqual(fp["root_cause_family"], "B")

    def test_inspect_137_positive_supervisor_kill_family_e(self):
        """
        POSITIVE CONTROL:
        When log shows 120s ProcessKill without rule explosion,
        the fingerprint MUST classify as SUPERVISOR_KILL_LIKELY (Family E).
        """
        log_file = os.path.join(self.temp_dir, "sandbox_400.log")
        with open(log_file, "w") as f:
            f.write('2026-10-08 12:00:00 ProcessKill(signal=Some("term")) exit_code=137\n')

        mock_guard = MagicMock()
        mock_guard.find_sandbox_center_socket.return_value = "/mock/center.sock"
        mock_guard.find_active_uid.return_value = "uid-test"
        mock_guard.send_sandbox_ipc.return_value = {
            "success": True,
            "data": {"fileRules": [{"path": "/var/folders/**"}]}
        }

        with patch.object(self.cli, "get_log_guard_module", return_value=mock_guard):
            fp = self.cli.inspect_137_failure(target_log_dir=self.temp_dir)

            self.assertEqual(fp["classification"], "SUPERVISOR_KILL_LIKELY")
            self.assertEqual(fp["root_cause_family"], "E")

    def test_cli_inspect_137_flags_and_json(self):
        """
        Verify CLI integration of wb-doctor --inspect-137 / --shell-failure and --json.
        """
        import io
        from contextlib import redirect_stdout

        buf = io.StringIO()
        with redirect_stdout(buf):
            self.cli.run_doctor(["--inspect-137", "--json"])

        output = buf.getvalue().strip()
        data = json.loads(output)
        self.assertIn("classification", data)
        self.assertIn("root_cause_family", data)
        self.assertIn("log_evidence", data)
        self.assertIn("workbuddy_version", data)
        self.assertIn("incident_evidence", data)
        self.assertIn("historical_evidence", data)
        self.assertIn("current_state", data)
        self.assertIn("taxonomy_scope", data)

    def test_inspect_137_positive_oom_family_c(self):
        """
        POSITIVE CONTROL:
        When log shows Jetsam / memorystatus kill or memory pressure is critical,
        the fingerprint MUST classify as OOM_LIKELY (Family C).
        """
        log_file = os.path.join(self.temp_dir, "sandbox_oom.log")
        with open(log_file, "w") as f:
            f.write("2026-10-08 12:00:00 Jetsam event: memorystatus kill process exit_code=137\n")

        mock_guard = MagicMock()
        mock_guard.find_sandbox_center_socket.return_value = "/mock/center.sock"
        mock_guard.find_active_uid.return_value = "uid-test"
        mock_guard.send_sandbox_ipc.return_value = {
            "success": True,
            "data": {"fileRules": [{"path": "/var/folders/**"}]}
        }

        with patch.object(self.cli, "get_log_guard_module", return_value=mock_guard):
            fp = self.cli.inspect_137_failure(target_log_dir=self.temp_dir)

            self.assertEqual(fp["classification"], "OOM_LIKELY")
            self.assertEqual(fp["root_cause_family"], "C")
            self.assertEqual(fp["confidence"], "MEDIUM")

    def test_inspect_137_positive_resource_limit_family_d(self):
        """
        POSITIVE CONTROL:
        When log shows rlimit/cgroup limit exhaustion without rule explosion,
        the fingerprint MUST classify as RESOURCE_LIMIT_LIKELY (Family D).
        """
        log_file = os.path.join(self.temp_dir, "sandbox_rlimit.log")
        with open(log_file, "w") as f:
            f.write("2026-10-08 12:00:00 RLIMIT_DATA exceeded memory limit, killed=true exit_code=137\n")

        mock_guard = MagicMock()
        mock_guard.find_sandbox_center_socket.return_value = "/mock/center.sock"
        mock_guard.find_active_uid.return_value = "uid-test"
        mock_guard.send_sandbox_ipc.return_value = {
            "success": True,
            "data": {"fileRules": [{"path": "/var/folders/**"}]}
        }

        with patch.object(self.cli, "get_log_guard_module", return_value=mock_guard):
            fp = self.cli.inspect_137_failure(target_log_dir=self.temp_dir)

            self.assertEqual(fp["classification"], "RESOURCE_LIMIT_LIKELY")
            self.assertEqual(fp["root_cause_family"], "D")
            self.assertEqual(fp["confidence"], "MEDIUM")

    def test_inspect_137_historical_pty_outside_window_does_not_pollute_current_state(self):
        """
        HARD NEGATIVE CONTROL (Bounded Incident Window Isolation):
        When an older log file (modified 2 hours ago) contains PTY 5002ms join timeout,
        but the current system state is healthy and the default incident window is 30 minutes:
        1. The historical PTY error MUST be relegated to historical_evidence.
        2. incident_evidence must be clean.
        3. Current classification MUST be UNKNOWN (Family H), NEVER PTY_LIFECYCLE_LIKELY (Family B).
        4. If the incident window is expanded to 180 minutes, it should then be captured in incident_evidence.
        """
        log_file = os.path.join(self.temp_dir, "sandbox_stale_pty.log")
        with open(log_file, "w") as f:
            f.write("2026-10-08 10:00:00 InteractiveProcess::drop join 超时 5000ms\n"
                    "waitpid returned exit_code=137\n")

        # Set mtime to 2 hours ago (7200 seconds before now)
        stale_mtime = time.time() - 7200
        os.utime(log_file, (stale_mtime, stale_mtime))

        mock_guard = MagicMock()
        mock_guard.find_sandbox_center_socket.return_value = "/mock/center.sock"
        mock_guard.find_active_uid.return_value = "uid-test"
        mock_guard.send_sandbox_ipc.return_value = {
            "success": True,
            "data": {
                "fileRules": [
                    {"path": "/var/folders/**", "action": "read=allow"},
                    {"path": "/tmp/**", "action": "read=allow"}
                ]
            }
        }

        with patch.object(self.cli, "get_log_guard_module", return_value=mock_guard):
            # Test default 30-minute window -> Stale log is ignored for current classification
            fp = self.cli.inspect_137_failure(target_log_dir=self.temp_dir, incident_window_minutes=30)

            self.assertEqual(fp["classification"], "UNKNOWN",
                             "Negative Control Failed: Historical PTY logs outside incident window polluted current state!")
            self.assertEqual(fp["root_cause_family"], "H")
            self.assertEqual(fp["confidence"], "LOW")
            self.assertTrue(fp["historical_evidence"]["pty_join_timeout_found"])
            self.assertFalse(fp["incident_evidence"]["pty_join_timeout_found"])
            self.assertIn("historical_evidence", fp["reason"])

            # Test expanded 180-minute window -> Stale log is now inside window
            fp_wide = self.cli.inspect_137_failure(target_log_dir=self.temp_dir, incident_window_minutes=180)
            self.assertEqual(fp_wide["classification"], "PTY_LIFECYCLE_LIKELY")
            self.assertEqual(fp_wide["root_cause_family"], "B")
            self.assertTrue(fp_wide["incident_evidence"]["pty_join_timeout_found"])

    def test_cli_inspect_137_window_flag(self):
        """
        Verify CLI accepts --since-minutes / --incident-window and exposes bounded evidence structure.
        """
        import io
        from contextlib import redirect_stdout

        buf = io.StringIO()
        with redirect_stdout(buf):
            self.cli.run_doctor(["--inspect-137", "--since-minutes=15", "--json"])

        output = buf.getvalue().strip()
        data = json.loads(output)
        self.assertEqual(data.get("incident_window_minutes"), 15)
        self.assertIn("incident_evidence", data)
        self.assertIn("historical_evidence", data)
        self.assertIn("current_state", data)
        self.assertIn("taxonomy_scope", data)


if __name__ == "__main__":
    unittest.main()
