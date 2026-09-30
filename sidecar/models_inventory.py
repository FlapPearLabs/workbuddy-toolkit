#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
WorkBuddy 模型全景资产库、倍率解析、使用统计与智能排序选择器
"""

import os
import sys
import re
import json
import math
import sqlite3
from typing import List, Dict, Any, Optional

DEFAULT_WORKBUDDY_DIR = os.path.expanduser("~/.workbuddy")
DEFAULT_DYNAMIC_CONFIG = os.path.join(DEFAULT_WORKBUDDY_DIR, "cache", "acc-product-config-v3.json")
DEFAULT_SPILL_DIR = os.path.join(DEFAULT_WORKBUDDY_DIR, "cache", "conversation-product-spill")
DEFAULT_PRODUCT_JSON = "/Applications/WorkBuddy.app/Contents/Resources/app.asar.unpacked/cli/product.json"
DEFAULT_MODELS_JSON = os.path.join(DEFAULT_WORKBUDDY_DIR, "models.json")
DEFAULT_DB_PATH = os.path.join(DEFAULT_WORKBUDDY_DIR, "workbuddy.db")
DEFAULT_ROUTER_CONFIG = os.path.join(DEFAULT_WORKBUDDY_DIR, "failover_router.json")

# ANSI 颜色定义
COLOR_RESET = "\033[0m"
COLOR_BOLD = "\033[1m"
COLOR_DIM = "\033[2m"
COLOR_GREEN = "\033[32m"
COLOR_YELLOW = "\033[33m"
COLOR_BLUE = "\033[34m"
COLOR_CYAN = "\033[36m"
COLOR_RED = "\033[31m"
COLOR_GRAY = "\033[90m"

def find_latest_dynamic_product_config(
    spill_dir: str = DEFAULT_SPILL_DIR,
    primary_cache: str = DEFAULT_DYNAMIC_CONFIG,
    fallback_static: str = DEFAULT_PRODUCT_JSON
) -> str:
    """
    动态寻找最新生效的官方模型配置真源：
    优先按修改时间寻找 ~/.workbuddy/cache/conversation-product-spill/ 或 acc-product-config-v3.json，
    确保每次启动都能抓取到最新版本（如已上线的 deepseek-v4.1-flash，替换旧版 v4-flash），
    仅在离线无缓存时降级至安装包静态 product.json。
    """
    candidates = []
    if os.path.isfile(primary_cache):
        candidates.append((os.path.getmtime(primary_cache), primary_cache))

    if os.path.isdir(spill_dir):
        import glob
        pattern = os.path.join(spill_dir, "acc-product-config-v3-*.json")
        for f in glob.glob(pattern):
            if os.path.isfile(f):
                candidates.append((os.path.getmtime(f), f))

    if candidates:
        # 按修改时间从新到旧排序
        candidates.sort(key=lambda x: x[0], reverse=True)
        return candidates[0][1]

    return fallback_static

def get_active_cli_models_whitelist(workbuddy_dir: str = DEFAULT_WORKBUDDY_DIR) -> Optional[set]:
    """
    从最新的 workbuddyMainThread 日志中提取实时的 cli.models 白名单，
    排除已经下线/废弃的旧模型（如旧版 deepseek-v4-flash）。
    """
    import glob
    log_pattern = os.path.join(workbuddy_dir, "logs", "*", "*MainThread*.log")
    logs = glob.glob(log_pattern)
    if not logs:
        return None
    try:
        latest_log = max(logs, key=os.path.getmtime)
        with open(latest_log, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()
        matches = re.findall(r"cli\.models=(\[[^\]]+\])", content)
        if matches:
            latest_list = json.loads(matches[-1])
            if isinstance(latest_list, list):
                return set(latest_list)
    except Exception:
        pass
    return None

def parse_credits_multiplier(credits_val: Optional[str]) -> float:
    """
    解析官方 product.json 中的 credits 字段倍率。
    如 'x0.00 credits' -> 0.0, 'x0.06 credits' -> 0.06, 'x0.11' -> 0.11, 'x2.00 credits' -> 2.0
    '1x' -> 1.0, 空或 None -> 1.0
    """
    if not credits_val or not isinstance(credits_val, str):
        return 1.0
    s = credits_val.strip().lower()
    if not s:
        return 1.0
    
    m = re.search(r"x?([0-9]+(?:\.[0-9]+)?)\s*(?:credits|x)?", s)
    if m:
        try:
            return float(m.group(1))
        except ValueError:
            pass
    return 1.0

def get_cost_badge(multiplier: float, source: str) -> str:
    """根据倍率生成直观的成本提示标签"""
    if source == "custom":
        return "三方渠道"
    if multiplier == 0.0:
        return "FREE (免积分)"
    elif multiplier <= 0.08:
        return f"{multiplier:.2f}x (极便宜)"
    elif multiplier <= 0.3:
        return f"{multiplier:.2f}x (低倍率)"
    elif multiplier <= 1.0:
        return f"{multiplier:.2f}x (标准)"
    else:
        return f"{multiplier:.2f}x (高昂)"

def get_usage_stats(db_path: str = DEFAULT_DB_PATH) -> Dict[str, Dict[str, Any]]:
    """
    查询本地 workbuddy.db SQLite 中的 sessions 表，获取模型历史调用频次与最后调用时间。
    返回 { normalized_model_id: { "count": int, "last_used": int } }
    """
    stats = {}
    if not os.path.exists(db_path):
        return stats
    
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        cur = conn.cursor()
        query = """
            SELECT model, COUNT(*) as cnt, MAX(updated_at) as last_ts
            FROM sessions
            WHERE model IS NOT NULL AND model != ''
            GROUP BY model
        """
        for row in cur.execute(query):
            raw_model = str(row[0])
            cnt = int(row[1])
            last_ts = int(row[2]) if row[2] else 0

            norm_id = raw_model
            if norm_id.startswith("custom-local:"):
                norm_id = norm_id[len("custom-local:"):]
            
            stats[raw_model] = {"count": cnt, "last_used": last_ts}
            if norm_id != raw_model:
                stats[norm_id] = {"count": cnt, "last_used": last_ts}
        conn.close()
    except Exception:
        pass
    return stats

def get_unified_inventory(
    product_json_path: Optional[str] = None,
    models_json_path: str = DEFAULT_MODELS_JSON,
    db_path: str = DEFAULT_DB_PATH,
    filter_active_only: bool = True
) -> List[Dict[str, Any]]:
    """
    聚合官方内置模型与第三方自定义模型。
    每次运行自动动态选择最新配置缓存，并比对最新日志中的 cli.models 白名单。
    """
    if product_json_path is None:
        product_json_path = find_latest_dynamic_product_config()

    usage_map = get_usage_stats(db_path)
    active_whitelist = get_active_cli_models_whitelist() if filter_active_only else None

    models = []
    seen_ids = set()

    # 1. 解析官方动态/静态模型配置
    if os.path.exists(product_json_path):
        try:
            with open(product_json_path, "r", encoding="utf-8") as f:
                pdata = json.load(f)
                raw_models = pdata.get("models", [])
                for rm in raw_models:
                    mid = rm.get("id")
                    if not mid or mid in seen_ids or mid.startswith("custom-local:"):
                        continue
                    
                    # 若启用了实时白名单过滤，且该模型明确已被官方下线移出，则跳过
                    if active_whitelist is not None and len(active_whitelist) > 0:
                        # 兼容非直接前台展示的通用补全模型，但过滤过期的主对话模型（如 deepseek-v4-flash）
                        if mid not in active_whitelist and mid in ("deepseek-v4-flash", "kimi-k2.5", "glm-5.0"):
                            continue

                    seen_ids.add(mid)
                    mult = parse_credits_multiplier(rm.get("credits"))
                    u_stat = usage_map.get(mid, {"count": 0, "last_used": 0})
                    models.append({
                        "id": mid,
                        "name": rm.get("name") or mid,
                        "source": "official",
                        "vendor": rm.get("vendor", "Tencent"),
                        "multiplier": mult,
                        "credits_raw": rm.get("credits", ""),
                        "cost_badge": get_cost_badge(mult, "official"),
                        "supportsToolCall": bool(rm.get("supportsToolCall", False)),
                        "supportsImages": bool(rm.get("supportsImages", False)),
                        "supportsReasoning": bool(rm.get("supportsReasoning", False)),
                        "usage_count": u_stat["count"],
                        "last_used": u_stat["last_used"],
                        "description": rm.get("descriptionZh") or rm.get("descriptionEn") or ""
                    })
        except Exception:
            pass

    # 2. 解析第三方自定义模型 (models.json)
    if os.path.exists(models_json_path):
        try:
            with open(models_json_path, "r", encoding="utf-8") as f:
                cdata = json.load(f)
                if isinstance(cdata, list):
                    for cm in cdata:
                        mid = cm.get("id")
                        if not mid or mid in seen_ids:
                            continue
                        seen_ids.add(mid)
                        u_stat = usage_map.get(mid, usage_map.get(f"custom-local:{mid}", {"count": 0, "last_used": 0}))
                        models.append({
                            "id": mid,
                            "name": cm.get("name") or mid,
                            "source": "custom",
                            "vendor": cm.get("vendor", "Custom"),
                            "url": cm.get("url", ""),
                            "apiKey": cm.get("apiKey", ""),
                            "multiplier": 1.0,
                            "credits_raw": "Custom Provider",
                            "cost_badge": get_cost_badge(1.0, "custom"),
                            "supportsToolCall": bool(cm.get("supportsToolCall", True)),
                            "supportsImages": bool(cm.get("supportsImages", False)),
                            "supportsReasoning": bool(cm.get("supportsReasoning", False)),
                            "usage_count": u_stat["count"],
                            "last_used": u_stat["last_used"],
                            "description": cm.get("url", "")
                        })
        except Exception:
            pass

    return models

def compute_smart_ranking(inventory: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    智能推荐排序算法：
    得分 = 工具调用权重 + 使用频次权重 (log衰减) + 成本性价比权重 + 最近使用奖励
    """
    def score_model(m: Dict[str, Any]) -> float:
        # Agent 任务工具调用是硬门槛
        tool_score = 1000.0 if m.get("supportsToolCall") else -500.0
        
        # 使用频次得分
        cnt = m.get("usage_count", 0)
        usage_score = math.log1p(cnt) * 50.0

        # 成本得分 (倍率越低分越高，免积分为满分)
        if m["source"] == "custom":
            # 自定义模型视渠道不同给予基准分
            cost_score = 40.0
        else:
            mult = m.get("multiplier", 1.0)
            if mult == 0.0:
                cost_score = 100.0  # FREE
            else:
                cost_score = 100.0 / (1.0 + mult * 2.0)

        # 最近活跃加分
        last_used = m.get("last_used", 0)
        recency_score = 10.0 if last_used > 0 else 0.0

        return tool_score + usage_score + cost_score + recency_score

    # 复制并按得分从高到低排序
    ranked = sorted(inventory, key=score_model, reverse=True)
    return ranked

