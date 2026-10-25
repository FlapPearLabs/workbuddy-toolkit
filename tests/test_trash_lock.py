"""tests/test_trash_lock.py — 验证 _TrashLock 的跨进程互斥。

两套测法，按平台各取所长（维护者评审建议）：

- POSIX：**进程内**连续两次获取 `_TrashLock`——两个实例各自 open 出独立的
  open file description，第二个 `flock(LOCK_EX|LOCK_NB)` 必然 EWOULDBLOCK，
  与调度完全无关、确定性失败；释放后必须能再次获取。零子进程、零文件
  导入抖动、既不会假绿也不会 skip。拆掉 flock 该用例必红。
- Windows：msvcrt 字节锁的语义与 flock 不同（同进程/同句柄行为有差异），
  保留**两个子进程**的多轮屏障用例——子进程代码由父进程 AST 抽取锁实现
  后经 `python -c` 内嵌传入，零模块文件读取，对 runner/杀软的进程启动
  抖动免疫（完整踩坑史见 git log 814c215/268b759/0a42f7d/78221f9）。

屏障/多轮的原理：每轮两个子进程各写一条 ready 并轮询到"本轮双方就绪"
后才进临界区，保证两者一定在锁门口相遇——无锁时必然 enter/enter 重叠，
与启动快慢无关；只有"双方始终未相遇"（环境确实跑不起来）才 skip。
"""
import ast
import importlib.machinery
import importlib.util
import os
import subprocess
import sys
import tempfile
import unittest

REPO_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BIN_PATH = os.environ.get("WB_BIN") or os.path.join(REPO_DIR, "bin", "workbuddy")

# 从 bin/workbuddy 抽出的锁实现 + 其依赖（供 Windows 子进程内嵌使用）
LOCK_MODULE_TEMPLATE = '''"""由 tests/test_trash_lock.py 从 bin/workbuddy 抽取的锁实现，勿手改。"""
import os
import sys
import time

PROFILES_DIR = None  # 由子进程注入


{code}
'''


def _extract_lock_module(source):
    """从工具箱源码里抽出 _TrashLock 与它的两个依赖函数的源码文本。"""
    defs = {n.name: ast.get_source_segment(source, n)
            for n in ast.parse(source).body
            if isinstance(n, (ast.FunctionDef, ast.ClassDef))}
    missing = {"_TrashLock", "get_trash_dir", "_ensure_trash_dir"} - set(defs)
    if missing:
        raise RuntimeError(f"bin/workbuddy 里找不到: {sorted(missing)}")
    # 用占位符替换而非 str.format：抽取的源码里可能出现花括号
    return LOCK_MODULE_TEMPLATE.replace("{code}", "\n\n\n".join(
        defs[n] for n in ("get_trash_dir", "_ensure_trash_dir", "_TrashLock")))


def _load_wb_module(profiles_dir):
    """进程内加载 bin/workbuddy（POSIX 用例用）。"""
    loader = importlib.machinery.SourceFileLoader("wb_lock_under_test", BIN_PATH)
    spec = importlib.util.spec_from_loader("wb_lock_under_test", loader)
    m = importlib.util.module_from_spec(spec)
    loader.exec_module(m)
    m.PROFILES_DIR = profiles_dir
    return m


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


def _count_markers(log_path, marker):
    try:
        with open(log_path, "rb") as f:
            return sum(1 for line in f if line.strip() == marker.encode())
    except OSError:
        return 0


log_path = sys.argv[2]
PROFILES_DIR = sys.argv[1]

ROUNDS = 3
for _round in range(ROUNDS):
    # 第 1 轮给 240s 吸收进程启动抖动，后续轮双方都已在跑，60s 足够
    _barrier_deadline = time.time() + (240 if _round == 0 else 60)
    _append(log_path, "ready")
    while _count_markers(log_path, "ready") < 2 * (_round + 1):
        if time.time() > _barrier_deadline:
            _append(log_path, "giveup")
            sys.exit(0)          # 对方始终未到场：由父进程按 ready 数判定
        time.sleep(0.05)
    with _TrashLock():
        _append(log_path, "enter")
        time.sleep(0.15)
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


