#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
WorkBuddy 容灾轮换路由引擎 (Failover Router Engine)
提供 OpenAI 兼容的 Wire 协议接缝 (POST /v1/chat/completions)
集成首包防挂起、429秒级容灾、熔断冷却与 macOS 轻通知
"""

import os
import sys
import time
import json
import socket
import select
import urllib.request
import urllib.error
import threading
import subprocess
from typing import Dict, Any, List, Optional
from http.server import HTTPServer, BaseHTTPRequestHandler
from socketserver import ThreadingMixIn

DEFAULT_WORKBUDDY_DIR = os.path.expanduser("~/.workbuddy")
DEFAULT_ROUTER_CONFIG = os.path.join(DEFAULT_WORKBUDDY_DIR, "failover_router.json")
DEFAULT_LOG_PATH = os.path.join(DEFAULT_WORKBUDDY_DIR, "logs", "failover_router.log")

def send_macos_notification(title: str, message: str):
    """通过系统 osascript 弹出轻量 macOS 通知，静默后台触发"""
    if sys.platform != "darwin":
        return
    def _run():
        try:
            clean_title = title.replace('"', '\\"')
            clean_msg = message.replace('"', '\\"')
            cmd = f'display notification "{clean_msg}" with title "{clean_title}"'
            subprocess.run(["osascript", "-e", cmd], capture_output=True, timeout=3)
        except Exception:
            pass
    threading.Thread(target=_run, daemon=True).start()

def append_audit_log(entry: Dict[str, Any], log_file: str = DEFAULT_LOG_PATH):
    """写入结构化物理审计日志"""
    try:
        os.makedirs(os.path.dirname(os.path.abspath(log_file)), exist_ok=True)
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception:
        pass

_wb_cli_module = None

def get_official_auth():
    """动态获取 WorkBuddy 官方当前活跃账号的凭证 (accessToken 与 uid)"""
    global _wb_cli_module
    if _wb_cli_module is None:
        candidates = [
            os.path.expanduser("~/.local/bin/workbuddy"),
            os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "bin", "workbuddy")),
            "/Users/songshiyao/.gemini/antigravity/scratch/workbuddy-toolkit/bin/workbuddy"
        ]
        import runpy
        for c in candidates:
            if os.path.exists(c):
                try:
                    _wb_cli_module = runpy.run_path(c)
                    break
                except Exception:
                    pass
    if _wb_cli_module:
        try:
            acc = _wb_cli_module["get_active_account"]()
            if acc:
                raw_token = acc.get("auth", {}).get("accessToken")
                uid = acc.get("account", {}).get("uid", "")
                token = _wb_cli_module["resolve_credential_field"](raw_token, "accessToken")
                return token, uid
        except Exception:
            pass
    return None, None

class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True
    allow_reuse_address = True

class FailoverRequestHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        # 内部静默，走结构化审计日志
        pass

    def do_GET(self):
        if self.path in ("/health", "/v1/health", "/"):
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"status":"ok","service":"workbuddy-failover-router"}\n')
            return
        elif self.path in ("/status", "/v1/status"):
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            status_data = self.server.router_instance.get_status()
            self.wfile.write(json.dumps(status_data).encode("utf-8") + b"\n")
            return
        self.send_response(404)
        self.end_headers()

    def do_POST(self):
        if self.path not in ("/v1/chat/completions", "/chat/completions"):
            self.send_response(404)
            self.end_headers()
            return

        content_length = int(self.headers.get("Content-Length", 0))
        body_bytes = self.rfile.read(content_length)
        try:
            req_data = json.loads(body_bytes.decode("utf-8"))
        except Exception as e:
            self.send_response(400)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"error": {"message": f"Invalid JSON payload: {e}", "code": 400}}).encode("utf-8"))
            return

        self.server.router_instance.handle_chat_completions(self, req_data, body_bytes)

class FailoverRouterServer:
    def __init__(self, config: Dict[str, Any], config_path: str = DEFAULT_ROUTER_CONFIG):
        self.config_path = config_path
        self.config = config
        self._last_mtime = 0
        if config_path and os.path.exists(config_path):
            try:
                self._last_mtime = os.path.getmtime(config_path)
            except Exception:
                pass
        self.cooldown_seconds = config.get("cooldown_seconds", 600)
        self.fast_timeout = config.get("fast_model_timeout_seconds", 15)
        self.thinking_timeout = config.get("thinking_model_timeout_seconds", 45)
        self.chain = config.get("chain", [])
        self.cooldowns: Dict[str, float] = {}
        self.lock = threading.Lock()
        self.server: Optional[ThreadedHTTPServer] = None
        self.server_thread: Optional[threading.Thread] = None

    def reload_config_if_needed(self):
        if not self.config_path or not os.path.exists(self.config_path):
            return
        try:
            mtime = os.path.getmtime(self.config_path)
            if mtime > self._last_mtime:
                with open(self.config_path, "r", encoding="utf-8") as f:
                    new_cfg = json.load(f)
                with self.lock:
                    self.config = new_cfg
                    self.chain = new_cfg.get("chain", [])
                    self.cooldown_seconds = new_cfg.get("cooldown_seconds", 600)
                    self.fast_timeout = new_cfg.get("fast_model_timeout_seconds", 15)
                    self.thinking_timeout = new_cfg.get("thinking_model_timeout_seconds", 45)
                self._last_mtime = mtime
        except Exception:
            pass

    def is_in_cooldown(self, model_id: str) -> bool:
        with self.lock:
            exp = self.cooldowns.get(model_id, 0)
            return time.time() < exp

    def trigger_cooldown(self, model_id: str):
        with self.lock:
            self.cooldowns[model_id] = time.time() + self.cooldown_seconds

    def clear_cooldown(self, model_id: str):
        with self.lock:
            self.cooldowns.pop(model_id, None)

    def get_status(self) -> Dict[str, Any]:
        self.reload_config_if_needed()
        with self.lock:
            now = time.time()
            cooldown_status = {
                mid: max(0, int(exp - now))
                for mid, exp in self.cooldowns.items()
                if exp > now
            }
        return {
            "enabled": self.config.get("enabled", True),
            "port": self.config.get("port", 8047),
            "chain": [c.get("id") for c in self.chain],
            "active_cooldowns": cooldown_status
        }

    def start(self, port: Optional[int] = None):
        target_port = port or self.config.get("port", 8047)
        self.server = ThreadedHTTPServer(('127.0.0.1', target_port), FailoverRequestHandler)
        self.server.router_instance = self
        self.server_thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.server_thread.start()

    def stop(self):
        if self.server:
            self.server.shutdown()
            self.server.server_close()
            self.server = None

    def handle_chat_completions(self, handler: BaseHTTPRequestHandler, req_data: Dict[str, Any], raw_body: bytes):
        """核心容灾轮换分发逻辑"""
        self.reload_config_if_needed()
        # 如果未显式配置 chain，从默认配置重新读取
        chain = self.chain
        if not chain:
            if os.path.exists(DEFAULT_ROUTER_CONFIG):
                try:
                    with open(DEFAULT_ROUTER_CONFIG, "r", encoding="utf-8") as f:
                        saved_cfg = json.load(f)
                        chain = saved_cfg.get("chain", [])
                except Exception:
                    pass

        if not chain:
            handler.send_response(503)
            handler.send_header("Content-Type", "application/json")
            handler.end_headers()
            handler.wfile.write(b'{"error":{"message":"Failover router has no candidate models configured","code":503}}\n')
            return

        is_streaming = req_data.get("stream", True)
        last_error = "All candidates failed"

        for idx, candidate in enumerate(chain):
            mid = candidate.get("id")
            if not mid:
                continue

            # 1. 熔断检查
            if self.is_in_cooldown(mid):
                continue

            # 2. 超时计算 (思考模型放宽至 45s，普通模型严格 15s)
            is_thinking = candidate.get("supportsReasoning", False) or "thinking" in mid or "pro" in mid or "opus" in mid
            timeout_limit = self.thinking_timeout if is_thinking else self.fast_timeout

            # 3. 构造请求目标与凭据
            url = candidate.get("url")
            api_key = candidate.get("apiKey", "")
            is_official = (candidate.get("source") == "official") or not url

            # 若为官方内置模型且未显式指定 URL
            if is_official:
                url = url or "https://copilot.tencent.com/v2/chat/completions"

            # 保证 URL 以 /chat/completions 结尾 (兼容 /v1 等前缀)
            if not url.endswith("/chat/completions") and not url.endswith("/v2/chat/completions"):
                url = url.rstrip("/") + "/chat/completions"

            # 构造转发 Payload (重写 model 字段)
            forward_payload = dict(req_data)
            forward_payload["model"] = mid

            # 官方接口要求必须 stream: true
            if is_official:
                forward_payload["stream"] = True

            # 若目标模型不支持 reasoning，安全剥离 reasoning_effort 避免上游报错
            if not candidate.get("supportsReasoning", False) and "reasoning_effort" in forward_payload:
                forward_payload.pop("reasoning_effort", None)

            out_body = json.dumps(forward_payload).encode("utf-8")

            # Headers
            headers = {
                "Content-Type": "application/json",
                "User-Agent": "WorkBuddy/5.5.3" if is_official else "WorkBuddy-FailoverRouter/2.0"
            }
            if is_streaming or is_official:
                headers["Accept"] = "text/event-stream"

            if is_official:
                if not api_key:
                    off_token, off_uid = get_official_auth()
                    if off_token:
                        api_key = off_token
                    if off_uid:
                        headers["X-User-Id"] = str(off_uid)

            if api_key:
                headers["Authorization"] = f"Bearer {api_key}"

            # 4. 首包探测与零泄露容灾
            req = urllib.request.Request(url, data=out_body, headers=headers)
            start_time = time.time()
            resp = None

            try:
                resp = urllib.request.urlopen(req, timeout=timeout_limit)
                status_code = resp.status

                # 若上游状态异常
                if status_code in (408, 429, 500, 502, 503, 504):
                    raise urllib.error.HTTPError(url, status_code, "Upstream status error", None, None)

                # 对于流式请求：进行“首包窥探 (Peek First Chunk)”
                if is_streaming:
                    first_chunk = resp.readline()
                    # 首包若是空或异常
                    if not first_chunk:
                        raise ValueError("Upstream closed stream before sending initial chunk")

                    # 探测成功！首包到达，立即将 HTTP 200 响应与首包透传给 WorkBuddy 客户端
                    handler.send_response(200)
                    handler.send_header("Content-Type", "text/event-stream")
                    handler.send_header("Cache-Control", "no-cache")
                    handler.send_header("Connection", "close")
                    handler.send_header("X-WorkBuddy-Routed-Model", mid)
                    handler.end_headers()
                    handler.close_connection = True

                    handler.wfile.write(first_chunk)
                    handler.wfile.flush()

                    # 继续流式透传剩余 Chunks
                    try:
                        while True:
                            chunk = resp.readline()
                            if not chunk:
                                break
                            handler.wfile.write(chunk)
                            handler.wfile.flush()
                            if b"[DONE]" in chunk:
                                break
                    except (BrokenPipeError, ConnectionResetError):
                        # 客户端主动断开
                        pass

                    # 成功完成该轮会话，解除该模型冷却
                    self.clear_cooldown(mid)
                    append_audit_log({
                        "timestamp": int(time.time()),
                        "event": "success",
                        "model": mid,
                        "duration_ms": int((time.time() - start_time) * 1000)
                    })
                    return

                else:
                    # 非流式客户端请求
                    if is_official:
                        # 官方接口为 SSE 流，汇聚为单一 JSON 返回
                        content_parts = []
                        reasoning_parts = []
                        usage_obj = None
                        call_id = f"chatcmpl-{int(time.time()*1000)}"
                        for raw_line in resp:
                            line_str = raw_line.decode("utf-8", errors="ignore").strip()
                            if line_str.startswith("data: "):
                                data_str = line_str[6:]
                                if data_str == "[DONE]":
                                    break
                                try:
                                    chunk = json.loads(data_str)
                                    if "id" in chunk:
                                        call_id = chunk["id"]
                                    delta = chunk.get("choices", [{}])[0].get("delta", {})
                                    if "content" in delta and delta["content"]:
                                        content_parts.append(delta["content"])
                                    if "reasoning_content" in delta and delta["reasoning_content"]:
                                        reasoning_parts.append(delta["reasoning_content"])
                                    if "usage" in chunk and chunk["usage"]:
                                        usage_obj = chunk["usage"]
                                except Exception:
                                    pass
                        msg_obj = {
                            "role": "assistant",
                            "content": "".join(content_parts)
                        }
                        if reasoning_parts:
                            msg_obj["reasoning_content"] = "".join(reasoning_parts)
                        out_resp = {
                            "id": call_id,
                            "object": "chat.completion",
                            "created": int(time.time()),
                            "model": mid,
                            "choices": [{
                                "index": 0,
                                "message": msg_obj,
                                "finish_reason": "stop"
                            }],
                            "usage": usage_obj or {
                                "prompt_tokens": 0,
                                "completion_tokens": len("".join(content_parts)),
                                "total_tokens": len("".join(content_parts))
                            }
                        }
                        full_content = json.dumps(out_resp, ensure_ascii=False).encode("utf-8")
                    else:
                        full_content = resp.read()

                    handler.send_response(200)
                    handler.send_header("Content-Type", "application/json")
                    handler.send_header("Content-Length", str(len(full_content)))
                    handler.send_header("X-WorkBuddy-Routed-Model", mid)
                    handler.end_headers()
                    handler.wfile.write(full_content)

                    self.clear_cooldown(mid)
                    append_audit_log({
                        "timestamp": int(time.time()),
                        "event": "success",
                        "model": mid,
                        "duration_ms": int((time.time() - start_time) * 1000)
                    })
                    return

            except urllib.error.HTTPError as he:
                last_error = f"HTTP {he.code}: {he.reason}"
                self.trigger_cooldown(mid)
                next_model = chain[idx + 1].get("id") if idx + 1 < len(chain) else "无备用"
                send_macos_notification(
                    "WorkBuddy 故障自动轮换",
                    f"模型 {mid} 返回 {he.code}，已无缝切换至 {next_model} 继续执行"
                )
                append_audit_log({
                    "timestamp": int(time.time()),
                    "event": "failover",
                    "reason": f"HTTP {he.code}",
                    "failed_model": mid,
                    "cooldown_seconds": self.cooldown_seconds
                })
                continue

            except (socket.timeout, TimeoutError) as te:
                last_error = f"Timeout after {timeout_limit}s on first chunk"
                self.trigger_cooldown(mid)
                next_model = chain[idx + 1].get("id") if idx + 1 < len(chain) else "无备用"
                send_macos_notification(
                    "WorkBuddy 首包挂起超时",
                    f"模型 {mid} 首包等待超过 {timeout_limit}s，已切换至 {next_model}"
                )
                append_audit_log({
                    "timestamp": int(time.time()),
                    "event": "timeout_failover",
                    "reason": "First-token timeout",
                    "failed_model": mid,
                    "timeout_seconds": timeout_limit
                })
                continue

            except Exception as ex:
                last_error = str(ex)
                self.trigger_cooldown(mid)
                continue
            finally:
                if resp:
                    try:
                        resp.close()
                    except Exception:
                        pass

        # 若全部候选模型均告竭
        handler.send_response(503)
        handler.send_header("Content-Type", "application/json")
        handler.end_headers()
        err_resp = {
            "error": {
                "message": f"All candidate models exhausted. Last error: {last_error}",
                "code": 503
            }
        }
        handler.wfile.write(json.dumps(err_resp).encode("utf-8") + b"\n")
        append_audit_log({
            "timestamp": int(time.time()),
            "event": "all_exhausted",
            "last_error": last_error
        })

def run_standalone_daemon(config_path: str = DEFAULT_ROUTER_CONFIG):
    """运行常驻路由器服务"""
    if os.path.exists(config_path):
        with open(config_path, "r", encoding="utf-8") as f:
            cfg = json.load(f)
    else:
        cfg = {"enabled": True, "port": 8047, "chain": []}

    port = cfg.get("port", 8047)
    router = FailoverRouterServer(cfg, config_path=config_path)
    print(f"WorkBuddy Failover Router starting on http://127.0.0.1:{port}...")
    router.start(port=port)
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nStopping Failover Router...")
        router.stop()

if __name__ == "__main__":
    run_standalone_daemon()
