#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""跨账号记忆汇总（共享记忆库）测试。"""

import json
import os
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

REPO_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SIDECAR_DIR = os.path.join(REPO_DIR, "sidecar")
if SIDECAR_DIR not in sys.path:
    sys.path.insert(0, SIDECAR_DIR)

import importlib.machinery
import importlib.util

import memory_share as ms

loader = importlib.machinery.SourceFileLoader("workbuddy", os.path.join(REPO_DIR, "bin", "workbuddy"))
spec = importlib.util.spec_from_loader("workbuddy", loader)
workbuddy = importlib.util.module_from_spec(spec)
loader.exec_module(workbuddy)


class TestMemoryHub(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.acc_a = {"alias": "alpha", "uid": "uid-a", "enterprise_id": None}
        self.acc_b = {"alias": "beta", "uid": "uid-b", "enterprise_id": None}
        self.path_a = self._write(self.acc_a, "# 记忆\n- 默认用中文回复\n- 称呼 ser\n")
        self.path_b = self._write(self.acc_b, "# 记忆\n- 改完代码先跑测试\n")

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def _write(self, acc, text):
        d = ms.memory_dir(self.root, acc["uid"], acc["enterprise_id"])
        os.makedirs(d, exist_ok=True)
        path = os.path.join(d, ms.MEMORY_FILE)
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
        return path

    def _read(self, path):
        with open(path, "r", encoding="utf-8") as f:
            return f.read()

    # ------------------------------------------------------------------
    def test_01_quality_prefers_specific_over_vague(self):
        """T01: 具体、可执行的条目得分高于模糊措辞"""
        specific, _ = ms.quality("- 提交前必须跑 python -m unittest discover -s tests")
        vague, _ = ms.quality("- 测试可能要多跑几次大概就稳了")
        self.assertGreater(specific, vague)
        self.assertGreater(specific, 5.0)
        self.assertLess(vague, 5.0)

    def test_02_similarity_groups_near_duplicates(self):
        """T02: 换标点/语序微调算相似，不同主题不算"""
        a = ms.normalize("默认用中文回复")
        b = ms.normalize("默认用中文回复。")
        c = ms.normalize("提交前先跑全量测试")
        self.assertGreaterEqual(ms.similarity(a, b), ms.SIMILARITY_THRESHOLD)
        self.assertLess(ms.similarity(a, c), ms.SIMILARITY_THRESHOLD)

    def test_03_collect_dedupes_and_keeps_better_version(self):
        """T03: 近重复条目只留质量更高的一条，落选版本仍留档"""
        self._write(self.acc_a, "# 记忆\n- 提交前必须跑全量测试，大概\n")
        self._write(self.acc_b, "# 记忆\n- 提交前必须跑全量测试\n")
        stats = ms.collect([self.acc_a, self.acc_b], root=self.root)
        self.assertEqual(stats["entries"], 1, "近重复条目应合并为一条")
        self.assertEqual(stats["merged"], 1)

        lib = ms.load_library(self.root)
        entry = lib["entries"][0]
        self.assertEqual(entry["text"], "- 提交前必须跑全量测试", "应保留无模糊措辞的版本")
        self.assertEqual(set(entry["sources"]), {"uid-a", "uid-b"})
        self.assertTrue(entry["superseded"], "落选版本必须留档，不能丢")
        self.assertIn("大概", entry["superseded"][0]["text"])

    def test_04_apply_appends_shared_and_keeps_origin_verbatim(self):
        """T04: 渲染后账号原文逐字保留，共享段落追加在后面"""
        origin = self._read(self.path_a)
        ms.collect([self.acc_a, self.acc_b], root=self.root)
        res = ms.apply_account(self.acc_a, root=self.root)
        self.assertTrue(res["ok"])
        self.assertEqual(res["action"], "created")
        self.assertGreaterEqual(res["shared"], 1)

        text = self._read(self.path_a)
        self.assertTrue(text.startswith(origin.rstrip()), "原文必须原样留在文件开头")
        self.assertIn(ms.BEGIN_MARK, text)
        self.assertIn("改完代码先跑测试", text)
        self.assertNotIn("改完代码先跑测试", origin)

    def test_05_apply_is_idempotent(self):
        """T05: 重复渲染不产生改动，也不重复追加"""
        ms.collect([self.acc_a, self.acc_b], root=self.root)
        ms.apply_account(self.acc_a, root=self.root)
        first = self._read(self.path_a)
        res = ms.apply_account(self.acc_a, root=self.root)
        self.assertEqual(res["action"], "unchanged")
        self.assertEqual(self._read(self.path_a), first)
        self.assertEqual(first.count(ms.BEGIN_MARK), 1)

    def test_06_limit_keeps_origin_intact(self):
        """T06: 原文接近 4000 字时，共享段落让位，原文一个字都不截"""
        origin = "# 记忆\n" + "\n".join("- 自有条目 {:04d} {}".format(i, "内" * 60) for i in range(50))
        self._write(self.acc_a, origin)
        self._write(self.acc_b, "# 记忆\n" + "\n".join(
            "- 必须遵守外来准则 {:02d} {}".format(i, "外" * 60) for i in range(10)))
        ms.collect([self.acc_a, self.acc_b], root=self.root)
        res = ms.apply_account(self.acc_a, root=self.root)

        text = self._read(self.path_a)
        self.assertTrue(text.startswith(origin.rstrip()), "原文不能被共享内容挤掉")
        self.assertLessEqual(len(text.strip()), ms.INJECT_LIMIT + 200, "超限时应只做有限展开")
        self.assertGreaterEqual(res["truncated"], 1, "放不下的共享条目应被计入截断")

    def test_07_restore_returns_exact_original(self):
        """T07: restore 用快照还原，内容与接入手写版本逐字一致"""
        origin = self._read(self.path_a)
        ms.collect([self.acc_a, self.acc_b], root=self.root)
        ms.apply_account(self.acc_a, root=self.root)
        self.assertNotEqual(self._read(self.path_a), origin)

        res = ms.restore_account(self.acc_a, root=self.root)
        self.assertTrue(res["ok"])
        self.assertEqual(self._read(self.path_a), origin)
        self.assertTrue(res["backup"] and os.path.isfile(res["backup"]))

    def test_08_absorb_keeps_old_and_adds_new(self):
        """T08: 账号自己在文件里新增条目，下次渲染既不丢旧条目也能吸收新条目"""
        ms.collect([self.acc_a, self.acc_b], root=self.root)
        ms.apply_account(self.acc_a, root=self.root)
        with open(self.path_a, "a", encoding="utf-8") as f:
            f.write("- 新规矩：提交信息用中文\n")

        res = ms.apply_account(self.acc_a, root=self.root)
        self.assertTrue(res["ok"])
        text = self._read(self.path_a)
        self.assertIn("默认用中文回复", text, "旧条目不能因为新增而丢失")
        self.assertIn("称呼 ser", text)
        self.assertIn("新规矩：提交信息用中文", text)
        self.assertEqual(res["added"], 1)

        snap = self._read(ms.snapshot_path(self.root, "uid-a"))
        self.assertIn("新规矩：提交信息用中文", snap)

    def test_09_snapshot_never_overwritten_on_recollect(self):
        """T09: 反复 collect 不覆盖基线快照"""
        ms.collect([self.acc_a, self.acc_b], root=self.root)
        ms.apply_account(self.acc_a, root=self.root)
        snap_before = self._read(ms.snapshot_path(self.root, "uid-a"))
        ms.collect([self.acc_a, self.acc_b], root=self.root)
        ms.apply_account(self.acc_a, root=self.root)
        self.assertEqual(self._read(ms.snapshot_path(self.root, "uid-a")), snap_before)

    def test_10_status_reports_own_and_shared(self):
        """T10: status 分别报告自有字数与共享条数"""
        ms.collect([self.acc_a, self.acc_b], root=self.root)
        ms.apply_account(self.acc_a, root=self.root)
        data = ms.status([self.acc_a, self.acc_b], root=self.root)
        row = [r for r in data["accounts"] if r["alias"] == "alpha"][0]
        self.assertTrue(row["exists"])
        self.assertTrue(row["snapshot"])
        self.assertGreater(row["own_chars"], 0)
        self.assertGreaterEqual(row["shared_entries"], 1)


class TestPublishScope(unittest.TestCase):
    """发布口径：只发布跨账号仍然成立的规则，不发布事实与本机细节。"""

    def test_20_publish_level_classifies_by_nature(self):
        """T20: 红线 / 显式指令 / 项目约定 / 习惯 / 事实 分级正确"""
        self.assertEqual(ms.publish_level("- 禁止把 token 写进仓库"), 0)
        self.assertEqual(ms.publish_level("- 以后都叫我 ser"), 1)
        self.assertEqual(ms.publish_level("- 提交前跑全量测试"), 2)
        self.assertEqual(ms.publish_level("- 偏好简洁回答"), 3)
        self.assertEqual(ms.publish_level("- 项目路径在 D:/work/pr"), 4)
        self.assertEqual(ms.publish_level("- 用户似乎偏好简洁"), 4, "模糊措辞按推断处理")

    def test_21_publishable_respects_budget(self):
        """T21: 预算按字符硬约束，装不下就停，不静默超发"""
        entries = [{"text": "- 必须遵守准则 {:02d} {}".format(i, "规" * 40), "quality": 6.0}
                   for i in range(30)]
        picked, stats = ms.publishable(entries, budget=300)
        self.assertLessEqual(stats["used"], 300)
        self.assertGreater(stats["budget"], 0)
        self.assertLess(len(picked), 30)
        for e in picked:
            self.assertLessEqual(len(e["text"]) + 3, 300)

    def test_22_local_fact_never_published(self):
        """T22: 含盘符路径/账号的条目一律不跨账号"""
        entries = [{"text": "- 项目在 D:/work/pr 下", "quality": 9.0},
                   {"text": "- 联系 ser@example.com", "quality": 9.0}]
        picked, stats = ms.publishable(entries)
        self.assertEqual(picked, [])
        self.assertEqual(stats["local_fact"], 2)

    def test_23_apply_does_not_leak_project_facts(self):
        """T23: B 号的项目事实不会出现在 A 号，规则会"""
        root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, root, True)
        a = {"alias": "alpha", "uid": "uid-a"}
        b = {"alias": "beta", "uid": "uid-b"}
        for acc, text in ((a, "# 记忆\n- 提交前必须跑测试\n"),
                          (b, "# 记忆\n- 项目路径在 D:/work/pr\n- 以后都叫我 ser\n")):
            d = ms.memory_dir(root, acc["uid"])
            os.makedirs(d, exist_ok=True)
            with open(os.path.join(d, "MEMORY.md"), "w", encoding="utf-8") as f:
                f.write(text)

        ms.collect([a, b], root=root)
        res = ms.apply_account(a, root=root)
        text = open(os.path.join(ms.memory_dir(root, "uid-a"), "MEMORY.md"),
                    encoding="utf-8").read()
        self.assertIn("叫我 ser", text)
        self.assertNotIn("D:/work/pr", text, "项目事实不能跨账号")
        self.assertGreaterEqual(res["skipped"]["local_fact"], 1)

    def test_24_published_block_stays_inside_window(self):
        """T24: 共享段落必须落在 4000 字窗口内，否则写了等于没写"""
        root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, root, True)
        a = {"alias": "alpha", "uid": "uid-a"}
        b = {"alias": "beta", "uid": "uid-b"}
        origin = "# 记忆\n" + "\n".join("- 自有事实 {:04d} {}".format(i, "内" * 50) for i in range(45))
        for acc, text in ((a, origin),
                          (b, "# 记忆\n" + "\n".join(
                              "- 必须遵守外来准则 {:02d} {}".format(i, "外" * 50) for i in range(12)))):
            d = ms.memory_dir(root, acc["uid"])
            os.makedirs(d, exist_ok=True)
            with open(os.path.join(d, "MEMORY.md"), "w", encoding="utf-8") as f:
                f.write(text)

        ms.collect([a, b], root=root)
        res = ms.apply_account(a, root=root)
        text = open(os.path.join(ms.memory_dir(root, "uid-a"), "MEMORY.md"), encoding="utf-8").read()
        self.assertGreaterEqual(res["shared"], 1)
        self.assertLessEqual(len(text.strip()), ms.INJECT_LIMIT, "总字数不能越过注入上限")
        self.assertTrue(text.startswith(origin.rstrip()), "原文优先")

    def test_25_forget_leaves_tombstone_and_blocks_resurrection(self):
        """T25: forget 之后重新 collect 也不能把条目收回来"""
        root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, root, True)
        acc = {"alias": "alpha", "uid": "uid-a"}
        d = ms.memory_dir(root, acc["uid"])
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, "MEMORY.md"), "w", encoding="utf-8") as f:
            f.write("# 记忆\n- 必须提交前跑全量测试\n- 必须用中文回复\n")

        ms.collect([acc], root=root)
        preview = ms.forget("跑全量测试", root=root)
        self.assertTrue(preview["matched"])
        self.assertFalse(preview["applied"], "默认只预览")
        self.assertEqual(len(ms.load_library(root)["entries"]), 2)

        res = ms.forget("跑全量测试", root=root, apply=True)
        self.assertTrue(res["applied"])
        remaining = [e["text"] for e in ms.load_library(root)["entries"]]
        self.assertEqual(remaining, ["- 必须用中文回复"])

        stats = ms.collect([acc], root=root)
        self.assertEqual(stats["forgotten"], 1, "账号文件里还在，但不能被收回库里")
        self.assertEqual(len(ms.load_library(root)["entries"]), 1)

    def test_26_conflicting_rules_only_publish_one(self):
        """T26: 只差一个否定词的两条规则，标冲突且只注入一条"""
        root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, root, True)
        a = {"alias": "alpha", "uid": "uid-a"}
        b = {"alias": "beta", "uid": "uid-b"}
        for acc, text in ((a, "# 记忆\n- 提交前必须跑全量测试\n"),
                          (b, "# 记忆\n- 提交前不要跑全量测试\n")):
            d = ms.memory_dir(root, acc["uid"])
            os.makedirs(d, exist_ok=True)
            with open(os.path.join(d, "MEMORY.md"), "w", encoding="utf-8") as f:
                f.write(text)

        stats = ms.collect([a, b], root=root)
        self.assertEqual(stats["conflicts"], 1)
        lib = ms.load_library(root)
        self.assertEqual(len(lib["entries"]), 2, "冲突双方都要留在库里")
        self.assertEqual(sum(1 for e in lib["entries"] if e.get("suppressed")), 1)

        picked, sk = ms.publishable(ms.active_entries(lib))
        self.assertEqual(len(picked), 1)
        self.assertEqual(sk["conflict"], 1)


