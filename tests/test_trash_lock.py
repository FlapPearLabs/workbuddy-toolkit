"""tests/test_trash_lock.py — 直接验证 _TrashLock 的跨进程互斥。

对抗审查指出：`test_concurrent_remove_same_alias` 在没有锁时也可能全绿
（失败方的 os.replace 抛 FileNotFoundError，断言照样成立）。这里不依赖
业务路径，直接让两个子进程持锁写同一份日志：

- 有锁：enter / exit / enter / exit（严格串行）
- 无锁：enter / enter / exit / exit（重叠）

变异校验把两处平台锁调用改成 pass 后，本用例必红。
"""
import os
import subprocess
import sys
import tempfile
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
with m._TrashLock():
    with open(sys.argv[3], "a", encoding="utf-8") as f:
        f.write("enter\n")
        f.flush()
    time.sleep(0.4)
    with open(sys.argv[3], "a", encoding="utf-8") as f:
        f.write("exit\n")
        f.flush()
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
            out, err = p.communicate(timeout=60)
            self.assertEqual(p.returncode, 0, out + err)

        with open(log, "r", encoding="utf-8") as f:
            lines = [line.strip() for line in f if line.strip()]
        self.assertEqual(lines, ["enter", "exit", "enter", "exit"],
                         f"两个进程的临界区发生了重叠: {lines}")


if __name__ == "__main__":
    unittest.main()
