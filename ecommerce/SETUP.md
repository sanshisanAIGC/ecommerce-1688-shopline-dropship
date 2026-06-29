# 跨境电商 AI Agent 启动清单

## 第一步：注册账号（需要你手动在浏览器完成）

### 1. Shopify 店铺
- [ ] 访问 https://www.shopify.com/signup
- [ ] 注册，选 14 天免费试用
- [ ] 店铺名建议：一个通用好记的英文名（后续可改）
- [ ] 不需要立即选套餐，试用期内足够跑通全流程

### 2. DSers 账号
- [ ] 访问 https://www.dsers.com
- [ ] 注册免费账号
- [ ] 在 DSers 后台绑定你的 Shopify 店铺
- [ ] 安装 DSers Chrome 扩展（可选，方便单商品导入）

### 3. AliExpress 账号
- [ ] 访问 https://www.aliexpress.com
- [ ] 注册免费账号
- [ ] 不需要卖家身份，买家账号即可

---

## 第二步：配置 Claude Code（你需要在 Claude Code 中逐条运行）

### A. 安装 Shopify AI Toolkit 插件
在 Claude Code 对话中依次输入：

```
/plugin marketplace add Shopify/shopify-ai-toolkit
```

```
/plugin install shopify-plugin@shopify-ai-toolkit
```

安装后重启 Claude Code。

### B. DSers MCP 首次登录
在 Claude Code 对话中输入：

```
请帮我在终端运行: npx @lofder/dsers-mcp-product login
```

这会打开浏览器跳转到 DSers 官方授权页面，授权后自动保存 session。

### C. 验证环境
重启 Claude Code 后，输入：

```
/mcp
```

确认能看到 `dsers` 和 `shopify-dev`（以及 shopify 插件工具）。

---

## 第三步：第一条商品导入链路

在 Claude Code 中直接说：

> "用 DSers MCP 在 AliExpress 上搜索「portable LED camping lantern」，找评分 4.5+、价格 $3-8、有美国仓的商品。找到后选评分最高的 3 个，分别评估利润率（按 2.5 倍定价），然后告诉我推荐哪个。"

Claude Code 会自动调用 DSers MCP 的搜索工具 → 拉取商品数据 → 分析 → 给你推荐。

你确认后说：

> "把推荐的那个导入到我的 Shopify 草稿，标题做 SEO 优化，定价按 2.5 倍成本。"

---

## 第四步：规模化流程

确认第一条链路跑通后，用项目目录下的选品评分模型批量操作：

```bash
# 批量评分
echo '[{"name":"商品A","cost_price":5,"sell_price":24.99,...},...]' | python ecommerce/scripts/product_scorer.py --batch
```

---

## 成本预估

| 项目 | 月费 |
|------|------|
| Claude Code Pro | $20 |
| Shopify 试用 | $0（前14天） |
| Shopify 正式 | $39/月（Basic） |
| DSers | $0（免费套餐 3000 商品） |
| **合计** | **$20-59/月** |

对比：一个跨境电商运营月薪 $1000+
