"""tests/test_profile_remove.py — 账号删除功能的隔离测试。

全程使用临时 USERPROFILE/HOME/APPDATA/LOCALAPPDATA 子进程环境，
真实用户目录在 setUpClass/tearDownClass 做快照哈希对比，保证零污染。
"""
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

REPO_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# WB_BIN 允许变异校验脚本指向"故意改坏"的副本，用来证明这些用例真的能抓到缺陷
WB = os.environ.get("WB_BIN") or os.path.join(REPO_DIR, "bin", "workbuddy")


def _snapshot(root):
    """只记录路径集合，不做内容哈希——测试期间真实客户端刷新 token 只改内容，
    不该被误判为"测试污染"；本断言守的是"没有新增/删除文件"。"""
    out = set()
    for root_, dirs, files in os.walk(root):
        for f in files:
            out.add(os.path.relpath(os.path.join(root_, f), root))
        for dn in dirs:
            out.add(os.path.relpath(os.path.join(root_, dn), root) + os.sep)
    return out


def _assert_isolated(env, base):
    """事前拦截：四个环境变量必须全部落在临时目录里。

    tearDownClass 的快照是"事后"断言，测试中途崩溃时根本不会执行；
    get_auth_file() 的候选顺序是 APPDATA → LOCALAPPDATA → USERPROFILE，
    只改后两个时 AUTH_FILE 仍指向真实客户端凭据，测试里的切号会把它覆盖掉。
    """
    base_real = os.path.realpath(base)
    for key in ("USERPROFILE", "HOME", "APPDATA", "LOCALAPPDATA"):
        got = os.path.realpath(env.get(key) or "")
        if not got.startswith(base_real):
            raise AssertionError(f"{key} 未重定向到临时目录: {got}")


