# -*- coding: utf-8 -*-
"""
1688 跨境一键代发 — Shopline 订单 → 1688 采购 → 物流同步
========================================================
半自动代发工具：监控 Shopline 新订单 → 生成 1688 采购清单 →
用户手动下单后录入物流单号 → 推送回 Shopline。

用法:
  python fulfillment.py mapping set <product_id> <1688_url> <cost_rmb> [--supplier NAME] [--sku SKU]
  python fulfillment.py mapping list
  python fulfillment.py mapping remove <product_id>
  python fulfillment.py mapping import <json_file>
  python fulfillment.py orders pending [--limit 50]
  python fulfillment.py orders info <order_id>
  python fulfillment.py fulfill sheet <order_id>
  python fulfillment.py fulfill batch
  python fulfillment.py tracking add <order_id> <tracking_number> [--carrier NAME] [--url URL]
  python fulfillment.py tracking list [order_id]
  python fulfillment.py tracking sync <order_id> [--notify]
  python fulfillment.py watch [--interval MINUTES] [--once]
  python fulfillment.py status
"""
import io
import json
import os
import sys
import time
import importlib.util
from datetime import datetime, timezone, timedelta

# ============================================================
# Bootstrap
# ============================================================

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJ_DIR = os.path.dirname(_THIS_DIR)
sys.path.insert(0, _PROJ_DIR)

if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

# Import shopline_api as module
_api_spec = importlib.util.spec_from_file_location(
    "shopline_api", os.path.join(_THIS_DIR, "shopline_api.py")
)
_api = importlib.util.module_from_spec(_api_spec)
_api_spec.loader.exec_module(_api)

# Re-export commonly used functions
orders_list = _api.orders_list
orders_get = _api.orders_get
orders_fulfillments_create = _api.orders_fulfillments_create
orders_fulfillments_list = _api.orders_fulfillments_list
orders_fulfillments_update_tracking = _api.orders_fulfillments_update_tracking
products_get = _api.products_get

TOKEN = getattr(_api, "TOKEN", "")

# ============================================================
# Paths
# ============================================================

DATA_DIR = os.path.join(_PROJ_DIR, "data")
MAPPING_FILE = os.path.join(DATA_DIR, "product_mapping.json")
FULFILLMENT_LOG_FILE = os.path.join(DATA_DIR, "fulfillment_log.json")

# Timezone for timestamps
CST = timezone(timedelta(hours=8))


def ensure_data_dir():
    os.makedirs(DATA_DIR, exist_ok=True)


# ============================================================
# Carrier name map (user-friendly → Shopline API value)
# ============================================================

CARRIER_MAP = {
    "yunexpress": "YunExpress",
    "云途": "YunExpress",
    "dhl": "DHL",
    "fedex": "FedEx",
    "ups": "UPS",
    "usps": "USPS",
    "ems": "EMS",
    "中国邮政": "ChinaPost",
    "chinapost": "ChinaPost",
    "4px": "4PX",
    "递四方": "4PX",
    "yanwen": "Yanwen",
    "燕文": "Yanwen",
    "cainiao": "Cainiao",
    "菜鸟": "Cainiao",
    "epacket": "ePacket",
    "e邮宝": "ePacket",
    "sf": "SF-Express",
    "顺丰": "SF-Express",
}


def normalize_carrier(raw: str) -> str:
    """Map user-friendly carrier name to Shopline API value."""
    key = raw.strip().lower()
    return CARRIER_MAP.get(key, raw.strip())


# ============================================================
# Atomic file I/O
# ============================================================

def _atomic_write(filepath: str, data: dict):
    """Write JSON atomically to avoid corruption."""
    ensure_data_dir()
    tmp = filepath + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    os.replace(tmp, filepath)


def _read_json(filepath: str, default: dict) -> dict:
    """Read JSON file, return default if missing or corrupt."""
    if not os.path.exists(filepath):
        return default
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return default


# ============================================================
# Product Mapping CRUD
# ============================================================

def load_mappings() -> list:
    """Load product mapping list."""
    data = _read_json(MAPPING_FILE, {"version": "1", "mappings": []})
    return data.get("mappings", [])


def save_mappings(mappings: list):
    """Save product mapping list."""
    _atomic_write(MAPPING_FILE, {
        "version": "1",
        "updated_at": datetime.now(CST).isoformat(),
        "mappings": mappings,
    })


def find_mapping(product_id: str, variant_id: str = None, sku: str = None) -> dict | None:
    """Find the best matching mapping for a product.
    Priority: variant_id match > sku match > product_id only match > None.
    """
    mappings = load_mappings()
    candidates = [m for m in mappings if m.get("shopline_product_id") == product_id]
    if not candidates:
        return None

    # Exact variant match
    if variant_id:
        for m in candidates:
            if m.get("variant_id") == variant_id:
                return m

    # SKU match
    if sku:
        for m in candidates:
            if m.get("sku") == sku:
                return m

    # First product-level match
    return candidates[0]


