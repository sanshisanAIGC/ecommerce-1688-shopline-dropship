# 跨境电商 AI 自动化 — 路线 A（1688 → Shopline 一键代发）

## 触发条件
用户提到：选品、上架、1688、Shopline、跨境电商、代发、dropshipping、露营灯/户外/家居等品类词 + 卖/销售/开店。

## 技术栈
```
1688 选品 → 评分模型 → Shopline 上架 → 订单代发
   │            │              │              │
   └─ 搜品      └─ Python      └─ REST API     └─ fulfillment.py
                                             (采购清单 + 物流回传)
```

## 环境变量（从 `ecommerce/.env` 自动加载）
- `SHOPLINE_API_TOKEN` — Shopline 开放平台 Token
- `APIFY_TOKEN` — Apify API Token（1688 搜品）
- `SHOPLINE_STORE` — 店铺 handle（默认 `sanshisan`）

## 核心脚本

| 脚本 | 功能 |
|------|------|
| `ecommerce/scripts/search_and_score.py` | 搜品 + 评分 + 上架（全链路） |
| `ecommerce/scripts/shopline_api.py` | Shopline REST API 封装（含履约 API） |
| `ecommerce/scripts/product_scorer_1688.py` | 1688 选品评分模型 |
| `ecommerce/scripts/enrich_products.py` | 补全产品图片 + 详情描述 |
| `ecommerce/scripts/fulfillment.py` | 订单代发管理（采购清单 + 物流回传） |

## 工作流

### 流程 A：搜品 → 评分 → 上架

**用户说**："用 1688 搜「关键词」，价格 X-Y 元，找 N 个评估利润，推荐最好的上架"

**执行步骤**：

1. **搜品**：
   ```bash
   # 使用 Apify 1688 Scraper MCP 搜索
   # 或直接调用 Apify API:
   curl -X POST "https://api.apify.com/v2/acts/futurizerush~1688-com-products-scraper/runs?token=$APIFY_TOKEN" \
     -H "Content-Type: application/json" \
     -d '{"queries":["关键词"],"maxItemsPerQuery":10}'
   ```
   等待 run 完成 → 获取 dataset items。

2. **评分**：将搜品结果传入评分模型
   ```bash
   python ecommerce/scripts/product_scorer_1688.py --batch < products.json
   ```
   评分维度：热度(20%) + 竞争比(25%) + 成本(20%) + 风险(15%) + 利润(20%)
   - 85+ = 爆品候选
   - 75-84 = 可测款
   - 60-74 = 谨慎
   - <60 = 不推荐

3. **上架**：创建评分最高的商品
   ```bash
   python ecommerce/scripts/shopline_api.py products create '<json>'
   ```
   默认定价 = 1688成本 × 3 倍（覆盖物流 + 平台费 + 广告）

4. **补全详情**：为每个商品添加图片和详细描述
   - 编写 `enrich_products.py` 更新脚本
   - 包含：3+ 产品图片、HTML 描述、规格表、使用场景、售后条款
   - 执行 `PUT /products/{id}.json`

### 流程 B：单个商品上架

**用户说**："把这个商品上架到 Shopline"（附带 1688 链接或商品信息）

直接跳到步骤 3-4，不需要搜索和评分。

### 流程 C：店铺管理

```bash
# 列出商品
python ecommerce/scripts/shopline_api.py products list --limit 20

# 查看数量
python ecommerce/scripts/shopline_api.py products count

# 更新商品
python ecommerce/scripts/shopline_api.py products update <id> '<json>'

# 删除商品
python ecommerce/scripts/shopline_api.py products delete <id>

# 订单列表
python ecommerce/scripts/shopline_api.py orders list
```

## Shopline API 参考

### 端点格式
```
https://{handle}.myshopline.com/admin/openapi/v20260601/
```

### 关键 API
| 操作 | 方法 | 路径 |
|------|------|------|
| 商品列表 | GET | `product_listings.json?limit=50` |
| 商品数量 | GET | `products/count.json` |
| 创建商品 | POST | `products/products.json` |
| 商品详情 | GET | `products/{id}.json` |
| 更新商品 | PUT | `products/{id}.json` |
| 删除商品 | DELETE | `products/{id}.json` |
| 订单列表 | GET | `orders.json?limit=50` |
| 订单详情 | GET | `orders/{id}.json` |

### 认证
```
Authorization: Bearer {SHOPLINE_API_TOKEN}
Content-Type: application/json; charset=utf-8
```