class TestLock(unittest.TestCase):
    def test_27_lock_is_reentrant(self):
        """T27: 同一进程可重入（apply_all 内层再取锁不能自锁）"""
        root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, root, True)
        with ms.file_lock(root):
            with ms.file_lock(root):
                self.assertIn(os.path.join(ms.hub_dir(root), ".hub.lock"), ms._lock_state)

    def test_28_apply_all_under_single_lock(self):
        """T28: apply_all 不会因为内层取锁而卡死"""
        root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, root, True)
        accs = []
        for i in (1, 2):
            acc = {"alias": "a{}".format(i), "uid": "uid-{}".format(i)}
            d = ms.memory_dir(root, acc["uid"])
            os.makedirs(d, exist_ok=True)
            with open(os.path.join(d, "MEMORY.md"), "w", encoding="utf-8") as f:
                f.write("# 记忆\n- 必须遵守准则 {}\n".format(i))
            accs.append(acc)
        ms.collect(accs, root=root)
        results = ms.apply_all(accs, root=root)
        self.assertEqual(len(results), 2)
        self.assertTrue(all(r["ok"] for r in results))


class TestShardIndex(unittest.TestCase):
    """索引 + 分片：窗口装不下的条目原文落分片，窗口里只留一行索引。"""

    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.root, True)
        self.a = {"alias": "alpha", "uid": "uid-a"}
        self.b = {"alias": "beta", "uid": "uid-b"}

    def _write(self, acc, text):
        d = ms.memory_dir(self.root, acc["uid"])
        os.makedirs(d, exist_ok=True)
        path = os.path.join(d, ms.MEMORY_FILE)
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
        return path

    def _read(self, path):
        with open(path, "r", encoding="utf-8") as f:
            return f.read()

    def test_29_compact_is_idempotent(self):
        """T29: compact 幂等，重复执行不重写、不重复生成分片"""
        long_rule = "- 必须遵守的超长协作准则：" + "细" * 200
        self._write(self.a, "# 记忆\n- 称呼 ser\n")
        self._write(self.b, "# 记忆\n" + long_rule + "\n- 偏好简洁回答\n")
        ms.collect([self.a, self.b], root=self.root)

        first = ms.compact(root=self.root)
        self.assertTrue(first["ok"])
        self.assertGreaterEqual(first["shards"], 2, "超长条目与偏好类条目都要建分片")
        self.assertEqual(first["shards"], first["indexed"])
        files = sorted(os.listdir(ms.shard_dir(self.root)))
        self.assertEqual(len(files), first["shards"])

        second = ms.compact(root=self.root)
        self.assertEqual(second["written"], 0, "内容没变不该重写分片")
        self.assertEqual(second["shards"], first["shards"])
        self.assertEqual(sorted(os.listdir(ms.shard_dir(self.root))), files,
                         "重复执行不能多出分片")

        lib = ms.load_library(self.root)
        for entry in ms.active_entries(lib):
            if entry.get("shard"):
                self.assertTrue(entry.get("index_line").startswith("- [P"))

        ms.collect([self.a, self.b], root=self.root)
        kept = [e for e in ms.active_entries(ms.load_library(self.root)) if e.get("shard")]
        self.assertEqual(len(kept), first["shards"], "重新汇总不能把已建索引抹掉")

    def test_30_shard_keeps_original_out_of_window(self):
        """T30: 分片内容 = 条目原文，且原文不会被注入 MEMORY.md"""
        long_rule = "- 必须遵守的超长协作准则：" + "密" * 900 + "尾部唯一标记ZZ"
        self._write(self.a, "# 记忆\n- 称呼 ser\n")
        self._write(self.b, "# 记忆\n" + long_rule + "\n")
        ms.collect([self.a, self.b], root=self.root)
        ms.compact(root=self.root)

        lib = ms.load_library(self.root)
        entry = [e for e in ms.active_entries(lib) if e["text"] == long_rule][0]
        self.assertTrue(entry["shard"].startswith("shards/"))
        shard_path = os.path.join(ms.hub_dir(self.root), entry["shard"])
        shard = self._read(shard_path)
        head, body = shard.split("\n\n", 1)
        self.assertIn("来源", head)
        self.assertIn("首次收录", head)
        self.assertEqual(body.strip(), long_rule, "分片里必须是原文，一字不改")

        res = ms.apply_account(self.a, root=self.root)
        text = self._read(os.path.join(ms.memory_dir(self.root, "uid-a"), ms.MEMORY_FILE))
        self.assertNotIn(long_rule, text, "超预算的原文不能进 4000 字窗口")
        self.assertNotIn("尾部唯一标记ZZ", text)
        self.assertIn(ms.INDEX_MARKER, text, "窗口里只留索引行")
        self.assertGreaterEqual(res["indexed"], 1)

    def test_31_index_fits_budget_without_touching_origin(self):
        """T31: 索引行落在 4000 预算内、原文一字不改；超预算时一条都不加"""
        long_rule = "- 必须遵守的超长协作准则：" + "密" * 900
        self._write(self.a, "# 记忆\n- 称呼 ser\n")
        self._write(self.b, "# 记忆\n" + long_rule + "\n")
        ms.collect([self.a, self.b], root=self.root)
        ms.compact(root=self.root)

        res = ms.apply_account(self.a, root=self.root)
        text = self._read(os.path.join(ms.memory_dir(self.root, "uid-a"), ms.MEMORY_FILE))
        self.assertTrue(text.startswith("# 记忆\n- 称呼 ser"), "原文必须原样留在开头")
        self.assertEqual(res["indexed"], 1)
        self.assertIn(ms.INDEX_MARKER, text)
        self.assertLessEqual(len(text.strip()), ms.INJECT_LIMIT)
        line = [l for l in text.splitlines() if l.startswith("- [P")][0]
        self.assertLessEqual(len(line), ms.MAX_INDEX_LINE_CHARS)
        self.assertIn("shards/", line)

        # 原文几乎占满窗口：索引让位，一条也不加，原文仍一字不改
        tight = "# 记忆\n" + "\n".join("- 自有条目 {:04d} {}".format(i, "内" * 60)
                                     for i in range(54))
        tight_path = self._write({"alias": "gamma", "uid": "uid-c"}, tight)
        tight_res = ms.apply_account({"alias": "gamma", "uid": "uid-c"}, root=self.root)
        tight_text = self._read(tight_path)
        self.assertEqual(tight_res["indexed"], 0, "没有余量就不能再加索引")
        self.assertNotIn(ms.INDEX_MARKER, tight_text)
        self.assertEqual(tight_text.strip(), tight.strip(), "原文一个字都不能变")
        self.assertLessEqual(len(tight_text.strip()), ms.INJECT_LIMIT)

    def test_32_apply_without_shards_keeps_old_behavior(self):
        """T32: 库里没有分片时，apply 走原来的渲染路径（回归保护）"""
        self._write(self.a, "# 记忆\n- 称呼 ser\n")
        self._write(self.b, "# 记忆\n- 提交前跑全量测试\n")
        ms.collect([self.a, self.b], root=self.root)
        lib = ms.load_library(self.root)
        self.assertFalse([e for e in ms.active_entries(lib) if e.get("shard")])
        self.assertFalse(os.path.isdir(ms.shard_dir(self.root)))

        res = ms.apply_account(self.a, root=self.root)
        text = self._read(os.path.join(ms.memory_dir(self.root, "uid-a"), ms.MEMORY_FILE))
        self.assertGreaterEqual(res["shared"], 1)
        self.assertEqual(res["indexed"], 0)
        self.assertNotIn(ms.INDEX_MARKER, text)

        shared = [e for e in ms.active_entries(lib) if "跑全量测试" in e["text"]]
        self.assertEqual(text, ms.render("# 记忆\n- 称呼 ser", shared)[0],
                         "无分片时的输出必须与旧渲染结果一致")

        again = ms.apply_account(self.a, root=self.root)
        self.assertEqual(again["action"], "unchanged")
        self.assertEqual(again["indexed"], 0)


