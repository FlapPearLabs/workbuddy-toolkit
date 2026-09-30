import os
import sys
import json
import sqlite3
import tempfile
import unittest

# Ensure sidecar is in path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "sidecar")))
import models_inventory

class TestModelInventory(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.product_json_path = os.path.join(self.temp_dir.name, "product.json")
        self.models_json_path = os.path.join(self.temp_dir.name, "models.json")
        self.db_path = os.path.join(self.temp_dir.name, "workbuddy.db")
        self.config_path = os.path.join(self.temp_dir.name, "failover_router.json")

        # Mock product.json
        product_data = {
            "models": [
                {
                    "id": "hy3",
                    "name": "Hy3",
                    "credits": "x0.00 credits",
                    "supportsToolCall": True,
                    "supportsImages": True
                },
                {
                    "id": "deepseek-v4-flash",
                    "name": "DeepSeek-V4-Flash",
                    "credits": "x0.06 credits",
                    "supportsToolCall": True,
                    "supportsImages": True
                },
                {
                    "id": "deepseek-v4-pro",
                    "name": "DeepSeek-V4-Pro",
                    "credits": "x0.16 credits",
                    "supportsToolCall": True,
                    "supportsImages": True
                },
                {
                    "id": "default",
                    "name": "Claude-3.7-Sonnet",
                    "credits": "x2.00 credits",
                    "supportsToolCall": True,
                    "supportsImages": True
                },
                {
                    "id": "hunyuan-3b",
                    "name": "hunyuan-3b",
                    "credits": "1x",
                    "supportsToolCall": False
                }
            ]
        }
        with open(self.product_json_path, "w", encoding="utf-8") as f:
            json.dump(product_data, f)

        # Mock models.json
        custom_data = [
            {
                "id": "gemini-3.8-flash-high",
                "name": "Gemini 3.8 Flash",
                "vendor": "Custom",
                "url": "http://127.0.0.1:8045/v1",
                "apiKey": "sk-test",
                "supportsToolCall": True,
                "supportsImages": True,
                "supportsReasoning": True
            },
            {
                "id": "space-bunny-free",
                "name": "Space Bunny",
                "vendor": "OpenCode Zen",
                "url": "https://opencode.ai/zen/v1",
                "apiKey": "sk-zen",
                "supportsToolCall": True,
                "supportsImages": True
            }
        ]
        with open(self.models_json_path, "w", encoding="utf-8") as f:
            json.dump(custom_data, f)

        # Mock SQLite workbuddy.db
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE sessions (
                id TEXT PRIMARY KEY,
                model TEXT,
                updated_at INTEGER
            )
        """)
        # Insert historical sessions
        sessions = [
            ("s1", "hy3", 1700000000000),
            ("s2", "hy3", 1700000001000),
            ("s3", "hy3", 1700000002000),
            ("s4", "deepseek-v4-flash", 1700000003000),
            ("s5", "deepseek-v4-flash", 1700000004000),
            ("s6", "space-bunny-free", 1700000005000),
            ("s7", "custom-local:gemini-3.8-flash-high", 1700000006000),
        ]
        cur.executemany("INSERT INTO sessions VALUES (?, ?, ?)", sessions)
        conn.commit()
        conn.close()

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_parse_credits_multiplier(self):
        self.assertEqual(models_inventory.parse_credits_multiplier("x0.00 credits"), 0.0)
        self.assertEqual(models_inventory.parse_credits_multiplier("x0.06 credits"), 0.06)
        self.assertEqual(models_inventory.parse_credits_multiplier("x2.00 credits"), 2.0)
        self.assertEqual(models_inventory.parse_credits_multiplier("1x"), 1.0)
        self.assertEqual(models_inventory.parse_credits_multiplier(""), 1.0)
        self.assertEqual(models_inventory.parse_credits_multiplier(None), 1.0)

    def test_discover_models_and_usage(self):
        inventory = models_inventory.get_unified_inventory(
            product_json_path=self.product_json_path,
            models_json_path=self.models_json_path,
            db_path=self.db_path,
            filter_active_only=False
        )
        self.assertGreater(len(inventory), 0)

        # Check hy3
        hy3 = next((m for m in inventory if m["id"] == "hy3"), None)
        self.assertIsNotNone(hy3)
        self.assertEqual(hy3["source"], "official")
        self.assertEqual(hy3["multiplier"], 0.0)
        self.assertEqual(hy3["usage_count"], 3)
        self.assertTrue(hy3["supportsToolCall"])

        # Check deepseek-v4-flash
        ds_flash = next((m for m in inventory if m["id"] == "deepseek-v4-flash"), None)
        self.assertIsNotNone(ds_flash)
        self.assertEqual(ds_flash["multiplier"], 0.06)
        self.assertEqual(ds_flash["usage_count"], 2)

        # Check space-bunny-free
        sb = next((m for m in inventory if m["id"] == "space-bunny-free"), None)
        self.assertIsNotNone(sb)
        self.assertEqual(sb["source"], "custom")
        self.assertEqual(sb["usage_count"], 1)

        # Check gemini-3.8-flash-high (matched with or without custom-local prefix)
        gemini = next((m for m in inventory if m["id"] == "gemini-3.8-flash-high"), None)
        self.assertIsNotNone(gemini)
        self.assertEqual(gemini["source"], "custom")
        self.assertEqual(gemini["usage_count"], 1)

    def test_smart_ranking(self):
        inventory = models_inventory.get_unified_inventory(
            product_json_path=self.product_json_path,
            models_json_path=self.models_json_path,
            db_path=self.db_path,
            filter_active_only=False
        )
        ranked = models_inventory.compute_smart_ranking(inventory)
        
        # hy3 (free + highest usage + tool call) should be #1
        self.assertEqual(ranked[0]["id"], "hy3")
        # deepseek-v4-flash (0.06x + second highest usage + tool call) should be #2
        self.assertEqual(ranked[1]["id"], "deepseek-v4-flash")
        
        # hunyuan-3b does NOT support tool calls, so it should be relegated or filtered from agent chain
        non_tool = next((m for m in ranked if m["id"] == "hunyuan-3b"), None)
        self.assertFalse(non_tool["supportsToolCall"])
        # In priority rank, non-tool model must be after tool models
        tool_ids = [m["id"] for m in ranked if m["supportsToolCall"]]
        self.assertIn("hy3", tool_ids)
        self.assertIn("deepseek-v4-flash", tool_ids)

    def test_save_and_load_router_config(self):
        inventory = models_inventory.get_unified_inventory(
            product_json_path=self.product_json_path,
            models_json_path=self.models_json_path,
            db_path=self.db_path,
            filter_active_only=False
        )
        selected_ids = ["hy3", "deepseek-v4-flash", "space-bunny-free"]
        models_inventory.save_failover_config(
            config_path=self.config_path,
            selected_ids=selected_ids,
            inventory=inventory,
            port=8047,
            cooldown_seconds=600
        )

        loaded = models_inventory.load_failover_config(self.config_path)
        self.assertEqual(loaded["port"], 8047)
        self.assertEqual(loaded["cooldown_seconds"], 600)
        self.assertEqual([c["id"] for c in loaded["chain"]], selected_ids)

    def test_dynamic_cache_priority(self):
        # Create an older static product.json and a newer dynamic spill config
        static_p = os.path.join(self.temp_dir.name, "static_product.json")
        with open(static_p, "w", encoding="utf-8") as f:
            json.dump({"models": [{"id": "deepseek-v4-flash"}]}, f)

        spill_dir = os.path.join(self.temp_dir.name, "spill")
        os.makedirs(spill_dir, exist_ok=True)
        dynamic_file = os.path.join(spill_dir, "acc-product-config-v3-new.json")
        with open(dynamic_file, "w", encoding="utf-8") as f:
            json.dump({"models": [{"id": "deepseek-v4.1-flash", "credits": "x0.11"}]}, f)

        resolved = models_inventory.find_latest_dynamic_product_config(
            spill_dir=spill_dir,
            primary_cache="/nonexistent/cache.json",
            fallback_static=static_p
        )
        self.assertEqual(resolved, dynamic_file)

    def test_register_virtual_model_in_models_json(self):
        models_inventory.register_virtual_model_in_models_json(
            models_json_path=self.models_json_path,
            port=8047
        )
        with open(self.models_json_path, "r", encoding="utf-8") as f:
            updated = json.load(f)

        ids = [m["id"] for m in updated]
        self.assertIn("workbuddy-autopilot", ids)
        self.assertIn("deepseek-v4.1-flash", ids)
        self.assertIn("space-bunny-free", ids)

        # 检查 space-bunny-free 的 URL 是否被重定向至本地容灾路由
        sb = next(m for m in updated if m["id"] == "space-bunny-free")
        self.assertEqual(sb["url"], "http://127.0.0.1:8047/v1")

        # 检查 deepseek-v4.1-flash 的 URL 与思维档位
        ds = next(m for m in updated if m["id"] == "deepseek-v4.1-flash")
        self.assertEqual(ds["url"], "http://127.0.0.1:8047/v1")
        self.assertTrue(ds["reasoning"]["canDisableThinking"])

if __name__ == "__main__":
    unittest.main()