### 商品 JSON 格式
```json
{
  "product": {
    "title": "Product Name",
    "body_html": "<p>Description</p>",
    "vendor": "1688 Supplier",
    "product_type": "Category",
    "tags": ["tag1", "tag2"],
    "status": "active",
    "images": [{"src": "https://image.url"}],
    "variants": [{
      "price": "19.99",
      "sku": "SKU-001",
      "inventory_tracker": true,
      "weight": "250",
      "weight_unit": "g"
    }]
  }
}
```

## 选品评分模型

### 评分公式
```
S = 0.20×T + 0.25×D + 0.20×C + 0.15×R + 0.20×P
```

| 维度 | 权重 | 说明 |
|------|------|------|
| T (热度) | 20% | 搜索量 + 趋势 + TikTok热度 |
| D (竞争比) | 25% | 搜索量/在售数 + 竞品评价门槛 |
| C (成本) | 20% | 1688成本 + 物流 + 平台费率 |
| R (风险) | 15% | 品牌侵权/认证/电池/食品/供应商年限 |
| P (利润) | 20% | 预估利润 + 利润率 |

### 跨境物流估算
| 方式 | 首重 | 续重/kg | 时效 |
|------|------|---------|------|
| ePacket | ¥15 | ¥50 | 7-12天 |
| 云途 | ¥25 | ¥45 | 5-10天 |
| 递四方 | ¥20 | ¥48 | 6-10天 |
| 海运 | ¥8 | ¥15 | 20-30天 |

### 利润估算
- 1688 成本 (RMB) + 物流 (RMB) → 总成本 (RMB)
- 总成本 ÷ 7.2 → USD 成本
- 定价 × (1 - 5% 平台+支付费) - USD 成本 - $2 广告 → 净利润

## 定价规则

默认：1688 成本(RMB) ÷ 7.2 × 3 = USD 售价
- 轻小件 (<200g)：×2.5
- 标准件 (200-500g)：×3.0
- 重货 (>500g)：×3.5

### 流程 D：订单代发（一键直发）

**用户说**："查看新订单" / "生成采购清单" / "录入物流" / "同步物流到 Shopline"

**执行步骤**：

1. **建立商品映射**（首次使用）：
   ```bash
   python ecommerce/scripts/fulfillment.py mapping set <product_id> <1688_url> <cost_rmb> --supplier "供应商名" --sku "SKU"
   python ecommerce/scripts/fulfillment.py mapping list   # 查看所有映射
   ```

2. **查看待发货订单**：
   ```bash
   python ecommerce/scripts/fulfillment.py orders pending
   python ecommerce/scripts/fulfillment.py orders info <order_id>
   ```

3. **生成 1688 采购清单**（核心步骤）：
   ```bash
   python ecommerce/scripts/fulfillment.py fulfill sheet <order_id> --mark
   # 或批量生成所有待发货订单的采购清单：
   python ecommerce/scripts/fulfillment.py fulfill batch --mark
   ```
   输出包含：1688 链接、规格、数量、单价、小计、客户地址。
   `--mark` 将订单状态写入 `data/fulfillment_log.json`。

4. **用户在 1688 手动下单** → 等待供应商发货 → 拿到物流单号

5. **录入物流单号**：
   ```bash
   python ecommerce/scripts/fulfillment.py tracking add <order_id> <tracking_number> --carrier yunexpress
   ```

6. **推送到 Shopline**（创建履约 + 通知买家）：
   ```bash
   python ecommerce/scripts/fulfillment.py tracking sync <order_id> --notify
   ```

7. **监控新订单**（后台轮询）：
   ```bash
   python ecommerce/scripts/fulfillment.py watch start --interval 5   # 每5分钟检查
   python ecommerce/scripts/fulfillment.py watch start --once         # 只检查一次
   ```

8. **查看全局状态**：
   ```bash
   python ecommerce/scripts/fulfillment.py status
   ```

**代发状态机**：`pending_purchase → purchased → tracking_received → synced`

**数据文件**：
- `ecommerce/data/product_mapping.json` — Shopline 商品 → 1688 货源映射
- `ecommerce/data/fulfillment_log.json` — 所有订单的代发记录

**物流商名称映射**（用户输入→API值）：云途→YunExpress、递四方→4PX、燕文→Yanwen、菜鸟→Cainiao、e邮宝→ePacket、顺丰→SF-Express 等。

## 注意事项

1. **1688 搜品**：Apify 1688 Scraper 成功率为 ~31%，失败时改为手动 1688 浏览 → 复制链接 → 让用户提供商品信息
2. **图片来源**：使用 Unsplash 免费图片作为占位图，用户应替换为真实 1688 产品图
3. **描述语言**：目标市场为海外 → 全部英文
4. **风控**：Shopline REST API 有速率限制，批量操作时每次间隔 1 秒
5. **Tag 格式**：更新商品时 `tags` 必须是数组 `["tag1","tag2"]`，非逗号分隔字符串