# ============================================================
# Fulfillment Log CRUD
# ============================================================

def load_fulfillment_log() -> dict:
    """Load the full fulfillment log."""
    return _read_json(FULFILLMENT_LOG_FILE, {"version": "1", "records": []})


def save_fulfillment_log(log: dict):
    """Save the full fulfillment log."""
    log["updated_at"] = datetime.now(CST).isoformat()
    _atomic_write(FULFILLMENT_LOG_FILE, log)


def find_log_record(order_id: str) -> dict | None:
    """Find a fulfillment log record by order_id."""
    log = load_fulfillment_log()
    for rec in log.get("records", []):
        if rec["order_id"] == order_id:
            return rec
    return None


def upsert_log_record(record: dict):
    """Insert or update a fulfillment log record (matched by order_id)."""
    log = load_fulfillment_log()
    records = log.get("records", [])
    for i, rec in enumerate(records):
        if rec["order_id"] == record["order_id"]:
            records[i] = record
            log["records"] = records
            save_fulfillment_log(log)
            return
    records.append(record)
    log["records"] = records
    save_fulfillment_log(log)


# ============================================================
# Helpers
# ============================================================

def now_iso() -> str:
    return datetime.now(CST).isoformat()


def print_stderr(msg: str):
    """Print human-readable message to stderr."""
    print(msg, file=sys.stderr)


def extract_shipping_address(order: dict) -> dict:
    """Extract shipping address from order object."""
    addr = order.get("shipping_address") or order.get("address") or {}
    return {
        "name": addr.get("name") or addr.get("first_name", "") + " " + addr.get("last_name", ""),
        "address1": addr.get("address1") or addr.get("address", ""),
        "address2": addr.get("address2", ""),
        "city": addr.get("city", ""),
        "province": addr.get("province") or addr.get("state", ""),
        "zip": addr.get("zip") or addr.get("postal_code", ""),
        "country_code": addr.get("country_code") or addr.get("country", ""),
        "phone": addr.get("phone") or addr.get("telephone", ""),
    }


def extract_line_items(order: dict) -> list:
    """Extract line items from order object. Try multiple possible paths."""
    items = order.get("line_items") or order.get("order_items") or []
    result = []
    for item in items:
        result.append({
            "line_item_id": item.get("id") or item.get("line_item_id"),
            "product_id": item.get("product_id"),
            "variant_id": item.get("variant_id"),
            "sku": item.get("sku", ""),
            "title": item.get("title") or item.get("name") or item.get("product_title", "Unknown"),
            "quantity": item.get("quantity", 1),
            "price": item.get("price", "0"),
            "fulfillable_quantity": item.get("fulfillable_quantity", item.get("quantity", 1)),
        })
    return result


def extract_customer_info(order: dict) -> dict:
    """Extract customer info from order object."""
    customer = order.get("customer") or {}
    email = order.get("email") or customer.get("email", "")
    name = (order.get("contact_name")
            or customer.get("first_name", "") + " " + customer.get("last_name", ""))
    return {"name": name.strip(), "email": email}


# ============================================================
# Command: mapping
# ============================================================

def cmd_mapping_list():
    """List all product→1688 mappings."""
    mappings = load_mappings()
    if not mappings:
        print_stderr("(empty) No product mappings yet. Use 'mapping set' to add one.")
        print(json.dumps({"mappings": []}, indent=2, ensure_ascii=False))
        return

    print_stderr(f"=== Product → 1688 Mappings ({len(mappings)}) ===")
    for i, m in enumerate(mappings, 1):
        print_stderr(f"{i}. [{m.get('shopline_product_id','?')[:20]}...] {m.get('sku','?')}")
        print_stderr(f"   1688: {m.get('source_url','?')[:70]}")
        print_stderr(f"   成本: ¥{m.get('cost_rmb','?')} | 供应商: {m.get('supplier_name','?')}")
        print_stderr("")
    print(json.dumps({"mappings": mappings}, indent=2, ensure_ascii=False))