def load_failover_config(config_path: str = DEFAULT_ROUTER_CONFIG) -> Dict[str, Any]:
    """读取 failover_router.json 配置"""
    if os.path.exists(config_path):
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {
        "enabled": True,
        "port": 8047,
        "cooldown_seconds": 600,
        "fast_model_timeout_seconds": 15,
        "thinking_model_timeout_seconds": 45,
        "chain": []
    }

DEFAULT_UPSTREAMS = {
    "space-bunny-free": {
        "id": "space-bunny-free",
        "name": "Space Bunny (太空兔 1M)",
        "source": "custom",
        "vendor": "OpenCode Zen",
        "url": "https://opencode.ai/zen/v1/chat/completions",
        "apiKey": "sk-fWTpWfNqsiknArM9R14Muk72U1DqAMavnZLv0fcysZoLt34EMKRXUqmt4g9TVhbL",
        "supportsToolCall": True,
        "supportsReasoning": True,
        "supportsImages": True
    },
    "longcat-2.5-preview-free": {
        "id": "longcat-2.5-preview-free",
        "name": "LongCat 2.5 Preview",
        "source": "custom",
        "vendor": "OpenCode Zen",
        "url": "https://opencode.ai/zen/v1/chat/completions",
        "apiKey": "sk-fWTpWfNqsiknArM9R14Muk72U1DqAMavnZLv0fcysZoLt34EMKRXUqmt4g9TVhbL",
        "supportsToolCall": True,
        "supportsReasoning": True,
        "supportsImages": False
    },
    "deepseek-v4.1-flash": {
        "id": "deepseek-v4.1-flash",
        "name": "DeepSeek-V4.1-Flash",
        "source": "official",
        "vendor": "DeepSeek",
        "url": "https://copilot.tencent.com/v2/chat/completions",
        "apiKey": "",
        "supportsToolCall": True,
        "supportsReasoning": True,
        "supportsImages": True
    },
    "hy3": {
        "id": "hy3",
        "name": "Hy3",
        "source": "official",
        "vendor": "Tencent",
        "url": "https://copilot.tencent.com/v2/chat/completions",
        "apiKey": "",
        "supportsToolCall": True,
        "supportsReasoning": True,
        "supportsImages": True
    },
    "glm-5.3-flash": {
        "id": "glm-5.3-flash",
        "name": "GLM-5.3-Flash",
        "source": "official",
        "vendor": "Zhipu",
        "url": "https://copilot.tencent.com/v2/chat/completions",
        "apiKey": "",
        "supportsToolCall": True,
        "supportsReasoning": True,
        "supportsImages": True
    },
    "hy4-preview": {
        "id": "hy4-preview",
        "name": "Hy4 preview",
        "source": "official",
        "vendor": "Tencent",
        "url": "https://copilot.tencent.com/v2/chat/completions",
        "apiKey": "",
        "supportsToolCall": True,
        "supportsReasoning": True,
        "supportsImages": True
    },
    "gemini-3.8-flash-high": {
        "id": "gemini-3.8-flash-high",
        "name": "Gemini 3.8 Flash",
        "source": "custom",
        "vendor": "Google",
        "url": "http://127.0.0.1:8045/v1",
        "apiKey": "sk-8246df449d384693a498cb627b26432c",
        "supportsToolCall": True,
        "supportsReasoning": True,
        "supportsImages": True
    },
    "gemini-3.1-pro-high": {
        "id": "gemini-3.1-pro-high",
        "name": "Gemini 3.1 Pro",
        "source": "custom",
        "vendor": "Google",
        "url": "http://127.0.0.1:8045/v1",
        "apiKey": "sk-8246df449d384693a498cb627b26432c",
        "supportsToolCall": True,
        "supportsReasoning": True,
        "supportsImages": True
    },
    "claude-opus-4-6-thinking": {
        "id": "claude-opus-4-6-thinking",
        "name": "Cloud OPS",
        "source": "custom",
        "vendor": "Anthropic",
        "url": "http://127.0.0.1:8045/v1",
        "apiKey": "sk-8246df449d384693a498cb627b26432c",
        "supportsToolCall": True,
        "supportsReasoning": True,
        "supportsImages": True
    },
    "claude-sonnet-4-6": {
        "id": "claude-sonnet-4-6",
        "name": "Cloud Sonnet 4.6",
        "source": "custom",
        "vendor": "Anthropic",
        "url": "http://127.0.0.1:8045/v1",
        "apiKey": "sk-8246df449d384693a498cb627b26432c",
        "supportsToolCall": True,
        "supportsReasoning": False,
        "supportsImages": True
    }
}

