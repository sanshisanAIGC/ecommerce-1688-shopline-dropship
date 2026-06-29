# -*- coding: utf-8 -*-
"""
选品评分模型 - AI 电商选品打分系统
用于 Claude Code 调用，对 AliExpress/1688 商品进行量化评分

模型: S = w1*T + w2*D + w3*C + w4*R + w5*P
  T = 市场热度 (Google Trends + 搜索量)
  D = 需求竞争比 (搜索量 / 在售商品数)
  C = 供应链成本 (利润率)
  R = 合规风险 (IP/认证/物流限制)
  P = 利润空间 (售价 - 成本 - 费用)

输出: JSON 格式，Claude Code 可直接消费
"""

import json
import sys
from typing import Optional


def score_heat(
    search_volume: int,
    trend_direction: str,  # 'up', 'flat', 'down'
    social_mentions: int = 0,
) -> float:
    """市场热度评分 (0-100)"""
    base = min(search_volume / 1000 * 20, 40)  # 搜索量贡献最多40分
    trend_bonus = {"up": 30, "flat": 15, "down": 5}[trend_direction]
    social_bonus = min(social_mentions / 100 * 5, 30)  # 社交媒体热度最多30分
    return min(base + trend_bonus + social_bonus, 100)


def score_competition(search_volume: int, active_listings: int) -> float:
    """需求竞争比评分 (0-100)"""
    if active_listings == 0:
        return 90  # 零竞争，高分
    ratio = search_volume / active_listings
    # ratio > 1: 需求大于供给；ratio < 1: 供给过剩
    if ratio >= 2.0:
        return 95
    elif ratio >= 1.0:
        return 80
    elif ratio >= 0.5:
        return 60
    elif ratio >= 0.2:
        return 40
    elif ratio >= 0.1:
        return 20
    else:
        return 10


def score_cost(
    cost_price: float,
    shipping_cost: float,
    platform_fee_rate: float = 0.15,  # Shopify 交易费
) -> float:
    """供应链成本评分 (0-100)，基于预估利润率"""
    total_cost = cost_price + shipping_cost
    # 按不同售价档位估算利润率
    estimated_sell_prices = [cost_price * 2.0, cost_price * 2.5, cost_price * 3.0]
    best_margin = 0
    for sell_price in estimated_sell_prices:
        revenue_after_fee = sell_price * (1 - platform_fee_rate)
        margin = (revenue_after_fee - total_cost) / sell_price
        if margin > best_margin:
            best_margin = margin

    # 利润率评分
    if best_margin >= 0.6:
        return 95
    elif best_margin >= 0.5:
        return 85
    elif best_margin >= 0.4:
        return 70
    elif best_margin >= 0.3:
        return 50
    elif best_margin >= 0.2:
        return 30
    else:
        return 10


def score_risk(
    has_patent_risk: bool,
    has_certification_required: bool,
    is_fragile: bool,
    is_battery: bool,
    is_liquid: bool,
    is_branded: bool,
    shipping_days: int,
) -> float:
    """合规风险评分 (0-100, 100=零风险)"""
    score = 100
    if has_patent_risk:
        score -= 30
    if has_certification_required:
        score -= 15
    if is_fragile:
        score -= 10
    if is_battery:
        score -= 20  # 电池物流限制严重
    if is_liquid:
        score -= 10
    if is_branded:
        score -= 25  # 侵权风险
    if shipping_days > 30:
        score -= 15
    elif shipping_days > 15:
        score -= 5
    return max(score, 0)


def score_profit(
    cost_price: float,
    estimated_sell_price: float,
    shipping_cost: float,
    platform_fee_rate: float = 0.15,
    ad_cost_per_unit: float = 0,
) -> float:
    """利润空间评分 (0-100)"""
    revenue = estimated_sell_price
    fees = revenue * platform_fee_rate
    profit = revenue - cost_price - shipping_cost - fees - ad_cost_per_unit
    margin = profit / revenue if revenue > 0 else 0

    # 综合利润金额和利润率
    profit_score = min(profit / 10 * 15, 40)  # $10利润=15分, $26+利润=40分
    margin_score = min(margin * 60, 60)  # 50%利润率=30分, 100%=60分
    return min(profit_score + margin_score, 100)