def cmd_mapping_set(args: list):
    """Add or update a product→1688 mapping."""
    if len(args) < 3:
        print_stderr("ERROR: mapping set <product_id> <1688_url> <cost_rmb> [--supplier NAME] [--sku SKU] [--variant-id ID] [--note TEXT]")
        sys.exit(1)

    product_id = args[0]
    source_url = args[1]
    try:
        cost_rmb = float(args[2])
    except ValueError:
        print_stderr(f"ERROR: cost_rmb must be a number, got: {args[2]}")
        sys.exit(1)

    # Parse optional flags
    supplier = None
    sku = None
    variant_id = None
    note = None
    i = 3
    while i < len(args):
        if args[i] == "--supplier" and i + 1 < len(args):
            supplier = args[i + 1]; i += 2
        elif args[i] == "--sku" and i + 1 < len(args):
            sku = args[i + 1]; i += 2
        elif args[i] == "--variant-id" and i + 1 < len(args):
            variant_id = args[i + 1]; i += 2
        elif args[i] == "--note" and i + 1 < len(args):
            note = args[i + 1]; i += 2
        else:
            i += 1

    mappings = load_mappings()

    # Upsert: find existing by product_id + variant_id
    found = False
    for m in mappings:
        if m["shopline_product_id"] == product_id and m.get("variant_id") == variant_id:
            m["source_url"] = source_url
            m["cost_rmb"] = cost_rmb
            if supplier is not None:
                m["supplier_name"] = supplier
            if sku is not None:
                m["sku"] = sku
            if note is not None:
                m["notes"] = note
            m["updated_at"] = now_iso()
            found = True
            break

    if not found:
        mappings.append({
            "shopline_product_id": product_id,
            "variant_id": variant_id,
            "sku": sku or "",
            "source_url": source_url,
            "source_platform": "1688",
            "cost_rmb": cost_rmb,
            "supplier_name": supplier or "",
            "spec_note": note or "",
            "notes": "",
            "created_at": now_iso(),
            "updated_at": now_iso(),
        })

    save_mappings(mappings)
    print_stderr(f"{'Updated' if found else 'Added'} mapping: {product_id} → {source_url[:60]} (¥{cost_rmb})")
    print(json.dumps({"ok": True, "product_id": product_id, "action": "updated" if found else "added"}, ensure_ascii=False))


def cmd_mapping_remove(args: list):
    """Remove a product→1688 mapping."""
    if len(args) < 1:
        print_stderr("ERROR: mapping remove <product_id> [--variant-id ID]")
        sys.exit(1)

    product_id = args[0]
    variant_id = None
    if "--variant-id" in args:
        idx = args.index("--variant-id")
        variant_id = args[idx + 1] if idx + 1 < len(args) else None

    mappings = load_mappings()
    before = len(mappings)
    mappings = [
        m for m in mappings
        if not (m["shopline_product_id"] == product_id and (
            variant_id is None or m.get("variant_id") == variant_id
        ))
    ]
    removed = before - len(mappings)

    if removed > 0:
        save_mappings(mappings)
        print_stderr(f"Removed {removed} mapping(s) for {product_id}")
        print(json.dumps({"ok": True, "removed": removed}, ensure_ascii=False))
    else:
        print_stderr(f"No mapping found for {product_id}")
        print(json.dumps({"ok": False, "removed": 0, "error": "not found"}, ensure_ascii=False))


def cmd_mapping_import(args: list):
    """Batch import mappings from JSON file."""
    if len(args) < 1:
        print_stderr("ERROR: mapping import <json_file>")
        sys.exit(1)

    filepath = args[0]
    if not os.path.exists(filepath):
        print_stderr(f"ERROR: file not found: {filepath}")
        sys.exit(1)

    with open(filepath, "r", encoding="utf-8") as f:
        import_data = json.load(f)

    items = import_data if isinstance(import_data, list) else import_data.get("mappings", [])
    mappings = load_mappings()
    created, updated = 0, 0

    for item in items:
        pid = item.get("shopline_product_id")
        if not pid:
            continue
        existing = None
        for m in mappings:
            if m["shopline_product_id"] == pid and m.get("variant_id") == item.get("variant_id"):
                existing = m
                break
        if existing:
            existing.update({k: v for k, v in item.items() if k not in ("created_at",)})
            existing["updated_at"] = now_iso()
            updated += 1
        else:
            item.setdefault("created_at", now_iso())
            item.setdefault("updated_at", now_iso())
            item.setdefault("source_platform", "1688")
            mappings.append(item)
            created += 1

    save_mappings(mappings)
    print_stderr(f"Imported: {created} created, {updated} updated ({len(items)} total)")
    print(json.dumps({"ok": True, "created": created, "updated": updated}, ensure_ascii=False))


# ============================================================
# Command: orders
# ============================================================

