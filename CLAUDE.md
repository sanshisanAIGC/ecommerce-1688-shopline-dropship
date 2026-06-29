# 电商 AI Agent — 路线 A（纯国内链路）

## Skill

项目 skill 已配置：`.claude/skills/ecommerce-dropship/SKILL.md`

触发词：选品、上架、1688、Shopline、跨境电商、代发、dropshipping + 品类词。

详细工作流、API 参考、评分模型说明均在 skill 文件中。

## 当前店铺

- **URL**: https://sanshisan.myshopline.com
- **商品数**: 3（USB LED Lantern / 复古煤油灯 / 太阳能露营灯）
- **API**: `https://sanshisan.myshopline.com/admin/openapi/v20260601/`

## 使用

```bash
# 启动前加载环境变量
source ecommerce/.env

# 全链路：搜品 → 评分 → 上架
python ecommerce/scripts/search_and_score.py

# 店铺管理
python ecommerce/scripts/shopline_api.py products list
python ecommerce/scripts/shopline_api.py products create '<json>'
python ecommerce/scripts/shopline_api.py products count
python ecommerce/scripts/shopline_api.py orders list
python ecommerce/scripts/shopline_api.py orders list --fulfillment-status unshipped

# 选品评分（独立使用）
python ecommerce/scripts/product_scorer_1688.py --batch < products.json

# 产品图片更新（用 1688 真实产品图替换占位图）
python ecommerce/scripts/update_product_images.py <product_id> <url1> [url2 ...]
python ecommerce/scripts/update_product_images.py <product_id> --from-file urls.txt

# 订单代发（一键直发）
python ecommerce/scripts/fulfillment.py mapping set <pid> <1688_url> <cost_rmb>
python ecommerce/scripts/fulfillment.py orders pending
python ecommerce/scripts/fulfillment.py fulfill sheet <order_id> --mark
python ecommerce/scripts/fulfillment.py tracking add <order_id> <tracking_no> --carrier yunexpress
python ecommerce/scripts/fulfillment.py tracking sync <order_id> --notify
python ecommerce/scripts/fulfillment.py status
python ecommerce/scripts/fulfillment.py watch start --interval 5
```
