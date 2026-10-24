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

CI 踩坑史（GitHub windows runner，四轮迭代）：
1. 子进程打开"刚创建"的日志/锁文件 PermissionError —— 杀软/Defender
   对新文件的实时扫描窗口。修复：append 与生产 _TrashLock.__enter__
   都做有界重试（2s）。
2. 子进程卡死在 exec_module（打点 spawned→无 imported）数分钟——
   先后试过"导入完整工具箱""AST 抽取成 86 行小文件再导入"，全都
   复现：只要子进程通过 importlib 读模块文件，runner 上就可能被拖住
   数分钟（大小无关、新旧无关）。最终修复：**子进程不用 importlib**
   ——父进程用 AST 抽出 _TrashLock / get_trash_dir / _ensure_trash_dir
   的真实源码，直接拼进 `python -c` 的代码文本，纯内存编译，子进程
   除日志与锁文件外零文件读取。
3. 抽的是源码文本：变异校验对 bin/workbuddy 的"拆锁"改动会原样进入
   子进程代码，CAUGHT 逻辑不变。
"""
import ast
import os
import subprocess
import sys
import tempfile
import unittest

REPO_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BIN_PATH = os.environ.get("WB_BIN") or os.path.join(REPO_DIR, "bin", "workbuddy")

# 子进程代码 = 抽取的锁实现 + 工作流逻辑，全部经 -c 传入（无模块文件）
WORKER = '''

def _append(log_path, line):
    # 杀软/Defender 会对刚创建的文件短暂拒绝打开（PermissionError），
    # 有界重试穿过扫描窗口；真实 ACL 问题超时后照常抛出
    o_flags = os.O_WRONLY | os.O_CREAT | os.O_APPEND | getattr(os, "O_BINARY", 0)
    deadline = time.time() + 2.0
    while True:
        try:
            fd = os.open(log_path, o_flags)
            try:
                os.write(fd, (line + "\\n").encode("utf-8"))
            finally:
                os.close(fd)
            return
        except PermissionError:
            if time.time() >= deadline:
                raise
            time.sleep(0.05)


def _count_ready(log_path):
    try:
        with open(log_path, "rb") as f:
            return sum(1 for line in f if line.strip() == b"ready")
    except OSError:
        return 0


log_path = sys.argv[2]
_append(log_path, "spawned")
# 锁实现已在 -c 源码里（无 importlib、无模块文件）
PROFILES_DIR = sys.argv[1]
_append(log_path, "imported")

# 就绪屏障：两进程都到场后才抢锁，消除启动抖动造成的假绿
_append(log_path, "ready")
_deadline = time.time() + 240
while _count_ready(log_path) < 2:
    if time.time() > _deadline:
        try:
            with open(log_path, "rb") as f:
                _snapshot = f.read().decode("utf-8", "replace")
        except OSError:
            _snapshot = "(log 不可读)"
        sys.exit(f"barrier timeout: 另一个子进程未就绪，当前日志={_snapshot!r}")
    time.sleep(0.05)

with _TrashLock():
    _append(log_path, "enter")
    time.sleep(0.2)
    _append(log_path, "exit")
'''

CHILD_ENV = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
ORDER_OK = ["ready", "ready", "enter", "exit", "enter", "exit"]


def _popen_kwargs():
    kw = dict(stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
              env=CHILD_ENV, stdin=subprocess.DEVNULL)
    if sys.platform == "win32":
        kw["creationflags"] = subprocess.CREATE_NO_WINDOW
    return kw


def _extract_lock_code(source):
    """从工具箱源码里抽出 _TrashLock 与它的两个依赖函数的源码文本。"""
    defs = {n.name: ast.get_source_segment(source, n)
            for n in ast.parse(source).body
            if isinstance(n, (ast.FunctionDef, ast.ClassDef))}
    missing = {"_TrashLock", "get_trash_dir", "_ensure_trash_dir"} - set(defs)
    if missing:
        raise RuntimeError(f"bin/workbuddy 里找不到: {sorted(missing)}")
    header = "import os\nimport sys\nimport time\n\nPROFILES_DIR = None\n"
    # 用占位符替换而非 str.format：抽取的源码里可能出现花括号
    return header + "\n\n" + "\n\n\n".join(
        defs[n] for n in ("get_trash_dir", "_ensure_trash_dir", "_TrashLock"))


def _run_scenario():
    """跑一次两进程互斥场景，返回 (raw_lines, [(idx, rc, out+err), ...])。

    无论成败都收齐两个子进程，失败信息永远带双方完整输出。
    """
    base = tempfile.mkdtemp(prefix="wb_lock_")
    try:
        profiles = os.path.join(base, "auth_profiles")
        os.makedirs(profiles, exist_ok=True)
        log = os.path.join(base, "lock.log")

        with open(BIN_PATH, "r", encoding="utf-8") as f:
            child_src = _extract_lock_code(f.read()) + WORKER
        compile(child_src, "<lock child>", "exec")   # 语法自检，尽早报错

        procs = [subprocess.Popen([sys.executable, "-c", child_src, profiles, log],
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
    def test_lock_serializes_two_processes(self):
        last_raw, last_results = [], []
        for attempt in range(2):
            raw, results = _run_scenario()
            failures = [(i, rc, blob) for i, rc, blob in results if rc != 0]
            if not failures:
                last_raw = raw
                break
            # 只有"屏障超时"（启动/环境问题，与被测对象无关）才值得重试；
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