def total_score(
    search_volume: int,
    trend_direction: str,
    social_mentions: int,
    active_listings: int,
    cost_price: float,
    estimated_sell_price: float,
    shipping_cost: float,
    has_patent_risk: bool = False,
    has_certification_required: bool = False,
    is_fragile: bool = False,
    is_battery: bool = False,
    is_liquid: bool = False,
    is_branded: bool = False,
    shipping_days: int = 15,
    platform_fee_rate: float = 0.15,
    ad_cost_per_unit: float = 0,
    weights: Optional[dict] = None,
) -> dict:
    """
    综合选品评分

    权重默认值（基于实战数据调优）：
    w1=0.25 热度, w2=0.30 竞争比(最高!), w3=0.15 成本, w4=0.15 风险, w5=0.15 利润
    """
    w = weights or {
        "T": 0.25, "D": 0.30, "C": 0.15, "R": 0.15, "P": 0.15,
    }

    T = score_heat(search_volume, trend_direction, social_mentions)
    D = score_competition(search_volume, active_listings)
    C = score_cost(cost_price, shipping_cost, platform_fee_rate)
    R = score_risk(has_patent_risk, has_certification_required, is_fragile, is_battery, is_liquid, is_branded, shipping_days)
    P = score_profit(cost_price, estimated_sell_price, shipping_cost, platform_fee_rate, ad_cost_per_unit)

    S = w["T"] * T + w["D"] * D + w["C"] * C + w["R"] * R + w["P"] * P

    verdict = "爆品候选" if S >= 85 else ("可测款" if S >= 75 else ("谨慎" if S >= 60 else "不推荐"))

    return {
        "total_score": round(S, 1),
        "verdict": verdict,
        "breakdown": {
            "T_热度": round(T, 1),
            "D_竞争比": round(D, 1),
            "C_成本": round(C, 1),
            "R_风险": round(R, 1),
            "P_利润": round(P, 1),
        },
        "weights_used": w,
        "estimated_margin": round(
            (estimated_sell_price * (1 - platform_fee_rate) - cost_price - shipping_cost - ad_cost_per_unit)
            / estimated_sell_price * 100, 1
        ),
        "estimated_profit_usd": round(
            estimated_sell_price * (1 - platform_fee_rate) - cost_price - shipping_cost - ad_cost_per_unit, 2
        ),
    }


def score_batch(products: list, weights: Optional[dict] = None) -> list:
    """批量评分"""
    results = []
    for p in products:
        result = total_score(
            search_volume=p.get("search_volume", 0),
            trend_direction=p.get("trend", "flat"),
            social_mentions=p.get("social_mentions", 0),
            active_listings=p.get("active_listings", 1),
            cost_price=p.get("cost_price", 0),
            estimated_sell_price=p.get("sell_price", p.get("cost_price", 0) * 2.5),
            shipping_cost=p.get("shipping_cost", 0),
            has_patent_risk=p.get("patent_risk", False),
            has_certification_required=p.get("cert_required", False),
            is_fragile=p.get("fragile", False),
            is_battery=p.get("battery", False),
            is_liquid=p.get("liquid", False),
            is_branded=p.get("branded", False),
            shipping_days=p.get("shipping_days", 15),
            weights=weights,
        )
        result["product_name"] = p.get("name", "Unknown")
        result["source_url"] = p.get("url", "")
        results.append(result)

    # 按总分降序排列
    results.sort(key=lambda r: r["total_score"], reverse=True)
    return results


# CLI 接口 - 供 Claude Code 通过 Bash 调用
if __name__ == "__main__":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    if len(sys.argv) > 1 and sys.argv[1] == "--batch":
        # 批量模式: echo '[{...},{...}]' | python product_scorer.py --batch
        data = json.loads(sys.stdin.read())
        results = score_batch(data)
        print(json.dumps(results, indent=2, ensure_ascii=False))
    elif len(sys.argv) > 1 and sys.argv[1] == "--single":
        # 单品模式: python product_scorer.py --single '<json>'
        data = json.loads(sys.argv[2])
        result = total_score(
            search_volume=data.get("search_volume", 0),
            trend_direction=data.get("trend", "flat"),
            social_mentions=data.get("social_mentions", 0),
            active_listings=data.get("active_listings", 1),
            cost_price=data.get("cost_price", 0),
            estimated_sell_price=data.get("sell_price", data.get("cost_price", 0) * 2.5),
            shipping_cost=data.get("shipping_cost", 0),
            has_patent_risk=data.get("patent_risk", False),
            has_certification_required=data.get("cert_required", False),
            is_fragile=data.get("fragile", False),
            is_battery=data.get("battery", False),
            is_liquid=data.get("liquid", False),
            is_branded=data.get("branded", False),
            shipping_days=data.get("shipping_days", 15),
        )
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        # 演示模式
        demo = {
            "name": "便携式露营灯 LED",
            "url": "https://aliexpress.com/item/100500xxxxx.html",
            "search_volume": 85000,
            "trend": "up",
            "social_mentions": 1200,
            "active_listings": 3200,
            "cost_price": 3.50,
            "sell_price": 19.99,
            "shipping_cost": 2.00,
            "shipping_days": 12,
            "battery": True,
            "cert_required": False,
            "patent_risk": False,
        }
        result = total_score(
            search_volume=demo["search_volume"],
            trend_direction=demo["trend"],
            social_mentions=demo["social_mentions"],
            active_listings=demo["active_listings"],
            cost_price=demo["cost_price"],
            estimated_sell_price=demo["sell_price"],
            shipping_cost=demo["shipping_cost"],
            is_battery=demo["battery"],
            has_certification_required=demo["cert_required"],
            has_patent_risk=demo["patent_risk"],
            shipping_days=demo["shipping_days"],
        )
        print("=== 选品评分模型演示 ===")
        print(json.dumps({"input": demo, "result": result}, indent=2, ensure_ascii=False))
