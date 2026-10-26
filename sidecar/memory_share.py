#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""跨账号全局记忆汇总（共享记忆库）。

与"覆盖式同步"的根本区别：

1. **汇总**：把所有账号 MEMORY.md 的条目收进一个库，而不是拿 A 的副本盖掉 B。
2. **去重择优**：相似条目聚成一簇，只让质量最高的一条参与注入；
   落选版本连同来源一起留档（superseded），不删除。
3. **不覆盖不丢失**：每个账号首次接入时把 MEMORY.md 存成基线快照；
   之后渲染 = 基线原文（一字不改）+ 共享段落（追加在后面）。
   账号自己新增的条目由 absorb() 增量并入基线，旧条目不会被顶掉。
4. **可还原**：restore() 把基线原样写回，写回前先备份当前文件。

只处理 MEMORY.md 一个文件。SOUL / IDENTITY / AGENT 属于"这个账号是谁"，
不参与汇总，避免人格互相污染。
"""

import contextlib
import difflib
import hashlib
import json
import os
import re
import shutil
import sys
import tempfile
import time
import unicodedata
from datetime import datetime

MEMORY_FILE = "MEMORY.md"

# 客户端 getUserLocalMemoryContent() 只注入前 4000 字，超出部分不会进上下文
INJECT_LIMIT = 4000

# 相似判定阈值：0.90 只合并"措辞几乎相同"的近重复。
# 刻意不做语义推断——把"用中文"和"不要用中文回复"判成同一条，比漏合并危险得多。
SIMILARITY_THRESHOLD = 0.90

# 每个条目最多保留几个落选版本（防止库无限膨胀）
MAX_SUPERSEDED = 5

BACKUP_KEEP = 10

# 发布预算：共享段落要在 4000 字窗口里生存，必须给原文留位置。
# 分诊后原文约 3200 字，4000-3200≈800，正好是共享段落的可用额度。
PUBLISH_BUDGET = 800

# 只发布 P0（红线）/ P1（显式指令）/ P2（项目约定）。
# P3（习惯）/ P4（推断/事实）不跨账号——"发布规则，不发布事实"。
PUBLISH_MAX_LEVEL = 2
MAX_PUBLISH_ENTRIES = 20

# 索引 + 分片：4000 字窗口装不下所有共享规则，超长或只属于"偏好/事实"的条目
# 原文落到 shards/<id>.md，窗口里只留一行索引（摘要 + 指向分片）。
SHARD_MIN_CHARS = 120
SHARD_DIRNAME = "shards"
INDEX_MARKER = "索引："
INDEX_SUMMARY_CHARS = 40
MAX_INDEX_LINES = 8
MAX_INDEX_LINE_CHARS = 80

BEGIN_MARK = "<!-- shared-memory:begin -->"
END_MARK = "<!-- shared-memory:end -->"
SHARED_HEADER = "## 共享记忆（来自其他账号）"
LIBRARY_VERSION = 1


# ----------------------------------------------------------------------------
# 路径
# ----------------------------------------------------------------------------
def default_root():
    return os.path.expanduser("~/.workbuddy")


def hub_dir(root=None):
    return os.path.normpath(os.path.join(root or default_root(), "cache", "shared_memory"))


def library_path(root=None):
    return os.path.join(hub_dir(root), "library.json")


def shard_dir(root=None):
    return os.path.join(hub_dir(root), SHARD_DIRNAME)


def snapshot_path(root, uid):
    return os.path.join(hub_dir(root), "originals", _safe(uid), MEMORY_FILE)


def memory_dir(root, uid, enterprise_id=None):
    """复刻客户端的账号目录规则：user-<uid>-<enterpriseId|personal>。"""
    uid = str(uid or "").strip()
    if not uid:
        return None
    ent = str(enterprise_id or "").strip() or "personal"
    return os.path.normpath(os.path.join(root or default_root(), "user-{}-{}".format(uid, ent)))


def memory_file(root, uid, enterprise_id=None):
    d = memory_dir(root, uid, enterprise_id)
    return os.path.join(d, MEMORY_FILE) if d else None


def _safe(name):
    return re.sub(r"[^\w\-]", "_", str(name or "unknown"))[:64] or "unknown"


def now_iso():
    return datetime.now().astimezone().isoformat(timespec="seconds")


# ----------------------------------------------------------------------------
# 跨进程锁
# ----------------------------------------------------------------------------
# 切号脚本与手动 CLI 可能同时跑 collect/apply：两个进程各读各写，后写的覆盖先写的。
# 文件内容不会写坏（原子写），但一次同步会白做。锁只保护"读-改-写"这一段。
class MemoryLockTimeout(RuntimeError):
    pass


_lock_state = {}


def _lock_file(fd):
    """非阻塞加锁；拿不到抛 OSError。"""
    if os.name == "nt":
        import msvcrt
        msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
    else:
        import fcntl
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)


def _unlock_file(fd):
    try:
        if os.name == "nt":
            import msvcrt
            msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
        else:
            import fcntl
            fcntl.flock(fd, fcntl.LOCK_UN)
    except OSError:
        pass


@contextlib.contextmanager
def file_lock(root=None, name="hub", timeout=5.0):
    """可重入的进程内 + 进程间锁。

    可重入是必需的：apply_all() 会逐个调用 apply_account()，外层已持锁，
    内层若再开一个句柄去抢同一把锁，在 Windows 上会自己把自己锁死。
    """
    path = os.path.join(hub_dir(root), ".{}.lock".format(name))
    state = _lock_state.get(path)
    if state is not None:
        state["depth"] += 1
        try:
            yield path
        finally:
            state["depth"] -= 1
        return

    os.makedirs(os.path.dirname(path), exist_ok=True)
    fd = os.open(path, os.O_CREAT | os.O_RDWR)
    deadline = time.time() + max(0.1, float(timeout))
    while True:
        try:
            _lock_file(fd)
            break
        except OSError:
            if time.time() >= deadline:
                os.close(fd)
                raise MemoryLockTimeout("另一个进程正在同步记忆（锁 {}）".format(path))
            time.sleep(0.05)

    _lock_state[path] = {"fd": fd, "depth": 1}
    try:
        yield path
    finally:
        _lock_state.pop(path, None)
        _unlock_file(fd)
        try:
            os.close(fd)
        except OSError:
            pass


# ----------------------------------------------------------------------------
# 文件读写
# ----------------------------------------------------------------------------
def read_text(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except (OSError, UnicodeDecodeError):
        return ""


def read_text_exact(path):
    """按字节读、不转换换行符。

    快照 / 还原必须走这条路径：`read_text()` 会把 CRLF 折成 LF，
    于是"第一次 apply 什么都没改"却把整篇文件的换行符换掉了。
    """
    try:
        with open(path, "rb") as f:
            return f.read().decode("utf-8")
    except (OSError, UnicodeDecodeError):
        return ""


def read_text_checked(path):
    """返回 (文本, 状态)。状态: ok | missing | not_utf8 | unreadable。

    非 UTF-8 必须与"空文件"区分开：把 GBK 文件当成空文件，会让基线快照被写成空、
    随后整篇被共享内容替换——这是不可接受的数据丢失。
    """
    try:
        with open(path, "rb") as f:
            raw = f.read()
    except FileNotFoundError:
        return "", "missing"
    except OSError:
        return "", "unreadable"
    try:
        return raw.decode("utf-8"), "ok"
    except UnicodeDecodeError:
        return "", "not_utf8"


def atomic_write_text(path, text):
    """同目录临时文件 + fsync + os.replace。客户端读记忆不做容错，不能出现半截文件。"""
    target_dir = os.path.dirname(os.path.abspath(path))
    os.makedirs(target_dir, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".tmp-mem-", dir=target_dir)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        if sys.platform != "win32":
            os.chmod(tmp, 0o600)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise


def backup_file(path, root):
    """覆盖前留一份带时间戳的副本，保留最近 BACKUP_KEEP 份。"""
    if not os.path.isfile(path):
        return None
    stamp = time.strftime("%Y%m%d-%H%M%S")
    base = os.path.join(hub_dir(root), "backups", _safe(os.path.basename(os.path.dirname(path))))
    os.makedirs(base, exist_ok=True)
    dest = os.path.join(base, "{}.md".format(stamp))
    seq = 1
    while os.path.exists(dest):
        dest = os.path.join(base, "{}-{}.md".format(stamp, seq))
        seq += 1
    shutil.copy2(path, dest)
    _prune(base)
    return dest


def _prune(base, keep=BACKUP_KEEP):
    try:
        names = sorted(n for n in os.listdir(base) if n.endswith(".md"))
    except OSError:
        return
    for name in names[:-keep] if len(names) > keep else []:
        try:
            os.remove(os.path.join(base, name))
        except OSError:
            pass


# ----------------------------------------------------------------------------
# 文本处理
# ----------------------------------------------------------------------------
def _managed_block_span(text):
    """返回受管段落的 (起, 止) 行号；结构不完整则返回 None。

    只认我们自己写出来的形状：起始标记独占一行 → 下一个非空行是标题 → 终止标记独占一行。
    这样用户正文里偶尔出现 `<!-- shared-memory:begin -->` 这几个字时不会被误判成
    "共享段开始"从而把后半篇截掉。
    """
    lines = text.splitlines(keepends=True)
    for i, line in enumerate(lines):
        if line.strip() != BEGIN_MARK:
            continue
        j = i + 1
        while j < len(lines) and not lines[j].strip():
            j += 1
        if j >= len(lines) or lines[j].strip() != SHARED_HEADER:
            continue
        for k in range(j, len(lines)):
            if lines[k].strip() == END_MARK:
                return i, k
        return None
    return None


def strip_shared_block(text):
    """去掉之前注入的共享段落，只留账号自己的原文。"""
    if not text:
        return text
    span = _managed_block_span(text)
    if span is None:
        return text
    start, end = span
    lines = text.splitlines(keepends=True)
    return ("".join(lines[:start]) + "".join(lines[end + 1:])).rstrip() + "\n"


def has_shared_block(text):
    return bool(text) and _managed_block_span(text) is not None


def normalize(text):
    """归一化：全角转半角、小写、去列表符号与标点空白。

    只用于比较，不用于回写——原文永远按原样保存。
    """
    t = unicodedata.normalize("NFKC", str(text or "")).lower()
    t = re.sub(r"^[\s\-*+>]+", "", t)
    t = re.sub(r"^\d+[.)]\s*", "", t)
    t = re.sub(r"[\s\W_]+", "", t, flags=re.UNICODE)
    return t


def _digits(norm):
    return tuple(re.findall(r"\d+", norm))


def similarity(a, b):
    """0~1。先做长度比剪枝，再算序列相似度，避免长文本两两比对的开销。

    两条硬规则（都是踩过坑补的）：
    - 数字序列不同 → 直接判不相似。"超时设为 30s" 和 "60s" 是两个事实，不是同一条
      记忆的两种写法；否则模板化的清单（只差编号）会被整片误合并。
    - 长度比 < 0.5 → 不相似。短句被长句包含的场景太容易误判。
    """
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    if _digits(a) != _digits(b):
        return 0.0
    short, long_ = (a, b) if len(a) <= len(b) else (b, a)
    if len(short) / float(len(long_)) < 0.5:
        return 0.0
    return difflib.SequenceMatcher(None, a, b, autojunk=False).ratio()


STRONG_WORDS = ("必须", "禁止", "不要", "默认", "一律", "始终", "永远", "只能",
                "must", "never", "always", "required")
HEDGE_WORDS = ("可能", "也许", "大概", "或许", "若干", "之类", "差不多", "应该是",
               "好像是", "大概是", "看情况", "似乎", "看起来")


def quality(text):
    """给一条记忆打 0~10 的质量分，返回 (分数, 理由列表)。

    刻意做成纯规则、可解释、可复现：同类实现里最容易出问题的是"用模型打分"——
    同样的输入两次分数不同，用户就无法理解为什么这条被保留、那条被丢掉。
    """
    raw = str(text or "").strip()
    norm = normalize(raw)
    if not norm:
        return 0.0, ["空内容"]
    score = 5.0
    reasons = []
    length = len(raw)

    if length < 6:
        score -= 2.0
        reasons.append("过短")
    elif length < 12:
        score -= 0.6
        reasons.append("偏短")
    elif length <= 120:
        score += 0.6
        reasons.append("长度适中")
    elif length > 240:
        score -= 0.8
        reasons.append("过长")

    if re.search(r"\d", raw):
        score += 0.6
        reasons.append("含具体数值")
    if re.search(r"[`/\\]|\b\w+\.(py|js|json|md|sh|ya?ml)\b", raw):
        score += 0.6
        reasons.append("含路径或代码")
    if any(w in raw.lower() for w in STRONG_WORDS):
        score += 0.8
        reasons.append("含明确约束")
    if re.search(r"^[\s]*[-*+]?\s*[^：:\n]{1,12}[：:]", raw):
        score += 0.5
        reasons.append("键值结构")

    hedges = sum(1 for w in HEDGE_WORDS if w in raw)
    if hedges:
        score -= min(1.2 * hedges, 2.4)
        reasons.append("含模糊措辞×{}".format(hedges))

    uniq_ratio = len(set(norm)) / float(len(norm))
    if uniq_ratio < 0.5:
        score -= 0.8
        reasons.append("重复度高")

    return round(max(0.0, min(10.0, score)), 2), reasons


def candidate_lines(text):
    """从记忆正文里挑出"条目行"：非空、不是标题、不是注释。"""
    out = []
    for line in str(text or "").splitlines():
        s = line.strip()
        if not s or s.startswith("#") or s.startswith("<!--"):
            continue
        if normalize(s):
            out.append(s)
    return out


# ----------------------------------------------------------------------------
# 发布口径：只发布规则，不发布事实
# ----------------------------------------------------------------------------
# 4,000 字窗口是全账号最容易踩的坑：把 99 条候选全塞进去，会把对方挤爆，
# 也会把 A 号的项目细节、路径、客户名搬到 B 号——那不是共享，是污染。
# 所以发布前先分级，只让"跨项目仍然成立的规则"过线。
REDLINE_WORDS = ("密钥", "秘钥", "token", "密码", "凭证", "隐私", "客户信息",
                 "身份证", "银行卡", "apikey", "api key")
EXPLICIT_WORDS = ("必须", "禁止", "不要", "不得", "一律", "始终", "永远", "只能",
                  "务必", "以后都", "叫我", "称呼", "默认用", "never", "must", "always")
PROJECT_WORDS = ("提交", "测试", "分支", "命名", "格式", "流程", "步骤", "目录",
                 "仓库", "合并", "推送", "审查", "构建", "部署")
HABIT_WORDS = ("偏好", "喜欢", "倾向", "简洁", "详细", "语气", "中文", "英文", "回复风格")

# 出现这些就说明是"某台机器上的事"，不是跨账号通用的规则
_LOCAL_FACT_PAT = re.compile(
    r"[A-Za-z]:[\\/]|/Users/|/home/|\\\\|https?://|file://"
    r"|~[\\/]|\.\.[\\/]|%[A-Za-z_]+%|\$HOME"
    r"|[\w.+-]+@[\w-]+\.[\w.]+"
    r"|[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
    re.IGNORECASE)


def publish_level(text):
    """0 红线 / 1 显式指令 / 2 项目约定 / 3 习惯 / 4 事实或推断。

    分级只用于"能不能跨账号发布"，不参与账号内择优——账号自己的记忆
    哪怕只是一条路径，也该留在自己的文件里。
    """
    raw = str(text or "").strip()
    low = raw.lower()
    if not normalize(raw):
        return 4
    if any(w in raw for w in HEDGE_WORDS):
        return 4
    if any(w in low for w in REDLINE_WORDS) and any(
            w in raw for w in ("禁止", "不要", "不得", "不能", "绝不", "must not")):
        return 0
    if any(w in raw for w in EXPLICIT_WORDS):
        return 1
    if any(w in raw for w in PROJECT_WORDS):
        return 2
    if any(w in raw for w in HABIT_WORDS):
        return 3
    return 4


def is_local_fact(text):
    r"""含"只在这台机器上成立"的细节：盘符/UNC/home 路径、相对上级路径、
    环境变量、URL、邮箱、UUID。

    先做 NFKC：全角 `Ｄ：\work` 与半角 `D:\work` 是同一个东西，
    不归一化就能被一个全角冒号绕过。
    """
    norm = unicodedata.normalize("NFKC", str(text or ""))
    return bool(_LOCAL_FACT_PAT.search(norm))


def is_fragment(text):
    """引用块、斜体元信息、表格行不是"一条规则"，是文档格式的碎片。

    它们常常含"必须/不要"这类词而骗过分级（例："> **启用条件**：…**不启用**"），
    但单独搬到另一个账号只会变成读不懂的断句。
    """
    s = str(text or "").lstrip()
    return s.startswith((">", "*", "_", "|")) or s in ("-", "--")


def publishable(entries, budget=PUBLISH_BUDGET, max_level=PUBLISH_MAX_LEVEL,
                limit=MAX_PUBLISH_ENTRIES):
    """挑出可跨账号发布的条目，返回 (选中, 统计)。

    排序先按级别、再按质量：一条 P0 红线永远排在一条 P4 推断前面，
    即使后者措辞更漂亮。预算按字符算（含列表符），先到先得，装不下就停。
    """
    ordered = sorted(entries or [],
                     key=lambda e: (publish_level(e.get("text", "")),
                                    -float(e.get("quality", 0) or 0)))
    picked = []
    skipped = {"level": 0, "local_fact": 0, "budget": 0, "empty": 0,
               "conflict": 0, "fragment": 0}
    used = 0
    for entry in ordered:
        text = str(entry.get("text") or "").strip()
        if not text:
            skipped["empty"] += 1
            continue
        if entry.get("suppressed"):
            # 与另一条规则互相否定，且优先级落败：保留在库里备查，但不注入
            skipped["conflict"] += 1
            continue
        if is_fragment(text):
            skipped["fragment"] += 1
            continue
        # 先判"是不是本机事实"：这个理由比"级别不够"更具体，
        # 一条带 D:/ 路径的规则被拦下时，用户需要看到的是"含本机路径"而不是"级别低"
        if is_local_fact(text):
            skipped["local_fact"] += 1
            continue
        if publish_level(text) > max_level:
            skipped["level"] += 1
            continue
        cost = len(text) + 3
        if used + cost > budget or len(picked) >= limit:
            skipped["budget"] += 1
            continue
        picked.append(entry)
        used += cost
    skipped["used"] = used
    return picked, skipped


def absorb(baseline_text, current_text):
    """把账号当前文件里的新条目并进基线，返回 (新基线, 新增数, 升级数)。

    规则：
    - 与基线里已有条目完全相同 → 跳过；
    - 相似但质量更高 → 用新的替换旧的那一行（旧的进库的 superseded）；
    - 都不相似 → 追加到末尾。
    基线里原有但当前文件没有的条目**不删除**——"不丢失"优先于"可删除"。
    """
    baseline = baseline_text or ""
    stripped = baseline.rstrip()
    eol = "\r\n" if "\r\n" in stripped else "\n"
    lines = stripped.splitlines() if stripped else []
    index = {normalize(l): i for i, l in enumerate(lines) if normalize(l)}
    added = upgraded = 0

    for line in candidate_lines(current_text):
        norm = normalize(line)
        if norm in index:
            continue
        best_i, best_sim = None, 0.0
        for existing_norm, i in index.items():
            sim = similarity(norm, existing_norm)
            if sim > best_sim:
                best_i, best_sim = i, sim
        if best_i is not None and best_sim >= SIMILARITY_THRESHOLD:
            old_q, _ = quality(lines[best_i])
            new_q, _ = quality(line)
            if new_q > old_q:
                del index[normalize(lines[best_i])]
                lines[best_i] = line
                index[norm] = best_i
                upgraded += 1
            continue
        lines.append(line)
        index[norm] = len(lines) - 1
        added += 1

    if not added and not upgraded:
        # 没有新条目就原样返回：`"\n".join()` 会把 CRLF 全文改写成 LF，
        # 一次"什么都没改"的 apply 也能把用户文件的字节全换掉。
        return baseline, 0, 0
    return eol.join(lines).rstrip() + eol, added, upgraded


def summarize(text, limit=INDEX_SUMMARY_CHARS):
    """摘要：去掉列表符/标题符后取正文前 N 字，超长加省略号。"""
    s = re.sub(r"\s+", " ", str(text or "").strip())
    s = re.sub(r"^[-*+>]+\s*", "", s)
    s = re.sub(r"^\d+[.)]\s*", "", s)
    s = re.sub(r"^#+\s*", "", s).strip()
    if len(s) > limit:
        s = s[:limit].rstrip() + "…"
    return s


def clip_index_line(line, limit=MAX_INDEX_LINE_CHARS):
    line = str(line or "").strip()
    if len(line) <= limit:
        return line
    return line[:max(1, limit - 1)].rstrip() + "…"


def build_index_line(entry, rel):
    """`- [P{n}] {摘要} → {shard}`，整行不超过 MAX_INDEX_LINE_CHARS。"""
    head = "- [P{}] ".format(publish_level(entry.get("text", "")))
    tail = " → " + rel
    room = MAX_INDEX_LINE_CHARS - len(head) - len(tail)
    return head + summarize(entry.get("text", ""), max(8, min(INDEX_SUMMARY_CHARS, room))) + tail


_LIST_PREFIX = re.compile(r"^[-*+•]\s+")


def _bullet(text):
    """条目 → 渲染行。条目本身可能已经带 "- "（候选行保留了列表符），
    再拼一次就会出现 "- - xxx"，所以先剥掉原前缀。"""
    return "- " + _LIST_PREFIX.sub("", str(text or "").strip())


def render(origin_text, shared_entries, limit=INJECT_LIMIT, index_entries=None):
    """基线原文 + 共享段落（+ 索引区）。返回 (全文, 写入条数, 截断条数, 索引条数)。

    字符预算优先给账号自己的内容：共享段落只能在剩余空间里塞，
    绝不为了塞共享而截断原文——那等于用别人的记忆挤掉自己的记忆。
    索引区排在正式条目之后、结尾提示之前，同样只吃剩余预算：
    连原文都放不下的账号，索引也不会被硬塞进去。

    预算按**最终拼出来的字节数**校验，不靠加减法估算——
    估算漏掉分隔符就会写出 4001 字的文件，而客户端只认前 4000 字。
    """
    origin = (origin_text or "").rstrip()
    index_entries = list(index_entries or [])

    def _plain():
        # 原文自己就顶到 4000 时，不能再补一个换行——那会写出 4001 字的文件，
        # 客户端只会注入前 4000 字，最后一行永远看不到
        return origin + "\n" if len(origin) + 1 <= limit else origin

    if not shared_entries and not index_entries:
        return _plain(), 0, 0, 0

    # 保留原文的换行风格：CRLF 文件不能被我改写成 LF，那是"原文一字不改"的底线
    eol = "\r\n" if "\r\n" in origin else "\n"
    header = [BEGIN_MARK, SHARED_HEADER, ""]
    footer_tpl = "- （另有 {} 条共享记忆未展开，超出单次注入上限）"

    def compose(lines, footer=None):
        tail = list(lines) + ([footer] if footer else [])
        return origin + eol * 2 + eol.join(header + tail + ["", END_MARK]) + eol

    body = []
    overflow = 0
    for entry in shared_entries:
        line = _bullet(entry.get("text"))
        if len(compose(body + [line])) > limit:
            overflow = len(shared_entries) - len(body)
            break
        body.append(line)
    written = len(body)

    footer = None
    if overflow:
        total = overflow
        footer = footer_tpl.format(total)
        while body and len(compose(body, footer)) > limit:
            body.pop()
            total += 1
            footer = footer_tpl.format(total)
        if len(compose(body, footer)) > limit:
            footer = None
        written = len(body)

    index_lines = []
    if index_entries and len(compose(body + [INDEX_MARKER], footer)) <= limit:
        for entry in index_entries[:MAX_INDEX_LINES]:
            line = clip_index_line(entry.get("index_line"))
            if not line:
                continue
            if len(compose(body + [INDEX_MARKER] + index_lines + [line], footer)) > limit:
                break
            index_lines.append(line)

    lines = body + ([INDEX_MARKER] + index_lines if index_lines else [])
    if not lines:
        return _plain(), 0, len(shared_entries), 0
    text = compose(lines, footer)
    if len(text) > limit:
        # 兜底：上面每一步都按最终长度校验过，走到这里说明有未预料的溢出。
        # 宁可少写一条共享，也不能写出一个会被客户端截断的文件。
        return _plain(), 0, len(shared_entries), 0
    return text, written, max(0, len(shared_entries) - written), len(index_lines)


# ----------------------------------------------------------------------------
# 记忆分诊（rebalance）：把 MEMORY.md 的内容按性质分流到容量更大的常驻通道
# ----------------------------------------------------------------------------
# 客户端有四个常驻通道，上限不同：
#   MEMORY.md  4000   —— 事实、配置、项目状态
#   SOUL.md   10000   —— 行为准则、红线、流程
#   USER.md   10000   —— 称呼、语言、沟通偏好
#   IDENTITY.md 10000 —— 身份元数据（不放记忆）
# 把全部内容堆在 MEMORY.md 是容量浪费：分诊后同样一份记忆可以完整保留，
# 而不是被 4000 字截掉三分之一。

REBALANCE_BEGIN = "<!-- memory-rebalance:begin -->"
REBALANCE_END = "<!-- memory-rebalance:end -->"

USER_MARKERS = ("称呼", "叫我", "昵称", "名字", "语言", "中文", "英文",
                "沟通", "语气", "画像", "回复风格", "称呼为")
SOUL_MARKERS = ("必须", "禁止", "不要", "不得", "默认", "一律", "始终", "永远",
                "优先", "流程", "步骤", "红线", "纪律", "规则", "规范",
                "提交", "测试", "分支", "推送", "审查", "命名", "格式")


def classify_line(line):
    """按"关于人 / 怎么做 / 什么事"给一行记忆分诊。

    纯关键词规则，刻意保守：分不清就留在 MEMORY（原处），不硬塞。
    迁移是可逆的，但把事实误塞进人格通道会让行为变怪，代价比多占几百字高。
    """
    s = str(line or "").strip()
    if not s or s.startswith("#") or s.startswith("<!--"):
        return "memory"
    if any(k in s for k in USER_MARKERS):
        return "user"
    if any(k in s for k in SOUL_MARKERS):
        return "soul"
    return "memory"


def strip_rebalance_section(text):
    """移除上一次分诊写入的受管段落（SOUL/USER 各一段）。"""
    if not text or REBALANCE_BEGIN not in text:
        return text
    start = text.find(REBALANCE_BEGIN)
    end = text.find(REBALANCE_END)
    if end == -1:
        return text
    return (text[:start] + text[end + len(REBALANCE_END):]).rstrip() + "\n"


def plan_rebalance(memory_text, target=3200):
    """算出"哪些行留在 MEMORY、哪些搬到 SOUL/USER"。

    只在 MEMORY 超过 target 时才搬，且优先搬 SOUL 类（通常占比最大），
    搬到 target 以下立即停止——不做无谓的整体迁移。
    """
    lines = str(memory_text or "").splitlines()
    kinds = [classify_line(line) for line in lines]
    total = sum(len(line) + 1 for line in lines)
    moved_idx = set()
    moved = {"soul": [], "user": []}

    remaining = total
    if remaining > target:
        for kind in ("soul", "user"):
            for i, line in enumerate(lines):
                if remaining <= target:
                    break
                if kinds[i] != kind or i in moved_idx:
                    continue
                moved[kind].append(line)
                moved_idx.add(i)
                remaining -= len(line) + 1

    kept = [line for i, line in enumerate(lines) if i not in moved_idx]
    kept_size = sum(len(line) + 1 for line in kept)
    return {
        "lines_in": len(lines),
        "memory_lines": len(kept),
        "memory_size": kept_size,
        "target": target,
        "moved_soul": moved["soul"],
        "moved_user": moved["user"],
        "moved_soul_size": sum(len(x) + 1 for x in moved["soul"]),
        "moved_user_size": sum(len(x) + 1 for x in moved["user"]),
        "kept": kept,
        "overflow_before": max(0, total - target),
    }


SECTION_USER_KEYS = ("称呼", "叫我", "昵称", "画像", "偏好", "沟通习惯", "语言习惯")
SECTION_FACT_KEYS = ("事实", "状态", "清单", "路径", "配置", "进度", "账号")


def _split_sections(text):
    """按 #/## 标题切块，标题之前的引言单独成块。块内保留原始行序。"""
    blocks = []
    heading = None
    buf = []
    for line in str(text or "").splitlines():
        if re.match(r"^#{1,2}\s+\S", line):
            if heading is not None or buf:
                blocks.append((heading, buf))
            heading, buf = line, [line]
        else:
            buf.append(line)
    if heading is not None or buf:
        blocks.append((heading, buf))
    return blocks