def save_failover_config(
    config_path: str,
    selected_ids: List[str],
    inventory: List[Dict[str, Any]],
    port: int = 8047,
    cooldown_seconds: int = 600
):
    """保存用户选定的梯队至 failover_router.json，并维护全局真实上游路由字典"""
    inv_map = {m["id"]: m for m in inventory}

    # 继承或初始化 upstreams
    upstreams = dict(DEFAULT_UPSTREAMS)
    if os.path.exists(config_path):
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                old_cfg = json.load(f)
                old_ups = old_cfg.get("upstreams", {})
                for k, v in old_ups.items():
                    if k not in upstreams or (v.get("url") and f":{port}" not in v.get("url", "")):
                        upstreams[k] = v
        except Exception:
            pass

    for m in inventory:
        mid = m["id"]
        m_url = m.get("url", "")
        if m_url and f":{port}" not in m_url:
            upstreams[mid] = {
                "id": mid,
                "name": m.get("name", mid),
                "source": m.get("source", "custom"),
                "vendor": m.get("vendor", ""),
                "url": m_url,
                "apiKey": m.get("apiKey", ""),
                "supportsToolCall": m.get("supportsToolCall", True),
                "supportsReasoning": m.get("supportsReasoning", False),
                "supportsImages": m.get("supportsImages", False)
            }

    chain = []
    for mid in selected_ids:
        upstream_info = upstreams.get(mid, {})
        if mid in inv_map:
            m = inv_map[mid]
            chain.append({
                "id": mid,
                "name": m.get("name", mid),
                "source": m.get("source", "official"),
                "supportsToolCall": m.get("supportsToolCall", True),
                "supportsReasoning": m.get("supportsReasoning", False),
                "multiplier": m.get("multiplier", 1.0),
                "url": upstream_info.get("url") or (m.get("url", "") if f":{port}" not in m.get("url", "") else ""),
                "apiKey": upstream_info.get("apiKey") or m.get("apiKey", "")
            })
        else:
            chain.append({
                "id": mid,
                "name": upstream_info.get("name", mid),
                "source": upstream_info.get("source", "custom"),
                "supportsToolCall": upstream_info.get("supportsToolCall", True),
                "supportsReasoning": upstream_info.get("supportsReasoning", False),
                "multiplier": 1.0,
                "url": upstream_info.get("url", ""),
                "apiKey": upstream_info.get("apiKey", "")
            })

    cfg = {
        "enabled": True,
        "port": port,
        "cooldown_seconds": cooldown_seconds,
        "fast_model_timeout_seconds": 15,
        "thinking_model_timeout_seconds": 45,
        "chain": chain,
        "upstreams": upstreams
    }

    os.makedirs(os.path.dirname(os.path.abspath(config_path)), exist_ok=True)
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)

