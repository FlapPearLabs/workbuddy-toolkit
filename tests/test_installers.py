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


if __name__ == "__main__":
    unittest.main()
