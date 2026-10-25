#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""变异校验：证明 tests/test_profile_remove.py 的关键用例真的能抓到缺陷。

做法：把 bin/workbuddy 复制一份到临时目录，逐个"改坏"一处修复点，
再用 WB_BIN 指向这份坏副本运行对应用例。用例必须失败——如果改坏了还全绿，
说明那条断言是恒真的，不能作为证据。

对应维护者评审里"两轮对抗抓出 5 个缺陷，但过程只有叙述，无法核验"。

用法:
    python scripts/mutation_check.py

退出码 0 = 每个变异都被抓住；1 = 有变异没被抓住，或有变异无法唯一定位。
"""
import os
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SOURCE = os.path.join(ROOT, "bin", "workbuddy")
CLS = "tests.test_profile_remove.TestProfileRemove."

MUTATIONS = [
    dict(
        name="argv[0] 软链分发",
        old='if "remove" in prog_name:',
        new='if False and "remove" in prog_name:',
        test=CLS + "test_wb_remove_argv0_dispatch",
        why="去掉后 wb-remove <别名> 会落进兜底分支被解释成切号",
    ),
    dict(
        name="--restore 路径穿越",
        old='if (not raw or raw in (".", "..") or "/" in raw',
        new='if False and (not raw or raw in (".", "..") or "/" in raw',
        test=CLS + "test_restore_rejects_path_traversal",
        why="不校验路径成分时，恢复会越出 .trash 查找/搬动外部文件",
    ),
    dict(
        name="模式 flag 互斥",
        old='if len(mode_flags) > 1:',
        new='if False:  # mutated',
        test=CLS + "test_remove_mode_flags_mutually_exclusive",
        why="不互斥时 --restore 与 --empty-trash 同用会先清空回收站",
    ),
    dict(
        name="墓碑判断顺序",
        old=['if active_uid and not already_saved:\n            try:\n                trashed = get_trashed_uids(strict=True)',
             'if active_uid and not already_saved and trashed is not None and active_uid in trashed:'],
        new=['if active_uid:\n            try:\n                trashed = get_trashed_uids(strict=True)',
             'if active_uid and trashed is not None and active_uid in trashed:'],
        test=CLS + "test_tombstone_does_not_shadow_resaved_account",
        why="先判墓碑会让重新 save 的账号每天刷一条假的'跳过自动入库'",
    ),
    dict(
        name="墓碑机制本身",
        old='if active_uid and not already_saved and trashed is not None and active_uid in trashed:',
        new='if False:  # mutated',
        test=CLS + "test_remove_active_account_warns_and_tombstones",
        why="没有墓碑时，已删账号次日签到会以昵称别名被重新收录",
    ),
    dict(
        name="同 uid 恢复去重",
        old='if uid in existing:',
        new='if False:  # mutated',
        test=CLS + "test_restore_rejects_duplicate_uid",
        why="不去重时恢复出第二份副本，checkin 会对同一账号签两次",
    ),
    dict(
        # 删除与恢复现在各有一处 O_EXCL 占位（交叉审查必修 2 之后），
        # 成对改坏：任意一处失去防覆盖，对应用例必红
        name="回收站文件名防覆盖",
        old=['trash_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY',
             'os.open(dst, os.O_CREAT | os.O_EXCL | os.O_WRONLY'],
        new=['trash_path, os.O_CREAT | os.O_WRONLY',
             'os.open(dst, os.O_CREAT | os.O_WRONLY'],
        test="tests.test_trash_collision.TestTrashCollision.test_collision_keeps_existing_bytes",
        why="去掉 O_EXCL 后同名占位会覆盖既有回收站文件，软删除静默失效",
    ),
    dict(
        name="活跃账号切号防护",
        old='if latest and latest_uid == target["uid"]:',
        new='if latest:  # mutated',
        test="tests.test_remove_sync_guard.TestRemoveSyncGuard."
             "test_active_switch_during_confirm_does_not_overwrite_backup",
        why="不校验 uid 会把切号后的 B 凭据写进 A 的备份，A 的原始字节永久丢失",
    ),
    dict(
        name="删除互斥锁(Windows)",
        old='msvcrt.locking(self.fd, msvcrt.LK_NBLCK, 1)',
        new='pass  # mutated',
        test="tests.test_trash_lock.TestTrashLock."
             "test_lock_excludes_second_holder_same_process",
        why="去掉字节锁后第二个持有者不再被拒，回收站互斥失效",
        platform="win32",
    ),
    dict(
        name="删除互斥锁(POSIX)",
        old='fcntl.flock(self.fd, fcntl.LOCK_EX | fcntl.LOCK_NB)',
        new='pass  # mutated',
        test="tests.test_trash_lock.TestTrashLock."
             "test_lock_excludes_second_holder_same_process",
        why="去掉 flock 后第二个持有者不再被拒，回收站互斥失效",
        platform=("linux", "darwin"),
    ),
]


def _applies(m):
    p = m.get("platform")
    if p is None:
        return True
    if isinstance(p, str):
        return sys.platform == p
    return sys.platform in p


def run_test(test_id, wb_path=None):
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    if wb_path:
        env["WB_BIN"] = wb_path
    # 600s：test_trash_lock 的屏障在子进程被安全软件拖慢时会等到 240s 并重试一次，
    # 180s 会把"慢启动重试"误杀成超时（变异的重叠效应是确定性的，重试不会漏报）
    return subprocess.run(
        [sys.executable, "-m", "unittest", test_id, "-v"],
        cwd=ROOT, env=env, capture_output=True, text=True, timeout=600,
    )


def main():
    with open(SOURCE, "r", encoding="utf-8") as f:
        source = f.read()

    # 只跑当前平台适用的变异（Windows 字节锁 / POSIX flock 各一条）
    muts = [m for m in MUTATIONS if _applies(m)]

    # 先确认每个被变异用例在未变异时都是绿的，否则"变异后报错"会被误判为 CAUGHT
    for m in muts:
        baseline = run_test(m["test"])
        if baseline.returncode != 0:
            print("[FAIL] 基线未通过：%s" % m["test"])
            print((baseline.stdout + baseline.stderr)[-800:])
            return 1
    print("基线 %d/%d OK\n" % (len(muts), len(muts)))

    tmpdir = tempfile.mkdtemp(prefix="wb_mutation_")
    mutant = os.path.join(tmpdir, "workbuddy")
    rows, escaped = [], []

    for m in muts:
        olds = m["old"] if isinstance(m["old"], (list, tuple)) else [m["old"]]
        news = m["new"] if isinstance(m["new"], (list, tuple)) else [m["new"]]
        body, bad = source, None
        for old, new in zip(olds, news):
            count = body.count(old)
            if count != 1:
                bad = "变异点出现 %d 次，无法唯一定位" % count
                break
            body = body.replace(old, new, 1)
        if bad:
            rows.append((m["name"], "SKIP", bad))
            escaped.append(m["name"])
            continue

        with open(mutant, "w", encoding="utf-8") as f:
            f.write(body)

        r = run_test(m["test"], wb_path=mutant)
        out = r.stdout + r.stderr
        kind = "FAIL" if "FAIL:" in out else ("ERROR" if "ERROR:" in out else "-")
        caught = r.returncode != 0 and kind in ("FAIL", "ERROR")
        rows.append((m["name"], "CAUGHT" if caught else "MISSED",
                     "测试%s (%s)" % ("失败" if caught else "仍通过", kind)))
        if not caught:
            escaped.append(m["name"])

    width = max(len(r[0]) for r in rows)
    print("%-*s  %-7s  %s" % (width, "缺陷", "结果", "说明"))
    print("%s  %-7s  %s" % ("-" * width, "-" * 7, "-" * 40))
    for name, result, detail in rows:
        print("%-*s  %-7s  %s" % (width, name, result, detail))

    print("\n%d/%d 个变异被用例抓住。" % (len(rows) - len(escaped), len(rows)))
    if escaped:
        print("未抓住: " + ", ".join(escaped))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
