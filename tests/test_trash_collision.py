"""tests/test_trash_collision.py — 回收站文件名碰撞的冻结时间用例。

维护者行内评审（P2）指出：原用例预置秒级文件名，而生产用微秒级格式，
物理上撞不上——把防覆盖分支删掉，用例仍然全绿。这里冻结 `datetime.now()`，
预置与生产完全一致的两级冲突名，直接验证"既有内容零改动"。

变异校验见 `scripts/mutation_check.py` 的"回收站文件名防覆盖"一项。
"""
import importlib.machinery
import importlib.util
import json
import os
import shutil
import tempfile
import unittest

REPO_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# WB_BIN 供变异校验指向"故意改坏"的副本；不设时用仓库里的正式文件
BIN_PATH = os.environ.get("WB_BIN") or os.path.join(REPO_DIR, "bin", "workbuddy")

_loader = importlib.machinery.SourceFileLoader("workbuddy_collision", BIN_PATH)
_spec = importlib.util.spec_from_loader("workbuddy_collision", _loader)
workbuddy = importlib.util.module_from_spec(_spec)
_loader.exec_module(workbuddy)

STAMP = "20261024-120000-123456"


class _FrozenDatetime(workbuddy.datetime):
    @classmethod
    def now(cls, tz=None):
        return cls(2026, 10, 24, 12, 0, 0, 123456)


class TestTrashCollision(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="wb_collision_")
        self._orig = (workbuddy.AUTH_FILE, workbuddy.PROFILES_DIR, workbuddy.datetime)
        workbuddy.AUTH_FILE = os.path.join(self.dir, "auth", "workbuddy-desktop.info")
        workbuddy.PROFILES_DIR = os.path.join(self.dir, "auth_profiles")
        workbuddy.datetime = _FrozenDatetime
        os.makedirs(os.path.dirname(workbuddy.AUTH_FILE), exist_ok=True)
        os.makedirs(os.path.join(workbuddy.PROFILES_DIR, ".trash"), exist_ok=True)

    def tearDown(self):
        workbuddy.AUTH_FILE, workbuddy.PROFILES_DIR, workbuddy.datetime = self._orig
        shutil.rmtree(self.dir, ignore_errors=True)

    def _make_profile(self, name="alpha", uid="uid-a"):
        with open(os.path.join(workbuddy.PROFILES_DIR, f"{name}.info"), "w", encoding="utf-8") as f:
            json.dump({"account": {"uid": uid, "nickname": "n"}, "auth": {}}, f, ensure_ascii=False)

    def _trash(self, suffix=""):
        return os.path.join(workbuddy.PROFILES_DIR, ".trash", f"alpha.{STAMP}{suffix}.info")

    def test_collision_keeps_existing_bytes(self):
        """生产同一微秒戳下已有同名文件：必须让位到 _1，既有字节零改动"""
        self._make_profile()
        with open(self._trash(), "wb") as f:
            f.write(b"OLD")
        self.assertTrue(workbuddy.remove_profile("alpha", assume_yes=True, force=True))
        with open(self._trash(), "rb") as f:
            self.assertEqual(f.read(), b"OLD", "既有回收站文件被覆盖")
        self.assertTrue(os.path.isfile(self._trash("_1")), "碰撞后未生成 _1")

    def test_double_collision_uses_next_suffix(self):
        """两级冲突：已有 base 与 _1，本次必须落到 _2"""
        self._make_profile()
        for suffix in ("", "_1"):
            with open(self._trash(suffix), "wb") as f:
                f.write(b"OLD" + suffix.encode())
        self.assertTrue(workbuddy.remove_profile("alpha", assume_yes=True, force=True))
        self.assertTrue(os.path.isfile(self._trash("_2")), "双重碰撞未落到 _2")
        with open(self._trash(), "rb") as f:
            self.assertEqual(f.read(), b"OLD")


if __name__ == "__main__":
    unittest.main()
