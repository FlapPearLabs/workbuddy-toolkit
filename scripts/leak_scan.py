#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Zero-Leak 仓库扫描器（CI 与本地共用）。

扫描工作区文件中的硬编码凭据、个人路径与手机号。发现任一命中即以 exit 1 退出。

用法:
    python3 scripts/leak_scan.py [ROOT]

说明:
- 只扫描当前工作区内容，不扫描 git 历史。历史中已经泄露的凭据必须到对应服务吊销/轮换，
  删除代码本身并不能让它失效。
- 测试中需要构造伪造凭据时，请在运行时拼接字符串（例如 "sk-" + "A" * 24），
  不要把完整字面量写进源码。
"""

import os
import re
import sys
from typing import List, Tuple

PATTERNS: List[Tuple[str, str]] = [
    # 个人主机路径
    (r"/Users/(?!runner\b)[a-zA-Z0-9_\-]+", "macOS local user home path"),
    (r"C:\\Users\\(?!runneradmin\b)[a-zA-Z0-9_\-]+", "Windows local user home path"),
    (r"/home/(?!runner\b)[a-zA-Z0-9_\-]+", "Linux local user home path"),
    # 令牌与 API Key
    (r"eyJh[A-Za-z0-9_\-\.]{25,}", "JWT Bearer token"),
    (r"\bsk-[A-Za-z0-9]{20,}", "OpenAI-compatible API key (sk-...)"),
    (r"\bsk-ant-[A-Za-z0-9_\-]{20,}", "Anthropic API key"),
    (r"\bAKIA[0-9A-Z]{16}\b", "AWS access key id"),
    (r"\b(?:ghp|gho|ghs|ghu|ghr)_[A-Za-z0-9]{30,}", "GitHub token"),
    (r"\bgithub_pat_[A-Za-z0-9_]{30,}", "GitHub fine-grained token"),
    (r"\bxox[abprs]-[A-Za-z0-9\-]{10,}", "Slack token"),
    (r"\bAIza[0-9A-Za-z_\-]{35}", "Google API key"),
    (r"-----BEGIN (?:[A-Z]+ )*PRIVATE KEY-----", "Private key block"),
    # 个人信息
    (r"(?<!\d)1[3-9]\d{9}(?!\d)", "Mainland China 11-digit phone number"),
]

SKIP_DIRS = {".git", "__pycache__", ".pytest_cache", ".ruff_cache", "node_modules", ".agents", ".scratch", ".codegraph"}


def _is_allowed(desc: str, match: str) -> bool:
    # 测试中使用的假毫秒时间戳 (如 1800000000000) 会被手机号规则误伤
    if desc.startswith("Mainland") and ("1800000000" in match or "1900000000" in match):
        return True
    return False


def scan_text(text: str) -> List[Tuple[str, List[str]]]:
    """返回 [(规则描述, [前 3 个命中])]，命中内容已掩码，避免扫描日志二次泄露。"""
    hits = []
    for pat, desc in PATTERNS:
        matches = [m for m in re.findall(pat, text) if not _is_allowed(desc, m)]
        if matches:
            hits.append((desc, [mask(m) for m in matches[:3]]))
    return hits


def mask(value: str) -> str:
    if len(value) <= 8:
        return value[:2] + "…"
    return value[:6] + "…(masked)"


def scan_tree(root: str) -> List[Tuple[str, str, List[str]]]:
    leaks = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for fname in filenames:
            path = os.path.join(dirpath, fname)
            try:
                with open(path, "r", encoding="utf-8", errors="ignore") as fp:
                    text = fp.read()
            except OSError:
                continue
            for desc, sample in scan_text(text):
                leaks.append((os.path.relpath(path, root), desc, sample))
    return leaks


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    root = argv[0] if argv else "."
    leaks = scan_tree(root)
    if leaks:
        print("Security scan failed! Leaks found:")
        for path, desc, sample in leaks:
            print(f"  - {path}: {desc} {sample}")
        return 1
    print("Security scan passed: Zero hardcoded user paths or credentials detected.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
