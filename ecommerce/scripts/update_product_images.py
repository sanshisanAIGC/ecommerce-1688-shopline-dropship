# -*- coding: utf-8 -*-
"""Shopline 产品图片更新工具 — 用真实 1688 产品图替换 Unsplash 占位图

用法:
  python update_product_images.py <product_id> <image_url> [image_url2] ...
  python update_product_images.py <product_id> --from-file <urls.txt>
  python update_product_images.py <product_id> --from-1688 <1688_product_url>
"""
import io, json, os, sys, urllib.request, urllib.error

# ============================================================
# Bootstrap — reuse shopline_api for auth
# ============================================================
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJ_DIR = os.path.dirname(_THIS_DIR)
sys.path.insert(0, _PROJ_DIR)

if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

import importlib.util
_spec = importlib.util.spec_from_file_location("api", os.path.join(_THIS_DIR, "shopline_api.py"))
_api = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_api)

TOKEN = getattr(_api, "TOKEN", "")
BASE = getattr(_api, "BASE", "")
products_update = _api.products_update
products_get = _api.products_get


# ============================================================
# Image update logic
# ============================================================

def update_product_images(product_id: str, image_urls: list, alt_texts: list = None):
    """Update a Shopline product's images. Replaces ALL existing images."""
    # First get current product to know what exists
    current = products_get(product_id)
    if not current.get("success"):
        print(f"ERROR: Failed to fetch product {product_id}: {current.get('error', 'Unknown')}", file=sys.stderr)
        return current

    product = current.get("data", {}).get("product", {})
    title = product.get("title", "Unknown")

    images = []
    for i, url in enumerate(image_urls):
        img = {"src": url}
        if alt_texts and i < len(alt_texts):
            img["alt"] = alt_texts[i]
        images.append(img)

    print(f"Updating images for: {title}", file=sys.stderr)
    print(f"  Current images: {len(product.get('images', []))}", file=sys.stderr)
    print(f"  New images: {len(images)}", file=sys.stderr)
    for i, img in enumerate(images, 1):
        print(f"  {i}. {img['src'][:90]}...", file=sys.stderr)

    result = products_update(product_id, {"images": images})
    if result.get("success"):
        new_product = result.get("data", {}).get("product", {})
        new_images = new_product.get("images", [])
        print(f"  -> SUCCESS! {len(new_images)} images updated.", file=sys.stderr)
    else:
        print(f"  -> FAILED: {result.get('error', 'Unknown')}", file=sys.stderr)

    return result


# ============================================================
# CLI
# ============================================================

def usage():
    print("""
Product Image Updater — 更新 Shopline 产品图片

用法:
  python update_product_images.py <product_id> <url1> [url2 url3 ...]
  python update_product_images.py <product_id> --from-file <urls.txt>
  python update_product_images.py <product_id> --from-1688 <url>  (手动粘贴1688图片URL)

示例:
  # 用 1688 产品图替换
  python update_product_images.py 16075888573709620414561495 \\
    "https://cbu01.alicdn.com/img/ibank/O1CN01xxx_1234567890.jpg" \\
    "https://cbu01.alicdn.com/img/ibank/O1CN01yyy_1234567890.jpg" \\
    "https://cbu01.alicdn.com/img/ibank/O1CN01zzz_1234567890.jpg"

  # 从文件批量读取
  python update_product_images.py 16075888573709620414561495 --from-file lantern_urls.txt

如何获取 1688 产品图片 URL：
  1. 浏览器打开 1688 产品详情页
  2. 点击产品主图放大
  3. 右键 → "复制图片地址" (Copy Image Address)
  4. 粘贴得到的 URL (通常以 cbu01.alicdn.com 或 img.alicdn.com 开头)
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

    product_id = args[0]
    rest = args[1:]

    if not rest:
        # No URLs provided — show current images
        result = products_get(product_id)
        if result.get("success"):
            p = result["data"]["product"]
            print(f"Current images for: {p['title']}", file=sys.stderr)
            for i, img in enumerate(p.get("images", []), 1):
                print(f"  {i}. {img['src']}", file=sys.stderr)
            print(json.dumps(result, indent=2, ensure_ascii=False))
        else:
            print(json.dumps(result, indent=2, ensure_ascii=False))
        return

    image_urls = []

    if rest[0] == "--from-file":
        if len(rest) < 2:
            print("ERROR: --from-file requires a file path", file=sys.stderr)
            sys.exit(1)
        filepath = rest[1]
        if not os.path.exists(filepath):
            print(f"ERROR: file not found: {filepath}", file=sys.stderr)
            sys.exit(1)
        with open(filepath, "r") as f:
            image_urls = [line.strip() for line in f if line.strip() and not line.startswith("#")]
    elif rest[0] == "--from-1688":
        # Interactive mode: user pastes 1688 URLs
        print("Paste 1688 image URLs (one per line, empty line to finish):", file=sys.stderr)
        while True:
            try:
                line = input().strip()
                if not line:
                    break
                image_urls.append(line)
            except EOFError:
                break
    else:
        image_urls = rest

    if not image_urls:
        print("ERROR: No image URLs provided", file=sys.stderr)
        sys.exit(1)

    result = update_product_images(product_id, image_urls)
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