def cmd_orders_pending(args: list):
    """List unfulfilled orders."""
    limit = 50
    if "--limit" in args:
        idx = args.index("--limit")
        limit = int(args[idx + 1]) if idx + 1 < len(args) else 50

    print_stderr(f"=== Fetching unfulfilled orders (limit={limit}) ===")
    # Fetch both "unshipped" and "partial" orders
    result = orders_list(limit=limit, fulfillment_status="unshipped")

    if not result.get("success"):
        print_stderr(f"API ERROR: {json.dumps(result.get('error',''), ensure_ascii=False)[:200]}")
        print(json.dumps(result, ensure_ascii=False))
        return

    orders = result.get("data", {}).get("orders") or []
    if not orders:
        print_stderr("(empty) No unfulfilled orders.")
        print(json.dumps({"orders": []}, indent=2, ensure_ascii=False))
        return

    output = []
    for order in orders:
        order_id = str(order.get("id", ""))
        order_number = order.get("order_number") or order.get("name", "N/A")
        customer = extract_customer_info(order)
        items = extract_line_items(order)
        fulfillment_status = order.get("fulfillment_status", "unshipped")
        total_price = order.get("total_price") or order.get("total", "N/A")

        print_stderr(f"--- Order #{order_number} ({order_id}) ---")
        print_stderr(f"  Status: {fulfillment_status} | Total: ${total_price}")
        print_stderr(f"  Customer: {customer['name']} <{customer['email']}>")
        print_stderr(f"  Items: {len(items)}")
        for item in items:
            pid = item.get("product_id", "?")
            mapping = find_mapping(pid, item.get("variant_id"), item.get("sku"))
            mapped = "✓" if mapping else "✗ UNMAPPED"
            print_stderr(f"    [{mapped}] {item['title'][:40]} x{item['quantity']} (SKU: {item.get('sku','?')})")
        print_stderr("")

        output.append({
            "order_id": order_id,
            "order_number": order_number,
            "customer": customer,
            "total_price": total_price,
            "fulfillment_status": fulfillment_status,
            "items": items,
            "has_unmapped": any(
                not find_mapping(it.get("product_id"), it.get("variant_id"), it.get("sku"))
                for it in items
            ),
        })

    print(json.dumps({"orders": output}, indent=2, ensure_ascii=False))


def cmd_orders_info(args: list):
    """Get detailed info for a single order."""
    if len(args) < 1:
        print_stderr("ERROR: orders info <order_id>")
        sys.exit(1)

    order_id = args[0]
    result = orders_get(order_id)

    if not result.get("success"):
        print_stderr(f"API ERROR: {json.dumps(result.get('error',''), ensure_ascii=False)[:200]}")
        print(json.dumps(result, ensure_ascii=False))
        return

    order = result.get("data", {}).get("order", result.get("data", {}))
    customer = extract_customer_info(order)
    address = extract_shipping_address(order)
    items = extract_line_items(order)

    print_stderr(f"=== Order #{order.get('order_number', order.get('name', order_id))} ===")
    print_stderr(f"ID: {order_id}")
    print_stderr(f"Status: {order.get('fulfillment_status','?')} | Financial: {order.get('financial_status','?')}")
    print_stderr(f"Total: ${order.get('total_price', order.get('total','?'))}")
    print_stderr(f"Customer: {customer['name']} <{customer['email']}>")
    print_stderr(f"Shipping: {address['name']}, {address['address1']}, {address['city']}, "
                 f"{address['province']} {address['zip']}, {address['country_code']}")
    print_stderr(f"Phone: {address.get('phone','N/A')}")
    print_stderr(f"Items ({len(items)}):")
    for item in items:
        pid = item.get("product_id", "?")
        mapping = find_mapping(pid, item.get("variant_id"), item.get("sku"))
        mapped = f"→ 1688 ¥{mapping['cost_rmb']}" if mapping else "✗ NO MAPPING"
        print_stderr(f"  {item['title'][:50]} x{item['quantity']} @ ${item.get('price','?')} {mapped}")
    print_stderr("")

    output = {
        "order_id": order_id,
        "order_number": order.get("order_number") or order.get("name"),
        "customer": customer,
        "shipping_address": address,
        "items": items,
        "total_price": order.get("total_price") or order.get("total"),
        "fulfillment_status": order.get("fulfillment_status"),
        "financial_status": order.get("financial_status"),
    }
    print(json.dumps(output, indent=2, ensure_ascii=False))


# ============================================================
# Command: fulfill
# ============================================================

