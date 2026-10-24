#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""变异校验：把关键保护逐个改坏，确认对应回归测试真的会红。

用法：
    python scripts/mutation_check.py

每个变异都在临时副本上执行，不改当前工作区。返回码 0 = 全部被测试杀死；
1 = 有变异存活（说明测试没有真正锁住该行为）。
"""
import os
import shutil
import subprocess
import sys
import tempfile


REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PY = sys.executable

MUTATIONS = [
    {
        "name": "删掉签到墓碑判断",
        "old": "if is_uid_removed(active_uid):",
        "new": "if False:",
        "test": "tests.test_toolkit.TestWorkBuddyCore.test_t84_removed_active_account_is_not_recreated_by_checkin",
    },
    {
        "name": "取消确认前快照",
        "old": "items=archive_paths, links=reparse_links",
        "new": "items=None, links=None",
        "test": "tests.test_toolkit.TestWorkBuddyCore.test_t85_confirmation_snapshot_does_not_delete_new_files",
    },
    {
        "name": "删掉 reparse point 保护",
        "old": "    if _is_reparse_point(path):\n        _unlink_reparse(path)\n        return",
        "new": "    if False:\n        _unlink_reparse(path)\n        return",
        "test": "tests.test_toolkit.TestWorkBuddyCore.test_t79_junction_is_never_traversed",
    },
    {
        "name": "回滚失败仍删 bundle",
        "old": "if rollback_failed:",
        "new": "if False:",
        "test": "tests.test_toolkit.TestWorkBuddyCore.test_t77_archive_rollback_failure_keeps_bundle",
    },
    {
        "name": "无效备份也允许恢复",
        "old": "if invalid_reason and not force:",
        "new": "if False:",
        "test": "tests.test_toolkit.TestWorkBuddyCore.test_t86_invalid_backup_restore_refused_and_purge_trash",
    },
    {
        "name": "取消确认仍写盘",
        "old": "    if not yes:\n        if not sys.stdin.isatty():\n            result[\"action\"] = \"refused_non_interactive\"\n            return _finish(\n                \"非交互式运行环境已阻止删除操作，确认删除请显式加 --yes\",",
        "new": "    if False:\n        if not sys.stdin.isatty():\n            result[\"action\"] = \"refused_non_interactive\"\n            return _finish(\n                \"非交互式运行环境已阻止删除操作，确认删除请显式加 --yes\",",
        "test": "tests.test_toolkit.TestWorkBuddyCore.test_t88_cancel_writes_nothing",
    },
    {
        "name": "purge-trash 不清理配对记忆",
        "old": "if os.path.isdir(paired):\n            targets.append(paired)",
        "new": "if False:\n            targets.append(paired)",
        "test": "tests.test_toolkit.TestWorkBuddyCore.test_t87_purge_trash_removes_paired_memory_bundle",
    },
]


def _rmtree(path):
    if not os.path.lexists(path):
        return
    if os.path.islink(path) or os.path.isfile(path):
        os.remove(path)
        return
    with os.scandir(path) as it:
        entries = [(e.path, e.is_dir(follow_symlinks=False)) for e in it]
    for p, is_dir in entries:
        if is_dir and not os.path.islink(p):
            _rmtree(p)
        else:
            os.remove(p)
    os.rmdir(path)


def _copy_repo(dst):
    ignore = shutil.ignore_patterns(".git", "__pycache__", "*.pyc", ".venv", "node_modules")
    shutil.copytree(REPO, dst, ignore=ignore)


def main():
    print("repo:", REPO)
    print("python:", PY)
    results = []
    for item in MUTATIONS:
        tmp = tempfile.mkdtemp(prefix="wb-mutation-")
        try:
            _copy_repo(os.path.join(tmp, "repo"))
            target = os.path.join(tmp, "repo", "bin", "workbuddy")
            with open(target, "r", encoding="utf-8") as f:
                content = f.read()
            if item["old"] not in content:
                results.append((item["name"], "ERROR", "变异点未找到"))
                continue
            with open(target, "w", encoding="utf-8", newline="") as f:
                f.write(content.replace(item["old"], item["new"], 1))

            proc = subprocess.run(
                [PY, "-m", "unittest", item["test"]],
                cwd=os.path.join(tmp, "repo"), capture_output=True, text=True, timeout=180,
            )
            output = (proc.stdout or "") + (proc.stderr or "")
            if proc.returncode == 0:
                status = "SKIP" if "skipped" in output.lower() else "SURVIVED"
                detail = "测试未变红" if status == "SURVIVED" else "测试被环境跳过"
            else:
                status = "KILLED"
                detail = "测试按预期失败"
            results.append((item["name"], status, detail))
        finally:
            _rmtree(tmp)

    print()
    width = max(len(name) for name, _, _ in results) if results else 10
    bad = 0
    for name, status, detail in results:
        print("{:<{w}}  {:<9}  {}".format(name, status, detail, w=width))
        if status in ("SURVIVED", "ERROR"):
            bad += 1
    print()
    if bad:
        print("FAIL: {} 个变异未被测试杀死".format(bad))
        return 1
    print("OK: {} 个变异全部被测试杀死（Windows-only 项在非 Windows 上记 SKIP）".format(len(results)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
