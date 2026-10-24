"""tests/test_profile_remove.py — 账号删除功能的隔离测试。

全程使用临时 USERPROFILE/HOME/APPDATA/LOCALAPPDATA 子进程环境，
真实用户目录在 setUpClass/tearDownClass 做快照哈希对比，保证零污染。
"""
import hashlib
import json
import os
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
                        LOCALAPPDATA=os.path.join(self.base, "AppData", "Local"),
                        WB_NO_NOTIFY="1")   # 假账号不得触发真实桌面通知
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
        return sorted(os.listdir(self.trash)) if os.path.isdir(self.trash) else []

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
        self._make("alpha", "uid-a")
        self._run("remove", "alpha", "-y")
        stamped = self._trash_names()[0]
        r = self._run("remove", "--restore", stamped)
        self.assertEqual(r.returncode, 0)
        self.assertTrue(os.path.exists(os.path.join(self.prof, stamped)))
        self.assertEqual(self._trash_names(), [])

    def test_restore_accepts_name_without_suffix(self):
        self._make("alpha", "uid-a")
        self._run("remove", "alpha", "-y")
        stamped = self._trash_names()[0]
        r = self._run("remove", "--restore", stamped[:-5])  # 不带 .info 后缀
        self.assertEqual(r.returncode, 0)
        self.assertTrue(os.path.exists(os.path.join(self.prof, stamped)))

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
        """评审第 4 条：并发删同一别名时，恰好一个成功、回收站恰好一份"""
        self._make("alpha", "uid-a")
        procs = [
            subprocess.Popen([sys.executable, WB, "remove", "alpha", "-y"], env=self.env,
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            for _ in range(2)
        ]
        codes = sorted(p.wait(timeout=60) for p in procs)
        for p in procs:
            p.stdout.close()
            p.stderr.close()
        self.assertEqual(codes, [0, 1], f"并发删除退出码异常: {codes}")
        self.assertEqual(len(self._trash_names()), 1, self._trash_names())
        self.assertFalse(os.path.exists(os.path.join(self.prof, "alpha.info")))

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
        # basename 先把路径压回文件名，所以查找范围始终在 .trash 内；
        # 去掉 basename 才会走到"非法文件名"分支——两种都拒绝，这里锁定"不越界查找"
        self.assertIn("回收站里没有", r.stdout)
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