class TestRenderRegressions(unittest.TestCase):
    """对抗验证抓到的 5 个真缺陷，逐条钉死。"""

    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.root, True)

    def _mk(self, acc, text, newline=""):
        d = ms.memory_dir(self.root, acc["uid"])
        os.makedirs(d, exist_ok=True)
        path = os.path.join(d, "MEMORY.md")
        with open(path, "w", encoding="utf-8", newline=newline) as f:
            f.write(text)
        return path

    def test_33_crlf_is_preserved(self):
        """T33: CRLF 文件不能被改写成 LF，且第二次 apply 必须是 unchanged"""
        a = {"alias": "alpha", "uid": "uid-a"}
        b = {"alias": "beta", "uid": "uid-b"}
        path = self._mk(a, "# 记忆\r\n- 提交前必须跑测试\r\n")
        self._mk(b, "# 记忆\n- 必须遵守外来准则\n")
        before = open(path, "rb").read()

        ms.collect([a, b], root=self.root)
        ms.apply_account(a, root=self.root)
        after = open(path, "rb").read()

        self.assertTrue(after.startswith(before.rstrip()), "原文逐字保留")
        self.assertGreater(after.count(b"\r\n"), before.count(b"\r\n"), "新增内容也应用 CRLF")
        self.assertEqual(after.count(b"\n") - after.count(b"\r\n"), 0, "不能出现裸 LF")

        res = ms.apply_account(a, root=self.root)
        self.assertEqual(res["action"], "unchanged", "字节相同就不能报 updated")

    def test_34_no_double_bullet(self):
        """T34: 条目自带 "- " 时不能再拼一个列表符"""
        a = {"alias": "alpha", "uid": "uid-a"}
        b = {"alias": "beta", "uid": "uid-b"}
        path = self._mk(a, "# 记忆\n- 自有\n")
        self._mk(b, "# 记忆\n- 必须遵守外来准则\n")
        ms.collect([a, b], root=self.root)
        ms.apply_account(a, root=self.root)
        text = open(path, encoding="utf-8").read()
        self.assertIn("- 必须遵守外来准则", text)
        self.assertNotIn("- - ", text)

    def test_35_local_fact_variants_blocked(self):
        """T35: ~/、../、全角盘符、环境变量都算本机事实"""
        for text in ("- 资料在 ~/docs 下", "- 配置在 ../conf 下",
                     "- 盘符 Ｄ：\\work", "- 变量 %APPDATA% 下"):
            self.assertTrue(ms.is_local_fact(text), text)
        self.assertFalse(ms.is_local_fact("- 提交前必须跑测试"))

    def test_36_render_never_exceeds_limit(self):
        """T36: 任意条目数下渲染结果都不越过 4000，且原文不动"""
        origin = "# 记忆\n" + "\n".join(
            "- 自有条目 {:04d} {}".format(i, "内" * 57) for i in range(50))
        for n in range(0, 31):
            text, _, _, _ = ms.render(origin, [{"text": "- 必须遵守这一条准则"}] * n,
                                      limit=ms.INJECT_LIMIT)
            self.assertLessEqual(len(text.strip()), ms.INJECT_LIMIT, "n={}".format(n))

    def test_37_lock_failure_returns_not_raises(self):
        """T37: 锁超时要返回 locked，不能让批量同步整体中断"""
        a = {"alias": "alpha", "uid": "uid-a"}
        self._mk(a, "# 记忆\n- 自有\n")

        def boom(*args, **kwargs):
            raise ms.MemoryLockTimeout("busy")

        original = ms.file_lock
        ms.file_lock = boom
        try:
            res = ms.apply_account(a, root=self.root)
        finally:
            ms.file_lock = original
        self.assertFalse(res["ok"])
        self.assertEqual(res["action"], "locked")


