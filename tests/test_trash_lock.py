"""tests/test_trash_lock.py — 直接验证 _TrashLock 的跨进程互斥。

对抗审查指出：`test_concurrent_remove_same_alias` 在没有锁时也可能全绿
（失败方的 os.replace 抛 FileNotFoundError，断言照样成立）。这里不依赖
业务路径，直接让两个子进程持锁写同一份日志：

- 有锁：ready / ready / enter / exit / enter / exit（严格串行）
- 无锁：enter / enter / exit / exit（重叠）

就绪屏障：两个子进程都先把 "ready" 写进日志并轮询到对方也就绪后才进
临界区——否则慢机器上子进程 B 比A 晚启动超过临界区时长时，无锁也会
表现为串行（假绿）。屏障保证两者一定在锁门口相遇，变异校验把平台锁
调用改成 pass 后本用例必红。

CI 稳定性：GitHub 的 Windows runner 偶发把子进程启动/导入拖到 90s+
（本用例曾在 3.9 / 3.12 两个作业上因一方 90s 未就绪而误报）。因此
- 父进程预编译 bin/workbuddy 并让子进程 PYTHONDONTWRITEBYTECODE=1，
  消除两子进程同时写同一 pyc 的竞争；
- 屏障超时放宽到 240s；
- 仅当失败原因是"屏障超时"（进程启动问题）时，整个场景重试一次；
  顺序断言失败（真的发生了重叠）绝不重试——那是要抓的缺陷。
"""
import os
import py_compile
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

# 就绪屏障：两进程都到场后才抢锁，消除启动抖动造成的假绿
append("ready")
deadline = time.time() + 240
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

CHILD_ENV = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
ORDER_OK = ["ready", "ready", "enter", "exit", "enter", "exit"]


def _run_scenario():
    """跑一次两进程互斥场景，返回 (lines, failures)。

    failures: [(proc_idx, returncode, out+err)]，仅收集 returncode != 0 的子进程。
    """
    base = tempfile.mkdtemp(prefix="wb_lock_")
    try:
        profiles = os.path.join(base, "auth_profiles")
        os.makedirs(profiles, exist_ok=True)
        log = os.path.join(base, "lock.log")

        procs = [
            subprocess.Popen([sys.executable, "-c", CHILD, BIN_PATH, profiles, log],
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                             text=True, env=CHILD_ENV)
            for _ in range(2)
        ]
        failures = []
        for i, p in enumerate(procs):
            out, err = p.communicate(timeout=300)
            if p.returncode != 0:
                failures.append((i, p.returncode, (out or "") + (err or "")))

        with open(log, "r", encoding="utf-8") as f:
            lines = [line.strip() for line in f if line.strip()]
        return lines, failures
    finally:
        import shutil
        shutil.rmtree(base, ignore_errors=True)


class TestTrashLock(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # 预编译主脚本：两个子进程不再各自首次编译/写同一份 pyc
        if not os.environ.get("WB_BIN"):
            py_compile.compile(BIN_PATH, doraise=True)

    def test_lock_serializes_two_processes(self):
        last_lines, last_failures = [], []
        for attempt in range(2):
            lines, failures = _run_scenario()
            if not failures:
                last_lines = lines
                break
            # 只有"屏障超时"（启动慢，与被测对象无关）才值得重试；
            # 其他失败或顺序重叠是真实缺陷，直接判负
            retryable = all("barrier timeout" in blob for _, _, blob in failures)
            last_lines, last_failures = lines, failures
            if not retryable or attempt == 1:
                break

        for i, rc, blob in last_failures:
            self.fail(f"子进程 {i} 退出码 {rc}：{blob}")
        self.assertEqual(last_lines, ORDER_OK,
                         f"两个进程的临界区发生了重叠: {last_lines}")


if __name__ == "__main__":
    unittest.main()
