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
        res = subprocess.run([sys.executable, installer], cwd=REPO_DIR, env=self.env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        self.assertEqual(res.returncode, 0, f"install.py 失败: {res.stderr}\n{res.stdout}")
        self.assertIn("安装部署全部完成", res.stdout)

        # 2. 检查安装物
        if sys.platform == "win32":
            bin_dir = os.path.join(self.temp_home, ".workbuddy", "bin")
            self.assertTrue(os.path.exists(os.path.join(bin_dir, "workbuddy")))
            self.assertTrue(os.path.exists(os.path.join(bin_dir, "workbuddy.cmd")))
            self.assertTrue(os.path.exists(os.path.join(bin_dir, "wb-switch.cmd")))
            self.assertTrue(os.path.exists(os.path.join(bin_dir, "wb-checkin.cmd")))
            self.assertTrue(os.path.exists(os.path.join(bin_dir, "wb-chat.cmd")))
        else:
            bin_dir = os.path.join(self.temp_home, ".local", "bin")
            self.assertTrue(os.path.exists(os.path.join(bin_dir, "workbuddy")))
            self.assertTrue(os.path.exists(os.path.join(bin_dir, "wb-switch")))
            self.assertTrue(os.path.exists(os.path.join(bin_dir, "wb-checkin")))
            self.assertTrue(os.path.exists(os.path.join(bin_dir, "wb-chat")))

        # 3. 运行卸载器（输入 n 回答不回滚数据库）
        unres = subprocess.run([sys.executable, uninstaller], input="n\n", cwd=REPO_DIR, env=self.env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        self.assertEqual(unres.returncode, 0, f"uninstall.py 失败: {unres.stderr}\n{unres.stdout}")
        self.assertIn("卸载完成", unres.stdout)

if __name__ == "__main__":
    unittest.main()