def _build_purchase_sheet(order: dict, mark: bool = False) -> dict:
    """Build a purchase sheet for an order. Returns the log record."""
    order_id = str(order.get("id", ""))
    order_number = order.get("order_number") or order.get("name", "N/A")
    customer = extract_customer_info(order)
    address = extract_shipping_address(order)
    items = extract_line_items(order)

    purchase_items = []
    unmapped_items = []
    total_cost_rmb = 0.0

    for item in items:
        pid = item.get("product_id")
        vid = item.get("variant_id")
        sku = item.get("sku", "")
        mapping = find_mapping(pid, vid, sku)

        if not mapping:
            unmapped_items.append(item)
            continue

        item_cost = mapping["cost_rmb"] * item["quantity"]
        total_cost_rmb += item_cost
        purchase_items.append({
            "line_item_id": item["line_item_id"],
            "product_title": item["title"],
            "shopline_product_id": pid,
            "variant_id": vid,
            "sku": sku,
            "quantity": item["quantity"],
            "source_url": mapping["source_url"],
            "cost_rmb": mapping["cost_rmb"],
            "total_cost_rmb": round(item_cost, 2),
            "supplier_name": mapping.get("supplier_name", ""),
            "spec_note": mapping.get("spec_note", ""),
        })

    # Estimate shipping (use epacket as default)
    total_weight_kg = 0.3 * len(purchase_items)
    shipping_estimate = 15 + 50 * max(0, total_weight_kg - 0.2) if total_weight_kg > 0 else 0
    shipping_estimate = round(shipping_estimate, 2)

    # Print purchase sheet (stderr)
    print_stderr("")
    print_stderr(f"{'='*60}")
    print_stderr(f"  采购清单: Order #{order_number} ({order_id})")
    print_stderr(f"  客户: {customer['name']} | {address['city']}, {address['country_code']}")
    print_stderr(f"{'='*60}")

    for i, pi in enumerate(purchase_items, 1):
        print_stderr(f"\n{i}. [{pi['shopline_product_id'][:20]}...] {pi['product_title'][:50]}")
        print_stderr(f"   1688 链接: {pi['source_url']}")
        print_stderr(f"   规格: {pi['spec_note'] or '默认'} | 单价: ¥{pi['cost_rmb']} | "
                     f"数量: {pi['quantity']} | 小计: ¥{pi['total_cost_rmb']}")
        if pi.get("supplier_name"):
            print_stderr(f"   供应商: {pi['supplier_name']}")

    if unmapped_items:
        print_stderr(f"\n{'!'*60}")
        print_stderr(f"  ⚠  WARNING: {len(unmapped_items)} item(s) have NO 1688 mapping:")
        for ui in unmapped_items:
            print_stderr(f"  - [{ui.get('product_id','?')[:20]}...] {ui['title'][:40]} (SKU: {ui.get('sku','?')})")
        print_stderr(f"  Run: python fulfillment.py mapping set <product_id> <1688_url> <cost_rmb>")
        print_stderr(f"{'!'*60}")

    print_stderr(f"\n{'-'*60}")
    print_stderr(f"  商品合计: ¥{total_cost_rmb:.2f} | 预估运费: ~¥{shipping_estimate:.2f}")
    print_stderr(f"  1688 采购总成本: ~¥{total_cost_rmb + shipping_estimate:.2f}")
    print_stderr(f"  订单售价: ${order.get('total_price', order.get('total', '?'))}")
    print_stderr(f"{'-'*60}\n")

    # Build log record
    record = {
        "id": f"rec_{order_id}",
        "order_id": order_id,
        "order_number": order_number,
        "customer_email": customer["email"],
        "customer_name": customer["name"],
        "shipping_address": address,
        "status": "pending_purchase",
        "items": purchase_items,
        "total_cost_rmb": round(total_cost_rmb, 2),
        "total_shipping_rmb_estimate": shipping_estimate,
        "unmapped_items": [{
            "line_item_id": ui.get("line_item_id"),
            "product_title": ui["title"],
            "shopline_product_id": ui.get("product_id"),
            "sku": ui.get("sku", ""),
            "quantity": ui.get("quantity", 1),
        } for ui in unmapped_items],
        "tracking": None,
        "shopline_fulfillment_id": None,
        "timestamps": {
            "detected_at": now_iso(),
            "sheet_generated_at": now_iso() if mark else None,
        },
    }

    if mark:
        upsert_log_record(record)

    return record


def cmd_fulfill_sheet(args: list):
    """Generate a 1688 purchase sheet for one order."""
    if len(args) < 1:
        print_stderr("ERROR: fulfill sheet <order_id> [--mark]")
        sys.exit(1)

    order_id = args[0]
    mark = "--mark" in args

    result = orders_get(order_id)
    if not result.get("success"):
        print_stderr(f"API ERROR: {json.dumps(result.get('error',''), ensure_ascii=False)[:300]}")
        print(json.dumps(result, ensure_ascii=False))
        sys.exit(1)

    order = result.get("data", {}).get("order", result.get("data", {}))
    if not order:
        print_stderr(f"ERROR: Order {order_id} not found in API response")
        sys.exit(1)

    record = _build_purchase_sheet(order, mark=mark)
    print(json.dumps(record, indent=2, ensure_ascii=False))


def cmd_fulfill_batch(args: list):
    """Generate purchase sheets for all unfulfilled orders."""
    mark = "--mark" in args

    result = orders_list(limit=50, fulfillment_status="unshipped")
    if not result.get("success"):
        print_stderr(f"API ERROR: {json.dumps(result.get('error',''), ensure_ascii=False)[:200]}")
        print(json.dumps(result, ensure_ascii=False))
        return

    orders = result.get("data", {}).get("orders") or []
    if not orders:
        print_stderr("No unfulfilled orders found.")
        print(json.dumps({"orders": [], "records": []}, ensure_ascii=False))
        return

    print_stderr(f"Found {len(orders)} unfulfilled order(s). Generating purchase sheets...\n")
    records = []
    for order in orders:
        order_id = str(order.get("id", ""))
        # Fetch full order details for line items
        detail = orders_get(order_id)
        if detail.get("success"):
            full_order = detail.get("data", {}).get("order", detail.get("data", {}))
            record = _build_purchase_sheet(full_order, mark=mark)
            records.append(record)
        else:
            print_stderr(f"  SKIP {order_id}: failed to fetch details")
        print_stderr("")  # separator

    output = {
        "count": len(records),
        "records": records,
    }
    print(json.dumps(output, indent=2, ensure_ascii=False))


