import os
import sys
import json
import time
import socket
import threading
import unittest
import urllib.request
import urllib.error
from http.server import HTTPServer, BaseHTTPRequestHandler

# Add sidecar to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "sidecar")))
import router_engine

def find_free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('', 0))
        return s.getsockname()[1]

class MockUpstreamHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass  # Suppress console logging

    def do_POST(self):
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length).decode("utf-8")
        req_json = json.loads(body) if body else {}

        mode = self.server.mode
        if mode == "success_stream":
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "close")
            self.end_headers()
            self.close_connection = True
            
            chunk1 = json.dumps({"choices": [{"delta": {"content": "Hello"}}]})
            self.wfile.write(f"data: {chunk1}\n\n".encode("utf-8"))
            self.wfile.flush()
            time.sleep(0.01)
            chunk2 = json.dumps({"choices": [{"delta": {"content": " World"}}]})
            self.wfile.write(f"data: {chunk2}\n\n".encode("utf-8"))
            self.wfile.write(b"data: [DONE]\n\n")
            self.wfile.flush()

        elif mode == "rate_limit_429":
            self.send_response(429)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"error":{"message":"Rate limit exceeded","code":429}}')

        elif mode == "server_error_503":
            self.send_response(503)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"error":{"message":"Service Unavailable","code":503}}')

        elif mode == "hang_timeout":
            # Sleep longer than the router test timeout
            time.sleep(1.0)
            try:
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.end_headers()
                self.wfile.write(b"data: [DONE]\n\n")
            except (BrokenPipeError, ConnectionResetError, OSError):
                pass

class MockServer:
    def __init__(self, mode="success_stream"):
        self.port = find_free_port()
        self.server = HTTPServer(('127.0.0.1', self.port), MockUpstreamHandler)
        self.server.mode = mode
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def set_mode(self, mode):
        self.server.mode = mode

    def stop(self):
        self.server.shutdown()
        self.server.server_close()

class TestFailoverRouter(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.upstream1 = MockServer(mode="rate_limit_429")
        cls.upstream2 = MockServer(mode="success_stream")
        cls.router_port = find_free_port()

        # Router config with short timeouts for fast tests
        cls.config = {
            "enabled": True,
            "port": cls.router_port,
            "cooldown_seconds": 2,  # 2 seconds cooldown for test
            "fast_model_timeout_seconds": 0.3,
            "thinking_model_timeout_seconds": 0.5,
            "chain": [
                {
                    "id": "model-primary",
                    "url": f"http://127.0.0.1:{cls.upstream1.port}/v1/chat/completions",
                    "apiKey": "test-key-1",
                    "supportsToolCall": True
                },
                {
                    "id": "model-secondary",
                    "url": f"http://127.0.0.1:{cls.upstream2.port}/v1/chat/completions",
                    "apiKey": "test-key-2",
                    "supportsToolCall": True
                }
            ]
        }

        cls.router = router_engine.FailoverRouterServer(cls.config)
        cls.router.start(port=cls.router_port)
        time.sleep(0.1)

    @classmethod
    def tearDownClass(cls):
        cls.router.stop()
        cls.upstream1.stop()
        cls.upstream2.stop()

    def test_01_rate_limit_failover(self):
        """测试 Primary 返回 429 时，无缝秒级轮换至 Secondary 成功输出 SSE 流"""
        self.upstream1.set_mode("rate_limit_429")
        self.upstream2.set_mode("success_stream")

        url = f"http://127.0.0.1:{self.router_port}/v1/chat/completions"
        payload = json.dumps({
            "model": "workbuddy-autopilot",
            "messages": [{"role": "user", "content": "hi"}],
            "stream": True
        }).encode("utf-8")

        req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            self.assertEqual(resp.status, 200)
            raw_body = resp.read().decode("utf-8")
            self.assertIn("Hello", raw_body)
            self.assertIn("World", raw_body)

        # Primary 应当进入冷却池
        self.assertTrue(self.router.is_in_cooldown("model-primary"))

    def test_02_circuit_breaker_bypasses_cooldown(self):
        """测试在冷却期内，后续请求直接跳过 Primary，零延迟走 Secondary"""
        # Ensure model-primary is in cooldown
        self.router.trigger_cooldown("model-primary")
        self.assertTrue(self.router.is_in_cooldown("model-primary"))

        url = f"http://127.0.0.1:{self.router_port}/v1/chat/completions"
        payload = json.dumps({
            "model": "workbuddy-autopilot",
            "messages": [{"role": "user", "content": "hi"}],
            "stream": True
        }).encode("utf-8")

        req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
        start_time = time.time()
        with urllib.request.urlopen(req, timeout=5) as resp:
            self.assertEqual(resp.status, 200)
            raw_body = resp.read().decode("utf-8")
            self.assertIn("Hello", raw_body)
        elapsed = time.time() - start_time
        # Should be almost instantaneous (< 0.1s), without testing upstream1
        self.assertLess(elapsed, 0.2)

    def test_03_first_token_timeout_failover(self):
        """测试 Primary 首包挂起超时时，主动断开并轮换至 Secondary"""
        # Wait for cooldown of primary to expire
        time.sleep(2.1)
        self.assertFalse(self.router.is_in_cooldown("model-primary"))

        # Set upstream1 to hang
        self.upstream1.set_mode("hang_timeout")
        self.upstream2.set_mode("success_stream")

        url = f"http://127.0.0.1:{self.router_port}/v1/chat/completions"
        payload = json.dumps({
            "model": "workbuddy-autopilot",
            "messages": [{"role": "user", "content": "hi"}],
            "stream": True
        }).encode("utf-8")

        req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            self.assertEqual(resp.status, 200)
            raw_body = resp.read().decode("utf-8")
            self.assertIn("Hello", raw_body)

        # Primary timed out, so it must be marked in cooldown
        self.assertTrue(self.router.is_in_cooldown("model-primary"))

    def test_04_all_exhausted_returns_503(self):
        """测试全部上游均故障时，网关返回确定性的 503 JSON 错误，不无故挂死"""
        self.upstream1.set_mode("rate_limit_429")
        self.upstream2.set_mode("server_error_503")

        url = f"http://127.0.0.1:{self.router_port}/v1/chat/completions"
        payload = json.dumps({
            "model": "workbuddy-autopilot",
            "messages": [{"role": "user", "content": "hi"}],
            "stream": True
        }).encode("utf-8")

        req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=5) as resp:
                self.fail("Expected HTTPError 503")
        except urllib.error.HTTPError as e:
            self.assertEqual(e.code, 503)
            err_data = json.loads(e.read().decode("utf-8"))
            self.assertIn("error", err_data)

if __name__ == "__main__":
    unittest.main()
