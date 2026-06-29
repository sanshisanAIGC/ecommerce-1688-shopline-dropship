# -*- coding: utf-8 -*-
"""
1688 专供选品评分模型 — 路线 A（纯国内供应链）
适配 1688 跨境专供商品，人民币成本 → 美元定价 → Shopline 上架

模型: S = w1*T + w2*D + w3*C + w4*R + w5*P
  T = 市场热度（目标市场搜索量 + 社交媒体热度）
  D = 需求竞争比
  C = 供应链成本（1688成本 + 跨境物流 + 平台费率）
  R = 合规风险（认证/专利/物流限制）
  P = 利润空间（美元售价 - 所有成本）
"""
import sys
import json
from typing import Optional

# ============================================================
# 跨境物流成本估算（1688 国内 → 海外客户）
# ============================================================

def estimate_shipping(
    weight_kg: float = 0.3,
    target_market: str = "us",
    method: str = "epacket",
) -> dict:
    """估算跨境物流成本"""
    rates = {
        "epacket": {"base": 15, "per_kg": 50},       # 邮政小包
        "yunexpress": {"base": 25, "per_kg": 45},    # 云途
        "4px": {"base": 20, "per_kg": 48},           # 递四方
        "sea": {"base": 8, "per_kg": 15},            # 海运（慢但便宜）
    }
    r = rates.get(method, rates["epacket"])
    cost_rmb = r["base"] + r["per_kg"] * weight_kg
    return {
        "method": method,
        "weight_kg": weight_kg,
        "cost_rmb": round(cost_rmb, 2),
        "cost_usd": round(cost_rmb / 7.2, 2),
        "days": 7 if method != "sea" else 25,
    }


# ============================================================
# 各维度评分函数
# ============================================================

def score_heat(
    keyword_search_volume: int,      # 目标市场月搜索量
    trend_direction: str = "flat",   # up / flat / down
    tiktok_views: int = 0,           # TikTok 相关话题播放量(万)
    growth_rate: float = 0.0,        # Google Trends 同比增长率
) -> float:
    """市场热度评分 (0-100)"""
    base = min(keyword_search_volume / 1000 * 15, 35)
    trend_map = {"up": 25, "flat": 15, "down": 5}
    trend = trend_map.get(trend_direction, 10)
    social = min(tiktok_views / 50 * 10, 25)
    growth = min(growth_rate * 30, 15) if growth_rate > 0 else 0
    return min(base + trend + social + growth, 100)


def score_competition(
    search_volume: int,
    active_listings: int,
    avg_review_count: int = 50,
) -> float:
    """需求竞争比评分 (0-100)"""
    if active_listings == 0:
        return 85
    ratio = search_volume / active_listings
    if ratio >= 2.0:
        ratio_score = 50
    elif ratio >= 1.0:
        ratio_score = 40
    elif ratio >= 0.5:
        ratio_score = 30
    elif ratio >= 0.2:
        ratio_score = 20
    else:
        ratio_score = 10

    # 竞品评价数的门槛：竞品评价少 = 市场不成熟 = 机会
    if avg_review_count < 20:
        barrier_score = 40
    elif avg_review_count < 50:
        barrier_score = 30
    elif avg_review_count < 100:
        barrier_score = 20
    else:
        barrier_score = 10

    return min(ratio_score + barrier_score, 100)


def score_cost(
    cost_rmb: float,          # 1688 拿货价
    shipping: dict,           # 物流成本
    markup: float = 3.0,      # 定价倍数
    shopline_fee: float = 0.02,  # Shopline 交易费
    payment_fee: float = 0.029,  # 支付网关费 (Stripe/PayPal)
) -> float:
    """供应链成本评分 (0-100)"""
    total_cost_rmb = cost_rmb + shipping["cost_rmb"]
    total_cost_usd = total_cost_rmb / 7.2

    # 按 3 倍定价算
    sell_price_usd = total_cost_usd * markup
    fees = sell_price_usd * (shopline_fee + payment_fee)
    margin = (sell_price_usd - total_cost_usd - fees) / sell_price_usd

    if margin >= 0.70:
        return 95
    elif margin >= 0.60:
        return 85
    elif margin >= 0.50:
        return 70
    elif margin >= 0.40:
        return 55
    elif margin >= 0.30:
        return 40
    else:
        return 20


def score_risk(
    is_branded: bool = False,        # 有无品牌（侵权风险）
    has_cert_required: bool = False, # CE/FDA 等强制认证
    is_battery: bool = False,        # 含电池（物流限制）
    is_liquid: bool = False,
    is_fragile: bool = False,
    is_food: bool = False,           # 食品（检疫风险）
    shipping_days: int = 12,
    supplier_years: int = 3,         # 供应商年限
) -> float:
    """合规风险评分 (0-100, 100=零风险)"""
    s = 100
    if is_branded:      s -= 30
    if has_cert_required: s -= 20
    if is_battery:      s -= 15
    if is_liquid:       s -= 10
    if is_fragile:      s -= 10
    if is_food:         s -= 25
    if shipping_days > 20: s -= 15
    elif shipping_days > 12: s -= 5
    if supplier_years < 1: s -= 20
    elif supplier_years < 3: s -= 10
    return max(s, 0)