# ============================================================
# Command: tracking
# ============================================================

def cmd_tracking_add(args: list):
    """Record a tracking number for an order."""
    if len(args) < 2:
        print_stderr("ERROR: tracking add <order_id> <tracking_number> [--carrier NAME] [--url URL]")
        sys.exit(1)

    order_id = args[0]
    tracking_number = args[1]

    carrier_raw = None
    url = None
    i = 2
    while i < len(args):
        if args[i] == "--carrier" and i + 1 < len(args):
            carrier_raw = args[i + 1]; i += 2
        elif args[i] == "--url" and i + 1 < len(args):
            url = args[i + 1]; i += 2
        else:
            i += 1

    carrier = normalize_carrier(carrier_raw) if carrier_raw else ""

    # Find existing record or create minimal one
    record = find_log_record(order_id)
    if not record:
        # Try to fetch order info for a minimal record
        result = orders_get(order_id)
        if result.get("success"):
            order = result.get("data", {}).get("order", result.get("data", {}))
            record = {
                "id": f"rec_{order_id}",
                "order_id": order_id,
                "order_number": order.get("order_number") or order.get("name", "N/A"),
                "customer_email": extract_customer_info(order)["email"],
                "customer_name": extract_customer_info(order)["name"],
                "shipping_address": extract_shipping_address(order),
                "status": "tracking_received",
                "items": [],
                "total_cost_rmb": 0,
                "total_shipping_rmb_estimate": 0,
                "tracking": None,
                "shopline_fulfillment_id": None,
                "timestamps": {"detected_at": now_iso()},
            }
        else:
            print_stderr(f"ERROR: Order {order_id} not found in Shopline")
            sys.exit(1)

    record["tracking"] = {
        "number": tracking_number,
        "carrier": carrier,
        "url": url or "",
        "added_at": now_iso(),
    }
    record["status"] = "tracking_received"
    ts = record.setdefault("timestamps", {})
    ts["tracking_added_at"] = now_iso()

    upsert_log_record(record)
    print_stderr(f"Tracking recorded: {tracking_number} ({carrier}) for order {order_id}")
    print(json.dumps({"ok": True, "order_id": order_id, "tracking": record["tracking"]}, indent=2, ensure_ascii=False))


def cmd_tracking_list(args: list):
    """List tracking records."""
    log = load_fulfillment_log()
    records = log.get("records", [])

    if args:
        order_id = args[0]
        records = [r for r in records if r["order_id"] == order_id]

    if not records:
        print_stderr("(empty) No tracking records found.")
        print(json.dumps({"records": []}, ensure_ascii=False))
        return

    for r in records:
        t = r.get("tracking") or {}
        print_stderr(f"  Order {r.get('order_number','?')} ({r['order_id']}) "
                     f"[{r['status']}] → {t.get('carrier','?')}: {t.get('number','?')}")

    print(json.dumps({"records": records}, indent=2, ensure_ascii=False))