def register_virtual_model_in_models_json(
    models_json_path: str = DEFAULT_MODELS_JSON,
    port: int = 8047
):
    """
    在 ~/.workbuddy/models.json 中配置模型接入点：
    1. 确保 deepseek-v4.1-flash 注册且走 8047 本地路由（带无感容灾保护）
    2. 将 space-bunny-free 的 url 重定向至 8047 本地路由（真实上游已留存至 failover_router.json）
    3. 注册通用备用池 workbuddy-autopilot
    4. 保留用户原有的其他自定义模型 (Gemini, Claude, LongCat 等)
    """
    if not os.path.exists(models_json_path):
        current_list = []
    else:
        try:
            with open(models_json_path, "r", encoding="utf-8") as f:
                current_list = json.load(f)
                if not isinstance(current_list, list):
                    current_list = []
        except Exception:
            current_list = []

    # 1. workbuddy-autopilot
    autopilot_entry = {
        "id": "workbuddy-autopilot",
        "name": "Auto Pilot (自动容灾轮换池)",
        "vendor": "FailoverRouter",
        "url": f"http://127.0.0.1:{port}/v1",
        "apiKey": "sk-workbuddy-router-local",
        "supportsToolCall": True,
        "supportsImages": True,
        "supportsReasoning": True,
        "useCustomProtocol": False,
        "reasoning": {
            "supportedEfforts": ["high", "medium", "low"],
            "canDisableThinking": True
        }
    }

    # 2. deepseek-v4.1-flash (无感容灾保护版)
    deepseek_entry = {
        "id": "deepseek-v4.1-flash",
        "name": "DeepSeek V4.1 Flash (无感容灾)",
        "vendor": "DeepSeek",
        "url": f"http://127.0.0.1:{port}/v1",
        "apiKey": "sk-workbuddy-router-local",
        "supportsToolCall": True,
        "supportsImages": True,
        "supportsReasoning": True,
        "useCustomProtocol": False,
        "reasoning": {
            "supportedEfforts": ["high", "medium", "low"],
            "canDisableThinking": True
        }
    }

    # 更新 autopilot
    idx_ap = next((i for i, m in enumerate(current_list) if m.get("id") == "workbuddy-autopilot"), -1)
    if idx_ap >= 0:
        current_list[idx_ap] = autopilot_entry
    else:
        current_list.insert(0, autopilot_entry)

    # 更新 deepseek-v4.1-flash
    idx_ds = next((i for i, m in enumerate(current_list) if m.get("id") == "deepseek-v4.1-flash"), -1)
    if idx_ds >= 0:
        current_list[idx_ds] = deepseek_entry
    else:
        current_list.insert(1, deepseek_entry)

    # 更新 space-bunny-free 的 url 指向本地路由
    for m in current_list:
        if m.get("id") == "space-bunny-free":
            m["url"] = f"http://127.0.0.1:{port}/v1"
            m["apiKey"] = "sk-workbuddy-router-local"

    with open(models_json_path, "w", encoding="utf-8") as f:
        json.dump(current_list, f, indent=2, ensure_ascii=False)

