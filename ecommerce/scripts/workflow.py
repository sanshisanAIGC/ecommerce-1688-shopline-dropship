"""
AliExpress → Shopify 选品导入工作流
Claude Code 通过 Bash 调用此脚本，串联整个选品→评分→导入流程

用法:
  python workflow.py search "portable led lantern" --min-price 3 --max-price 15
  python workflow.py score product_data.json
  python workflow.py import product_id --markup 2.5 --store default
"""

import json
import sys
import os
import subprocess
from datetime import datetime

SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(os.path.dirname(SCRIPTS_DIR), "data")
LISTINGS_DIR = os.path.join(os.path.dirname(SCRIPTS_DIR), "listings")


def ensure_dirs():
    os.makedirs(DATA_DIR, exist_ok=True)
    os.makedirs(LISTINGS_DIR, exist_ok=True)


def save_search_results(keyword, results):
    """保存搜索结果到 data 目录"""
    ensure_dirs()
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    fname = f"search_{keyword.replace(' ', '_')}_{ts}.json"
    fpath = os.path.join(DATA_DIR, fname)
    with open(fpath, "w", encoding="utf-8") as f:
        json.dump({"keyword": keyword, "timestamp": ts, "results": results}, f, indent=2, ensure_ascii=False)
    print(f"搜索结果已保存: {fpath}")
    return fpath


def save_listing(product, optimized_title, optimized_desc):
    """保存生成的 Listing 草稿"""
    ensure_dirs()
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    name = product.get("name", "unknown").replace(" ", "_")[:50]
    fname = f"listing_{name}_{ts}.md"
    fpath = os.path.join(LISTINGS_DIR, fname)
    with open(fpath, "w", encoding="utf-8") as f:
        f.write(f"# {optimized_title}\n\n")
        f.write(f"## Product Info\n")
        f.write(f"- Source: {product.get('url', 'N/A')}\n")
        f.write(f"- Cost: ${product.get('cost_price', 'N/A')}\n")
        f.write(f"- Sell Price: ${product.get('sell_price', 'N/A')}\n")
        f.write(f"- Markup: {product.get('markup', 'N/A')}x\n\n")
        f.write(f"## SEO Optimized Description\n\n{optimized_desc}\n")
    print(f"Listing 已保存: {fpath}")
    return fpath


def create_import_batch(search_keyword, products, markup=2.5):
    """
    生成 DSers MCP 批量导入指令
    Claude Code 可读取此 JSON 并逐条调用 dsers MCP 工具
    """
    ensure_dirs()
    batch = {
        "search_keyword": search_keyword,
        "markup": markup,
        "created_at": datetime.now().isoformat(),
        "instructions": "以下商品待导入到 Shopify。逐条调用 dsers MCP 的 import_product 工具。",
        "products": [],
    }
    for p in products:
        cost = p.get("cost_price", 0)
        batch["products"].append({
            "name": p.get("name", ""),
            "source_url": p.get("url", ""),
            "cost_price": cost,
            "target_price": round(cost * markup, 2),
            "markup": markup,
            "needs_seo_rewrite": True,
            "target_store": p.get("store", "default"),
            "score": p.get("score", {}),
        })

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    fpath = os.path.join(DATA_DIR, f"batch_{ts}.json")
    with open(fpath, "w", encoding="utf-8") as f:
        json.dump(batch, f, indent=2, ensure_ascii=False)
    print(f"批量导入指令已生成: {fpath}")
    print(f"共 {len(batch['products'])} 个商品待导入")
    return fpath


def generate_seo_title(product_name, keywords, max_length=70):
    """生成 SEO 优化标题模板"""
    template = f"{product_name} - {keywords[:3]}"
    if len(template) > max_length:
        template = template[:max_length-3] + "..."
    return template


def generate_description(product, tone="professional"):
    """生成产品描述模板"""
    name = product.get("name", "Product")
    features = product.get("features", [])
    specs = product.get("specs", {})

    sections = [
        f"## Product Overview",
        f"Introducing the {name} — designed for quality and performance.",
        "",
        "## Key Features",
    ]
    for i, feat in enumerate(features[:5], 1):
        sections.append(f"{i}. **{feat}**")
    sections.append("")
    sections.append("## Specifications")
    for k, v in specs.items():
        sections.append(f"- **{k}**: {v}")
    sections.append("")
    sections.append("## Why Choose Us")
    sections.append("- Fast shipping from US warehouse")
    sections.append("- 30-day money-back guarantee")
    sections.append("- 24/7 customer support")

    return "\n".join(sections)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="电商选品导入工作流")
    subparsers = parser.add_subparsers(dest="command")

    # search 子命令 (实际由 Claude Code 通过 DSers MCP 执行)
    search_parser = subparsers.add_parser("search")
    search_parser.add_argument("keyword")
    search_parser.add_argument("--min-price", type=float, default=1)
    search_parser.add_argument("--max-price", type=float, default=30)

    # batch 子命令
    batch_parser = subparsers.add_parser("batch")
    batch_parser.add_argument("json_file", help="评分后的产品 JSON 文件")
    batch_parser.add_argument("--markup", type=float, default=2.5)

    args = parser.parse_args()

    if args.command == "batch":
        with open(args.json_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        products = data if isinstance(data, list) else data.get("results", [])
        create_import_batch(
            search_keyword=data.get("keyword", "unknown") if isinstance(data, dict) else "unknown",
            products=products,
            markup=args.markup,
        )
    else:
        parser.print_help()