def cmd_tracking_sync(args: list):
    """Push tracking info to Shopline API."""
    if len(args) < 1:
        print_stderr("ERROR: tracking sync <order_id> [--notify] [--force]")
        sys.exit(1)

    order_id = args[0]
    notify = "--notify" in args
    force = "--force" in args

    record = find_log_record(order_id)
    if not record:
        print_stderr(f"ERROR: No fulfillment record for order {order_id}. Run 'fulfill sheet' first.")
        sys.exit(1)

    if record.get("status") == "synced" and not force:
        print_stderr(f"Order {order_id} is already synced. Use --force to re-sync.")
        print(json.dumps({"ok": False, "error": "already synced", "order_id": order_id}, ensure_ascii=False))
        return

    tracking = record.get("tracking")
    if not tracking or not tracking.get("number"):
        print_stderr(f"ERROR: No tracking number for order {order_id}. Run 'tracking add' first.")
        sys.exit(1)

    # Fetch current order for line item snapshot IDs
    result = orders_get(order_id)
    if not result.get("success"):
        print_stderr(f"API ERROR fetching order: {json.dumps(result.get('error',''), ensure_ascii=False)[:300]}")
        print(json.dumps(result, ensure_ascii=False))
        sys.exit(1)

    order = result.get("data", {}).get("order", result.get("data", {}))
    items = extract_line_items(order)

    # Build line items for fulfillment
    line_items = [
        {"id": item["line_item_id"], "quantity": item["quantity"]}
        for item in items
        if item.get("line_item_id")
    ]

    if not line_items:
        print_stderr(f"ERROR: No fulfillable line items found for order {order_id}")
        sys.exit(1)

    # Build fulfillment payload
    fulfillment_data = {
        "line_items": line_items,
        "notify_customer": notify,
        "tracking_info_list": [{
            "tracking_company": tracking.get("carrier", ""),
            "tracking_number": tracking["number"],
        }],
    }
    if tracking.get("url"):
        fulfillment_data["tracking_info_list"][0]["tracking_url"] = tracking["url"]

    print_stderr(f"Pushing fulfillment to Shopline for order {record.get('order_number', order_id)}...")
    print_stderr(f"  Carrier: {tracking.get('carrier','?')}")
    print_stderr(f"  Tracking: {tracking['number']}")
    print_stderr(f"  Notify customer: {notify}")

    resp = orders_fulfillments_create(order_id, fulfillment_data)

    if resp.get("success"):
        fid = resp.get("data", {}).get("fulfillment", {}).get("id", "N/A")
        record["shopline_fulfillment_id"] = str(fid)
        record["status"] = "synced"
        ts = record.setdefault("timestamps", {})
        ts["synced_at"] = now_iso()
        upsert_log_record(record)
        print_stderr(f"  → SUCCESS! Fulfillment ID: {fid}")
    else:
        print_stderr(f"  → FAILED: {json.dumps(resp.get('error',''), ensure_ascii=False)[:300]}")

    print(json.dumps(resp, indent=2, ensure_ascii=False))


# ============================================================
# Command: watch
# ============================================================

def cmd_watch(args: list):
    """Poll for new orders and auto-generate purchase sheets."""
    if len(args) < 1 or args[0] != "start":
        print_stderr("ERROR: watch start [--interval MINUTES] [--once]")
        sys.exit(1)

    interval = 5  # minutes
    once = False
    i = 1
    while i < len(args):
        if args[i] == "--interval" and i + 1 < len(args):
            interval = int(args[i + 1]); i += 2
        elif args[i] == "--once":
            once = True; i += 1
        else:
            i += 1

    # Load known order IDs
    log = load_fulfillment_log()
    seen_ids = {r["order_id"] for r in log.get("records", [])}

    print_stderr(f"👀 Watching for new orders (interval: {interval} min)...")
    print_stderr(f"   Seen {len(seen_ids)} existing orders. Press Ctrl+C to stop.\n")

    try:
        while True:
            result = orders_list(limit=30, fulfillment_status="unshipped")
            if not result.get("success"):
                print_stderr(f"[{datetime.now(CST).strftime('%H:%M:%S')}] API error, retrying next cycle...")
                if once:
                    break
                time.sleep(interval * 60)
                continue

            orders = result.get("data", {}).get("orders") or []
            new_orders = [o for o in orders if str(o.get("id", "")) not in seen_ids]

            if new_orders:
                print_stderr(f"\n{'='*60}")
                print_stderr(f"[{datetime.now(CST).strftime('%H:%M:%S')}] 🔔 {len(new_orders)} NEW ORDER(S)!")
                print_stderr(f"{'='*60}")

                for order in new_orders:
                    order_id = str(order.get("id", ""))
                    # Fetch full detail
                    detail = orders_get(order_id)
                    if detail.get("success"):
                        full_order = detail.get("data", {}).get("order", detail.get("data", {}))
                        record = _build_purchase_sheet(full_order, mark=True)
                        seen_ids.add(order_id)

                        # Loud warning for unmapped items
                        if record.get("unmapped_items"):
                            print_stderr(f"⚠⚠⚠  ORDER {order_id} HAS UNMAPPED ITEMS — MAPPING REQUIRED ⚠⚠⚠")
                    else:
                        print_stderr(f"  Failed to fetch details for order {order_id}")
            else:
                ts = datetime.now(CST).strftime('%H:%M:%S')
                print_stderr(f"[{ts}] No new orders. ({len(orders)} unfulfilled total)")

            if once:
                break

            time.sleep(interval * 60)

    except KeyboardInterrupt:
        print_stderr("\nWatch stopped.")


# ============================================================
# Command: status
# ============================================================