def score_profit(
    cost_rmb: float,
    sell_price_usd: float,
    shipping: dict,
    shopline_fee: float = 0.02,
    payment_fee: float = 0.029,
    ad_budget_per_unit_usd: float = 2.0,
) -> float:
    """利润空间评分 (0-100)"""
    total_cost_usd = (cost_rmb + shipping["cost_rmb"]) / 7.2
    fees = sell_price_usd * (shopline_fee + payment_fee)
    profit_usd = sell_price_usd - total_cost_usd - fees - ad_budget_per_unit_usd
    margin = profit_usd / sell_price_usd if sell_price_usd > 0 else 0

    profit_score = min(profit_usd / 5 * 25, 40)   # $5 利润 = 25分, $8+ = 40分
    margin_score = min(margin * 60, 60)             # 50% 利润率 = 30分
    return round(min(profit_score + margin_score, 100), 1)


# ============================================================
# 综合评分
# ============================================================

def total_score_1688(
    product_name: str,
    cost_rmb: float,
    sell_price_usd: float,
    weight_kg: float = 0.3,
    search_volume: int = 0,
    active_listings: int = 1,
    trend: str = "flat",
    tiktok_views: int = 0,
    avg_review_count: int = 50,
    is_branded: bool = False,
    has_cert_required: bool = False,
    is_battery: bool = False,
    is_liquid: bool = False,
    is_fragile: bool = False,
    is_food: bool = False,
    shipping_days: int = 12,
    supplier_years: int = 3,
    shipping_method: str = "epacket",
    markup: float = 3.0,
    ad_budget_usd: float = 2.0,
    weights: Optional[dict] = None,
) -> dict:
    """1688 商品综合选品评分"""
    w = weights or {"T": 0.20, "D": 0.25, "C": 0.20, "R": 0.15, "P": 0.20}

    shipping = estimate_shipping(weight_kg, method=shipping_method)

    T = score_heat(search_volume, trend, tiktok_views)
    D = score_competition(search_volume, active_listings, avg_review_count)
    C = score_cost(cost_rmb, shipping, markup)
    R = score_risk(is_branded, has_cert_required, is_battery, is_liquid, is_fragile, is_food, shipping_days, supplier_years)
    P = score_profit(cost_rmb, sell_price_usd, shipping, ad_budget_per_unit_usd=ad_budget_usd)

    S = w["T"] * T + w["D"] * D + w["C"] * C + w["R"] * R + w["P"] * P

    if S >= 85:
        verdict = "爆品候选"
    elif S >= 75:
        verdict = "可测款"
    elif S >= 60:
        verdict = "谨慎"
    else:
        verdict = "不推荐"

    return {
        "product": product_name,
        "total_score": round(S, 1),
        "verdict": verdict,
        "breakdown": {"T_热度": round(T, 1), "D_竞争比": round(D, 1), "C_成本": round(C, 1), "R_风险": round(R, 1), "P_利润": round(P, 1)},
        "costs": {
            "cost_rmb": cost_rmb,
            "shipping_rmb": shipping["cost_rmb"],
            "total_cost_rmb": round(cost_rmb + shipping["cost_rmb"], 2),
            "total_cost_usd": round((cost_rmb + shipping["cost_rmb"]) / 7.2, 2),
            "sell_price_usd": sell_price_usd,
            "estimated_profit_usd": round(sell_price_usd - (cost_rmb + shipping["cost_rmb"]) / 7.2 - sell_price_usd * 0.049 - ad_budget_usd, 2),
            "margin_pct": round((sell_price_usd - (cost_rmb + shipping["cost_rmb"]) / 7.2 - sell_price_usd * 0.049 - ad_budget_usd) / sell_price_usd * 100, 1),
        },
    }


def score_batch_1688(products: list, weights: Optional[dict] = None) -> list:
    """批量评分"""
    results = []
    for p in products:
        r = total_score_1688(
            product_name=p.get("name", "Unknown"),
            cost_rmb=p.get("cost_rmb", 0),
            sell_price_usd=p.get("sell_price_usd", 19.99),
            weight_kg=p.get("weight_kg", 0.3),
            search_volume=p.get("search_volume", 0),
            active_listings=p.get("active_listings", 1),
            trend=p.get("trend", "flat"),
            tiktok_views=p.get("tiktok_views", 0),
            is_branded=p.get("branded", False),
            has_cert_required=p.get("cert_required", False),
            is_battery=p.get("battery", False),
            is_fragile=p.get("fragile", False),
            supplier_years=p.get("supplier_years", 3),
            shipping_method=p.get("shipping_method", "epacket"),
            markup=p.get("markup", 3.0),
            ad_budget_usd=p.get("ad_budget_usd", 2.0),
            weights=weights,
        )
        results.append(r)
    results.sort(key=lambda r: r["total_score"], reverse=True)
    return results


# ============================================================
# CLI
# ============================================================

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--batch":
        data = json.loads(sys.stdin.read())
        results = score_batch_1688(data)
        print(json.dumps(results, indent=2, ensure_ascii=False))
    elif len(sys.argv) > 1 and sys.argv[1] == "--single":
        data = json.loads(sys.argv[2])
        result = total_score_1688(**data)
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        # 演示
        demo = total_score_1688(
            product_name="便携露营灯 USB充电 LED",
            cost_rmb=15.0,
            sell_price_usd=19.99,
            weight_kg=0.25,
            search_volume=65000,
            active_listings=2800,
            trend="up",
            tiktok_views=1200,
            is_battery=True,
            is_branded=False,
            has_cert_required=False,
            supplier_years=5,
            shipping_method="epacket",
        )
        print(json.dumps(demo, indent=2, ensure_ascii=False))