class TestSectionRebalance(unittest.TestCase):
    """分节迁移：整节搬，不把列表和它的标题拆散。"""

    def test_38_section_move_keeps_lists_whole(self):
        """T38: 整节迁移不会留下孤立子项"""
        doc = ("# MEMORY.md\n"
               "## 一、排错\n"
               "- 先复现\n"
               "  - 记录完整错误\n"
               "  - 记录版本\n"
               "## 二、git\n"
               "- 分支是指向提交历史的名字\n")
        plan = ms.plan_rebalance_sections(doc, target=40)
        self.assertEqual(plan["mode"], "section")
        self.assertIn("## 一、排错", plan["moved_soul"])
        self.assertIn("  - 记录版本", plan["moved_soul"], "缩进子项必须跟父节一起走")
        self.assertNotIn("  - 记录版本", plan["kept"])

    def test_39_auto_mode_prefers_sections(self):
        """T39: 有 ≥2 个二级标题时自动走按节迁移"""
        root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, root, True)
        acc = {"alias": "alpha", "uid": "uid-a"}
        d = ms.memory_dir(root, "uid-a")
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, "MEMORY.md"), "w", encoding="utf-8") as f:
            f.write("# MEMORY.md\n"
                    "## 一、方法论\n" + "\n".join("- 必须遵守准则 {}".format(i) for i in range(80)) + "\n"
                    "## 二、事实\n- 项目在 D:/work/x\n")
        res = ms.rebalance_account(acc, root=root, target=500, apply=False)
        self.assertEqual(res["plan"]["mode"], "section")
        self.assertTrue(res["plan"]["sections"])
        self.assertTrue(any(s["moved"] for s in res["plan"]["sections"]))

    def test_40_section_facts_stay_in_memory(self):
        """T40: 含本机路径的节不搬——那是本机事实，不是行为准则"""
        doc = ("# MEMORY.md\n"
               "## 一、环境\n"
               "- 工作区在 D:/work/app\n"
               "- 虚拟环境在 D:/venv\n"
               "## 二、方法\n" + "\n".join("- 必须这样做 {}".format(i) for i in range(60)) + "\n")
        plan = ms.plan_rebalance_sections(doc, target=200)
        self.assertIn("## 一、环境", plan["kept"])
        self.assertNotIn("## 一、环境", plan["moved_soul"])


    def test_41_document_fragments_are_not_published(self):
        """T41: 引用块/斜体/表格行不是规则，不能跨账号"""
        entries = [{"text": "> **启用条件**：涉及视频时生效，其它任务**不启用**", "quality": 7.0},
                   {"text": "*本文件用于记录跨项目规则*", "quality": 6.0},
                   {"text": "| 通道 | 上限 |", "quality": 5.0},
                   {"text": "- 提交前必须跑测试", "quality": 6.0}]
        picked, stats = ms.publishable(entries)
        self.assertEqual([e["text"] for e in picked], ["- 提交前必须跑测试"])
        self.assertEqual(stats["fragment"], 3)


