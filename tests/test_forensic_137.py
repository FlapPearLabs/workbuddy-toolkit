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
import datetime
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
        now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_file = os.path.join(self.temp_dir, "sandbox_100.log")
        with open(log_file, "w", encoding="utf-8") as f:
            f.write(f"{now_str} waitpid returned exit_code=137, killed=true\n")

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
        now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_file = os.path.join(self.temp_dir, "sandbox_200.log")
        with open(log_file, "w", encoding="utf-8") as f:
            f.write(f"{now_str} sandbox.rules.fetch_profile 超时 3000ms\n"
                    f"rules_json_len=6985694\nexit_code=137\n")

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
        When log shows PTY 5002ms teardown hangs without rule explosion in incident window,
        the fingerprint MUST classify as PTY_LIFECYCLE_LIKELY (Family B).
        """
        now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_file = os.path.join(self.temp_dir, "sandbox_300.log")
        with open(log_file, "w", encoding="utf-8") as f:
            f.write(f"{now_str} InteractiveProcess::drop join 超时 5000ms\n")

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
        When log shows 120s ProcessKill without rule explosion in incident window,
        the fingerprint MUST classify as SUPERVISOR_KILL_LIKELY (Family E).
        """
        now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_file = os.path.join(self.temp_dir, "sandbox_400.log")
        with open(log_file, "w", encoding="utf-8") as f:
            f.write(f'{now_str} ProcessKill(signal=Some("term")) exit_code=137\n')

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
        self.assertIn("unscoped_evidence", data)
        self.assertIn("current_state", data)
        self.assertIn("taxonomy_scope", data)

    def test_inspect_137_positive_oom_family_c(self):
        """
        POSITIVE CONTROL:
        When log shows Jetsam / memorystatus kill or memory pressure is critical in incident window,
        the fingerprint MUST classify as OOM_LIKELY (Family C).
        """
        now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_file = os.path.join(self.temp_dir, "sandbox_oom.log")
        with open(log_file, "w", encoding="utf-8") as f:
            f.write(f"{now_str} Jetsam event: memorystatus kill process exit_code=137\n")

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
        When log shows rlimit/cgroup limit exhaustion without rule explosion in incident window,
        the fingerprint MUST classify as RESOURCE_LIMIT_LIKELY (Family D).
        """
        now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_file = os.path.join(self.temp_dir, "sandbox_rlimit.log")
        with open(log_file, "w", encoding="utf-8") as f:
            f.write(f"{now_str} RLIMIT_DATA exceeded memory limit, killed=true exit_code=137\n")

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
        stale_time = time.time() - 7200
        stale_str = datetime.datetime.fromtimestamp(stale_time).strftime("%Y-%m-%d %H:%M:%S")
        with open(log_file, "w", encoding="utf-8") as f:
            f.write(f"{stale_str} InteractiveProcess::drop join 超时 5000ms\n"
                    f"waitpid returned exit_code=137\n")

        os.utime(log_file, (stale_time, stale_time))

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

    def test_inspect_137_p1_negative_control_stale_log_recent_append(self):
        """
        P1 HARD NEGATIVE CONTROL (Record-level windowing vs. file mtime):
        When a long-running log file has 3-hour-old PTY timeout and Supervisor kill records,
        but recently received a benign append (bringing file mtime to NOW):
        1. File mtime is in incident window, BUT record timestamps are 3 hours old.
        2. Record-level windowing MUST route the stale errors to historical_evidence.
        3. incident_evidence must be clean.
        4. Current classification MUST be UNKNOWN (Family H), NEVER Family B or E.
        """
        log_file = os.path.join(self.temp_dir, "sandbox_longrunning.log")
        t_3h_ago = datetime.datetime.fromtimestamp(time.time() - 10800).strftime("%Y-%m-%d %H:%M:%S")
        t_now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        with open(log_file, "w", encoding="utf-8") as f:
            # 3 hours ago: stale PTY timeout and ProcessKill
            f.write(f"{t_3h_ago} InteractiveProcess::drop join 超时 5000ms\n")
            f.write(f'{t_3h_ago} ProcessKill(signal=Some("term")) exit_code=137\n')
            # NOW: benign normal log entry
            f.write(f"{t_now} [sandbox-core][I] normal command execution exit_code=0\n")

        # File mtime is implicitly NOW because we just wrote to it
        mock_guard = MagicMock()
        mock_guard.find_sandbox_center_socket.return_value = "/mock/center.sock"
        mock_guard.find_active_uid.return_value = "uid-test"
        mock_guard.send_sandbox_ipc.return_value = {
            "success": True,
            "data": {"fileRules": [{"path": "/var/folders/**"}]}
        }

        with patch.object(self.cli, "get_log_guard_module", return_value=mock_guard):
            fp = self.cli.inspect_137_failure(target_log_dir=self.temp_dir, incident_window_minutes=30)

            self.assertFalse(fp["incident_evidence"]["pty_join_timeout_found"],
                             "Record-level windowing failed: 3h-old PTY error was falsely included in incident_evidence!")
            self.assertFalse(fp["incident_evidence"]["supervisor_kill_found"],
                             "Record-level windowing failed: 3h-old supervisor kill was falsely included in incident_evidence!")
            self.assertTrue(fp["historical_evidence"]["pty_join_timeout_found"])
            self.assertTrue(fp["historical_evidence"]["supervisor_kill_found"])
            self.assertEqual(fp["classification"], "UNKNOWN")
            self.assertEqual(fp["root_cause_family"], "H")
            self.assertEqual(fp["confidence"], "LOW")
            self.assertIn("historical_evidence", fp["reason"])

    def test_inspect_137_p1_negative_control_unparseable_timestamp_not_promoted(self):
        """
        P1 NEGATIVE CONTROL:
        When log records lack parseable timestamps, they MUST be relegated to
        historical_evidence / unscoped_evidence, and NEVER elevated to incident_evidence
        or high-confidence diagnosis when incident_window_minutes is active.
        """
        log_file = os.path.join(self.temp_dir, "sandbox_no_timestamps.log")
        with open(log_file, "w", encoding="utf-8") as f:
            f.write("InteractiveProcess::drop join 超时 5000ms\n"
                    "waitpid returned exit_code=137\n")

        mock_guard = MagicMock()
        mock_guard.find_sandbox_center_socket.return_value = "/mock/center.sock"
        mock_guard.find_active_uid.return_value = "uid-test"
        mock_guard.send_sandbox_ipc.return_value = {
            "success": True,
            "data": {"fileRules": [{"path": "/var/folders/**"}]}
        }

        with patch.object(self.cli, "get_log_guard_module", return_value=mock_guard):
            fp = self.cli.inspect_137_failure(target_log_dir=self.temp_dir, incident_window_minutes=30)

            self.assertFalse(fp["incident_evidence"]["pty_join_timeout_found"],
                             "Unparseable timestamp record must NOT be promoted to incident_evidence!")
            self.assertTrue(fp["historical_evidence"]["pty_join_timeout_found"])
            self.assertTrue(fp["unscoped_evidence"]["pty_join_timeout_found"])
            self.assertEqual(fp["classification"], "UNKNOWN")
            self.assertEqual(fp["root_cause_family"], "H")

    def test_inspect_137_p2_negative_control_memorystatus_informational(self):
        """
        P2 NEGATIVE CONTROL:
        Informational lines containing 'memorystatus subsystem initialized' or
        'kernel memorystatus thread started' without actual kill/termination events
        MUST NEVER trigger Family C (OOM_LIKELY).
        """
        now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_file = os.path.join(self.temp_dir, "sandbox_info_mem.log")
        with open(log_file, "w", encoding="utf-8") as f:
            f.write(f"{now_str} memorystatus subsystem initialized\n"
                    f"{now_str} kernel memorystatus thread started\n")

        mock_guard = MagicMock()
        mock_guard.find_sandbox_center_socket.return_value = "/mock/center.sock"
        mock_guard.find_active_uid.return_value = "uid-test"
        mock_guard.send_sandbox_ipc.return_value = {
            "success": True,
            "data": {"fileRules": [{"path": "/var/folders/**"}]}
        }

        with patch.object(self.cli, "get_log_guard_module", return_value=mock_guard):
            fp = self.cli.inspect_137_failure(target_log_dir=self.temp_dir, incident_window_minutes=30)

            self.assertFalse(fp["incident_evidence"]["oom_found"],
                             "Purely informational memorystatus logs must not set oom_found!")
            self.assertNotEqual(fp["classification"], "OOM_LIKELY")
            self.assertNotEqual(fp["root_cause_family"], "C")
            self.assertEqual(fp["root_cause_family"], "H")

    def test_inspect_137_p2_negative_control_cgroup_informational(self):
        """
        P2 NEGATIVE CONTROL:
        Informational lines mentioning 'detected cgroup v2' or '/proc/self/cgroup' or
        'rlimit_nofile configured: 1024' without actual limit exceeded or kill events
        MUST NEVER trigger Family D (RESOURCE_LIMIT_LIKELY).
        """
        now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_file = os.path.join(self.temp_dir, "sandbox_info_cgroup.log")
        with open(log_file, "w", encoding="utf-8") as f:
            f.write(f"{now_str} detected cgroup v2 controller hierarchy\n"
                    f"{now_str} /proc/self/cgroup inspection complete\n"
                    f"{now_str} rlimit_nofile configured: 1024\n")

        mock_guard = MagicMock()
        mock_guard.find_sandbox_center_socket.return_value = "/mock/center.sock"
        mock_guard.find_active_uid.return_value = "uid-test"
        mock_guard.send_sandbox_ipc.return_value = {
            "success": True,
            "data": {"fileRules": [{"path": "/var/folders/**"}]}
        }

        with patch.object(self.cli, "get_log_guard_module", return_value=mock_guard):
            fp = self.cli.inspect_137_failure(target_log_dir=self.temp_dir, incident_window_minutes=30)

            self.assertFalse(fp["incident_evidence"]["resource_limit_found"],
                             "Purely informational cgroup/rlimit logs must not set resource_limit_found!")
            self.assertNotEqual(fp["classification"], "RESOURCE_LIMIT_LIKELY")
            self.assertNotEqual(fp["root_cause_family"], "D")
            self.assertEqual(fp["root_cause_family"], "H")

    def test_inspect_137_p2_positive_control_cgroup_oom_kill(self):
        """
        P2 POSITIVE CONTROL:
        Log record containing 'cgroup oom-kill event: memory.max exceeded, terminated exit_code=137'
        has both context and termination event, MUST trigger Family D (RESOURCE_LIMIT_LIKELY).
        """
        now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_file = os.path.join(self.temp_dir, "sandbox_cgroup_kill.log")
        with open(log_file, "w", encoding="utf-8") as f:
            f.write(f"{now_str} cgroup oom-kill event: memory.max exceeded, terminated exit_code=137\n")

        mock_guard = MagicMock()
        mock_guard.find_sandbox_center_socket.return_value = "/mock/center.sock"
        mock_guard.find_active_uid.return_value = "uid-test"
        mock_guard.send_sandbox_ipc.return_value = {
            "success": True,
            "data": {"fileRules": [{"path": "/var/folders/**"}]}
        }

        with patch.object(self.cli, "get_log_guard_module", return_value=mock_guard):
            fp = self.cli.inspect_137_failure(target_log_dir=self.temp_dir, incident_window_minutes=30)

            self.assertTrue(fp["incident_evidence"]["resource_limit_found"])
            self.assertEqual(fp["classification"], "RESOURCE_LIMIT_LIKELY")
            self.assertEqual(fp["root_cause_family"], "D")

    def test_inspect_137_workbuddy_slash_timestamp_format(self):
        """
        Verify that WorkBuddy's native [YYYY/M/D HH:MM:SS.mmm] log format is parsed correctly.
        """
        now_dt = datetime.datetime.now()
        wb_ts = f"[{now_dt.year}/{now_dt.month}/{now_dt.day} {now_dt.hour:02d}:{now_dt.minute:02d}:{now_dt.second:02d}.123]"
        log_file = os.path.join(self.temp_dir, "sandbox_wb_format.log")
        with open(log_file, "w", encoding="utf-8") as f:
            f.write(f"{wb_ts}[6105640960][sandbox-core][I] InteractiveProcess::drop join 超时 5000ms\n")

        mock_guard = MagicMock()
        mock_guard.find_sandbox_center_socket.return_value = "/mock/center.sock"
        mock_guard.find_active_uid.return_value = "uid-test"
        mock_guard.send_sandbox_ipc.return_value = {
            "success": True,
            "data": {"fileRules": [{"path": "/var/folders/**"}]}
        }

        with patch.object(self.cli, "get_log_guard_module", return_value=mock_guard):
            fp = self.cli.inspect_137_failure(target_log_dir=self.temp_dir, incident_window_minutes=30)

            self.assertTrue(fp["incident_evidence"]["pty_join_timeout_found"],
                            "Native WorkBuddy [YYYY/M/D HH:MM:SS.mmm] format was not recognized!")
            self.assertEqual(fp["classification"], "PTY_LIFECYCLE_LIKELY")
            self.assertEqual(fp["root_cause_family"], "B")

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
        self.assertIn("unscoped_evidence", data)
        self.assertIn("current_state", data)
        self.assertIn("taxonomy_scope", data)

    def test_t1_malformed_timestamp_after_recent_record(self):
        """
        T1: A line with timestamp-like prefix but unparseable format must not
        inherit the timestamp of a preceding recent record.
        """
        now_dt = datetime.datetime.now()
        recent_ts_str = f"[{now_dt.year:04d}-{now_dt.month:02d}-{now_dt.day:02d} {now_dt.hour:02d}:{now_dt.minute:02d}:{now_dt.second:02d}]"
        malformed_line = "[2026-99-99 99:99:99] InteractiveProcess::drop join 超时 5000ms"

        # Check helper behavior directly
        self.assertTrue(self.cli.looks_like_timestamp_prefix(malformed_line))
        self.assertIsNone(self.cli.parse_log_timestamp(malformed_line))

        content = f"{recent_ts_str} benign worker start\n{malformed_line}\n"
        records = self.cli.split_log_into_records(content)
        self.assertEqual(len(records), 2)
        self.assertIsNotNone(records[0][0])
        self.assertIsNone(records[1][0], "Malformed timestamp line must have timestamp=None, not inherit previous ts")

        log_file = os.path.join(self.temp_dir, "sandbox_t1.log")
        with open(log_file, "w", encoding="utf-8") as f:
            f.write(content)

        fp = self.cli.inspect_137_failure(target_log_dir=self.temp_dir, incident_window_minutes=30)
        self.assertFalse(fp["incident_evidence"]["pty_join_timeout_found"])
        self.assertTrue(fp["unscoped_evidence"]["pty_join_timeout_found"])
        self.assertEqual(fp["classification"], "UNKNOWN")
        self.assertEqual(fp["root_cause_family"], "H")

    def test_t2_future_timestamp_exclusion(self):
        """
        T2: A log record with a future timestamp must be excluded from the incident
        window and must not trigger an active incident classification.
        """
        future_dt = datetime.datetime.now() + datetime.timedelta(hours=2)
        future_ts_str = f"[{future_dt.year:04d}-{future_dt.month:02d}-{future_dt.day:02d} {future_dt.hour:02d}:{future_dt.minute:02d}:{future_dt.second:02d}]"
        content = f"{future_ts_str} ProcessKill signal=Some(\"term\")\n"

        log_file = os.path.join(self.temp_dir, "sandbox_t2.log")
        with open(log_file, "w", encoding="utf-8") as f:
            f.write(content)

        fp = self.cli.inspect_137_failure(target_log_dir=self.temp_dir, incident_window_minutes=30)
        self.assertFalse(fp["incident_evidence"]["supervisor_kill_found"])
        self.assertEqual(fp["classification"], "UNKNOWN")
        self.assertEqual(fp["root_cause_family"], "H")

    def test_t3_iso_positive_offset_parsing(self):
        """
        T3: ISO-8601 timestamps with positive offset (+05:30) must parse to exact Unix epoch.
        """
        iso_str = "2026-10-08T12:00:00+05:30"
        ts = self.cli.parse_log_timestamp(iso_str)
        self.assertIsNotNone(ts)
        expected_epoch = datetime.datetime.fromisoformat(iso_str).timestamp()
        self.assertEqual(ts, expected_epoch)

    def test_t4_iso_negative_offset_parsing(self):
        """
        T4: ISO-8601 timestamps with negative offset (-05:30) must inherit negative sign
        on minutes component, matching standard datetime.fromisoformat.
        """
        iso_str = "2026-10-08T12:00:00-05:30"
        ts = self.cli.parse_log_timestamp(iso_str)
        self.assertIsNotNone(ts)
        expected_epoch = datetime.datetime.fromisoformat(iso_str).timestamp()
        self.assertEqual(ts, expected_epoch)

    def test_t5_iso_negative_zero_hours_offset_parsing(self):
        """
        T5: ISO-8601 timestamps with zero hours and negative minutes (-00:30) and +00:30 and Z.
        """
        for iso_str in ["2026-10-08T12:00:00-00:30", "2026-10-08T12:00:00+00:30", "2026-10-08T12:00:00Z"]:
            ts = self.cli.parse_log_timestamp(iso_str)
            self.assertIsNotNone(ts)
            # Python 3.9 fromisoformat does not support trailing 'Z', normalize to '+00:00' for comparison
            expected_epoch = datetime.datetime.fromisoformat(iso_str.replace("Z", "+00:00")).timestamp()
            self.assertEqual(ts, expected_epoch)

    def test_t6_cgroup_oom_classifies_as_family_d(self):
        """
        T6: Cgroup OOM kills must classify as Family D (Resource Limit), NOT Family C (Host OOM).
        """
        now_dt = datetime.datetime.now()
        ts_str = f"[{now_dt.year:04d}-{now_dt.month:02d}-{now_dt.day:02d} {now_dt.hour:02d}:{now_dt.minute:02d}:{now_dt.second:02d}]"
        line = f"{ts_str} Memory cgroup out of memory: Killed process 12345 (bash) total-vm:1024kB, anon-rss:512kB\n"

        log_file = os.path.join(self.temp_dir, "sandbox_t6.log")
        with open(log_file, "w", encoding="utf-8") as f:
            f.write(line)

        fp = self.cli.inspect_137_failure(target_log_dir=self.temp_dir, incident_window_minutes=30)
        self.assertTrue(fp["incident_evidence"]["resource_limit_found"], "Cgroup OOM must trigger resource_limit_found")
        self.assertFalse(fp["incident_evidence"]["oom_found"], "Cgroup OOM must not trigger host oom_found")
        self.assertEqual(fp["classification"], "RESOURCE_LIMIT_LIKELY")
        self.assertEqual(fp["root_cause_family"], "D")

    def test_t7_global_kernel_oom_classifies_as_family_c(self):
        """
        T7: Global host/kernel OOM kills (without cgroup/rlimit context) must classify as Family C.
        """
        now_dt = datetime.datetime.now()
        ts_str = f"[{now_dt.year:04d}-{now_dt.month:02d}-{now_dt.day:02d} {now_dt.hour:02d}:{now_dt.minute:02d}:{now_dt.second:02d}]"
        line = f"{ts_str} Out of memory: Kill process 12345 (bash) score 900 or sacrifice child\n"

        log_file = os.path.join(self.temp_dir, "sandbox_t7.log")
        with open(log_file, "w", encoding="utf-8") as f:
            f.write(line)

        fp = self.cli.inspect_137_failure(target_log_dir=self.temp_dir, incident_window_minutes=30)
        self.assertTrue(fp["incident_evidence"]["oom_found"])
        self.assertFalse(fp["incident_evidence"]["resource_limit_found"])
        self.assertEqual(fp["classification"], "OOM_LIKELY")
        self.assertEqual(fp["root_cause_family"], "C")

    def test_t8_negated_oom_kill_fails_negative_to_family_h(self):
        """
        T8: Negated OOM kill phrases ('no process was killed', '0 processes killed')
        must fail negative and classify as Family H (UNKNOWN).
        """
        self.assertFalse(self.cli.check_oom_event("memorystatus: no process was killed"))
        self.assertFalse(self.cli.check_oom_event("kernel-oom: 0 processes killed"))
        self.assertFalse(self.cli.check_oom_event("out of memory subsystem initialized without killing"))

        now_dt = datetime.datetime.now()
        ts_str = f"[{now_dt.year:04d}-{now_dt.month:02d}-{now_dt.day:02d} {now_dt.hour:02d}:{now_dt.minute:02d}:{now_dt.second:02d}]"
        line = f"{ts_str} memorystatus: no process was killed during low memory event\n"

        log_file = os.path.join(self.temp_dir, "sandbox_t8.log")
        with open(log_file, "w", encoding="utf-8") as f:
            f.write(line)

        fp = self.cli.inspect_137_failure(target_log_dir=self.temp_dir, incident_window_minutes=30)
        self.assertFalse(fp["incident_evidence"]["oom_found"])
        self.assertEqual(fp["classification"], "UNKNOWN")
        self.assertEqual(fp["root_cause_family"], "H")

    def test_t9_negated_resource_limit_fails_negative_to_family_h(self):
        """
        T9: Negated resource limit phrases ('limit not exceeded', 'no process killed')
        must fail negative and classify as Family H (UNKNOWN).
        """
        self.assertFalse(self.cli.check_resource_limit_event("cgroup memory limit not exceeded; no process killed"))
        self.assertFalse(self.cli.check_resource_limit_event("rlimit quota not exceeded"))

        now_dt = datetime.datetime.now()
        ts_str = f"[{now_dt.year:04d}-{now_dt.month:02d}-{now_dt.day:02d} {now_dt.hour:02d}:{now_dt.minute:02d}:{now_dt.second:02d}]"
        line = f"{ts_str} cgroup memory limit not exceeded; no process killed\n"

        log_file = os.path.join(self.temp_dir, "sandbox_t9.log")
        with open(log_file, "w", encoding="utf-8") as f:
            f.write(line)

        fp = self.cli.inspect_137_failure(target_log_dir=self.temp_dir, incident_window_minutes=30)
        self.assertFalse(fp["incident_evidence"]["resource_limit_found"])
        self.assertEqual(fp["classification"], "UNKNOWN")
        self.assertEqual(fp["root_cause_family"], "H")

    def test_t10_affirmative_oom_event_classifies_as_family_c(self):
        """
        T10: Affirmative OOM kill event must trigger Family C.
        """
        self.assertTrue(self.cli.check_oom_event("memorystatus: process was killed by jetsam"))

        now_dt = datetime.datetime.now()
        ts_str = f"[{now_dt.year:04d}-{now_dt.month:02d}-{now_dt.day:02d} {now_dt.hour:02d}:{now_dt.minute:02d}:{now_dt.second:02d}]"
        line = f"{ts_str} memorystatus: process was killed by jetsam; exit_code=137\n"

        log_file = os.path.join(self.temp_dir, "sandbox_t10.log")
        with open(log_file, "w", encoding="utf-8") as f:
            f.write(line)

        fp = self.cli.inspect_137_failure(target_log_dir=self.temp_dir, incident_window_minutes=30)
        self.assertTrue(fp["incident_evidence"]["oom_found"])
        self.assertEqual(fp["classification"], "OOM_LIKELY")
        self.assertEqual(fp["root_cause_family"], "C")

    def test_t11_affirmative_resource_limit_event_classifies_as_family_d(self):
        """
        T11: Affirmative resource limit event must trigger Family D.
        """
        self.assertTrue(self.cli.check_resource_limit_event("cgroup memory limit exceeded; process killed"))

        now_dt = datetime.datetime.now()
        ts_str = f"[{now_dt.year:04d}-{now_dt.month:02d}-{now_dt.day:02d} {now_dt.hour:02d}:{now_dt.minute:02d}:{now_dt.second:02d}]"
        line = f"{ts_str} cgroup memory limit exceeded; process killed\n"

        log_file = os.path.join(self.temp_dir, "sandbox_t11.log")
        with open(log_file, "w", encoding="utf-8") as f:
            f.write(line)

        fp = self.cli.inspect_137_failure(target_log_dir=self.temp_dir, incident_window_minutes=30)
        self.assertTrue(fp["incident_evidence"]["resource_limit_found"])
        self.assertEqual(fp["classification"], "RESOURCE_LIMIT_LIKELY")
        self.assertEqual(fp["root_cause_family"], "D")

    def test_t12_tail_boundary_record_recovery(self):
        """
        T12: In a log file larger than 500 KiB, a record whose timestamp lies just before
        the 500 KiB cutoff but whose body crosses into the tail must be recovered
        via bounded backtracking without losing its timestamp.
        """
        now_dt = datetime.datetime.now()
        now_str = f"[{now_dt.year:04d}-{now_dt.month:02d}-{now_dt.day:02d} {now_dt.hour:02d}:{now_dt.minute:02d}:{now_dt.second:02d}]"

        log_file = os.path.join(self.temp_dir, "sandbox_t12.log")
        # Generate 520 KiB total:
        # 1. 490 KiB padding
        # 2. Record timestamp starting at ~490 KiB (within the 64 KiB backtrack region before 500 KiB)
        # 3. Crossing the 500 KiB boundary with PTY deadlock body
        with open(log_file, "wb") as f:
            pad_line = b"[2026-01-01 00:00:00] benign prefix filler line padding\n"
            target_padding = 490 * 1024
            while f.tell() < target_padding:
                f.write(pad_line)

            # Record timestamp in the backtrack zone
            f.write(f"{now_str} worker task dispatch\n".encode("utf-8"))
            # Body lines crossing the 500 KiB mark
            while f.tell() < 515 * 1024:
                f.write(b"  intermediate continuation stack trace info\n")
            f.write(b"  InteractiveProcess::drop join \xe8\xb6\x85\xe6\x97\xb6 5000ms\n")

        fp = self.cli.inspect_137_failure(target_log_dir=self.temp_dir, incident_window_minutes=30)
        self.assertTrue(fp["incident_evidence"]["pty_join_timeout_found"],
                        "Record crossing the 500 KiB boundary must have its timestamp recovered by backtrack!")
        self.assertEqual(fp["classification"], "PTY_LIFECYCLE_LIKELY")
        self.assertEqual(fp["root_cause_family"], "B")

    def test_t13_tail_boundary_no_timestamp_degrades_to_unscoped(self):
        """
        T13: In a log file larger than 500 KiB where no timestamp exists anywhere in
        the backtrack window, the record must degrade to unscoped evidence without
        fabricating a false timestamp or triggering an active incident.
        """
        log_file = os.path.join(self.temp_dir, "sandbox_t13.log")
        with open(log_file, "wb") as f:
            # 580 KiB file with no timestamps at all in the last 100 KiB
            pad_line = b"[2026-01-01 00:00:00] very old header line\n"
            f.write(pad_line)
            unanchored_line = b"unanchored raw continuation line without timestamp prefix\n"
            while f.tell() < 570 * 1024:
                f.write(unanchored_line)
            f.write(b"InteractiveProcess::drop join \xe8\xb6\x85\xe6\x97\xb6 5000ms\n")

        fp = self.cli.inspect_137_failure(target_log_dir=self.temp_dir, incident_window_minutes=30)
        self.assertFalse(fp["incident_evidence"]["pty_join_timeout_found"],
                         "Unanchored tail record must not enter incident_evidence")
        self.assertTrue(fp["unscoped_evidence"]["pty_join_timeout_found"],
                        "Unanchored tail record must be captured in unscoped_evidence")
        self.assertEqual(fp["classification"], "UNKNOWN")
        self.assertEqual(fp["root_cause_family"], "H")

    def test_t14_dst_ambiguous_local_timestamp_safe_handling(self):
        """
        T14: Local timestamps falling in an ambiguous DST repeated hour (e.g. 01:10 America/New_York)
        must resolve to the candidate consistent with the inspection window (not falsely pushed 70m away),
        and wide/undifferentiable windows must degrade safely to None (unscoped).
        """
        if hasattr(time, "tzset"):
            orig_tz = os.environ.get("TZ")
            try:
                os.environ["TZ"] = "America/New_York"
                time.tzset()

                # At second occurrence 01:20:
                # 01:10 could be fold=0 (EDT, 70 min ago) or fold=1 (EST, 10 min ago).
                ref_ts = time.mktime((2026, 11, 1, 1, 20, 0, 0, 0, 0))
                window_30m = ref_ts - 30 * 60

                resolved_ts = self.cli.resolve_local_timestamp(2026, 11, 1, 1, 10, 0,
                                                                reference_ts=ref_ts, window_cutoff=window_30m)
                self.assertIsNotNone(resolved_ts)
                self.assertEqual((ref_ts - resolved_ts) / 60, 10.0,
                                 "Must resolve to candidate inside the 30m window (10m ago), not 70m ago")

                # Wide window covering both occurrences (e.g. 120 minutes)
                window_wide = ref_ts - 120 * 60
                ambiguous_res = self.cli.resolve_local_timestamp(2026, 11, 1, 1, 10, 0,
                                                                 reference_ts=ref_ts, window_cutoff=window_wide)
                self.assertIsNone(ambiguous_res,
                                  "When both candidate epochs fall inside window, must degrade to None (unscoped)")
            finally:
                if orig_tz is not None:
                    os.environ["TZ"] = orig_tz
                else:
                    os.environ.pop("TZ", None)
                time.tzset()

    def test_t15_dst_repeated_hour_clock_skew_tolerance(self):
        """
        T15: Candidate epoch selection during DST repeated hour fold must
        respect CLOCK_SKEW_TOLERANCE_SECONDS so timestamps slightly ahead
        of reference_ts (e.g. 2s ahead due to clock jitter) are not rejected.
        """
        if hasattr(time, "tzset"):
            orig_tz = os.environ.get("TZ")
            try:
                os.environ["TZ"] = "America/New_York"
                time.tzset()

                # At second occurrence 01:20:00:
                # A log written at 01:20:02 (2 seconds ahead of reference_ts 01:20:00)
                # within CLOCK_SKEW_TOLERANCE_SECONDS (5s) must be accepted.
                ref_ts = time.mktime((2026, 11, 1, 1, 20, 0, 0, 0, 0))
                window_30m = ref_ts - 30 * 60

                resolved_ts = self.cli.resolve_local_timestamp(
                    2026, 11, 1, 1, 20, 2,
                    reference_ts=ref_ts,
                    window_cutoff=window_30m
                )
                self.assertIsNotNone(resolved_ts)
                self.assertEqual(resolved_ts - ref_ts, 2.0,
                                 "Must resolve fold within CLOCK_SKEW_TOLERANCE_SECONDS")
            finally:
                if orig_tz is not None:
                    os.environ["TZ"] = orig_tz
                else:
                    os.environ.pop("TZ", None)
                time.tzset()

    def test_t16_oom_victim_process_with_cgroup_in_name_classifies_as_family_c(self):
        """
        T16: Host OOM killing a victim process whose name contains 'cgroup'
        (e.g. cgroup-exporter) must NOT be misclassified as Family D (resource limit),
        and must strictly classify as Family C (kernel/host OOM).
        """
        line_victim = "Out of memory: Killed process 123 (cgroup-exporter) total-vm:100000kB, anon-rss:50000kB"
        self.assertTrue(self.cli.check_oom_event(line_victim))
        self.assertFalse(self.cli.check_resource_limit_event(line_victim))

        now_dt = datetime.datetime.now()
        ts_str = f"[{now_dt.year:04d}-{now_dt.month:02d}-{now_dt.day:02d} {now_dt.hour:02d}:{now_dt.minute:02d}:{now_dt.second:02d}]"
        log_line = f"{ts_str} {line_victim}\n"

        log_file = os.path.join(self.temp_dir, "sandbox_t16.log")
        with open(log_file, "w", encoding="utf-8") as f:
            f.write(log_line)

        fp = self.cli.inspect_137_failure(target_log_dir=self.temp_dir, incident_window_minutes=30)
        self.assertTrue(fp["incident_evidence"]["oom_found"])
        self.assertFalse(fp["incident_evidence"]["resource_limit_found"])
        self.assertEqual(fp["classification"], "OOM_LIKELY")
        self.assertEqual(fp["root_cause_family"], "C")

    def test_t17_offset_free_iso_timestamp_dst_fold_resolution(self):
        """
        T17 (P2-1): Offset-free ISO timestamps (e.g. 2026-11-01T01:10:00) must route
        through resolve_local_timestamp to ensure consistent DST ambiguous fold resolution
        with slash and dash local formats, rather than relying on naive datetime.timestamp().
        Explicit timezone offsets (-04:00, -05:00, Z) must maintain direct epoch conversion.
        """
        if hasattr(time, "tzset"):
            orig_tz = os.environ.get("TZ")
            try:
                os.environ["TZ"] = "America/New_York"
                time.tzset()

                # At second occurrence 01:20:00 EST (fold=1):
                # 01:10 could be fold=0 (EDT, 70 min ago) or fold=1 (EST, 10 min ago).
                ref_ts = time.mktime((2026, 11, 1, 1, 20, 0, 0, 0, 0))
                window_30m = ref_ts - 30 * 60

                # Dash format resolves to fold=1 (10 min ago)
                dash_ts = self.cli.parse_log_timestamp(
                    "[2026-11-01 01:10:00] task failure",
                    reference_ts=ref_ts,
                    window_cutoff=window_30m
                )
                self.assertIsNotNone(dash_ts)
                self.assertEqual((ref_ts - dash_ts) / 60, 10.0)

                # Offset-free ISO format must match dash format behavior
                iso_naive_ts = self.cli.parse_log_timestamp(
                    "2026-11-01T01:10:00 task failure",
                    reference_ts=ref_ts,
                    window_cutoff=window_30m
                )
                self.assertIsNotNone(iso_naive_ts)
                self.assertEqual(
                    iso_naive_ts,
                    dash_ts,
                    "Offset-free ISO timestamp must resolve to the same fold as dash local format (10m ago), not 70m ago"
                )
                self.assertEqual((ref_ts - iso_naive_ts) / 60, 10.0)

                # Explicit UTC and offset ISO timestamps must NOT be modified by local fold resolution
                explicit_z_ts = self.cli.parse_log_timestamp(
                    "2026-11-01T06:10:00Z task failure",
                    reference_ts=ref_ts,
                    window_cutoff=window_30m
                )
                self.assertIsNotNone(explicit_z_ts)
                self.assertEqual((ref_ts - explicit_z_ts) / 60, 10.0)

                explicit_est_ts = self.cli.parse_log_timestamp(
                    "2026-11-01T01:10:00-05:00 task failure",
                    reference_ts=ref_ts,
                    window_cutoff=window_30m
                )
                self.assertIsNotNone(explicit_est_ts)
                self.assertEqual((ref_ts - explicit_est_ts) / 60, 10.0)

                explicit_edt_ts = self.cli.parse_log_timestamp(
                    "2026-11-01T01:10:00-04:00 task failure",
                    reference_ts=ref_ts,
                    window_cutoff=window_30m
                )
                self.assertIsNotNone(explicit_edt_ts)
                self.assertEqual((ref_ts - explicit_edt_ts) / 60, 70.0)
            finally:
                if orig_tz is not None:
                    os.environ["TZ"] = orig_tz
                else:
                    os.environ.pop("TZ", None)
                time.tzset()

    def test_t18_canonical_rlimit_identifiers_and_controls(self):
        """
        T18 (P2-2): Canonical RLIMIT identifiers (RLIMIT_CPU, RLIMIT_AS, RLIMIT_NOFILE, RLIMIT_NPROC)
        must match context in check_resource_limit_event and check_oom_event despite underscore.
        Positive: Context + affirmative event -> Family D (True).
        Negative: Mentions in doc, process name with hyphen, or negation -> Must NOT be Family D (False).
        """
        # POSITIVE CONTROLS
        self.assertTrue(
            self.cli.check_resource_limit_event("RLIMIT_CPU hard limit reached; process killed by SIGKILL"),
            "RLIMIT_CPU killed must match resource limit event"
        )
        self.assertTrue(
            self.cli.check_resource_limit_event("RLIMIT_AS exceeded; process terminated"),
            "RLIMIT_AS exceeded must match resource limit event"
        )
        self.assertTrue(
            self.cli.check_resource_limit_event("RLIMIT_NOFILE exhausted"),
            "RLIMIT_NOFILE exhausted must match resource limit event"
        )
        self.assertTrue(
            self.cli.check_resource_limit_event("RLIMIT_NPROC exceeded maximum limit"),
            "RLIMIT_NPROC exceeded must match resource limit event"
        )

        # NEGATIVE CONTROLS
        self.assertFalse(
            self.cli.check_resource_limit_event("documentation mentions RLIMIT_CPU support"),
            "Informational documentation mentioning RLIMIT_CPU must NOT trigger Family D"
        )
        self.assertFalse(
            self.cli.check_resource_limit_event("rlimit-exporter process started"),
            "Process name rlimit-exporter must NOT trigger Family D"
        )
        self.assertFalse(
            self.cli.check_resource_limit_event("Out of memory: Killed process 123 (rlimit_cpu_exporter) total-vm:100000kB, anon-rss:50000kB"),
            "Process name rlimit_cpu_exporter must NOT trigger Family D"
        )
        self.assertTrue(
            self.cli.check_oom_event("Out of memory: Killed process 123 (rlimit_cpu_exporter) total-vm:100000kB, anon-rss:50000kB"),
            "Host OOM killing process rlimit_cpu_exporter must trigger Family C (not rejected as Family D)"
        )
        self.assertFalse(
            self.cli.check_resource_limit_event("Out of memory: Killed process 123 (rlimit_cpu-exporter) total-vm:100000kB, anon-rss:50000kB"),
            "Process name rlimit_cpu-exporter must NOT trigger Family D"
        )
        self.assertTrue(
            self.cli.check_oom_event("Out of memory: Killed process 123 (rlimit_cpu-exporter) total-vm:100000kB, anon-rss:50000kB"),
            "Host OOM killing process rlimit_cpu-exporter must trigger Family C (not rejected as Family D)"
        )
        self.assertFalse(
            self.cli.check_resource_limit_event("RLIMIT_CPU not exceeded; no process killed"),
            "Negated statement 'not exceeded; no process killed' must NOT trigger Family D"
        )

        # End-to-end inspect_137_failure classification test
        now_dt = datetime.datetime.now()
        ts_str = f"[{now_dt.year:04d}-{now_dt.month:02d}-{now_dt.day:02d} {now_dt.hour:02d}:{now_dt.minute:02d}:{now_dt.second:02d}]"
        log_line = f"{ts_str} RLIMIT_CPU hard limit reached; process killed by SIGKILL\n"
        log_file = os.path.join(self.temp_dir, "sandbox_t18.log")
        with open(log_file, "w", encoding="utf-8") as f:
            f.write(log_line)

        fp = self.cli.inspect_137_failure(target_log_dir=self.temp_dir, incident_window_minutes=30)
        self.assertTrue(fp["incident_evidence"]["resource_limit_found"])
        self.assertEqual(fp["root_cause_family"], "D")
        self.assertEqual(fp["classification"], "RESOURCE_LIMIT_LIKELY")

    def test_t19_exceed_inflections_and_negations(self):
        """
        T19 (P2-3): Verb inflections of exceed (exceed, exceeds, exceeded, exceeding)
        must all match affirmative limit events with context.
        Negated phrases (does not exceed, doesn't exceed, never exceeds, is not exceeding,
        isn't exceeding, limit not exceeded, etc.) must be safely stripped and remain negative.
        """
        # POSITIVE CONTROLS
        self.assertTrue(
            self.cli.check_resource_limit_event("memory.max exceed hard limit"),
            "exceed must match"
        )
        self.assertTrue(
            self.cli.check_resource_limit_event("memory.max exceeds hard limit"),
            "exceeds must match"
        )
        self.assertTrue(
            self.cli.check_resource_limit_event("memory.max exceeded hard limit"),
            "exceeded must match"
        )
        self.assertTrue(
            self.cli.check_resource_limit_event("memory.max exceeding hard limit"),
            "exceeding must match"
        )
        self.assertTrue(
            self.cli.check_resource_limit_event("memory.max not only exceeds hard limit; usage is twice the cap"),
            "Affirmative 'not only exceeds' must match limit event"
        )

        # NEGATIVE CONTROLS
        self.assertFalse(
            self.cli.check_resource_limit_event("memory.max usage no longer exceeds hard limit"),
            "'no longer exceeds' must be stripped as negative"
        )
        self.assertFalse(
            self.cli.check_resource_limit_event("memory.max does not exceed hard limit"),
            "does not exceed must be stripped as negative"
        )
        self.assertFalse(
            self.cli.check_resource_limit_event("memory.max doesn't exceed hard limit"),
            "doesn't exceed must be stripped as negative"
        )
        self.assertFalse(
            self.cli.check_resource_limit_event("memory.max never exceeds hard limit"),
            "never exceeds must be stripped as negative"
        )
        self.assertFalse(
            self.cli.check_resource_limit_event("memory.max is not exceeding hard limit"),
            "is not exceeding must be stripped as negative"
        )
        self.assertFalse(
            self.cli.check_resource_limit_event("memory.max is not currently exceeding hard limit"),
            "is not currently exceeding (adverb-qualified) must be stripped as negative"
        )
        self.assertFalse(
            self.cli.check_resource_limit_event("memory.max does not actually exceed hard limit"),
            "does not actually exceed (adverb-qualified) must be stripped as negative"
        )
        self.assertFalse(
            self.cli.check_resource_limit_event("memory.max has not yet exceeded hard limit"),
            "has not yet exceeded (adverb-qualified) must be stripped as negative"
        )
        self.assertFalse(
            self.cli.check_resource_limit_event("memory.max isn't exceeding hard limit"),
            "isn't exceeding must be stripped as negative"
        )
        self.assertFalse(
            self.cli.check_resource_limit_event("memory.max did not exceed hard limit"),
            "did not exceed must be stripped as negative"
        )
        self.assertFalse(
            self.cli.check_resource_limit_event("memory.max didn't exceed hard limit"),
            "didn't exceed must be stripped as negative"
        )
        self.assertFalse(
            self.cli.check_resource_limit_event("limit not exceeded"),
            "limit not exceeded must remain negative"
        )
        self.assertFalse(
            self.cli.check_resource_limit_event("without exceeding memory.max"),
            "without exceeding must remain negative"
        )


if __name__ == "__main__":
    unittest.main()