def cmd_status():
    """Print fulfillment dashboard."""
    log = load_fulfillment_log()
    records = log.get("records", [])

    # Count by status
    status_counts = {}
    for r in records:
        s = r.get("status", "unknown")
        status_counts[s] = status_counts.get(s, 0) + 1

    # Count unmapped items across all records
    total_unmapped = sum(len(r.get("unmapped_items", [])) for r in records)

    # Check API for orders without any log record
    result = orders_list(limit=50, fulfillment_status="unshipped")
    api_unshipped = 0
    if result.get("success"):
        unshipped = result.get("data", {}).get("orders") or []
        logged_ids = {r["order_id"] for r in records}
        api_unshipped = sum(1 for o in unshipped if str(o.get("id", "")) not in logged_ids)

    print_stderr("")
    print_stderr(f"{'='*50}")
    print_stderr(f"  代发状态面板 — {datetime.now(CST).strftime('%Y-%m-%d %H:%M')}")
    print_stderr(f"{'='*50}")
    print_stderr(f"  待采购 (pending_purchase):     {status_counts.get('pending_purchase', 0):>4} 单")
    print_stderr(f"  已采购 (purchased):             {status_counts.get('purchased', 0):>4} 单")
    print_stderr(f"  待同步 (tracking_received):     {status_counts.get('tracking_received', 0):>4} 单")
    print_stderr(f"  已同步 (synced):                {status_counts.get('synced', 0):>4} 单")
    print_stderr(f"  {'─'*40}")
    print_stderr(f"  API 未追踪新订单:               {api_unshipped:>4} 单")
    print_stderr(f"  未映射 SKU 警告:                {total_unmapped:>4} 个")
    print_stderr(f"{'='*50}\n")

    dashboard = {
        "status_counts": status_counts,
        "total_records": len(records),
        "untracked_api_orders": api_unshipped,
        "unmapped_sku_warnings": total_unmapped,
        "records": records,
    }
    print(json.dumps(dashboard, indent=2, ensure_ascii=False))


# ============================================================
# CLI Router
# ============================================================

def usage():
    print_stderr("""
1688 跨境一键代发工具 — Order Fulfillment Manager

用法:
  python fulfillment.py mapping set <product_id> <1688_url> <cost_rmb> [--supplier NAME] [--sku SKU]
  python fulfillment.py mapping list
  python fulfillment.py mapping remove <product_id>
  python fulfillment.py mapping import <json_file>
  python fulfillment.py orders pending [--limit 50]
  python fulfillment.py orders info <order_id>
  python fulfillment.py fulfill sheet <order_id> [--mark]
  python fulfillment.py fulfill batch [--mark]
  python fulfillment.py tracking add <order_id> <tracking_number> [--carrier NAME] [--url URL]
  python fulfillment.py tracking list [order_id]
  python fulfillment.py tracking sync <order_id> [--notify] [--force]
  python fulfillment.py watch start [--interval MINUTES] [--once]
  python fulfillment.py status

典型工作流:
  1. python fulfillment.py mapping set <pid> <1688_url> <cost>   # 关联货源
  2. python fulfillment.py orders pending                          # 查看订单
  3. python fulfillment.py fulfill sheet <oid> --mark              # 生成采购清单
  4. (手动去 1688 下单，拿到物流单号)
  5. python fulfillment.py tracking add <oid> <number> --carrier yunexpress
  6. python fulfillment.py tracking sync <oid> --notify            # 推送到 Shopline
  7. python fulfillment.py status                                  # 看板
""")
    print(json.dumps({"error": "no command"}, ensure_ascii=False))


def main():
    if not TOKEN:
        print("ERROR: Please set SHOPLINE_API_TOKEN environment variable", file=sys.stderr)
        sys.exit(1)

    args = sys.argv[1:]
    if not args:
        usage()
        sys.exit(0)

    resource = args[0]
    rest = args[1:]

    if resource == "mapping":
        action = rest[0] if rest else "list"
        if action == "list":
            cmd_mapping_list()
        elif action == "set":
            cmd_mapping_set(rest[1:])
        elif action == "remove":
            cmd_mapping_remove(rest[1:])
        elif action == "import":
            cmd_mapping_import(rest[1:])
        else:
            print_stderr(f"Unknown mapping action: {action}")
            sys.exit(1)

    elif resource == "orders":
        action = rest[0] if rest else "pending"
        if action == "pending":
            cmd_orders_pending(rest[1:])
        elif action == "info":
            cmd_orders_info(rest[1:])
        else:
            print_stderr(f"Unknown orders action: {action}")
            sys.exit(1)

    elif resource == "fulfill":
        action = rest[0] if rest else "sheet"
        if action == "sheet":
            cmd_fulfill_sheet(rest[1:])
        elif action == "batch":
            cmd_fulfill_batch(rest[1:])
        else:
            print_stderr(f"Unknown fulfill action: {action}")
            sys.exit(1)

    elif resource == "tracking":
        action = rest[0] if rest else "list"
        if action == "add":
            cmd_tracking_add(rest[1:])
        elif action == "list":
            cmd_tracking_list(rest[1:])
        elif action == "sync":
            cmd_tracking_sync(rest[1:])
        else:
            print_stderr(f"Unknown tracking action: {action}")
            sys.exit(1)

    elif resource == "watch":
        cmd_watch(rest)

    elif resource == "status":
        cmd_status()

    else:
        print_stderr(f"Unknown resource: {resource}")
        usage()
        sys.exit(1)


if __name__ == "__main__":
    main()