def classify_section(heading, body):
    """按"这一节在讲什么"决定去处。

    单行分类（classify_line）会把一个列表拆散：缩进子项被搬走，父标题留在原地，
    两边都读不懂。所以文档有分节结构时先按节判断，整节一起搬。
    """
    head = heading or ""
    if not head:
        return "memory"
    if head.startswith("# "):          # 文档标题，永远留在 MEMORY
        return "memory"
    if any(k in head for k in SECTION_USER_KEYS):
        return "user"
    if any(k in head for k in SECTION_FACT_KEYS):
        return "memory"
    if sum(1 for line in body if is_local_fact(line)) >= 2:
        return "memory"
    return "soul"


def plan_rebalance_sections(memory_text, target=3200):
    """按整节迁移：从最后一节往前搬，搬到 target 以下就停。

    从尾部搬是为了保持文档顺序——被搬走的总是结尾的几节，
    留在 MEMORY 里的前几节仍然读得通顺。
    """
    blocks = _split_sections(memory_text)
    sizes = [sum(len(line) + 1 for line in body) for _, body in blocks]
    kinds = [classify_section(head, body) for head, body in blocks]
    keep = [True] * len(blocks)
    moved = {"soul": [], "user": []}
    remaining = sum(sizes)

    if remaining > target:
        for i in range(len(blocks) - 1, -1, -1):
            if remaining <= target:
                break
            if kinds[i] == "memory":
                continue
            moved[kinds[i]].extend(blocks[i][1])
            remaining -= sizes[i]
            keep[i] = False

    kept = []
    for i, (_, body) in enumerate(blocks):
        if keep[i]:
            kept.extend(body)
    return {
        "mode": "section",
        "lines_in": sum(len(body) for _, body in blocks),
        "memory_lines": len(kept),
        "memory_size": sum(len(line) + 1 for line in kept),
        "target": target,
        "moved_soul": [l for l in moved["soul"] if l.strip()],
        "moved_user": [l for l in moved["user"] if l.strip()],
        "moved_soul_size": sum(len(l) + 1 for l in moved["soul"] if l.strip()),
        "moved_user_size": sum(len(l) + 1 for l in moved["user"] if l.strip()),
        "sections": [{"heading": h or "（引言）", "kind": k, "size": s, "moved": not keep[i]}
                     for i, ((h, _), k, s) in enumerate(zip(blocks, kinds, sizes))],
        "kept": kept,
        "overflow_before": max(0, sum(sizes) - target),
    }