def print_model_table(inventory: List[Dict[str, Any]], active_chain: Optional[List[str]] = None):
    """格式化打印模型清单与梯队列表"""
    active_set = set(active_chain or [])
    chain_order = {mid: i + 1 for i, mid in enumerate(active_chain or [])}

    print(f"\n{COLOR_BOLD}{COLOR_CYAN}=== WorkBuddy 模型全景资产与计费透视 ==={COLOR_RESET}\n")
    print(f"{'梯队':<6} {'类型':<6} {'模型 ID':<26} {'显示名称':<22} {'计费倍率':<16} {'调用频次':<10} {'能力'}")
    print("-" * 105)

    for m in inventory:
        mid = m["id"]
        rank_str = f"[{chain_order[mid]}] ★" if mid in active_set else "  -  "
        src_str = "官方" if m["source"] == "official" else "三方"
        name_str = m["name"][:20]
        cost_str = m["cost_badge"]
        calls = f"{m['usage_count']} 次" if m['usage_count'] > 0 else "-"
        
        caps = []
        if m["supportsToolCall"]:
            caps.append("Tool")
        if m["supportsImages"]:
            caps.append("Vision")
        if m["supportsReasoning"]:
            caps.append("Thinking")
        cap_str = "/".join(caps) if caps else "Text"

        # 颜色修饰
        if m["source"] == "official" and m["multiplier"] == 0.0:
            c_tag = COLOR_GREEN
        elif m["source"] == "official" and m["multiplier"] <= 0.08:
            c_tag = COLOR_CYAN
        elif m["source"] == "official" and m["multiplier"] >= 1.5:
            c_tag = COLOR_YELLOW
        else:
            c_tag = COLOR_RESET

        if mid in active_set:
            print(f"{COLOR_BOLD}{COLOR_GREEN}{rank_str:<6}{COLOR_RESET} {src_str:<6} {mid:<26} {name_str:<22} {c_tag}{cost_str:<16}{COLOR_RESET} {calls:<10} {cap_str}")
        else:
            print(f"{COLOR_GRAY}{rank_str:<6} {src_str:<6} {mid:<26} {name_str:<22} {cost_str:<16} {calls:<10} {cap_str}{COLOR_RESET}")

    print("-" * 105)
    if active_chain:
        print(f"{COLOR_BOLD}当前生效容灾梯队: {COLOR_CYAN}{' -> '.join(active_chain)}{COLOR_RESET}\n")

