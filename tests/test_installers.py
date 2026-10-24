#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Installer E2E Smoke Test
Runs on macOS, Linux, and Windows to verify that install.py and platform scripts succeed.
"""

import os
import sys
import shutil
import tempfile
import unittest
import subprocess
import importlib.util
from unittest import mock

if sys.platform == "win32":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

REPO_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

class TestInstallersE2E(unittest.TestCase):
    def setUp(self):
        self.temp_home = tempfile.mkdtemp()
        self.env = os.environ.copy()
        self.env["HOME"] = self.temp_home
        self.env["USERPROFILE"] = self.temp_home
        self.env["APPDATA"] = os.path.join(self.temp_home, "AppData", "Roaming")
        self.env["LOCALAPPDATA"] = os.path.join(self.temp_home, "AppData", "Local")
        self.env["PYTHONIOENCODING"] = "utf-8"
        self.env["PYTHONUTF8"] = "1"

    def tearDown(self):
        shutil.rmtree(self.temp_home, ignore_errors=True)

    def test_python_installer_and_uninstaller(self):
        """测试 python install.py 和 python uninstall.py 的端到端执行与文件产物"""
        installer = os.path.join(REPO_DIR, "install.py")
        uninstaller = os.path.join(REPO_DIR, "uninstall.py")

        # 1. 运行安装器
        res = subprocess.run([sys.executable, installer, "--no-input"], cwd=REPO_DIR, env=self.env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        self.assertEqual(res.returncode, 0, f"install.py 失败: {res.stderr}\n{res.stdout}")
        self.assertIn("安装部署全部完成", res.stdout)

        # 2. 检查安装物
        if sys.platform == "win32":
            bin_dir = os.path.join(self.temp_home, ".workbuddy", "bin")
            self.assertTrue(os.path.exists(os.path.join(bin_dir, "workbuddy")))
            self.assertTrue(os.path.exists(os.path.join(bin_dir, "workbuddy.cmd")))
            self.assertTrue(os.path.exists(os.path.join(bin_dir, "wb-help.cmd")))
            self.assertTrue(os.path.exists(os.path.join(bin_dir, "workbuddy-help.cmd")))
            self.assertTrue(os.path.exists(os.path.join(bin_dir, "wb-login.cmd")))
            self.assertTrue(os.path.exists(os.path.join(bin_dir, "wb-audit.cmd")))
            self.assertTrue(os.path.exists(os.path.join(bin_dir, "wb-list.cmd")))
            self.assertTrue(os.path.exists(os.path.join(bin_dir, "workbuddy-list.cmd")))
            self.assertTrue(os.path.exists(os.path.join(bin_dir, "wb-status.cmd")))
            self.assertTrue(os.path.exists(os.path.join(bin_dir, "workbuddy-status.cmd")))
            self.assertTrue(os.path.exists(os.path.join(bin_dir, "wb-switch.cmd")))
            self.assertTrue(os.path.exists(os.path.join(bin_dir, "wb-checkin.cmd")))
            self.assertTrue(os.path.exists(os.path.join(bin_dir, "wb-chat.cmd")))
            self.assertTrue(os.path.exists(os.path.join(bin_dir, "wb-doctor.cmd")))
            self.assertTrue(os.path.exists(os.path.join(bin_dir, "wb-usage.cmd")))
            self.assertTrue(os.path.exists(os.path.join(bin_dir, "workbuddy-usage.cmd")))
            self.assertTrue(os.path.exists(os.path.join(bin_dir, "wb-sandbox.cmd")))
            self.assertTrue(os.path.exists(os.path.join(bin_dir, "wb-tool.cmd")))
            self.assertTrue(os.path.exists(os.path.join(bin_dir, "workbuddy-tool.cmd")))
            self.assertTrue(os.path.exists(os.path.join(bin_dir, "workbuddy-log-guard.cmd")))
        else:
            bin_dir = os.path.join(self.temp_home, ".local", "bin")
            self.assertTrue(os.path.exists(os.path.join(bin_dir, "workbuddy")))
            self.assertTrue(os.path.exists(os.path.join(bin_dir, "workbuddy-log-guard")))
            self.assertTrue(os.path.exists(os.path.join(bin_dir, "wb-help")))
            self.assertTrue(os.path.exists(os.path.join(bin_dir, "workbuddy-help")))
            self.assertTrue(os.path.exists(os.path.join(bin_dir, "wb-login")))
            self.assertTrue(os.path.exists(os.path.join(bin_dir, "wb-audit")))
            self.assertTrue(os.path.exists(os.path.join(bin_dir, "wb-list")))
            self.assertTrue(os.path.exists(os.path.join(bin_dir, "workbuddy-list")))
            self.assertTrue(os.path.exists(os.path.join(bin_dir, "wb-status")))
            self.assertTrue(os.path.exists(os.path.join(bin_dir, "workbuddy-status")))
            self.assertTrue(os.path.exists(os.path.join(bin_dir, "wb-switch")))
            self.assertTrue(os.path.exists(os.path.join(bin_dir, "wb-checkin")))
            self.assertTrue(os.path.exists(os.path.join(bin_dir, "wb-chat")))
            self.assertTrue(os.path.exists(os.path.join(bin_dir, "wb-doctor")))
            self.assertTrue(os.path.exists(os.path.join(bin_dir, "wb-usage")))
            self.assertTrue(os.path.exists(os.path.join(bin_dir, "workbuddy-usage")))
            self.assertTrue(os.path.exists(os.path.join(bin_dir, "wb-sandbox")))
            self.assertTrue(os.path.exists(os.path.join(bin_dir, "wb-tool")))
            self.assertTrue(os.path.exists(os.path.join(bin_dir, "workbuddy-tool")))

        # 3. 运行卸载器（输入 n 回答不回滚数据库）
        unres = subprocess.run([sys.executable, uninstaller], input="n\n", cwd=REPO_DIR, env=self.env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        self.assertEqual(unres.returncode, 0, f"uninstall.py 失败: {unres.stderr}\n{unres.stdout}")
        self.assertIn("卸载完成", unres.stdout)

        # 4. 验证清理干净
        if sys.platform == "win32":
            self.assertFalse(os.path.exists(os.path.join(bin_dir, "wb-help.cmd")))
            self.assertFalse(os.path.exists(os.path.join(bin_dir, "workbuddy-help.cmd")))
            self.assertFalse(os.path.exists(os.path.join(bin_dir, "wb-list.cmd")))
            self.assertFalse(os.path.exists(os.path.join(bin_dir, "workbuddy-list.cmd")))
            self.assertFalse(os.path.exists(os.path.join(bin_dir, "wb-status.cmd")))
            self.assertFalse(os.path.exists(os.path.join(bin_dir, "workbuddy-status.cmd")))
            self.assertFalse(os.path.exists(os.path.join(bin_dir, "wb-usage.cmd")))
            self.assertFalse(os.path.exists(os.path.join(bin_dir, "workbuddy-usage.cmd")))
            self.assertFalse(os.path.exists(os.path.join(bin_dir, "wb-sandbox.cmd")))
            self.assertFalse(os.path.exists(os.path.join(bin_dir, "wb-tool.cmd")))
            self.assertFalse(os.path.exists(os.path.join(bin_dir, "workbuddy-tool.cmd")))
        else:
            self.assertFalse(os.path.exists(os.path.join(bin_dir, "workbuddy-log-guard")))
            self.assertFalse(os.path.exists(os.path.join(bin_dir, "wb-help")))
            self.assertFalse(os.path.exists(os.path.join(bin_dir, "workbuddy-help")))
            self.assertFalse(os.path.exists(os.path.join(bin_dir, "wb-list")))
            self.assertFalse(os.path.exists(os.path.join(bin_dir, "workbuddy-list")))
            self.assertFalse(os.path.exists(os.path.join(bin_dir, "wb-status")))
            self.assertFalse(os.path.exists(os.path.join(bin_dir, "workbuddy-status")))
            self.assertFalse(os.path.exists(os.path.join(bin_dir, "wb-usage")))
            self.assertFalse(os.path.exists(os.path.join(bin_dir, "workbuddy-usage")))
            self.assertFalse(os.path.exists(os.path.join(bin_dir, "wb-sandbox")))
            self.assertFalse(os.path.exists(os.path.join(bin_dir, "wb-tool")))
            self.assertFalse(os.path.exists(os.path.join(bin_dir, "workbuddy-tool")))

        # 验证 ~/.workbuddy/toolkit 伴随组件目录已物理 100% 移除
        toolkit_path = os.path.join(self.temp_home, ".workbuddy", "toolkit")
        self.assertFalse(os.path.exists(toolkit_path))

    def _load_installer(self, name):
        spec = importlib.util.spec_from_file_location(name, os.path.join(REPO_DIR, "install.py"))
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_startup_fallback_writes_utf16_with_bom(self):
        """WSH 只认 ANSI 或 UTF-16+BOM；UTF-8 无 BOM 在中文用户名下会读成乱码"""
        startup = os.path.join(self.env["APPDATA"], "Microsoft", "Windows",
                               "Start Menu", "Programs", "Startup")
        os.makedirs(startup)
        installer = self._load_installer("install_utf16")

        cmd = 'cmd /c ""C:\\Users\\张三\\pythonw.exe" "C:\\x" checkin >> "C:\\log" 2>&1"'
        with mock.patch.dict(os.environ, {"APPDATA": self.env["APPDATA"]}):
            path = installer._install_windows_startup_fallback("T", cmd)

        self.assertTrue(path and os.path.exists(path))
        with open(path, "rb") as f:
            raw = f.read()
        self.assertTrue(raw.startswith(b"\xff\xfe"))       # UTF-16LE BOM，WSH 才认
        body = raw[2:].decode("utf-16-le")
        self.assertEqual(body.count("\r\n"), 2)            # 三行、两处换行，不多不少
        self.assertNotIn("\r\r\n", body)                   # 解码后断言才有意义
        self.assertIn("张三", body)                        # 中文路径无损往返

    def test_startup_fallback_can_be_removed(self):
        """任务计划恢复或卸载时必须能删掉，否则会一天跑两次"""
        startup = os.path.join(self.env["APPDATA"], "Microsoft", "Windows",
                               "Start Menu", "Programs", "Startup")
        os.makedirs(startup)
        installer = self._load_installer("install_remove")

        with mock.patch.dict(os.environ, {"APPDATA": self.env["APPDATA"]}):
            path = installer._install_windows_startup_fallback("T", "x")
            self.assertTrue(path and os.path.exists(path))
            self.assertTrue(installer._remove_windows_startup_fallback("T"))
            self.assertFalse(os.path.exists(path))

    def test_scheduler_success_removes_leftover_startup_entry(self):
        """任务计划恢复后必须删掉旧的 .vbs，否则同一天会触发两次

        把 setup_scheduler 里那句 _remove_windows_startup_fallback() 改成 pass，
        这条用例就会失败——它是本 PR 互斥承诺的唯一守卫。
        """
        installer = self._load_installer("install_mutex")
        startup = os.path.join(self.env["APPDATA"], "Microsoft", "Windows",
                               "Start Menu", "Programs", "Startup")
        os.makedirs(startup)

        with mock.patch.dict(os.environ, {"APPDATA": self.env["APPDATA"]}):
            installer._install_windows_startup_fallback("WorkBuddyDailyCheckin", "x")
            vbs = installer._startup_fallback_path()
            self.assertTrue(os.path.exists(vbs))

            with mock.patch("sys.platform", "win32"), \
                    mock.patch.object(installer.subprocess, "run") as run:
                run.return_value = mock.Mock(returncode=0, stdout="", stderr="")
                installer.setup_scheduler("/tmp/bin", "/tmp", {"checkin": True})

            self.assertFalse(os.path.exists(vbs), "任务计划成功后旧启动项必须被删除")
    def test_launcher_skips_store_stub_and_fails_loudly(self):
        """启动器必须过滤 WindowsApps 占位符，找不到解释器时以 9009 明确失败"""
        if sys.platform != "win32":
            self.skipTest("launcher 只在 Windows 上生成")

        installer = os.path.join(REPO_DIR, "install.py")
        subprocess.run([sys.executable, installer, "--no-input"], cwd=REPO_DIR,
                       env=self.env, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

        launcher = os.path.join(self.temp_home, ".workbuddy", "bin", "workbuddy.cmd")
        with open(launcher, "r", encoding="ascii", errors="replace") as f:
            body = f.read()

        self.assertIn("findstr /v", body)
        self.assertIn("exit /b 9009", body)
        self.assertNotIn("echo(%%i|", body)

    def test_launcher_prefers_real_python_over_store_stub(self):
        """真 Python 在前、商店 0 字节占位符在后时，必须选中真 Python"""
        if sys.platform != "win32":
            self.skipTest("Windows only")

        installer = os.path.join(REPO_DIR, "install.py")
        subprocess.run([sys.executable, installer, "--no-input"], cwd=REPO_DIR,
                       env=self.env, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

        # 造一个与商店占位符同形态的 0 字节假 python，排在真 python 之后
        stub_dir = os.path.join(self.temp_home, "WindowsApps")
        os.makedirs(stub_dir, exist_ok=True)
        open(os.path.join(stub_dir, "python.exe"), "wb").close()

        env = dict(self.env)
        env["PATH"] = env.get("PATH", "") + os.pathsep + stub_dir
        launcher = os.path.join(self.temp_home, ".workbuddy", "bin", "wb-help.cmd")

        res = subprocess.run(["cmd", "/c", launcher], env=env,
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)

    def test_launcher_ignores_store_stub_when_it_comes_first(self):
        """占位符排在 PATH 第一位时也不能被选中：要么用真 Python，要么明确 9009

        旧写法把过滤放在 `if ... echo | findstr ... || set` 里，第一轮选中占位符
        后就再也不会被替换；这条用例专门覆盖那个顺序。
        """
        if sys.platform != "win32":
            self.skipTest("Windows only")

        installer = os.path.join(REPO_DIR, "install.py")
        subprocess.run([sys.executable, installer, "--no-input"], cwd=REPO_DIR,
                       env=self.env, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

        stub_dir = os.path.join(self.temp_home, "WindowsApps")
        os.makedirs(stub_dir, exist_ok=True)
        open(os.path.join(stub_dir, "python.exe"), "wb").close()

        env = dict(self.env)
        env["PATH"] = stub_dir + os.pathsep + env.get("PATH", "")   # 占位符在前
        launcher = os.path.join(self.temp_home, ".workbuddy", "bin", "wb-help.cmd")

        res = subprocess.run(["cmd", "/c", launcher], env=env,
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

        # 0 = 选中了真 Python；9009 = 过滤后确实没有可用解释器。
        # 其它退出码意味着占位符被选中并执行了，正是这条用例要挡的。
        self.assertIn(res.returncode, (0, 9009), res.stdout + res.stderr)

    def test_launcher_falls_back_to_bundled_python(self):
        """PATH 里没有 python 时，应能选中 WorkBuddy 自带解释器

        早期实现用 `for /f ... in ('"%WBCAND%" -c "..."')` 解析版本号，cmd 会把
        以引号开头的命令串当成文件名，解析失败且静默落空；这条分支于是永远选不中，
        最终落到 9009。本用例专门盯这条路径。

        注意：需要本机存在 %USERPROFILE%\\.workbuddy\\binaries\\python\\versions\\*，
        只有装了 WorkBuddy 客户端的机器才会真正执行，CI 上恒 skip——它不构成门禁，
        门禁是 test_launcher_reports_missing_python 与占位符那两条。
        """
        if sys.platform != "win32":
            self.skipTest("Windows only")

        bundled_root = os.path.join(os.path.expanduser("~"), ".workbuddy",
                                    "binaries", "python", "versions")
        if not os.path.isdir(bundled_root):
            self.skipTest("本机没有 WorkBuddy 自带解释器，无法覆盖这条分支")

        installer = os.path.join(REPO_DIR, "install.py")
        subprocess.run([sys.executable, installer, "--no-input"], cwd=REPO_DIR,
                       env=self.env, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

        launcher = os.path.join(self.temp_home, ".workbuddy", "bin", "wb-help.cmd")
        env = dict(self.env)
        env["USERPROFILE"] = os.path.expanduser("~")   # launcher 运行时按它找内置解释器
        env["PATH"] = r"C:\Windows\System32"           # 确保 PATH 里既没有 python 也没有 py

        res = subprocess.run(["cmd", "/c", launcher], env=env,
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)

    def test_launcher_reports_missing_python(self):
        """PATH 里完全没有解释器时，应以 9009 失败并给出可读提示

        与 `test_launcher_skips_store_stub_and_fails_loudly` 的区别：那条只断言
        生成文本里有没有某个字符串，这条真的跑一遍启动器。
        """
        if sys.platform != "win32":
            self.skipTest("Windows only")

        installer = os.path.join(REPO_DIR, "install.py")
        subprocess.run([sys.executable, installer, "--no-input"], cwd=REPO_DIR,
                       env=self.env, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

        launcher = os.path.join(self.temp_home, ".workbuddy", "bin", "wb-help.cmd")
        env = dict(self.env)
        env["PATH"] = r"C:\Windows\System32"     # 既没有 python 也没有 py

        # cmd 自己「命令找不到」的原生退出码也是 9009：启动器若没生成，
        # 下面的断言会在一片绿意中通过。先确认它真的存在。
        self.assertTrue(os.path.isfile(launcher), "启动器没生成，这条测试就没有意义")

        # 不用 text=True：提示文案的编码跟随系统代码页（中文 Windows 是 GBK），
        # 而 WorkBuddy 客户端会强制 PYTHONUTF8=1，utf-8 解码 GBK 会直接崩掉读取线程。
        # bytes 模式对任何编码都安全；本分支落盘纯 ASCII 文案，同形字节。
        res = subprocess.run(["cmd", "/c", launcher], env=env,
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.assertEqual(res.returncode, 9009, res.stdout + res.stderr)
        # 9009 必须是我们主动返回的：stderr 里要有商店版那句可执行的下一步。
        # 本分支落盘纯 ASCII（"Store-installed ..."）；#20 合入后中文 Windows
        # 会落 GBK 中文（"不支持 Microsoft Store 版 Python..."）。两种文案没有
        # 公共强锚点，用 or 各自命中，避免本地化合入时本用例假红。
        self.assertTrue(
            b"Store-installed" in res.stderr or b"Microsoft Store" in res.stderr,
            f"9009 提示缺少商店版说明: {res.stderr!r}",
        )
        self.assertTrue(res.stderr.strip(), "9009 分支必须输出可读提示")


def _copy_repo(dest):
    shutil.copytree(REPO_DIR, dest, ignore=shutil.ignore_patterns(".git", "__pycache__", ".ruff_cache"))
    return dest


class TestInstallerLayouts(unittest.TestCase):
    """覆盖 README 推荐的真实安装位置：仓库直接 clone 在 ~/.workbuddy/toolkit。"""

    def setUp(self):
        self.temp_home = tempfile.mkdtemp()
        self.env = os.environ.copy()
        self.env.update({
            "HOME": self.temp_home,
            "USERPROFILE": self.temp_home,
            "APPDATA": os.path.join(self.temp_home, "AppData", "Roaming"),
            "LOCALAPPDATA": os.path.join(self.temp_home, "AppData", "Local"),
            "PYTHONIOENCODING": "utf-8",
            "PYTHONUTF8": "1",
        })

    def tearDown(self):
        shutil.rmtree(self.temp_home, ignore_errors=True)

    def _sidecar_files(self, root):
        return sorted(f for f in os.listdir(os.path.join(root, "sidecar")) if not f.startswith("__"))

    def test_install_py_from_recommended_clone_location_keeps_sidecar(self):
        clone = _copy_repo(os.path.join(self.temp_home, ".workbuddy", "toolkit"))
        before = self._sidecar_files(clone)
        res = subprocess.run([sys.executable, os.path.join(clone, "install.py"), "--no-input"],
                             cwd=clone, env=self.env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        self.assertEqual(res.returncode, 0, res.stderr + res.stdout)
        self.assertIn("安装部署全部完成", res.stdout)
        self.assertEqual(self._sidecar_files(clone), before, "安装器不得删除仓库自身的 sidecar 源码")

    def test_install_py_registers_no_background_services_by_default(self):
        res = subprocess.run([sys.executable, os.path.join(REPO_DIR, "install.py"), "--no-input"],
                             cwd=REPO_DIR, env=self.env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        self.assertEqual(res.returncode, 0, res.stderr + res.stdout)
        launch_dir = os.path.join(self.temp_home, "Library", "LaunchAgents")
        self.assertFalse(os.path.isdir(launch_dir) and any(f.startswith("com.workbuddy.") for f in os.listdir(launch_dir)))
        systemd_dir = os.path.join(self.temp_home, ".config", "systemd", "user")
        self.assertFalse(os.path.isdir(systemd_dir) and any(f.startswith("workbuddy-") for f in os.listdir(systemd_dir)))
        self.assertFalse(os.path.exists(os.path.join(self.temp_home, ".gemini", "config", "sidecars", "workbuddy-checkin")))
        self.assertIn("未注册任何后台任务", res.stdout)

    @unittest.skipIf(sys.platform == "win32", "install.sh 仅用于 macOS / Linux")
    def test_install_sh_deploys_sidecar_for_any_clone_location(self):
        clone = _copy_repo(os.path.join(self.temp_home, "src", "workbuddy-toolkit"))
        res = subprocess.run(["bash", os.path.join(clone, "install.sh"), "--no-input"],
                             cwd=clone, env=self.env, stdin=subprocess.DEVNULL,
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        self.assertEqual(res.returncode, 0, res.stderr + res.stdout)
        deployed = os.path.join(self.temp_home, ".workbuddy", "toolkit", "sidecar", "credit_meter.py")
        self.assertTrue(os.path.exists(deployed), "install.sh 必须部署 sidecar 模块")
        usage = subprocess.run([sys.executable, os.path.join(self.temp_home, ".local", "bin", "wb-usage"), "--help"],
                               env=self.env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        self.assertEqual(usage.returncode, 0, usage.stderr)

    @unittest.skipIf(sys.platform == "win32", "install.sh 仅用于 macOS / Linux")
    def test_install_sh_from_recommended_clone_location_keeps_sidecar(self):
        clone = _copy_repo(os.path.join(self.temp_home, ".workbuddy", "toolkit"))
        before = self._sidecar_files(clone)
        res = subprocess.run(["bash", os.path.join(clone, "install.sh"), "--no-input"],
                             cwd=clone, env=self.env, stdin=subprocess.DEVNULL,
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        self.assertEqual(res.returncode, 0, res.stderr + res.stdout)
        self.assertEqual(self._sidecar_files(clone), before)


class TestAliasConsistency(unittest.TestCase):
    """三处别名清单必须都注册 wb-remove（评审指出缺一致性测试兜底）"""

    def test_remove_alias_registered_in_all_installers(self):
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        for name in ("install.py", "install.sh", "uninstall.py"):
            with open(os.path.join(root, name), "r", encoding="utf-8") as f:
                self.assertIn("wb-remove", f.read(), f"{name} 未注册 wb-remove")


if __name__ == "__main__":
    unittest.main()