class TestRebalanceThenPublish(unittest.TestCase):
    """分诊与发布必须兼容：apply 不能把刚搬走的章节写回来。"""

    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.root, True)
        self.a = {"alias": "alpha", "uid": "uid-a"}
        self.b = {"alias": "beta", "uid": "uid-b"}
        d = ms.memory_dir(self.root, "uid-a")
        os.makedirs(d, exist_ok=True)
        self.mem_a = os.path.join(d, "MEMORY.md")
        with open(self.mem_a, "w", encoding="utf-8") as f:
            f.write("# MEMORY.md\n"
                    "## 一、方法论\n" + "\n".join(
                        "- 必须遵守准则 {}".format(i) for i in range(60)) + "\n"
                    "## 二、环境\n- 工作区在 D:/work/app\n- 虚拟环境在 D:/venv\n")
        d = ms.memory_dir(self.root, "uid-b")
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, "MEMORY.md"), "w", encoding="utf-8") as f:
            f.write("# 记忆\n- 提交前必须跑全量测试\n")

    def test_42_apply_does_not_undo_rebalance(self):
        """T42: 分诊后 apply，搬走的章节不能回到 MEMORY"""
        before = open(self.mem_a, encoding="utf-8").read()
        ms.rebalance_account(self.a, root=self.root, target=300, apply=True)
        slim = open(self.mem_a, encoding="utf-8").read()
        self.assertLess(len(slim), len(before))
        self.assertNotIn("必须遵守准则 0", slim)

        ms.collect([self.a, self.b], root=self.root)
        ms.apply_account(self.a, root=self.root)
        after = open(self.mem_a, encoding="utf-8").read()

        self.assertNotIn("必须遵守准则 0", after, "分诊被 apply 撤销了")
        self.assertLessEqual(len(after.strip()), ms.INJECT_LIMIT, "共享段落必须落在窗口内")
        self.assertIn(ms.BEGIN_MARK, after)

    def test_43_restore_also_clears_rebalance_section(self):
        """T43: restore 回到分诊前，SOUL 里的受管段落要一并摘掉，避免两处重复"""
        ms.rebalance_account(self.a, root=self.root, target=300, apply=True)
        soul = os.path.join(ms.memory_dir(self.root, "uid-a"), "SOUL.md")
        self.assertIn(ms.REBALANCE_BEGIN, open(soul, encoding="utf-8").read())

        res = ms.restore_account(self.a, root=self.root)
        self.assertTrue(res["ok"])
        self.assertIn("SOUL.md", res.get("cleaned") or [])
        self.assertNotIn(ms.REBALANCE_BEGIN, open(soul, encoding="utf-8").read())
        self.assertIn("必须遵守准则 0", open(self.mem_a, encoding="utf-8").read())