class TestProfileRemove(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # POSIX 上没有 USERPROFILE 环境变量，统一用 expanduser
        cls.real_profile = os.path.join(os.path.expanduser("~"), ".workbuddy", "auth_profiles")
        cls._before = _snapshot(cls.real_profile)
        cls.base = tempfile.mkdtemp(prefix="wb_remove_test_")

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.base, ignore_errors=True)
        after = _snapshot(cls.real_profile)
        if after != cls._before:
            raise AssertionError("测试污染了真实用户目录！")

    def setUp(self):
        # 每个用例一个独立的临时 HOME，互不串味
        self.base = tempfile.mkdtemp(prefix="wb_remove_case_")
        self.env = dict(os.environ, USERPROFILE=self.base, HOME=self.base,
                        APPDATA=os.path.join(self.base, "AppData", "Roaming"),
                        LOCALAPPDATA=os.path.join(self.base, "AppData", "Local"))
        self.prof = os.path.join(self.base, ".workbuddy", "auth_profiles")
        os.makedirs(self.prof)
        self.trash = os.path.join(self.prof, ".trash")

    def tearDown(self):
        shutil.rmtree(self.base, ignore_errors=True)

    def _make(self, name, uid, active=False):
        with open(os.path.join(self.prof, f"{name}.info"), "w", encoding="utf-8") as f:
            json.dump({"account": {"nickname": f"昵称_{name}", "uid": uid, "uin": "0"},
                       "auth": {"expiresAt": 0}}, f, ensure_ascii=False)
        if active:
            auth_dir = os.path.join(self.base, ".workbuddy", "auth")
            os.makedirs(auth_dir, exist_ok=True)
            with open(os.path.join(auth_dir, "workbuddy-desktop.info"), "w", encoding="utf-8") as f:
                json.dump({"account": {"nickname": f"昵称_{name}", "uid": uid, "uin": "0"},
                           "auth": {"expiresAt": 0}}, f, ensure_ascii=False)

    def _run(self, *args, stdin=None, script=None):
        _assert_isolated(self.env, self.base)   # 每次起子进程前都拦一次
        return subprocess.run([sys.executable, script or WB, *args], env=self.env, input=stdin,
                              capture_output=True, text=True, timeout=60)

    def _write_info(self, path, uid, token, nickname="n"):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"account": {"uid": uid, "nickname": nickname, "uin": "0"},
                       "auth": {"accessToken": token, "expiresAt": 0}}, f, ensure_ascii=False)

    def _read_bytes(self, path):
        with open(path, "rb") as f:
            return f.read()

    def _trash_names(self):
        # 只看凭据文件：跨进程锁 .trash.lock 在 auth_profiles 下，不在 .trash 里
        if not os.path.isdir(self.trash):
            return []
        return sorted(n for n in os.listdir(self.trash) if n.endswith(".info"))

    def _load_wb(self):
        """进程内加载 bin/workbuddy 并指向本用例的临时目录（不走子进程）。"""
        import importlib.machinery
        import importlib.util
        loader = importlib.machinery.SourceFileLoader("wb_inline_test", WB)
        spec = importlib.util.spec_from_loader("wb_inline_test", loader)
        wb = importlib.util.module_from_spec(spec)
        loader.exec_module(wb)
        wb.PROFILES_DIR = self.prof
        wb.AUTH_FILE = os.path.join(self.base, ".workbuddy", "auth", "workbuddy-desktop.info")
        return wb

    # ------------------------------------------------------------------

    def test_remove_requires_alias(self):
        r = self._run("remove")
        self.assertEqual(r.returncode, 1)
        self.assertIn("请提供要删除的账号别名", r.stdout)

    def test_remove_unknown_alias(self):
        self._make("alpha", "uid-a")
        r = self._run("remove", "ghost")
        self.assertEqual(r.returncode, 1)
        self.assertIn("未找到唯一匹配", r.stdout)
        self.assertIn("alpha", r.stdout)

    def test_remove_confirm_y_moves_to_trash(self):
        self._make("alpha", "uid-a")
        r = self._run("remove", "alpha", stdin="y\n")
        self.assertEqual(r.returncode, 0)
        self.assertIn("昵称_alpha", r.stdout)
        self.assertFalse(os.path.exists(os.path.join(self.prof, "alpha.info")))
        self.assertTrue(any(n.startswith("alpha.20") for n in self._trash_names()), self._trash_names())

    def test_remove_timestamp_collision(self):
        self._make("alpha", "uid-a")
        os.makedirs(self.trash)
        open(os.path.join(self.trash, "alpha.info"), "wb").close()
        r = self._run("remove", "alpha", stdin="y\n")
        self.assertEqual(r.returncode, 0)
        names = self._trash_names()
        # 原占位文件必须原样保留，新文件带时间戳后缀
        self.assertIn("alpha.info", names)
        self.assertTrue(any(n.startswith("alpha.20") for n in names), names)

    def test_remove_timestamp_double_collision(self):
        """同秒二次删除不得覆盖回收站既有文件（曾在此处静默丢凭据）"""
        self._make("alpha", "uid-a")
        os.makedirs(self.trash)
        # 用真实的时间戳格式预置两个碰撞名——历史文件名（1999 年）物理上
        # 撞不上当天 stamp，while 循环一次都不进，断言对任何实现都成立
        import datetime as _dt
        stamp = _dt.datetime.now().strftime("%Y%m%d-%H%M%S")
        open(os.path.join(self.trash, f"alpha.{stamp}.info"), "wb").close()
        open(os.path.join(self.trash, f"alpha.{stamp}_1.info"), "wb").close()
        before = set(self._trash_names())
        r = self._run("remove", "alpha", stdin="y\n")
        self.assertEqual(r.returncode, 0)
        after = set(self._trash_names())
        self.assertTrue(before.issubset(after), f"回收站既有文件被覆盖: {before - after}")
        self.assertEqual(len(after), len(before) + 1)

    def test_remove_cancel_eof(self):
        self._make("beta", "uid-b", active=True)
        r = self._run("remove", "beta", stdin="")
        self.assertEqual(r.returncode, 1)
        self.assertIn("已取消", r.stdout)
        self.assertTrue(os.path.exists(os.path.join(self.prof, "beta.info")))

    def test_remove_cancel_n(self):
        self._make("beta", "uid-b")
        r = self._run("remove", "beta", stdin="n\n")
        self.assertEqual(r.returncode, 1)
        self.assertTrue(os.path.exists(os.path.join(self.prof, "beta.info")))

    def test_remove_force_still_confirms(self):
        """--force 只放宽活跃账号保护，不再兼任"跳过确认"（评审第 2 条）"""
        self._make("beta", "uid-b")
        r = self._run("remove", "beta", "--force", stdin="n\n")
        self.assertEqual(r.returncode, 1)
        self.assertIn("已取消", r.stdout)
        self.assertTrue(os.path.exists(os.path.join(self.prof, "beta.info")))

    def test_remove_yes_still_confirms_active_account(self):
        """-y 不能跳过活跃账号的二次确认（评审第 3 条）"""
        self._make("work", "uid-work", active=True)
        r = self._run("remove", "work", "-y", stdin="")
        self.assertEqual(r.returncode, 1)
        self.assertIn("当前登录账号", r.stdout)
        self.assertTrue(os.path.exists(os.path.join(self.prof, "work.info")))

    def test_remove_force_relaxes_active_protection(self):
        """--force + -y 才允许无交互删除活跃账号的备份"""
        self._make("work2", "uid-work2", active=True)
        r = self._run("remove", "work2", "-y", "--force", stdin="")
        self.assertEqual(r.returncode, 0)
        self.assertFalse(os.path.exists(os.path.join(self.prof, "work2.info")))

    def test_remove_active_account_warns_and_tombstones(self):
        """删除活跃账号：黄色警告 + 次日签到的自动发现不再复活该账号"""
        self._make("work", "uid-work", active=True)
        r = self._run("remove", "work", stdin="y\n")
        self.assertEqual(r.returncode, 0)
        self.assertIn("当前正在登录使用", r.stdout)

        # 模拟次日 09:00 的 checkin：活跃 uid 已不在 profiles 且在墓碑里，
        # 自动发现必须跳过而不是以昵称别名重新收录
        r2 = self._run("checkin")
        self.assertIn("跳过自动入库", r2.stdout)
        self.assertNotIn("已自动保存 Profile", r2.stdout)
        # profiles 顶层不允许出现任何账号文件（.trash 子目录除外）
        self.assertEqual([f for f in os.listdir(self.prof) if f.endswith(".info")], [])

    def test_remove_unknown_flag_rejected(self):
        """破坏性命令必须拒绝未知选项——--dry-run 被吞掉就真删了"""
        self._make("beta", "uid-b")
        r = self._run("remove", "beta", "--dry-run")
        self.assertEqual(r.returncode, 1)
        self.assertIn("未知选项", r.stdout)
        self.assertTrue(os.path.exists(os.path.join(self.prof, "beta.info")))

    def test_remove_multiple_args_rejected(self):
        self._make("alpha", "uid-a")
        self._make("beta", "uid-b")
        r = self._run("remove", "alpha", "beta")
        self.assertEqual(r.returncode, 1)
        self.assertIn("一次只能删除一个账号", r.stdout)
        self.assertTrue(os.path.exists(os.path.join(self.prof, "alpha.info")))
        self.assertTrue(os.path.exists(os.path.join(self.prof, "beta.info")))

    def test_remove_exit_code_success(self):
        self._make("alpha", "uid-a")
        self.assertEqual(self._run("remove", "alpha", "-y").returncode, 0)

    def test_tui_end_to_end(self):
        """TUI：主菜单2 → 账号5 → 选号 → y → 返回 → 退出，落进回收站"""
        self._make("delta", "uid-d")
        r = self._run("tool", stdin="2\n5\n1\ny\n0\n0\n")
        self.assertIn("已移入回收站", r.stdout)
        self.assertTrue(any("delta" in n for n in self._trash_names()))

    # ---------------- 回收站生命周期（精进 #1） ----------------

    def test_list_trash_shows_nicknames(self):
        self._make("alpha", "uid-a")
        self._run("remove", "alpha", "-y")
        r = self._run("remove", "--list-trash")
        self.assertIn("回收站 (1 项)", r.stdout)
        self.assertIn("昵称_alpha", r.stdout)

    def test_list_trash_empty(self):
        r = self._run("remove", "--list-trash")
        self.assertIn("回收站为空", r.stdout)

    def test_restore_moves_back(self):
        """恢复必须还原删除前的别名，而不是把时间戳带进别名"""
        self._make("alpha", "uid-a")
        self._run("remove", "alpha", "-y")
        stamped = self._trash_names()[0]
        r = self._run("remove", "--restore", stamped)
        self.assertEqual(r.returncode, 0)
        self.assertIn("已恢复为账号别名 'alpha'", r.stdout)
        self.assertTrue(os.path.exists(os.path.join(self.prof, "alpha.info")))
        self.assertEqual(self._trash_names(), [])

    def test_restore_accepts_name_without_suffix(self):
        self._make("alpha", "uid-a")
        self._run("remove", "alpha", "-y")
        stamped = self._trash_names()[0]
        r = self._run("remove", "--restore", stamped[:-5])  # 不带 .info 后缀
        self.assertEqual(r.returncode, 0)
        self.assertTrue(os.path.exists(os.path.join(self.prof, "alpha.info")))

    def test_restore_tolerates_surrounding_whitespace(self):
        # 命令行粘贴常带首尾空白：校验按 strip 后的入参放行，查找也必须用同一份，
        # 否则 " xxx.info " 会被拼成不存在的 " xxx.info .info" 并误报不存在
        self._make("alpha", "uid-a")
        self._run("remove", "alpha", "-y")
        stamped = self._trash_names()[0]
        r = self._run("remove", "--restore", f"  {stamped} ")
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertTrue(os.path.exists(os.path.join(self.prof, "alpha.info")))
        self.assertEqual(self._trash_names(), [])

    def test_restore_missing_errors(self):
        r = self._run("remove", "--restore", "ghost")
        self.assertEqual(r.returncode, 1)
        self.assertIn("回收站里没有", r.stdout)

    def test_empty_trash_needs_confirm(self):
        self._make("alpha", "uid-a")
        self._run("remove", "alpha", "-y")
        r = self._run("remove", "--empty-trash", stdin="n\n")
        self.assertEqual(r.returncode, 1)
        self.assertEqual(len(self._trash_names()), 1)

    def test_empty_trash_destroys(self):
        self._make("alpha", "uid-a")
        self._run("remove", "alpha", "-y")
        r = self._run("remove", "--empty-trash", "-y")
        self.assertEqual(r.returncode, 0)
        self.assertEqual(self._trash_names(), [])

    def test_yes_flag_skips_confirm(self):
        """-y/--yes 是跳过普通确认的一等公民；--force 只管放宽保护"""
        self._make("alpha", "uid-a")
        self.assertEqual(self._run("remove", "alpha", "-y").returncode, 0)
        self._make("beta", "uid-b")
        self.assertEqual(self._run("remove", "beta", "--yes").returncode, 0)
        self._make("gamma", "uid-c")
        self.assertEqual(self._run("remove", "gamma", "--force", stdin="y\n").returncode, 0)
        self.assertEqual([f for f in os.listdir(self.prof) if f.endswith(".info")], [])

    def test_status_shows_trash_count(self):
        """精进 #1：wb-status 露出回收站条目数"""
        self._make("alpha", "uid-a")
        self._run("remove", "alpha", "-y")
        r = self._run("status")
        self.assertIn("回收站: 1 项", r.stdout)

    def test_interactive_menu_delete_entry(self):
        """精进 #4：无参数菜单的 d 入口 → 删除流程 → q 退出"""
        self._make("alpha", "uid-a")
        r = self._run(stdin="d\n1\ny\nq\n")
        self.assertIn("已移入回收站", r.stdout)
        self.assertTrue(any("alpha" in n for n in self._trash_names()))

    # ---------------- 第二轮对抗审查修复的回归 ----------------

    def test_wb_remove_argv0_dispatch(self):
        """P0：POSIX 上 wb-remove 是指向 workbuddy 的软链，argv[0]=wb-remove。
        缺 argv[0] 分发时，wb-remove <别名> 会落进兜底分支被解释成"快捷切号"。"""
        script = os.path.join(self.base, "wb-remove")
        shutil.copyfile(WB, script)
        self._make("alpha", "uid-a", active=True)
        r = self._run("--list-trash", script=script)
        self.assertIn("回收站为空", r.stdout)
        self.assertNotIn("未知命令或账号", r.stdout)
        # 删除路径同样必须走 remove 而不是切号：切号会改写 AUTH_FILE
        auth_file = os.path.join(self.base, ".workbuddy", "auth", "workbuddy-desktop.info")
        auth_before = open(auth_file, "rb").read()
        r = self._run("alpha", "-y", "--force", script=script)
        self.assertEqual(r.returncode, 0)
        self.assertIn("已移入回收站", r.stdout)
        self.assertEqual(open(auth_file, "rb").read(), auth_before, "wb-remove 触发了切号！")

    def test_concurrent_remove_same_alias(self):
        """并发删同一别名：恰好一个成功，且成功方打印的恢复路径必须真实存在。

        Windows 上两个进程对同一源同时 os.replace 可能都返回成功，但文件
        只落在其中一方；若不做校验，失败方也会打印成功并给出不存在的恢复
        文件名（对抗审查 P1）。
        """
        self._make("alpha", "uid-a")
        procs = [
            subprocess.Popen([sys.executable, WB, "remove", "alpha", "-y"], env=self.env,
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            for _ in range(2)
        ]
        outs = []
        for p in procs:
            out, _err = p.communicate(timeout=60)
            outs.append(out)
        codes = sorted(p.returncode for p in procs)
        self.assertEqual(codes, [0, 1], f"并发删除退出码异常: {codes}")
        self.assertEqual(len(self._trash_names()), 1, self._trash_names())
        self.assertFalse(os.path.exists(os.path.join(self.prof, "alpha.info")))

        winners = [o for o in outs if "已移入回收站" in o]
        self.assertEqual(len(winners), 1, f"两个进程都声称成功: {outs}")
        m = re.search(r"已移入回收站:\s*(.+?)\s*$", winners[0], re.M)
        self.assertTrue(m, winners[0])
        self.assertTrue(os.path.isfile(m.group(1).strip()), f"恢复路径不存在: {m.group(1)}")

    def test_remove_mode_flags_mutually_exclusive(self):
        """--restore 与 --empty-trash 同用会静默销毁想恢复的文件，必须拒绝"""
        self._make("alpha", "uid-a")
        self._run("remove", "alpha", "-y")
        r = self._run("remove", "--restore", "whatever", "--empty-trash", "-y")
        self.assertEqual(r.returncode, 1)
        self.assertIn("不能同时使用", r.stdout)
        self.assertEqual(len(self._trash_names()), 1, "回收站被误清空")

    def test_restore_rejects_path_traversal(self):
        """--restore ../victim 不得越界查找/搬动备份库之外的文件"""
        self._make("alpha", "uid-a")
        self.assertEqual(self._run("remove", "alpha", "-y").returncode, 0)

        # 在备份库之外放一个真实存在的 .info：只有它存在，"越界"才有意义
        outside = os.path.join(os.path.dirname(self.prof), "victim.info")
        with open(outside, "w", encoding="utf-8") as f:
            f.write('{"account": {"uid": "uid-victim"}}')
        with open(outside, "rb") as f:
            before = f.read()

        r = self._run("remove", "--restore", "../victim")
        self.assertEqual(r.returncode, 1)
        # 入参带路径成分时直接拒绝，连 .trash 之外的路径都不会被查找
        self.assertIn("非法的回收站文件名", r.stdout)
        with open(outside, "rb") as f:
            self.assertEqual(f.read(), before, "备份库外的文件被搬动")
        self.assertFalse(os.path.exists(os.path.join(self.prof, "victim.info")))
        self.assertTrue(any("alpha" in n for n in self._trash_names()))

    def test_restore_rejects_duplicate_uid(self):
        """恢复出同 uid 的第二份副本会让 checkin 对同一账号签两次，必须拒绝"""
        self._make("alpha", "uid-dup")
        self._run("remove", "alpha", "-y")
        self._make("beta", "uid-dup")  # 同 uid 不同别名
        stamped = self._trash_names()[0]
        r = self._run("remove", "--restore", stamped)
        self.assertEqual(r.returncode, 1)
        self.assertIn("已在备份库中", r.stdout)
        self.assertIn(stamped, self._trash_names())
        self.assertTrue(os.path.exists(os.path.join(self.prof, "beta.info")))

    def test_restore_rejects_corrupt_entry(self):
        """0 字节/坏 JSON 不得恢复成功——否则备份库会出现命令看不见的账号"""
        os.makedirs(self.trash, exist_ok=True)
        bad = os.path.join(self.trash, "broken.20261024-120000-000000.info")
        open(bad, "wb").close()
        r = self._run("remove", "--restore", "broken.20261024-120000-000000.info")
        self.assertEqual(r.returncode, 1)
        self.assertIn("无法解析", r.stdout)
        self.assertTrue(os.path.exists(bad), "坏条目被搬走或删除了")
        self.assertEqual([f for f in os.listdir(self.prof) if f.endswith(".info")], [])

    def test_restore_rejects_missing_uid(self):
        os.makedirs(self.trash, exist_ok=True)
        p = os.path.join(self.trash, "noid.20261024-120000-000000.info")
        with open(p, "w", encoding="utf-8") as f:
            f.write('{"account": {"nickname": "x"}}')
        r = self._run("remove", "--restore", "noid.20261024-120000-000000.info")
        self.assertEqual(r.returncode, 1)
        self.assertIn("缺少账号 uid", r.stdout)
        self.assertTrue(os.path.exists(p))

    # ---------------- 交叉审查必修 1：确认集合 == 删除集合 ----------------

    def test_empty_trash_spares_entries_added_during_confirm(self):
        """确认期间新增的条目从未被展示，绝不能随确认一起销毁（必修 1，已实机复现）"""
        import io
        from unittest import mock
        self._make("alpha", "uid-a")
        self._make("beta", "uid-b")
        self.assertEqual(self._run("remove", "alpha", "-y").returncode, 0)
        self.assertEqual(self._run("remove", "beta", "-y").returncode, 0)
        shown, late = self._trash_names()
        wb = self._load_wb()
        listings = [[shown], [shown, late]]   # 展示时只见 shown，锁内多了 late
        with mock.patch.object(wb, "_trash_files", side_effect=lambda: listings.pop(0)), \
             mock.patch.object(wb, "get_trashed_uids", return_value={"uid-a"}), \
             mock.patch("builtins.input", return_value="y"), \
             mock.patch("sys.stdout", new=io.StringIO()) as fake_out:
            self.assertTrue(wb.empty_trash())
        self.assertFalse(os.path.exists(os.path.join(self.trash, shown)),
                         "已确认的条目没有被删除")
        self.assertTrue(os.path.exists(os.path.join(self.trash, late)),
                        "确认期间新增的条目被销毁了——用户从未见过它")
        self.assertIn("新增", fake_out.getvalue())

    def test_empty_trash_reports_when_shown_already_gone(self):
        import io
        from unittest import mock
        self._make("alpha", "uid-a")
        self.assertEqual(self._run("remove", "alpha", "-y").returncode, 0)
        shown = self._trash_names()[0]
        wb = self._load_wb()
        with mock.patch.object(wb, "_trash_files", side_effect=[[shown], []]), \
             mock.patch.object(wb, "get_trashed_uids", return_value=set()), \
             mock.patch("builtins.input", return_value="y"), \
             mock.patch("sys.stdout", new=io.StringIO()) as fake_out:
            self.assertTrue(wb.empty_trash())
        self.assertIn("未删除任何内容", fake_out.getvalue())

    # ---------------- 交叉审查必修 3：目录级 fail closed ----------------

    def test_trash_strict_raises_when_dir_unreadable(self):
        """_trash_files 把 listdir 的 OSError 吞成 [] 时，墓碑会整体失效（必修 3）"""
        from unittest import mock
        wb = self._load_wb()
        os.makedirs(self.trash, exist_ok=True)
        with mock.patch("os.listdir", side_effect=PermissionError(13, "denied")):
            with self.assertRaises(OSError):
                wb.get_trashed_uids(strict=True)
            self.assertEqual(wb.get_trashed_uids(), set(),
                             "非 strict 调用方（status 等排障命令）不应崩栈")

    # ---------------- 交叉审查必修 4：别名无损还原 ----------------

    def test_restore_preserves_alias_exactly(self):
        """别名不经过任何改写：a.b 删除再恢复还是 a.b（此前会被洗成 a_b）"""
        self._make("a.b", "uid-dot")
        self.assertEqual(self._run("remove", "a.b", "-y").returncode, 0)
        stamped = self._trash_names()[0]
        self.assertTrue(stamped.startswith("a.b."))
        r = self._run("remove", "--restore", stamped)
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertTrue(os.path.exists(os.path.join(self.prof, "a.b.info")),
                        "别名被改写，不再是删除前的 a.b")
        self.assertEqual(self._trash_names(), [])

    def test_restore_preserves_alias_with_space(self):
        self._make("a b", "uid-sp")
        self.assertEqual(self._run("remove", "a b", "-y").returncode, 0)
        stamped = self._trash_names()[0]
        r = self._run("remove", "--restore", stamped)
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertTrue(os.path.exists(os.path.join(self.prof, "a b.info")))

    def test_restore_keeps_underscores_exactly(self):
        """_a_ 不能被 strip 成 a——那是另一个别名"""
        self._make("_a_", "uid-us")
        self.assertEqual(self._run("remove", "_a_", "-y").returncode, 0)
        stamped = self._trash_names()[0]
        r = self._run("remove", "--restore", stamped)
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertTrue(os.path.exists(os.path.join(self.prof, "_a_.info")))

    @unittest.skipUnless(sys.platform != "win32", "Windows 文件名不允许 :；POSIX 上 a:b 合法")
    def test_restore_preserves_colon_alias_posix(self):
        self._make("a:b", "uid-colon")
        self.assertEqual(self._run("remove", "a:b", "-y").returncode, 0)
        stamped = self._trash_names()[0]
        r = self._run("remove", "--restore", stamped)
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertTrue(os.path.exists(os.path.join(self.prof, "a:b.info")))

    def test_restore_rejects_aliasless_name(self):
        os.makedirs(self.trash, exist_ok=True)
        p = os.path.join(self.trash, ".info")
        with open(p, "w", encoding="utf-8") as f:
            json.dump({"account": {"uid": "uid-x"}}, f)
        r = self._run("remove", "--restore", ".info")
        self.assertEqual(r.returncode, 1)
        self.assertIn("无法还原出合法账号别名", r.stdout)
        self.assertTrue(os.path.exists(p))

    # ---------------- 交叉审查必修 5：--purge 单条销毁 ----------------

    def test_purge_removes_single_entry_only(self):
        self._make("alpha", "uid-a")
        self._make("beta", "uid-b")
        self.assertEqual(self._run("remove", "alpha", "-y").returncode, 0)
        self.assertEqual(self._run("remove", "beta", "-y").returncode, 0)
        first, second = self._trash_names()
        r = self._run("remove", "--purge", first, stdin="y\n")
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertIn("已彻底销毁", r.stdout)
        self.assertEqual(self._trash_names(), [second], "把别的条目也删了")

    def test_purge_skips_confirm_with_yes(self):
        os.makedirs(self.trash, exist_ok=True)
        p = os.path.join(self.trash, "residue.20261025-000000-000000.info")
        open(p, "wb").close()
        r = self._run("remove", "--purge", "residue.20261025-000000-000000.info", "-y")
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertNotIn("确认销毁", r.stdout)
        self.assertFalse(os.path.exists(p))

    def test_purge_zero_byte_residue_hinted(self):
        os.makedirs(self.trash, exist_ok=True)
        p = os.path.join(self.trash, "residue.20261025-000000-000000.info")
        open(p, "wb").close()
        r = self._run("remove", "--purge", "residue.20261025-000000-000000.info", stdin="y\n")
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertIn("0 字节", r.stdout)

    def test_purge_rejects_traversal_and_missing(self):
        r = self._run("remove", "--purge", "../victim")
        self.assertEqual(r.returncode, 1)
        self.assertIn("非法的回收站文件名", r.stdout)
        r2 = self._run("remove", "--purge", "ghost.info")
        self.assertEqual(r2.returncode, 1)
        self.assertIn("回收站里没有", r2.stdout)

    def test_purge_rejects_extra_positional_and_mode_mix(self):
        r = self._run("remove", "--purge", "a.info", "b.info")
        self.assertEqual(r.returncode, 1)
        r2 = self._run("remove", "--purge", "a.info", "--restore", "b.info")
        self.assertEqual(r2.returncode, 1)
        self.assertIn("不能同时使用", r2.stdout)

    # ---------------- 交叉审查 P2：参数解析吞位置参数 / -- 支持 ----------------

    def test_remove_rejects_positional_before_restore(self):
        """remove alpha --restore x 此前静默忽略 alpha（已实机复现）"""
        self._make("alpha", "uid-a")
        r = self._run("remove", "alpha", "--restore", "whatever.info")
        self.assertEqual(r.returncode, 1)
        self.assertIn("只接受一个文件名", r.stdout)
        self.assertTrue(os.path.exists(os.path.join(self.prof, "alpha.info")),
                        "alpha 被静默跳过，用户却以为它被删了")

    def test_remove_rejects_duplicate_mode_flag(self):
        r = self._run("remove", "--restore", "a.info", "--restore")
        self.assertEqual(r.returncode, 1)
        self.assertIn("重复出现", r.stdout)

    def test_remove_double_dash_allows_dash_alias(self):
        """首评必修 2：工具能造出 -old 这种别名，remove -- -old 必须能删"""
        self._make("-old", "uid-old")
        r = self._run("remove", "-old", "-y")
        self.assertEqual(r.returncode, 1)
        self.assertIn("未知选项", r.stdout)
        r2 = self._run("remove", "-y", "--", "-old")
        self.assertEqual(r2.returncode, 0, r2.stdout + r2.stderr)
        self.assertFalse(os.path.exists(os.path.join(self.prof, "-old.info")))

    def test_remove_double_dash_requires_alias(self):
        r = self._run("remove", "--")
        self.assertEqual(r.returncode, 1)
        self.assertIn("'--' 之后要跟账号别名", r.stdout)

    def test_remove_double_dash_rejected_with_modes(self):
        r = self._run("remove", "--restore", "--", "x.info")
        self.assertEqual(r.returncode, 1)
        self.assertIn("不能与回收站模式同用", r.stdout)

    # ---------------- 交叉审查 P3：AUTH_FILE 合法 JSON 非对象 ----------------

    def test_remove_tolerates_non_dict_auth_json(self):
        self._make("alpha", "uid-a")
        auth_dir = os.path.join(self.base, ".workbuddy", "auth")
        os.makedirs(auth_dir, exist_ok=True)
        with open(os.path.join(auth_dir, "workbuddy-desktop.info"), "w", encoding="utf-8") as f:
            f.write("[]")
        r = self._run("remove", "alpha", "-y")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertNotIn("Traceback", r.stdout + r.stderr)
        self.assertFalse(os.path.exists(os.path.join(self.prof, "alpha.info")))

    # ---------------- 复核必修 3：无 uid 凭据删除侧对称拒绝 ----------------

    def test_remove_refuses_uidless_profile(self):
        """无 uid 的凭据此前能删但打印的恢复命令必然失败——现在删除侧拒绝：

        没有 uid 就建不了删除墓碑（checkin 会重新收录），恢复命令也过不了
        fail-closed 校验。两头的坑一起堵上，文件原样保留待手工处理。
        """
        self._make("legacy", "")
        r = self._run("remove", "legacy", "-y")
        self.assertEqual(r.returncode, 1)
        self.assertIn("缺少账号 uid", r.stdout)
        self.assertIn("无法安全删除", r.stdout)
        self.assertTrue(os.path.exists(os.path.join(self.prof, "legacy.info")),
                        "无 uid 凭据被静默删掉了")

    def test_restore_restores_alias_with_suffix_on_collision(self):
        """原别名被其他账号占用时用 _1，绝不覆盖既有凭据"""
        self._make("alpha", "uid-a")
        self._run("remove", "alpha", "-y")
        stamped = self._trash_names()[0]
        self._write_info(os.path.join(self.prof, "alpha.info"), "uid-other", "OTHER", "其他")
        before = self._read_bytes(os.path.join(self.prof, "alpha.info"))

        r = self._run("remove", "--restore", stamped)
        self.assertEqual(r.returncode, 0)
        self.assertIn("alpha_1", r.stdout)
        self.assertTrue(os.path.exists(os.path.join(self.prof, "alpha_1.info")))
        self.assertEqual(self._read_bytes(os.path.join(self.prof, "alpha.info")), before)

    def test_restore_rejects_option_as_filename(self):
        r = self._run("remove", "--restore", "-y")
        self.assertEqual(r.returncode, 1)
        self.assertIn("而不是选项", r.stdout)

    def test_checkin_fails_closed_on_corrupt_trash(self):
        """回收站条目读不出时，签到必须放弃自动入库，而不是把已删账号复活"""
        auth = os.path.join(self.base, ".workbuddy", "auth", "workbuddy-desktop.info")
        self._write_info(auth, "uid-new", "TOKEN", "新号")
        os.makedirs(self.trash, exist_ok=True)
        with open(os.path.join(self.trash, "broken.info"), "w", encoding="utf-8") as f:
            f.write("{")

        r = self._run("checkin")
        self.assertIn("跳过自动入库", r.stdout)
        self.assertIn("--purge", r.stdout, "警告必须给出单条清除的补救命令")
        self.assertFalse(os.path.exists(os.path.join(self.prof, "新号.info")),
                         "墓碑读不出时仍然把账号自动入库了")

    def test_tombstone_does_not_shadow_resaved_account(self):
        """删号后重新 save 同 uid：签到不该每天刷"已被删除，跳过自动入库"的假消息。

        这条锁定墓碑判断与"是否已在库"的先后顺序——顺序放反时用例必红。
        """
        self._make("work", "uid-work", active=True)
        self.assertEqual(self._run("remove", "work", stdin="y\n").returncode, 0)
        self.assertEqual(self._run("save", "work").returncode, 0)
        r = self._run("checkin")
        self.assertNotIn("跳过自动入库", r.stdout)
        self.assertTrue(os.path.exists(os.path.join(self.prof, "work.info")))

    def test_cancel_is_zero_write(self):
        """回答 n 时不得改写备份字节（评审行内 P2：原先确认前就 sync 了）"""
        self._make("work", "uid-work", active=True)
        prof_path = os.path.join(self.prof, "work.info")
        self._write_info(prof_path, "uid-work", "OLD", "旧昵称")
        auth_file = os.path.join(self.base, ".workbuddy", "auth", "workbuddy-desktop.info")
        self._write_info(auth_file, "uid-work", "NEW", "新昵称")
        before = self._read_bytes(prof_path)

        r = self._run("remove", "work", stdin="n\n")
        self.assertEqual(r.returncode, 1)
        self.assertIn("已取消", r.stdout)
        self.assertEqual(self._read_bytes(prof_path), before, "取消后备份字节被改写")
        self.assertIn("旧昵称", before.decode("utf-8"))

    def test_sync_only_touches_target_profile(self):
        """同 uid 的另一个别名不得被同步改写（评审行内 P2：原先写同 uid 全部）"""
        self._make("alpha", "uid-shared")
        self._make("beta", "uid-shared")
        prof_alpha = os.path.join(self.prof, "alpha.info")
        prof_beta = os.path.join(self.prof, "beta.info")
        self._write_info(prof_alpha, "uid-shared", "OLD-A", "A")
        self._write_info(prof_beta, "uid-shared", "OLD-B", "B")
        auth_file = os.path.join(self.base, ".workbuddy", "auth", "workbuddy-desktop.info")
        self._write_info(auth_file, "uid-shared", "NEW", "NEW-NICK")
        before_beta = self._read_bytes(prof_beta)

        r = self._run("remove", "alpha", stdin="y\n")   # 活跃账号 → 二次确认
        self.assertEqual(r.returncode, 0)
        self.assertEqual(self._read_bytes(prof_beta), before_beta, "同 uid 的非目标 profile 被改写")
        trash_file = os.path.join(self.trash, self._trash_names()[0])
        self.assertIn("NEW", self._read_bytes(trash_file).decode("utf-8"))

    # ---------------- P2：参数严格性与回收站形态异常 ----------------

    def test_force_rejected_with_trash_modes(self):
        """--force 只表示放宽活跃账号保护，对回收站模式无意义，必须拒绝而非静默忽略"""
        self._make("alpha", "uid-a")
        self._run("remove", "alpha", "-y")
        stamped = self._trash_names()[0]
        r = self._run("remove", "--restore", stamped, "--force")
        self.assertEqual(r.returncode, 1)
        self.assertIn("不适用于", r.stdout)
        self.assertIn(stamped, self._trash_names())
        r2 = self._run("remove", "--empty-trash", "--force")
        self.assertEqual(r2.returncode, 1)
        self.assertEqual(len(self._trash_names()), 1, "回收站被误清空")

    def test_mode_flags_reject_positional(self):
        """--list-trash / --empty-trash 带位置参数时不得静默忽略"""
        self._make("alpha", "uid-a")
        r = self._run("remove", "--list-trash", "alpha")
        self.assertEqual(r.returncode, 1)
        self.assertIn("不接受位置参数", r.stdout)
        r2 = self._run("remove", "--empty-trash", "alpha", "-y")
        self.assertEqual(r2.returncode, 1)
        self.assertTrue(os.path.exists(os.path.join(self.prof, "alpha.info")))

    def test_restore_rejects_extra_positional(self):
        self._make("alpha", "uid-a")
        self._run("remove", "alpha", "-y")
        stamped = self._trash_names()[0]
        r = self._run("remove", "--restore", stamped, "beta")
        self.assertEqual(r.returncode, 1)
        self.assertIn("只接受一个文件名", r.stdout)
        self.assertIn(stamped, self._trash_names())

    def test_status_json_has_trash_count(self):
        self._make("alpha", "uid-a")
        self._run("remove", "alpha", "-y")
        r = self._run("status", "--json")
        self.assertEqual(r.returncode, 0)
        self.assertEqual(json.loads(r.stdout)["trash_count"], 1)

    def test_restore_handles_broken_trash_gracefully(self):
        """.trash 被换成普通文件时，恢复也要优雅报错，不抛栈。

        锁文件已移到 auth_profiles/.trash.lock（不在 .trash 里，避免目录
        删除/重建导致换 inode）——锁能正常获取，失败发生在"条目不存在"
        这一步，同样必须优雅、不许崩栈。
        """
        with open(self.trash, "w", encoding="utf-8") as f:
            f.write("not a dir")
        r = self._run("remove", "--restore", "anything")
        self.assertEqual(r.returncode, 1)
        self.assertIn("回收站里没有", r.stdout)
        self.assertNotIn("Traceback", r.stdout + r.stderr)

    @unittest.skipIf(sys.platform == "win32", "POSIX 权限位")
    def test_trash_dir_is_0700(self):
        self._make("alpha", "uid-a")
        self.assertEqual(self._run("remove", "alpha", "-y").returncode, 0)
        self.assertEqual(os.stat(self.trash).st_mode & 0o777, 0o700)

    # ---------------- 隔离与跨平台证据（评审标注"无法核验"的三项） ----------------

    def test_isolation_guard_rejects_real_paths(self):
        """正断言不是摆设：把 APPDATA 指回真实目录时必须拦下来"""
        bad = dict(self.env, APPDATA=os.path.join(os.path.expanduser("~"), "AppData", "Roaming"))
        with self.assertRaises(AssertionError):
            _assert_isolated(bad, self.base)

    def test_child_process_sees_temp_home(self):
        """子进程里 expanduser('~') 必须落在临时目录——证明重定向真的生效"""
        r = subprocess.run([sys.executable, "-c", "import os;print(os.path.expanduser('~'))"],
                           env=self.env, capture_output=True, text=True, timeout=30)
        self.assertEqual(r.returncode, 0)
        self.assertTrue(os.path.realpath(r.stdout.strip()).startswith(os.path.realpath(self.base)),
                        r.stdout)

    @unittest.skipIf(sys.platform == "win32", "POSIX 同盘语义")
    def test_trash_is_same_device_as_profiles(self):
        """POSIX：回收站与备份库同 st_dev，os.replace 才是原子 rename 而非跨盘拷贝"""
        self._make("alpha", "uid-a")
        self.assertEqual(self._run("remove", "alpha", "-y").returncode, 0)
        trash_file = os.path.join(self.trash, self._trash_names()[0])
        self.assertEqual(os.stat(trash_file).st_dev, os.stat(self.prof).st_dev)


if __name__ == "__main__":
    unittest.main()