def _render_channel_section(title, lines):
    body = "\n".join(lines)
    return "{}\n## {}\n\n{}\n{}\n".format(REBALANCE_BEGIN, title, body, REBALANCE_END)


def rebalance_account(acc, root=None, target=3200, apply=False):
    """把一个账号的记忆按通道重新分配。

    apply=False（默认）只返回计划，不写任何文件。
    写入顺序：先备份三个文件 → 写 SOUL/USER 的新段落 → 最后改 MEMORY，
    这样即使中途失败，MEMORY 原文仍在，最坏情况是多了两段可清理的内容。
    """
    root = root or default_root()
    alias = acc.get("alias") or acc.get("uid")
    try:
        with file_lock(root):
            return _rebalance_locked(acc, root, target, apply)
    except MemoryLockTimeout as e:
        return {"ok": False, "alias": alias, "action": "locked", "reason": str(e),
                "apply": bool(apply), "plan": None, "written": [], "backups": []}
    except OSError as e:
        return {"ok": False, "alias": alias, "action": "write_failed", "reason": str(e),
                "apply": bool(apply), "plan": None, "written": [], "backups": []}


def _rebalance_locked(acc, root, target, apply):
    uid = str(acc.get("uid") or "").strip()
    d = memory_dir(root, uid, acc.get("enterprise_id"))
    result = {"ok": False, "alias": acc.get("alias") or uid, "apply": bool(apply),
              "plan": None, "written": [], "backups": []}
    if not d:
        result["action"] = "no_memory_file"
        return result
    mem_path = os.path.join(d, MEMORY_FILE)
    soul_path = os.path.join(d, "SOUL.md")
    user_path = os.path.join(d, "USER.md")
    mem_text, state = read_text_checked(mem_path)
    if state != "ok":
        result["action"] = "skipped_encoding" if state == "not_utf8" else "no_memory_file"
        return result

    # 规划只看自有内容：共享段落由 apply 维护，不能被当成"一节"搬进 SOUL
    own_text = strip_shared_block(mem_text)
    shared_block = ""
    if has_shared_block(mem_text):
        s = mem_text.find(BEGIN_MARK)
        e = mem_text.find(END_MARK) + len(END_MARK)
        shared_block = mem_text[s:e].strip()

    # 有分节结构的文档按整节搬（不拆列表）；散条目的文档仍按行搬
    blocks = _split_sections(own_text)
    has_sections = sum(1 for head, _ in blocks if head and head.startswith("## ")) >= 2
    plan = (plan_rebalance_sections(own_text, target=target) if has_sections
            else plan_rebalance(own_text, target=target))
    if "mode" not in plan:
        plan["mode"] = "line"
    # 投影要减掉上一次分诊写进去的受管段落，否则重复计数，
    # 明明文件没变也会显示 5253 → 8634
    soul_base = len(strip_rebalance_section(read_text_exact(soul_path)))
    user_base = len(strip_rebalance_section(read_text_exact(user_path)))
    soul_before = len(read_text_exact(soul_path))
    user_before = len(read_text_exact(user_path))
    result["projected"] = {
        "memory_before": len(own_text),
        "memory_after": plan["memory_size"],
        "shared_chars": len(shared_block),
        "soul_before": soul_before,
        "soul_after": soul_base + plan["moved_soul_size"],
        "user_before": user_before,
        "user_after": user_base + plan["moved_user_size"],
    }
    result["plan"] = {
        "mode": plan.get("mode"),
        "memory_size": plan["memory_size"],
        "moved_soul": len(plan["moved_soul"]),
        "moved_user": len(plan["moved_user"]),
        "moved_soul_size": plan["moved_soul_size"],
        "moved_user_size": plan["moved_user_size"],
        "sections": plan.get("sections") or [],
        "target": target,
    }
    if not apply or (not plan["moved_soul"] and not plan["moved_user"]):
        result["ok"] = True
        result["action"] = "planned" if apply is False else "nothing_to_do"
        return result

    # 先留存基线快照（供 restore 还原），再备份三个文件，最后才写
    _ensure_snapshot(root, uid, mem_path, current_text=mem_text)
    for p in (mem_path, soul_path, user_path):
        b = backup_file(p, root)
        if b:
            result["backups"].append(b)

    if plan["moved_soul"]:
        soul_text = strip_rebalance_section(read_text(soul_path))
        soul_text = soul_text.rstrip() + "\n\n" + _render_channel_section(
            "工作准则（来自长期记忆）", plan["moved_soul"])
        atomic_write_text(soul_path, soul_text)
        result["written"].append("SOUL.md")

    if plan["moved_user"]:
        user_text = strip_rebalance_section(read_text(user_path))
        user_text = user_text.rstrip() + "\n\n" + _render_channel_section(
            "用户偏好（来自长期记忆）", plan["moved_user"])
        atomic_write_text(user_path, user_text)
        result["written"].append("USER.md")

    new_mem = "\n".join(plan["kept"]).rstrip() + "\n"
    if shared_block:
        # 共享段落不属于"自有内容"，原样保留在文件末尾，等下轮 apply 重新渲染
        new_mem = new_mem.rstrip() + "\n\n" + shared_block + "\n"
    atomic_write_text(mem_path, new_mem)
    result["written"].append(MEMORY_FILE)
    result["ok"] = True
    result["action"] = "rebalanced"
    return result