def _run_scenario():
    """跑一次多轮互斥场景，返回 (lines, [(idx, rc, out+err), ...])。

    无论成败都收齐两个子进程，失败信息永远带双方完整输出。
    """
    base = tempfile.mkdtemp(prefix="wb_lock_")
    try:
        profiles = os.path.join(base, "auth_profiles")
        os.makedirs(profiles, exist_ok=True)
        log = os.path.join(base, "lock.log")

        with open(BIN_PATH, "r", encoding="utf-8") as f:
            child_src = _extract_lock_module(f.read()) + WORKER
        compile(child_src, "<lock child>", "exec")   # 语法自检，尽早报错

        procs = [subprocess.Popen([sys.executable, "-c", child_src, profiles, log],
                                  **_popen_kwargs())
                 for _ in range(2)]
        results = []
        for i, p in enumerate(procs):
            out, err = p.communicate(timeout=400)
            results.append((i, p.returncode, (out or "") + (err or "")))

        with open(log, "r", encoding="utf-8", errors="replace") as f:
            lines = [line.strip() for line in f if line.strip()]
        return lines, results
    finally:
        import shutil
        shutil.rmtree(base, ignore_errors=True)


class TestTrashLock(unittest.TestCase):
    def test_lock_excludes_second_holder_same_process(self):
        """同进程两个 _TrashLock 实例 = 两个 open file description：

        POSIX：第二个 flock(LOCK_EX|LOCK_NB) 必然 EWOULDBLOCK；Windows：
        msvcrt 字节锁对同进程的另一个 fd 同样拒绝（实测 Errno 13，锁属于
        文件区域而非句柄）。与调度完全无关的确定性互斥证明——拆掉任一
        平台锁该用例必红（变异校验「拆锁」两条的目标），零子进程、零
        文件导入抖动、既不会假绿也不会 skip。
        """
        base = tempfile.mkdtemp(prefix="wb_lock_posix_")
        self.addCleanup(lambda: __import__("shutil").rmtree(base, ignore_errors=True))
        profiles = os.path.join(base, "auth_profiles")
        wb = _load_wb_module(profiles)

        with wb._TrashLock(timeout=2.0):
            with self.assertRaises(TimeoutError):
                with wb._TrashLock(timeout=2.0):
                    pass   # 持锁期间第二个持有者必须被拒
        with wb._TrashLock(timeout=2.0):
            pass           # 释放之后必须能再次获取

    @unittest.skipUnless(sys.platform == "win32",
                         "Windows msvcrt 语义与 flock 不同，用两个真实子进程验证")
    def test_lock_serializes_two_processes(self):
        lines, results = _run_scenario()

        detail = "\n".join(f"子进程 {i} rc={rc}：{blob}" for i, rc, blob in results)
        for i, rc, blob in results:
            self.assertEqual(rc, 0, f"子进程 {i} 失败（另一个：{detail}）")

        ready = lines.count("ready")
        enters_exits = [x for x in lines if x in ("enter", "exit")]
        giveups = lines.count("giveup")

        if ready < 2 or (giveups and not enters_exits):
            # 两个子进程始终未能相遇（runner 把进程创建/首行执行拖过
            # 240s），环境确实跑不起来。skip 但不掩护坏锁：拆锁变异下
            # 只要相遇一次就会留下 enter/enter 重叠并 FAIL。
            self.skipTest(
                f"两个子进程始终未能相遇（ready={ready}, giveup={giveups}），"
                f"runner/杀软拖慢进程创建；互斥语义由本机与变异校验验证")
            return

        # 不变量 1：至少完成一轮完整临界区
        self.assertGreaterEqual(len(enters_exits), 2,
                                f"没有任何一轮完整临界区: {lines}")
        # 不变量 2：enter/exit 严格交替且从 enter 开始（无锁必然 enter,enter）
        for i, x in enumerate(enters_exits):
            self.assertEqual(x, "enter" if i % 2 == 0 else "exit",
                             f"第 {i} 个临界区标记错位，临界区发生了重叠: {lines}")
        # 不变量 3：双方至少各到场一次（ready 成对出现）
        self.assertEqual(ready % 2, 0,
                         f"ready 数应为偶数（屏障成对放行）: {lines}")


if __name__ == "__main__":
    unittest.main()