class TestMemoryHubCli(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.orig_root = workbuddy.get_memory_root
        self.orig_profiles = workbuddy.PROFILES_DIR
        self.orig_hub = workbuddy.MEMORY_HUB_FILE
        workbuddy.PROFILES_DIR = os.path.join(self.root, "auth_profiles")
        workbuddy.MEMORY_HUB_FILE = os.path.join(self.root, "cache", "memory_hub.json")
        workbuddy.get_memory_root = lambda: self.root
        os.makedirs(workbuddy.PROFILES_DIR, exist_ok=True)

    def tearDown(self):
        workbuddy.get_memory_root = self.orig_root
        workbuddy.PROFILES_DIR = self.orig_profiles
        workbuddy.MEMORY_HUB_FILE = self.orig_hub
        shutil.rmtree(self.root, ignore_errors=True)

    def _profile(self, alias, uid, nick="Nick"):
        path = os.path.join(workbuddy.PROFILES_DIR, "{}.info".format(alias))
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"account": {"uid": uid, "nickname": nick},
                       "auth": {"accessToken": "t", "expiresAt": 1800000000000}}, f)
        return path

    def test_11_cli_collect_apply_status_restore(self):
        """T11: collect → apply → status → restore 全链路可用"""
        import io

        self._profile("alpha", "uid-a")
        self._profile("beta", "uid-b")
        a_dir = ms.memory_dir(self.root, "uid-a")
        b_dir = ms.memory_dir(self.root, "uid-b")
        os.makedirs(a_dir)
        os.makedirs(b_dir)
        with open(os.path.join(a_dir, "MEMORY.md"), "w", encoding="utf-8") as f:
            f.write("# 记忆\n- 称呼 ser\n")
        with open(os.path.join(b_dir, "MEMORY.md"), "w", encoding="utf-8") as f:
            f.write("# 记忆\n- 提交前跑全量测试\n")

        with patch("sys.stdout", io.StringIO()):
            self.assertEqual(workbuddy.run_memory_cmd(["collect"]), 0)
            self.assertEqual(workbuddy.run_memory_cmd(["apply", "alpha"]), 0)
            self.assertEqual(workbuddy.run_memory_cmd(["status"]), 0)
            self.assertEqual(workbuddy.run_memory_cmd(["restore", "alpha"]), 0)

        with open(os.path.join(a_dir, "MEMORY.md"), encoding="utf-8") as f:
            self.assertEqual(f.read(), "# 记忆\n- 称呼 ser\n")

    def test_12_disabled_switch_does_not_touch_memory(self):
        """T12: 未开启时切号不写任何记忆文件"""
        self._profile("alpha", "uid-a")
        self._profile("beta", "uid-b")
        a_dir = ms.memory_dir(self.root, "uid-a")
        os.makedirs(a_dir)
        path = os.path.join(a_dir, "MEMORY.md")
        with open(path, "w", encoding="utf-8") as f:
            f.write("# 记忆\n")
        before = os.path.getmtime(path)

        workbuddy._sync_memory_on_switch({"uid": "uid-b", "nickname": "Beta"})
        self.assertEqual(before, os.path.getmtime(path))
        self.assertFalse(os.path.exists(workbuddy.MEMORY_HUB_FILE))

    def test_13_enabled_switch_applies_before_restart(self):
        """T13: 切号时先渲染共享记忆，再重启客户端；顺序不能反"""
        import io

        self._profile("alpha", "uid-a")
        self._profile("beta", "uid-b")
        for uid, text in (("uid-a", "# 记忆\n- 称呼 ser\n"), ("uid-b", "# 记忆\n- 提交前跑测试\n")):
            d = ms.memory_dir(self.root, uid)
            os.makedirs(d, exist_ok=True)
            with open(os.path.join(d, "MEMORY.md"), "w", encoding="utf-8") as f:
                f.write(text)
        workbuddy.save_memory_hub_config({"enabled": True})

        order = []
        original_sync = workbuddy._sync_memory_on_switch

        def spy_sync(target):
            order.append("sync")
            return original_sync(target)

        auth_file = os.path.join(self.root, "auth", "workbuddy-desktop.info")
        os.makedirs(os.path.dirname(auth_file), exist_ok=True)
        with open(auth_file, "w", encoding="utf-8") as f:
            json.dump({"account": {"uid": "uid-a", "nickname": "Alpha"},
                       "auth": {"accessToken": "t", "expiresAt": 1800000000000}}, f)

        with patch("sys.stdout", io.StringIO()), \
                patch.object(workbuddy, "AUTH_FILE", auth_file), \
                patch.object(workbuddy, "DB_FILE", os.path.join(self.root, "wb.db")), \
                patch.object(workbuddy, "check_profile_health", lambda *a, **k: {"status": "HEALTHY"}), \
                patch.object(workbuddy, "_sync_memory_on_switch", spy_sync), \
                patch.object(workbuddy, "restart_workbuddy", lambda: order.append("restart")):
            self.assertTrue(workbuddy.switch_to_profile("beta", auto_restart=True))

        self.assertEqual(order, ["sync", "restart"], "渲染必须在重启之前完成")
        with open(os.path.join(ms.memory_dir(self.root, "uid-b"), "MEMORY.md"), encoding="utf-8") as f:
            text = f.read()
        self.assertIn("称呼 ser", text)
        self.assertIn(ms.BEGIN_MARK, text)


    def test_14_non_utf8_file_is_never_touched(self):
        """T14: 非 UTF-8 的 MEMORY.md 必须整篇跳过，不能被当成空文件覆盖"""
        d = ms.memory_dir(self.root, "uid-gbk")
        os.makedirs(d, exist_ok=True)
        path = os.path.join(d, "MEMORY.md")
        raw = "# 记忆\n- 这条很重要：用中文回复\n".encode("gbk")
        with open(path, "wb") as f:
            f.write(raw)

        acc = {"alias": "gbk", "uid": "uid-gbk"}
        ms.collect([acc], root=self.root)
        res = ms.apply_account(acc, root=self.root)
        self.assertEqual(res["action"], "skipped_encoding")
        self.assertTrue(res["ok"])
        with open(path, "rb") as f:
            self.assertEqual(f.read(), raw, "编码不认识时一个字节都不能改")
        self.assertFalse(os.path.exists(ms.snapshot_path(self.root, "uid-gbk")))

    def test_15_marker_like_text_is_not_truncated(self):
        """T15: 用户正文里出现受管标记字样时，不能把后半篇当共享段截掉"""
        origin = ("# 记忆\n- 第一条自有\n"
                  "<!-- shared-memory:begin -->\n- 用户手写的说明\n"
                  "<!-- shared-memory:end -->\n- 最后一条自有\n")
        for uid, text in (("uid-a", origin), ("uid-b", "# 记忆\n- 乙\n")):
            d = ms.memory_dir(self.root, uid)
            os.makedirs(d, exist_ok=True)
            with open(os.path.join(d, "MEMORY.md"), "w", encoding="utf-8") as f:
                f.write(text)
        a = {"alias": "alpha", "uid": "uid-a"}
        b = {"alias": "beta", "uid": "uid-b"}
        ms.collect([a, b], root=self.root)
        ms.apply_account(a, root=self.root)
        with open(ms.snapshot_path(self.root, "uid-a"), encoding="utf-8") as f:
            snap = f.read()
        for line in ("第一条自有", "用户手写的说明", "最后一条自有"):
            self.assertIn(line, snap, "用户正文不能被误判为共享段而丢失")


    def test_16_classify_routes_by_nature(self):
        """T16: 分诊按“关于人 / 怎么做 / 什么事”归类，分不清的留在 MEMORY"""
        self.assertEqual(ms.classify_line("- 称呼我 ser"), "user")
        self.assertEqual(ms.classify_line("- 提交前必须跑全量测试"), "soul")
        self.assertEqual(ms.classify_line("- 项目路径在 D:/work/pr"), "memory")
        self.assertEqual(ms.classify_line("# 一级标题"), "memory", "标题不参与搬迁")

    def test_17_plan_only_moves_overflow(self):
        """T17: 未超目标时一行都不搬；超了才搬，且搬完不超过目标"""
        small = "# 记忆\n" + "\n".join("- 事实 {}".format(i) for i in range(5))
        plan = ms.plan_rebalance(small, target=3200)
        self.assertEqual(plan["moved_soul"], [])
        self.assertEqual(plan["moved_user"], [])

        big = "# 记忆\n" + "\n".join(
            ["- 事实 {}".format(i) for i in range(20)]
            + ["- 必须遵守的准则第 {} 条".format(i) for i in range(120)]
        )
        plan = ms.plan_rebalance(big, target=1200)
        self.assertGreater(len(plan["moved_soul"]), 0)
        self.assertLessEqual(plan["memory_size"], 1200)
        self.assertEqual(plan["memory_size"] + plan["moved_soul_size"]
                         + plan["moved_user_size"], sum(len(l) + 1 for l in big.splitlines()))

    def test_18_rebalance_dry_run_writes_nothing(self):
        """T18: 默认只出计划，不写任何文件"""
        acc = {"alias": "alpha", "uid": "uid-a"}
        d = ms.memory_dir(self.root, "uid-a")
        os.makedirs(d, exist_ok=True)
        mem = os.path.join(d, "MEMORY.md")
        with open(mem, "w", encoding="utf-8") as f:
            f.write("# 记忆\n" + "\n".join("- 必须遵守准则 {}".format(i) for i in range(200)))
        before = open(mem, encoding="utf-8").read()
        res = ms.rebalance_account(acc, root=self.root, target=500, apply=False)
        self.assertEqual(res["action"], "planned")
        self.assertEqual(open(mem, encoding="utf-8").read(), before)
        self.assertFalse(os.path.exists(os.path.join(d, "SOUL.md")))

    def test_19_rebalance_apply_moves_and_preserves(self):
        """T19: 执行后 MEMORY 瘦身、SOUL/USER 各得一段，且有备份可还原"""
        acc = {"alias": "alpha", "uid": "uid-a"}
        d = ms.memory_dir(self.root, "uid-a")
        os.makedirs(d, exist_ok=True)
        mem = os.path.join(d, "MEMORY.md")
        soul = os.path.join(d, "SOUL.md")
        user = os.path.join(d, "USER.md")
        with open(soul, "w", encoding="utf-8") as f:
            f.write("# SOUL.md - Who You Are\n\n原有内容\n")
        with open(user, "w", encoding="utf-8") as f:
            f.write("# USER.md\n\n- 称呼 ser\n")
        with open(mem, "w", encoding="utf-8") as f:
            f.write("# 记忆\n"
                    + "\n".join("- 必须遵守准则 {}".format(i) for i in range(80))
                    + "\n" + "\n".join("- 事实条目 {}".format(i) for i in range(10)))

        res = ms.rebalance_account(acc, root=self.root, target=800, apply=True)
        self.assertTrue(res["ok"])
        self.assertEqual(res["action"], "rebalanced")
        self.assertEqual(len(res["backups"]), 3)

        self.assertLessEqual(len(open(mem, encoding="utf-8").read()), 800 + 40)
        soul_text = open(soul, encoding="utf-8").read()
        self.assertIn("原有内容", soul_text, "原有内容不能被删")
        self.assertIn(ms.REBALANCE_BEGIN, soul_text)
        self.assertIn("必须遵守准则 0", soul_text)

        # 幂等：再跑一次不会重复追加段落
        ms.rebalance_account(acc, root=self.root, target=800, apply=True)
        soul_text2 = open(soul, encoding="utf-8").read()
        self.assertEqual(soul_text2.count(ms.REBALANCE_BEGIN), 1)

        # restore 能把 MEMORY 还原
        ms.restore_account(acc, root=self.root)
        self.assertIn("必须遵守准则 0", open(mem, encoding="utf-8").read())


if __name__ == "__main__":
    unittest.main()