# ----------------------------------------------------------------------------
# 共享库
# ----------------------------------------------------------------------------
def empty_library():
    return {"version": LIBRARY_VERSION, "updated_at": None, "entries": [], "tombstones": []}


def load_library(root=None):
    try:
        with open(library_path(root), "r", encoding="utf-8") as f:
            raw = json.load(f)
    except (OSError, ValueError):
        return empty_library()
    if not isinstance(raw, dict):
        return empty_library()
    entries = raw.get("entries")
    stones = raw.get("tombstones")
    lib = empty_library()
    lib["updated_at"] = raw.get("updated_at")
    lib["entries"] = entries if isinstance(entries, list) else []
    lib["tombstones"] = stones if isinstance(stones, list) else []
    return lib


def save_library(lib, root=None):
    lib["updated_at"] = now_iso()
    atomic_write_text(library_path(root), json.dumps(lib, ensure_ascii=False, indent=2) + "\n")


def _entry_id(norm):
    return hashlib.sha1(norm.encode("utf-8")).hexdigest()[:12]


def tombstone_norms(lib):
    return {t.get("norm") for t in (lib or {}).get("tombstones") or [] if t.get("norm")}


def active_entries(lib):
    """库里真正还活着的条目（排除被 forget 掉的）。"""
    dead = tombstone_norms(lib)
    out = []
    for e in (lib or {}).get("entries") or []:
        norm = e.get("norm") or normalize(e.get("text", ""))
        if norm and norm in dead:
            continue
        out.append(e)
    return out