def run_curses_selector(inventory: List[Dict[str, Any]], config_path: str = DEFAULT_ROUTER_CONFIG):
    """
    轻量终端 curses 交互式选择器
    """
    import curses

    cfg = load_failover_config(config_path)
    existing_chain = [c["id"] for c in cfg.get("chain", []) if isinstance(c, dict) and "id" in c]
    
    # 若无配置，默认用智能推荐的前 4 个
    if not existing_chain:
        smart_init = compute_smart_ranking(inventory)
        existing_chain = [m["id"] for m in smart_init if m["supportsToolCall"]][:4]

    selected_ids = list(existing_chain)

    def curses_app(stdscr):
        nonlocal selected_ids
        curses.curs_set(0)
        curses.init_pair(1, curses.COLOR_BLACK, curses.COLOR_CYAN)    # 光标选中
        curses.init_pair(2, curses.COLOR_GREEN, curses.COLOR_BLACK)   # 激活模型
        curses.init_pair(3, curses.COLOR_YELLOW, curses.COLOR_BLACK)  # 提示说明
        curses.init_pair(4, curses.COLOR_CYAN, curses.COLOR_BLACK)    # 标题

        cursor_idx = 0
        scroll_offset = 0

        while True:
            stdscr.clear()
            max_y, max_x = stdscr.getmaxyx()

            # 标题与操作指南
            title = " WorkBuddy 容灾轮换与模型资产控制台 (wb-models) "
            stdscr.addstr(0, max(0, (max_x - len(title)) // 2), title, curses.color_pair(4) | curses.A_BOLD)
            
            help_line1 = "[↑/↓] 移动光标   [空格] 切换入选/移出   [+/- 或 J/K] 调整优先级   [s] 智能推荐重排"
            help_line2 = "[Enter] 保存并生效    [q/Esc] 放弃退出"
            stdscr.addstr(1, 2, help_line1[:max_x - 3], curses.color_pair(3))
            stdscr.addstr(2, 2, help_line2[:max_x - 3], curses.color_pair(3))
            stdscr.hline(3, 1, "-", max_x - 2)

            header = f"{'序号':<6} {'状态':<6} {'类型':<6} {'模型 ID':<24} {'显示名称':<18} {'倍率/成本':<16} {'调用频次'}"
            stdscr.addstr(4, 2, header[:max_x - 3], curses.A_BOLD)

            # 可视行数
            visible_rows = max_y - 7
            if visible_rows <= 0:
                continue

            if cursor_idx < scroll_offset:
                scroll_offset = cursor_idx
            elif cursor_idx >= scroll_offset + visible_rows:
                scroll_offset = cursor_idx - visible_rows + 1

            for i in range(visible_rows):
                item_idx = scroll_offset + i
                if item_idx >= len(inventory):
                    break

                m = inventory[item_idx]
                mid = m["id"]
                y = 5 + i

                is_in_pool = mid in selected_ids
                if is_in_pool:
                    rank_num = selected_ids.index(mid) + 1
                    status_str = f"Rank {rank_num}"
                    check_mark = "[★]"
                else:
                    status_str = "未启用"
                    check_mark = "[ ]"

                src_str = "官方" if m["source"] == "official" else "三方"
                calls_str = f"{m['usage_count']} 次" if m['usage_count'] > 0 else "-"
                cost_str = m["cost_badge"]

                row_text = f"{check_mark} {status_str:<6} {src_str:<6} {mid:<24} {m['name'][:16]:<18} {cost_str:<16} {calls_str}"
                row_text = row_text[:max_x - 3]

                is_cursor = (item_idx == cursor_idx)
                if is_cursor:
                    stdscr.addstr(y, 2, row_text, curses.color_pair(1) | curses.A_BOLD)
                elif is_in_pool:
                    stdscr.addstr(y, 2, row_text, curses.color_pair(2) | curses.A_BOLD)
                else:
                    stdscr.addstr(y, 2, row_text, curses.A_NORMAL)

            # 底部当前轮换链展示
            stdscr.hline(max_y - 2, 1, "-", max_x - 2)
            chain_str = "当前已选梯队: " + (" -> ".join(selected_ids) if selected_ids else "尚未选取任何模型！")
            stdscr.addstr(max_y - 1, 2, chain_str[:max_x - 3], curses.color_pair(2) | curses.A_BOLD)

            stdscr.refresh()

            # 按键处理
            ch = stdscr.getch()

            if ch in (ord('q'), ord('Q'), 27):  # q or Esc
                return False
            elif ch == curses.KEY_UP:
                if cursor_idx > 0:
                    cursor_idx -= 1
            elif ch == curses.KEY_DOWN:
                if cursor_idx < len(inventory) - 1:
                    cursor_idx += 1
            elif ch == ord(' '):  # 空格切换加入/移除
                cur_m = inventory[cursor_idx]["id"]
                if cur_m in selected_ids:
                    selected_ids.remove(cur_m)
                else:
                    selected_ids.append(cur_m)
            elif ch in (ord('+'), ord('='), ord('k'), ord('K')):  # 上调优先级
                cur_m = inventory[cursor_idx]["id"]
                if cur_m in selected_ids:
                    pos = selected_ids.index(cur_m)
                    if pos > 0:
                        selected_ids[pos], selected_ids[pos - 1] = selected_ids[pos - 1], selected_ids[pos]
            elif ch in (ord('-'), ord('_'), ord('j'), ord('J')):  # 下调优先级
                cur_m = inventory[cursor_idx]["id"]
                if cur_m in selected_ids:
                    pos = selected_ids.index(cur_m)
                    if pos < len(selected_ids) - 1:
                        selected_ids[pos], selected_ids[pos + 1] = selected_ids[pos + 1], selected_ids[pos]
            elif ch in (ord('s'), ord('S')):  # 智能排序推荐
                ranked = compute_smart_ranking(inventory)
                selected_ids = [m["id"] for m in ranked if m["supportsToolCall"]][:5]
            elif ch in (curses.KEY_ENTER, 10, 13):  # 回车确认
                if not selected_ids:
                    continue
                save_failover_config(config_path, selected_ids, inventory)
                register_virtual_model_in_models_json()
                return True

    try:
        saved = curses.wrapper(curses_app)
        if saved:
            print(f"\n{COLOR_GREEN}{COLOR_BOLD}✔ 容灾轮换梯队已成功保存至 {config_path}，已注册虚拟模型 'workbuddy-autopilot'！{COLOR_RESET}")
            cfg = load_failover_config(config_path)
            active_chain = [c["id"] for c in cfg.get("chain", [])]
            print(f"{COLOR_CYAN}生效梯队: {' -> '.join(active_chain)}{COLOR_RESET}\n")
    except Exception as e:
        print(f"终端图形界面无法初始化，降级至标准命令行模式: {e}")
        # 降级打印表格
        print_model_table(inventory, selected_ids)
        save_failover_config(config_path, selected_ids, inventory)
        register_virtual_model_in_models_json()

def main():
    import argparse
    parser = argparse.ArgumentParser(description="WorkBuddy 模型全景资产与容灾编排控制台")
    parser.add_argument("--list", action="store_true", help="以格式化文本表格打印所有模型资产与倍率")
    parser.add_argument("--json", action="store_true", help="以 JSON 格式输出模型全景资产")
    parser.add_argument("--smart-apply", action="store_true", help="自动计算最优性价比智能梯队并直接应用落盘")
    parser.add_argument("--set-chain", nargs="+", help="直接通过命令行指定梯队模型 ID 列表")

    args = parser.parse_args()

    inventory = get_unified_inventory()

    if args.json:
        print(json.dumps(inventory, indent=2, ensure_ascii=False))
        return

    cfg = load_failover_config()
    current_chain = [c["id"] for c in cfg.get("chain", []) if isinstance(c, dict) and "id" in c]

    if args.set_chain:
        raw_ids = []
        for item in args.set_chain:
            for part in item.split(","):
                part = part.strip()
                if part:
                    raw_ids.append(part)
        save_failover_config(DEFAULT_ROUTER_CONFIG, raw_ids, inventory)
        register_virtual_model_in_models_json()
        print(f"{COLOR_GREEN}✔ 已设置新梯队: {' -> '.join(raw_ids)}{COLOR_RESET}")
        return

    if args.smart_apply:
        ranked = compute_smart_ranking(inventory)
        chain = [m["id"] for m in ranked if m["supportsToolCall"]][:5]
        save_failover_config(DEFAULT_ROUTER_CONFIG, chain, inventory)
        register_virtual_model_in_models_json()
        print(f"{COLOR_GREEN}✔ 已应用智能推荐梯队: {' -> '.join(chain)}{COLOR_RESET}")
        return

    if args.list:
        print_model_table(inventory, current_chain)
        return

    # 默认进入交互式终端选择器
    run_curses_selector(inventory)

if __name__ == "__main__":
    main()
