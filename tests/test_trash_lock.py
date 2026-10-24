"""tests/test_trash_lock.py — 直接验证 _TrashLock 的跨进程互斥。

对抗审查指出：`test_concurrent_remove_same_alias` 在没有锁时也可能全绿
（失败方的 os.replace 抛 FileNotFoundError，断言照样成立）。这里不依赖
业务路径，直接让两个子进程持锁写同一份日志：

- 有锁：enter / exit / enter / exit（严格串行）
- 无锁：enter / enter / exit / exit（重叠）

就绪屏障：两个子进程都先把 "ready" 写进日志并轮询到对方也就绪后才进
临界区——否则慢机器上子进程 B 比A 晚启动超过临界区时长时，无锁也会
表现为串行（假绿）。屏障保证两者一定在锁门口相遇，变异校验把平台锁
调用改成 pass 后本用例必红。
"""
import os
import subprocess
import sys
import tempfile
import time
import unittest

REPO_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BIN_PATH = os.environ.get("WB_BIN") or os.path.join(REPO_DIR, "bin", "workbuddy")

CHILD = r'''
import importlib.machinery, importlib.util, sys, time
loader = importlib.machinery.SourceFileLoader("wb_lock", sys.argv[1])
spec = importlib.util.spec_from_loader("wb_lock", loader)
m = importlib.util.module_from_spec(spec)
loader.exec_module(m)
m.PROFILES_DIR = sys.argv[2]
log_path = sys.argv[3]

def append(line):
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(line + "\n")
        f.flush()

def count_ready():
    try:
        with open(log_path, "r", encoding="utf-8") as f:
            return sum(1 for line in f if line.strip() == "ready")
    except OSError:
        return 0

# 就绪屏障：两进程都到场后才抢锁，消除启动抖动造成的假绿。
# 超时放宽到 90s：安全软件/AV 偶发把子进程启动拖到几十秒，30s 会误报。
append("ready")
deadline = time.time() + 90
while count_ready() < 2:
    if time.time() > deadline:
        try:
            with open(log_path, "r", encoding="utf-8") as f:
                snapshot = f.read()
        except OSError:
            snapshot = "(log 不可读)"
        sys.exit(f"barrier timeout: 另一个子进程未就绪，当前日志={snapshot!r}")
    time.sleep(0.05)

with m._TrashLock():
    append("enter")
    time.sleep(0.2)
    append("exit")
'''


class TestTrashLock(unittest.TestCase):
    def test_lock_serializes_two_processes(self):
        base = tempfile.mkdtemp(prefix="wb_lock_")
        self.addCleanup(lambda: __import__("shutil").rmtree(base, ignore_errors=True))
        profiles = os.path.join(base, "auth_profiles")
        os.makedirs(profiles, exist_ok=True)
        log = os.path.join(base, "lock.log")

        procs = [
            subprocess.Popen([sys.executable, "-c", CHILD, BIN_PATH, profiles, log],
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            for _ in range(2)
        ]
        for p in procs:
            out, err = p.communicate(timeout=180)
            self.assertEqual(p.returncode, 0, out + err)

        with open(log, "r", encoding="utf-8") as f:
            lines = [line.strip() for line in f if line.strip()]
        self.assertEqual(lines, ["ready", "ready", "enter", "exit", "enter", "exit"],
                         f"两个进程的临界区发生了重叠: {lines}")


if __name__ == "__main__":
    unittest.main()