def forget(keyword, root=None, apply=False):
    """按关键词/条目 id 把条目从库里摘掉，并留墓碑防复活。

    只动共享库，不动账号文件：账号自己的原文属于用户，工具不替人删记忆。
    下次 apply 重建共享段落时，这几条自然消失。
    """
    key = str(keyword or "").strip()
    result = {"ok": False, "keyword": key, "matched": [], "applied": False}
    if not key:
        result["reason"] = "关键词为空"
        return result
    norm_key = normalize(key)
    with file_lock(root):
        lib = load_library(root)
        matched = []
        for e in lib.get("entries") or []:
            text = str(e.get("text") or "")
            if key == e.get("id") or key in text or (norm_key and norm_key in (e.get("norm") or "")):
                matched.append(e)
        result["matched"] = [{"id": e.get("id"), "text": e.get("text")} for e in matched]
        if not apply or not matched:
            result["ok"] = True
            result["applied"] = False
            return result

        dead = tombstone_norms(lib)
        stones = lib.setdefault("tombstones", [])
        for e in matched:
            norm = e.get("norm") or normalize(e.get("text", ""))
            if norm and norm not in dead:
                stones.append({"norm": norm, "text": e.get("text"),
                               "id": e.get("id"), "at": now_iso()})
                dead.add(norm)
        ids = {e.get("id") for e in matched}
        lib["entries"] = [e for e in lib.get("entries") or [] if e.get("id") not in ids]
        save_library(lib, root)
        result["ok"] = True
        result["applied"] = True
        result["tombstones"] = len(stones)
        return result


