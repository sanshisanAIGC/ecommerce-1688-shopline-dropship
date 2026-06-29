# 路线 A：纯国内电商链路 启动指南

## 技术架构

```
1688 跨境专供（选品源）
    │
    ├── Apify 1688 Scraper MCP (搜品/比价)
    │   或手动浏览 1688.com 复制链接
    │
    ▼
Claude Code + 选品评分模型
    │
    ▼
Shopline MCP (143 工具，开店/上架/订单/库存全管)
    │
    ▼
客户下单 → 1688 一键代发 (DSFulfill / 手动)
```

**全程不需要外网访问。**

---

## 第一步：注册账号（浏览器完成，5 分钟）

### 1. Shopline 开店
- [ ] 访问 https://www.shopline.cn （中国站，直接访问）
- [ ] 注册，14 天免费试用
- [ ] 创建店铺，选一个品类模板

### 2. 获取 Shopline API Token
- [ ] 登录 Shopline 后台 → 设置 → API 管理
- [ ] 创建 API Token，权限勾选：商品读写、订单读写、库存读写
- [ ] 复制 Token 备用

### 3. Apify 账号（用于 1688 搜品自动化）
- [ ] 访问 https://console.apify.com （国内可访问）
- [ ] 注册免费账号（每月 $5 免费额度，够搜几千商品）
- [ ] 设置 → Integrations → 复制 API Token

### 4. 1688 账号（手动备选）
- [ ] 访问 https://www.1688.com
- [ ] 注册（淘宝/支付宝直接登录）
- [ ] 不需要开店，买家身份即可

---

## 第二步：配置环境变量

在你终端中设置（或加到 `~/.bashrc`）：

```bash
export SHOPLINE_API_TOKEN="你的Shopline Token"
export APIFY_TOKEN="你的Apify Token"
```

---

## 第三步：验证 MCP 环境

重启 Claude Code 后，确认 MCP 加载：

```
/mcp
```

应该看到 `shopline` (143 工具) 和 `1688-scraper` (1688 搜品工具)。

---

## 第四步：第一条链路

在 Claude Code 中说：

> "用 1688-scraper 搜「便携露营灯」跨境专供商品，价格 5-30 元，支持一件代发。找 5 个评分最高的，评估跨境利润（Shopline 卖 $15-25），推荐 2 个最好的。"

AI 会调用 1688 MCP 搜品 → 拉数据 → 评估 → 推荐。

确认后：

> "把这两个商品通过 shopline MCP 上架到我的 Shopline 店铺，标题做英文 SEO 优化，描述翻译成英文，定价 $19.99。"

---

## 第五步：代发配置

注册 DSFulfill（https://dsfulfill.cn，国内平台）：
- 绑定 1688 账号
- 绑定 Shopline 店铺
- 配置自动采购规则：客户下单 → DSFulfill 自动向 1688 下单 → 供应商直发客户

---

## 成本预估

| 项目 | 月费 |
|------|------|
| Claude Code | $20（¥140） |
| Shopline | ¥0（14 天试用）→ ¥199/月（基础版） |
| Apify | $0（免费层够用） |
| 1688 | ¥0（买家账号） |
| DSFulfill | ¥0（基础功能免费） |
| **合计** | **¥140-339/月** |

对比：跨境运营月薪 ¥8,000-15,000
