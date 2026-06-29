# -*- coding: utf-8 -*-
"""
Shopline Admin REST API 封装 — v20260601
供 Claude Code 直接调用的店铺管理工具

端点格式: https://{handle}.myshopline.com/admin/openapi/v20260601/
认证: Authorization: Bearer {SHOPLINE_API_TOKEN}

用法:
  python shopline_api.py products list            # 列出商品
  python shopline_api.py products create <json>   # 创建商品
  python shopline_api.py products get <id>        # 获取商品详情
  python shopline_api.py products update <id> <json>  # 更新商品
  python shopline_api.py products delete <id>     # 删除商品
  python shopline_api.py products count           # 商品数量
  python shopline_api.py orders list              # 订单列表
  python shopline_api.py orders get <id>          # 订单详情
  python shopline_api.py store info               # 店铺信息
"""
import json
import os
import sys
import urllib.request
import urllib.error
from typing import Optional

# ============================================================
# 配置
# ============================================================

# 自动加载 .env
_env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")
if os.path.exists(_env_path):
    with open(_env_path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                if k not in os.environ:
                    os.environ[k] = v

TOKEN = os.environ.get("SHOPLINE_API_TOKEN", "")
STORE = os.environ.get("SHOPLINE_STORE", "sanshisan")
VERSION = "v20260601"
BASE = f"https://{STORE}.myshopline.com/admin/openapi/{VERSION}"


def _headers():
    return {
        "Authorization": f"Bearer {TOKEN}",
        "Content-Type": "application/json; charset=utf-8",
    }


def _request(method: str, path: str, data: Optional[dict] = None) -> dict:
    """通用 API 请求"""
    url = f"{BASE}/{path}"
    body = json.dumps(data).encode() if data else None

    req = urllib.request.Request(url, data=body, headers=_headers(), method=method)

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read().decode())
            return {"success": True, "status": resp.status, "data": result}
    except urllib.error.HTTPError as e:
        err = json.loads(e.read().decode()) if e.fp else str(e)
        return {"success": False, "status": e.code, "error": err}


# ============================================================
# 商品操作
# ============================================================

def products_list(limit: int = 50, status: str = None):
    """列出商品"""
    path = f"product_listings.json?limit={limit}"
    if status:
        path += f"&status={status}"
    return _request("GET", path)


def products_count():
    """商品总数"""
    return _request("GET", "products/count.json")


def products_create(product: dict):
    """创建商品"""
    return _request("POST", "products/products.json", {"product": product})


def products_get(product_id: str):
    """获取商品详情"""
    return _request("GET", f"products/{product_id}.json")


def products_update(product_id: str, updates: dict):
    """更新商品"""
    return _request("PUT", f"products/{product_id}.json", {"product": updates})


def products_delete(product_id: str):
    """删除商品"""
    return _request("DELETE", f"products/{product_id}.json")


# ============================================================
# 订单操作
# ============================================================

def orders_list(limit: int = 50, status: str = None, fulfillment_status: str = None):
    """订单列表"""
    path = f"orders.json?limit={limit}"
    if status:
        path += f"&status={status}"
    if fulfillment_status:
        path += f"&fulfillment_status={fulfillment_status}"
    return _request("GET", path)


def orders_get(order_id: str):
    """订单详情"""
    return _request("GET", f"orders/{order_id}.json")


def orders_fulfillments_list(order_id: str):
    """列出订单的所有履约记录"""
    return _request("GET", f"orders/{order_id}/fulfillments.json")


def orders_fulfillments_create(order_id: str, fulfillment: dict):
    """创建履约（可同时填写物流追踪信息）"""
    return _request("POST", f"orders/{order_id}/fulfillments.json", {"fulfillment": fulfillment})


def orders_fulfillments_update_tracking(order_id: str, fulfillment_id: str, tracking: dict):
    """更新已创建履约的物流追踪信息"""
    return _request("POST", f"fulfillments/{order_id}/{fulfillment_id}/update_tracking.json", {"fulfillment": tracking})


# ============================================================
# 店铺信息
# ============================================================

def store_info():
    """获取店铺基本信息"""
    return _request("GET", "shop.json")


# ============================================================
# CLI
# ============================================================

def usage():
    print("""
Shopline API 工具 — Claude Code 电商助手

用法:
  python shopline_api.py products list [--limit 50] [--status active]
  python shopline_api.py products create '<json>'
  python shopline_api.py products get <id>
  python shopline_api.py products update <id> '<json>'
  python shopline_api.py products delete <id>
  python shopline_api.py products count
  python shopline_api.py orders list [--limit 50] [--fulfillment-status unshipped]
  python shopline_api.py orders get <id>
  python shopline_api.py orders fulfillments list <order_id>
  python shopline_api.py orders fulfillments create <order_id> '<json>'
  python shopline_api.py orders fulfillments tracking <order_id> <fulfillment_id> '<json>'
  python shopline_api.py store info

示例:
  python shopline_api.py products list --limit 5
  python shopline_api.py products create '{"title":"LED Light","variants":[{"price":"19.99"}]}'
""")


if __name__ == "__main__":
    if not TOKEN:
        print("ERROR: Please set SHOPLINE_API_TOKEN environment variable")
        sys.exit(1)

    args = sys.argv[1:]

    if not args:
        usage()
        sys.exit(0)

    resource = args[0]

    if resource == "products":
        action = args[1] if len(args) > 1 else "list"
        if action == "list":
            limit = int(args[args.index("--limit") + 1]) if "--limit" in args else 50
            status = args[args.index("--status") + 1] if "--status" in args else None
            r = products_list(limit, status)
        elif action == "create":
            data = json.loads(args[2]) if len(args) > 2 else {}
            r = products_create(data)
        elif action == "get":
            r = products_get(args[2])
        elif action == "update":
            data = json.loads(args[3])
            r = products_update(args[2], data)
        elif action == "delete":
            r = products_delete(args[2])
        elif action == "count":
            r = products_count()
        else:
            r = {"error": f"Unknown action: {action}"}

    elif resource == "orders":
        action = args[1] if len(args) > 1 else "list"
        if action == "list":
            limit = int(args[args.index("--limit") + 1]) if "--limit" in args else 50
            fstatus = args[args.index("--fulfillment-status") + 1] if "--fulfillment-status" in args else None
            r = orders_list(limit, fulfillment_status=fstatus)
        elif action == "get":
            r = orders_get(args[2])
        elif action == "fulfillments":
            sub = args[2] if len(args) > 2 else "list"
            if sub == "list":
                r = orders_fulfillments_list(args[3])
            elif sub == "create":
                data = json.loads(args[4]) if len(args) > 4 else {}
                r = orders_fulfillments_create(args[3], data)
            elif sub == "tracking":
                data = json.loads(args[5]) if len(args) > 5 else {}
                r = orders_fulfillments_update_tracking(args[3], args[4], data)
            else:
                r = {"error": f"Unknown fulfillments sub-action: {sub}"}
        else:
            r = {"error": f"Unknown action: {action}"}

    elif resource == "store":
        r = store_info()

    else:
        r = {"error": f"Unknown resource: {resource}"}

    print(json.dumps(r, indent=2, ensure_ascii=False))