_negated_pattern = re.compile(r"不要|禁止|不得|不能|绝不|别再|never|must\s+not|don'?t", re.IGNORECASE)
_polarity_strip = re.compile(
    r"不要|禁止|不得|不能|绝不|别再|不许|必须|务必|一律|只能|always|never|must|don'?t|别",
    re.IGNORECASE)


def is_negated(text):
    """一条记忆是不是"否定式约束"。用于发现两个账号互相打架的规则。"""
    return bool(_negated_pattern.search(str(text or "")))


def polarity_form(text):
    """抹掉肯定/否定与强度词后的形式。

    两条规则如果只差一个"不要"，字面相似度会被这个差异拉低到 0.7 以下，
    永远进不了同一个相似簇——所以冲突检测必须先把极性抹平再比。
    """
    return _polarity_strip.sub("", normalize(text))


def _cluster(items):
    """并查集聚类：相似度 ≥ 阈值的条目归为一簇。"""
    n = len(items)
    parent = list(range(n))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    for i in range(n):
        for j in range(i + 1, n):
            if similarity(items[i]["norm"], items[j]["norm"]) >= SIMILARITY_THRESHOLD:
                union(i, j)

    groups = {}
    for i in range(n):
        groups.setdefault(find(i), []).append(i)
    return list(groups.values())


def _mark_conflicts(entries):
    """找出"只差一个否定词"的两条规则，标记落败方为不注入。

    为什么不在聚类里做：负号差异会把字面相似度压到 0.9 以下，两条根本进不了
    同一个簇。所以这里用"抹掉极性后的形式"重新分桶，再按级别+质量选唯一注入版本。
    落败方不删除——它可能才是用户真正想要的，只是暂时排在后面。
    """
    buckets = {}
    for e in entries:
        form = polarity_form(e.get("text", ""))
        if form:
            buckets.setdefault(form, []).append(e)

    count = 0
    for form, group in buckets.items():
        if len(group) < 2:
            continue
        if not any(is_negated(e.get("text", "")) for e in group):
            continue
        ordered = sorted(group, key=lambda e: (publish_level(e.get("text", "")),
                                               -len(e.get("sources") or []),
                                               -float(e.get("quality") or 0),
                                               e.get("text") or ""))
        winner = ordered[0]
        for loser in ordered[1:]:
            loser["suppressed"] = True
            loser["conflict_of"] = winner.get("id")
            winner.setdefault("conflicts", []).append({
                "id": loser.get("id"),
                "text": loser.get("text"),
                "sources": loser.get("sources") or [],
                "reason": "否定差异（只保留优先级更高的一条参与注入）",
            })
            count += 1
    for e in entries:
        e.setdefault("conflicts", [])
    return count


def collect(accounts, root=None):
    """扫描所有账号的 MEMORY.md，汇总去重后写库。

    accounts: [{"alias","uid","enterprise_id"}]
    返回 {ok, accounts, raw_entries, entries, merged, superseded, conflicts, forgotten}
    """
    root = root or default_root()
    with file_lock(root):
        return _collect_locked(accounts, root)


