# -*- coding: utf-8 -*-
"""1688 搜品 → 评分 → 上架 全流程脚本"""
import io, json, os, sys
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJ_DIR = os.path.dirname(_THIS_DIR)
sys.path.insert(0, _PROJ_DIR)
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

# Import from sibling modules in ecommerce/scripts/
import importlib.util
def _load(mod_name, file_name):
    spec = importlib.util.spec_from_file_location(mod_name, os.path.join(_THIS_DIR, file_name))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

_scorer = _load("scorer", "product_scorer_1688.py")
_api = _load("api", "shopline_api.py")
score_batch_1688 = _scorer.score_batch_1688
products_create = _api.products_create

# 1688 搜品结果 (实际搜品时此处替换为 MCP 返回的数据)
products = [
    {
        "name": "USB充电LED露营灯 户外帐篷灯 便携马灯 防水野营灯",
        "cost_rmb": 8.5, "sell_price_usd": 19.99, "weight_kg": 0.2,
        "search_volume": 85000, "active_listings": 3200, "trend": "up",
        "tiktok_views": 1200, "supplier_years": 5, "is_battery": True,
        "shipping_method": "epacket",
    },
    {
        "name": "太阳能露营灯 户外应急灯 多功能手提照明灯",
        "cost_rmb": 12.0, "sell_price_usd": 24.99, "weight_kg": 0.35,
        "search_volume": 65000, "active_listings": 2100, "trend": "up",
        "tiktok_views": 800, "supplier_years": 3,
        "shipping_method": "epacket",
    },
    {
        "name": "迷你钥匙扣LED灯 便携应急灯 户外EDC装备",
        "cost_rmb": 3.5, "sell_price_usd": 9.99, "weight_kg": 0.05,
        "search_volume": 45000, "active_listings": 1800, "trend": "flat",
        "tiktok_views": 500, "supplier_years": 4,
        "shipping_method": "epacket",
    },
    {
        "name": "复古煤油灯造型LED氛围灯 户外露营装饰灯 可调光",
        "cost_rmb": 18.0, "sell_price_usd": 34.99, "weight_kg": 0.5,
        "search_volume": 35000, "active_listings": 900, "trend": "up",
        "tiktok_views": 2500, "supplier_years": 6,
        "shipping_method": "epacket",
    },
    {
        "name": "头戴式LED感应头灯 户外夜跑钓鱼灯 挥手感应开关",
        "cost_rmb": 6.8, "sell_price_usd": 14.99, "weight_kg": 0.12,
        "search_volume": 95000, "active_listings": 4500, "trend": "flat",
        "tiktok_views": 300, "supplier_years": 2, "is_battery": True,
        "shipping_method": "epacket",
    },
]

# Step 1: 评分排序
print("=" * 60)
print("STEP 1: 选品评分")
print("=" * 60)
results = score_batch_1688(products)

for i, r in enumerate(results, 1):
    c = r["costs"]
    print(f"{i}. [{r['verdict']}] {r['product'][:50]}")
    print(f"   Score: {r['total_score']} | RMB {c['cost_rmb']} -> USD {c['sell_price_usd']} | Profit: USD {c['estimated_profit_usd']} ({c['margin_pct']}%)")
    print()

# Step 2: 把评分最高的 2 个上架到 Shopline
print("=" * 60)
print("STEP 2: 上架到 Shopline")
print("=" * 60)

top2 = [r for r in results if r["verdict"] in ("爆品候选", "可测款")][:2]

if not top2:
    print("No products met the threshold, using top 2 by score")
    top2 = results[:2]

for r in top2:
    c = r["costs"]
    product_data = {
        "title": r["product"],
        "body_html": f"<p>High quality outdoor gear sourced from 1688. Fast shipping. 30-day money back guarantee.</p><p><strong>Features:</strong> Portable, Durable, Easy to Use</p>",
        "vendor": "1688 Supplier",
        "product_type": "Camping & Hiking",
        "tags": ["camping", "outdoor", "lantern", "portable"],
        "status": "active",
        "variants": [{
            "price": str(c["sell_price_usd"]),
            "sku": f"CAMP-{r['product'][:3].upper()}-001",
            "inventory_tracker": True,
            "weight": str(int(c.get("weight_kg", 0.3) * 1000)),
            "weight_unit": "g",
        }],
    }

    print(f"Creating: {r['product'][:60]}...")
    resp = products_create(product_data)
    if resp["success"]:
        pid = resp["data"].get("product", {}).get("id", "N/A")
        print(f"  -> SUCCESS! Product ID: {pid}")
    else:
        print(f"  -> FAILED: {resp.get('error', 'Unknown')}")
    print()

# Step 3: 验证
print("=" * 60)
print("STEP 3: 验证结果")
print("=" * 60)
products_count = _api.products_count
cnt = products_count()
print(f"Total products in store: {cnt['data']['count']}")
