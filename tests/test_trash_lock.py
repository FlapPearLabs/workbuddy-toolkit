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

CI 诊断（windows 3.9/3.12 曾两次出现"一方 480s 未就绪"）：
- 子进程在 spawned / imported / ready 三个关口打点，卡死位置可见；
- 父进程先收齐两个子进程的结果再断言，失败信息带双方完整输出；
- 子进程 stdin=DEVNULL（不继承父进程的管道），Windows 上加
  CREATE_NO_WINDOW（无头会话里控制台分配可能挂起）；
- 仅"屏障超时"（启动问题）允许整个场景重试一次；临界区重叠（真实
  缺陷）绝不重试——拆锁变异仍然必红（重叠是确定性的）。
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
import importlib.machinery, importlib.util, os, sys, time

O_FLAGS = os.O_WRONLY | os.O_CREAT | os.O_APPEND | getattr(os, "O_BINARY", 0)

def append(log_path, line):
    # 杀软/Defender 会对刚创建的文件短暂拒绝打开（PermissionError），
    # 有界重试穿过扫描窗口；真实 ACL 问题超时后照常抛出
    deadline = time.time() + 2.0
    while True:
        try:
            fd = os.open(log_path, O_FLAGS)
            try:
                os.write(fd, (line + "\n").encode("utf-8"))
            finally:
                os.close(fd)
            return
        except PermissionError:
            if time.time() >= deadline:
                raise
            time.sleep(0.05)

log_path = sys.argv[3]
append(log_path, "spawned")
loader = importlib.machinery.SourceFileLoader("wb_lock", sys.argv[1])
spec = importlib.util.spec_from_loader("wb_lock", loader)
m = importlib.util.module_from_spec(spec)
loader.exec_module(m)
append(log_path, "imported")
m.PROFILES_DIR = sys.argv[2]

def count_ready():
    try:
        with open(log_path, "rb") as f:
            return sum(1 for line in f if line.strip() == b"ready")
    except OSError:
        return 0

# 就绪屏障：两进程都到场后才抢锁，消除启动抖动造成的假绿
append(log_path, "ready")
deadline = time.time() + 240
while count_ready() < 2:
    if time.time() > deadline:
        try:
            with open(log_path, "rb") as f:
                snapshot = f.read().decode("utf-8", "replace")
        except OSError:
            snapshot = "(log 不可读)"
        sys.exit(f"barrier timeout: 另一个子进程未就绪，当前日志={snapshot!r}")
    time.sleep(0.05)

with m._TrashLock():
    append(log_path, "enter")
    time.sleep(0.2)
    append(log_path, "exit")
'''

CHILD_ENV = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
ORDER_OK = ["ready", "ready", "enter", "exit", "enter", "exit"]


def _popen_kwargs():
    kw = dict(stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
              env=CHILD_ENV, stdin=subprocess.DEVNULL)
    if sys.platform == "win32":
        kw["creationflags"] = subprocess.CREATE_NO_WINDOW
    return kw


def _run_scenario():
    """跑一次两进程互斥场景，返回 (raw_lines, [(idx, rc, out+err), ...])。

    无论成败都收齐两个子进程，失败信息永远带双方完整输出。
    """
    base = tempfile.mkdtemp(prefix="wb_lock_")
    try:
        profiles = os.path.join(base, "auth_profiles")
        os.makedirs(profiles, exist_ok=True)
        log = os.path.join(base, "lock.log")

        procs = [subprocess.Popen([sys.executable, "-c", CHILD, BIN_PATH, profiles, log],
                                  **_popen_kwargs())
                 for _ in range(2)]
        results = []
        for i, p in enumerate(procs):
            out, err = p.communicate(timeout=300)
            results.append((i, p.returncode, (out or "") + (err or "")))

        with open(log, "r", encoding="utf-8", errors="replace") as f:
            raw_lines = [line.strip() for line in f if line.strip()]
        return raw_lines, results
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
        last_raw, last_results = [], []
        for attempt in range(2):
            raw, results = _run_scenario()
            failures = [(i, rc, blob) for i, rc, blob in results if rc != 0]
            if not failures:
                last_raw = raw
                break
            # 只有"屏障超时"（启动问题，与被测对象无关）才值得重试；
            # 其他失败或顺序重叠是真实缺陷，直接判负
            retryable = all("barrier timeout" in blob for _, _, blob in failures)
            last_raw, last_results = raw, results
            if not retryable or attempt == 1:
                break

        detail = "\n".join(f"子进程 {i} rc={rc}：{blob}" for i, rc, blob in last_results)
        for i, rc, blob in last_results:
            self.assertEqual(rc, 0, f"子进程 {i} 失败（另一个：{detail}）")
        lines = [x for x in last_raw if x in ("ready", "enter", "exit")]
        self.assertEqual(lines, ORDER_OK,
                         f"两个进程的临界区发生了重叠: {last_raw}")


if __name__ == "__main__":
    unittest.main()