def _collect_locked(accounts, root):
    old = load_library(root)
    old_by_id = {e.get("id"): e for e in old.get("entries") or []}
    dead = tombstone_norms(old)

    items = []
    per_account = {}
    skipped = []
    forgotten = 0
    for acc in accounts or []:
        uid = str(acc.get("uid") or "").strip()
        path = memory_file(root, uid, acc.get("enterprise_id"))
        if not path:
            continue
        raw, state = read_text_checked(path)
        alias = acc.get("alias") or uid
        if state == "not_utf8":
            per_account[alias] = "跳过（非 UTF-8）"
            skipped.append(alias)
            continue
        text = strip_shared_block(raw)
        lines = candidate_lines(text)
        per_account[alias] = len(lines)
        for line in lines:
            norm = normalize(line)
            if norm in dead:
                # forget 过的条目不能因为账号文件里还在就被收回来
                forgotten += 1
                continue
            score, _ = quality(line)
            items.append({
                "text": line.strip(),
                "norm": norm,
                "uid": uid,
                "alias": acc.get("alias") or "",
                "quality": score,
            })

    merged = 0
    superseded_count = 0
    conflict_count = 0
    entries = []
    for group in _cluster(items) if items else []:
        versions = [items[i] for i in group]
        versions.sort(key=lambda v: (v["quality"], len(v["norm"])), reverse=True)
        winner = versions[0]
        eid = _entry_id(winner["norm"])
        prev = old_by_id.get(eid) or {}
        losers = []
        for loser in versions[1:]:
            if normalize(loser["text"]) == normalize(winner["text"]):
                continue
            losers.append({
                "text": loser["text"],
                "uid": loser["uid"],
                "quality": loser["quality"],
            })
        if versions[1:]:
            merged += 1
        superseded_count += len(losers)
        entries.append({
            "id": eid,
            "text": winner["text"],
            "norm": winner["norm"],
            "quality": winner["quality"],
            "sources": sorted({v["uid"] for v in versions if v["uid"]}),
            "aliases": sorted({v["alias"] for v in versions if v["alias"]}),
            "superseded": (prev.get("superseded") or []) + losers,
            "conflicts": [],
            "first_seen": prev.get("first_seen") or now_iso(),
            "last_seen": now_iso(),
            # id 由归一化文本决定，同一个 id 就是同一条记忆：compact 建好的
            # 分片与索引行原样带过来，否则每次 collect 都会把索引抹掉
            "shard": prev.get("shard"),
            "index_line": prev.get("index_line"),
        })

    conflict_count = _mark_conflicts(entries)

    for e in entries:
        if len(e["superseded"]) > MAX_SUPERSEDED:
            e["superseded"] = e["superseded"][:MAX_SUPERSEDED]

    entries.sort(key=lambda e: (-e["quality"], e["text"]))
    lib = {"version": LIBRARY_VERSION, "updated_at": now_iso(), "entries": entries,
           "tombstones": old.get("tombstones") or []}
    save_library(lib, root)
    return {
        "ok": True,
        "accounts": per_account,
        "skipped": skipped,
        "raw_entries": len(items),
        "entries": len(entries),
        "merged": merged,
        "superseded": superseded_count,
        "conflicts": conflict_count,
        "forgotten": forgotten,
    }


def _ensure_snapshot(root, uid, memory_path, current_text=None):
    """首次接入时保存基线快照；已存在则原样返回，绝不覆盖。"""
    path = snapshot_path(root, uid)
    if os.path.isfile(path):
        return read_text_exact(path)
    current = strip_shared_block(current_text if current_text is not None else read_text(memory_path))
    atomic_write_text(path, current)
    return current


def apply_account(acc, root=None, lib=None, budget=PUBLISH_BUDGET,
                  max_level=PUBLISH_MAX_LEVEL):
    """把一个账号的 MEMORY.md 渲染成「基线原文 + 共享段落」。

    返回 {ok, alias, action, shared, truncated, added, upgraded, backup, skipped}
    action: created | updated | unchanged | no_memory_file | error | locked | write_failed

    锁拿不到、目录不可写都必须变成返回值而不是异常：这个函数会在切号流程里
    被批量调用，一次异常会把后面所有账号的同步都中断掉。
    """
    root = root or default_root()
    alias = acc.get("alias") or acc.get("uid")
    blank = {"ok": False, "alias": alias, "action": "error", "shared": 0,
             "truncated": 0, "added": 0, "upgraded": 0, "backup": None, "skipped": {}}
    try:
        with file_lock(root):
            return _apply_locked(acc, root, lib, budget, max_level)
    except MemoryLockTimeout as e:
        blank["action"] = "locked"
        blank["reason"] = str(e)
        return blank
    except OSError as e:
        blank["action"] = "write_failed"
        blank["reason"] = str(e)
        return blank


def _apply_locked(acc, root, lib, budget, max_level):
    lib = lib or load_library(root)
    uid = str(acc.get("uid") or "").strip()
    alias = acc.get("alias") or uid
    path = memory_file(root, uid, acc.get("enterprise_id"))
    result = {"ok": False, "alias": alias, "action": "error", "shared": 0,
              "truncated": 0, "indexed": 0, "added": 0, "upgraded": 0,
              "backup": None, "skipped": {}}
    if not path:
        result["action"] = "no_memory_file"
        return result
    if not os.path.isfile(path):
        result["action"] = "no_memory_file"
        return result

    current, state = read_text_checked(path)
    if state == "not_utf8":
        # 读不了就不动：宁可这次不共享，也不能把 GBK/UTF-16 文件当空文件覆盖掉
        result["ok"] = True
        result["action"] = "skipped_encoding"
        result["reason"] = "MEMORY.md 不是 UTF-8 编码，已跳过（未做任何写入）"
        return result
    # 基线取"文件里现在的自有内容"，不是首次快照。
    # 快照是接入那一刻的原样，只用于 restore；拿它当基线会把 rebalance 刚搬走的
    # 章节原样写回来——分诊被撤销，文件回到 5953 字，共享段落又落到截断线外。
    own_text = strip_shared_block(current)
    snap_before = _ensure_snapshot(root, uid, path, current_text=current)
    new_snap, added, upgraded = absorb(snap_before, own_text)
    if new_snap != snap_before:
        # 用户手写的新条目仍要进快照，否则 restore 会把它抹掉
        backup_file(snapshot_path(root, uid), root)
        atomic_write_text(snapshot_path(root, uid), new_snap)
    baseline = own_text
    new_baseline = baseline
    result["added"] = added
    result["upgraded"] = upgraded

    own_norms = [normalize(l) for l in candidate_lines(new_baseline)]
    candidates = []
    for entry in active_entries(lib):
        norm = entry.get("norm") or normalize(entry.get("text", ""))
        if not norm:
            continue
        if any(norm == n for n in own_norms):
            continue
        if any(similarity(norm, n) >= SIMILARITY_THRESHOLD for n in own_norms):
            continue
        candidates.append(entry)

    shared, skipped = publishable(candidates, budget=budget, max_level=max_level)
    result["skipped"] = skipped
    rendered, written, truncated, indexed = render(
        new_baseline, shared, index_entries=_index_fallback(shared, candidates))
    result["shared"] = written
    result["truncated"] = truncated
    result["indexed"] = indexed

    if rendered == current:
        result["ok"] = True
        result["action"] = "unchanged"
        return result

    result["backup"] = backup_file(path, root)
    try:
        atomic_write_text(path, rendered)
    except OSError as e:
        result["ok"] = False
        result["action"] = "write_failed"
        result["reason"] = str(e)
        return result
    result["ok"] = True
    result["action"] = "created" if not has_shared_block(current) else "updated"
    return result


def _index_fallback(shared, candidates, limit=MAX_INDEX_LINES):
    """挑出"没进正式条目、但已有索引行"的条目，供 render 在剩余预算里补索引。

    排除两类，哪怕它们有索引行：
    - suppressed：与另一条互相否定且落败，注入索引等于把两条冲突规则都摆出来；
    - 含本机路径/账号的条目：索引行会把 D:/ 路径、邮箱原样搬到别的账号。
    """
    picked = {e.get("norm") or normalize(e.get("text", "")) for e in shared or []}
    out = []
    for entry in candidates or []:
        if entry.get("suppressed"):
            continue
        norm = entry.get("norm") or normalize(entry.get("text", ""))
        if norm in picked or not entry.get("index_line"):
            continue
        if is_local_fact(entry.get("text", "")):
            continue
        out.append(entry)
    out.sort(key=lambda e: (publish_level(e.get("text", "")),
                            -float(e.get("quality") or 0)))
    return out[:limit]


def shard_rel(entry_id):
    return "{}/{}.md".format(SHARD_DIRNAME, _safe(entry_id))


def _shard_text(entry, text):
    """分片文件：第一行写来源账号与首次收录时间（纯文本，不引 YAML），空行后是原文。"""
    who = "、".join(entry.get("aliases") or []) or "、".join(entry.get("sources") or []) or "未知"
    first = entry.get("first_seen")
    if not first:
        first = now_iso()
        entry["first_seen"] = first
    return "来源: {} | 首次收录: {} | 条目 id: {}\n\n{}\n".format(
        who, first, entry.get("id") or "-", text)


def compact(root=None, shard_min=SHARD_MIN_CHARS):
    """给"窗口装不下"的条目建分片 + 索引行，返回 {ok, shards, indexed, skipped}。

    只处理原文，不改发布口径：分片是存放处，索引行才是注入物。
    内容没变就不重写文件，重复执行也不会多出分片——文件名只由条目 id 决定。
    """
    root = root or default_root()
    with file_lock(root):
        lib = load_library(root)
        out = {"ok": True, "shards": 0, "indexed": 0, "skipped": 0, "written": 0}
        changed = False
        for entry in active_entries(lib):
            text = str(entry.get("text") or "").strip()
            if not text or not (len(text) > shard_min or publish_level(text) >= 3):
                out["skipped"] += 1
                continue
            rel = shard_rel(entry.get("id") or _entry_id(entry.get("norm") or normalize(text)))
            content = _shard_text(entry, text)
            path = os.path.join(hub_dir(root), rel)
            if read_text(path) != content:
                atomic_write_text(path, content)
                out["written"] += 1
            line = build_index_line(entry, rel)
            if entry.get("shard") != rel or entry.get("index_line") != line:
                changed = True
            entry["shard"] = rel
            entry["index_line"] = line
            out["indexed"] += 1
        out["shards"] = out["indexed"]
        if changed or out["written"]:
            save_library(lib, root)
        return out


def apply_all(accounts, root=None, budget=PUBLISH_BUDGET, max_level=PUBLISH_MAX_LEVEL):
    # 不在这里整批持锁：每个账号自己取锁，一个账号拿不到锁不会拖死其余账号
    lib = load_library(root)
    return [apply_account(a, root=root, lib=lib, budget=budget, max_level=max_level)
            for a in accounts or []]


def restore_account(acc, root=None):
    """把基线快照原样写回账号文件；写回前备份当前文件。"""
    root = root or default_root()
    alias = acc.get("alias") or acc.get("uid")
    try:
        with file_lock(root):
            return _restore_locked(acc, root)
    except MemoryLockTimeout as e:
        return {"ok": False, "alias": alias, "action": "locked", "reason": str(e)}
    except OSError as e:
        return {"ok": False, "alias": alias, "action": "write_failed", "reason": str(e)}


def _restore_locked(acc, root):
    uid = str(acc.get("uid") or "").strip()
    path = memory_file(root, uid, acc.get("enterprise_id"))
    snap = snapshot_path(root, uid)
    result = {"ok": False, "action": "error", "backup": None, "alias": acc.get("alias") or uid}
    if not os.path.isfile(snap):
        result["action"] = "no_snapshot"
        return result
    if not path:
        result["action"] = "no_memory_file"
        return result
    result["backup"] = backup_file(path, root)
    atomic_write_text(path, read_text_exact(snap))

    # 还原是"回到 rebalance 之前"，所以 SOUL/USER 里由分诊写入的段落也要摘掉，
    # 否则内容会在 MEMORY 与 SOUL 各存一份
    d = os.path.dirname(path)
    cleaned = []
    for name in ("SOUL.md", "USER.md"):
        p = os.path.join(d, name)
        text = read_text_exact(p)
        if REBALANCE_BEGIN in text:
            backup_file(p, root)
            atomic_write_text(p, strip_rebalance_section(text))
            cleaned.append(name)
    result["cleaned"] = cleaned
    result["ok"] = True
    result["action"] = "restored"
    return result


def status(accounts, root=None):
    root = root or default_root()
    lib = load_library(root)
    live = active_entries(lib)
    picked, pub_stats = publishable(live)
    rows = []
    for acc in accounts or []:
        uid = str(acc.get("uid") or "").strip()
        path = memory_file(root, uid, acc.get("enterprise_id"))
        current = read_text(path) if path else ""
        own = strip_shared_block(current)
        shared_lines = 0
        if has_shared_block(current):
            block = current[current.find(BEGIN_MARK):current.find(END_MARK)]
            shared_lines = len([l for l in block.splitlines() if l.strip().startswith("- ")])
        rows.append({
            "alias": acc.get("alias") or uid,
            "uid": uid,
            "file": path,
            "exists": bool(path and os.path.isfile(path)),
            "snapshot": os.path.isfile(snapshot_path(root, uid)),
            "own_chars": len(own.strip()),
            "shared_entries": shared_lines,
            "total_chars": len(current.strip()),
            "over_limit": len(current.strip()) > INJECT_LIMIT,
            "headroom": max(0, INJECT_LIMIT - len(own.strip())),
        })
    return {"library": {"entries": len(lib.get("entries") or []),
                        "live": len(live),
                        "publishable": len(picked),
                        "publish_chars": pub_stats["used"],
                        "budget": PUBLISH_BUDGET,
                        "conflicts": sum(1 for e in live if e.get("conflicts")),
                        "tombstones": len(lib.get("tombstones") or []),
                        "updated_at": lib.get("updated_at"),
                        "path": library_path(root)},
            "accounts": rows}


# ----------------------------------------------------------------------------
# 独立命令行（供人工核对与排障）
# ----------------------------------------------------------------------------
def _print_status(data):
    lib = data["library"]
    print("共享记忆库: {} 条  ({})".format(lib["entries"], lib["path"]))
    for row in data["accounts"]:
        if not row["exists"]:
            print("  {:<12} 无 MEMORY.md".format(row["alias"]))
            continue
        print("  {:<12} 自有 {:>5} 字 | 共享 {:>2} 条 | 合计 {:>5} 字{}".format(
            row["alias"], row["own_chars"], row["shared_entries"], row["total_chars"],
            "  超 4000 字上限" if row["over_limit"] else ""))


def main(argv=None, root=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    root = root or default_root()
    if not argv or argv[0] in ("status", "-h", "--help"):
        _print_status(status([], root=root))
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
