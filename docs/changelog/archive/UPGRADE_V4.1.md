# V4.1 · Website-first 研究首页

本轮冻结 PWA / 移动端功能扩展，网站继续作为主产品。

## 首页信息架构

- 市场核心指标由 4 张同质化大卡片改为轻量 Market Tape。
- 新增“市场简报”：按 VIX、SPX 回撤、Breadth、核心 ETF 距一级阈值自动生成，不接大模型 API。
- 新增“今日变化”：比较上一份 `docs/data.json` 快照，展示 VIX、SPX 回撤、20 日宽度、QLD/TQQQ 回撤变化。
- 新增 `IREN Daily Brief`：固定展示 IREN 日涨跌、YTD 高点回撤、RSI、200MA 距离、策略参考价关系。
- IREN 新闻通过 Yahoo Finance Search 公共接口尝试抓取最近 72 小时消息；失败不会阻塞主页面构建。
- 新闻仅做标题关键词的“偏利好 / 偏利空 / 中性”快速筛选，页面明确提示它不是基本面结论。

## 视觉调整

- 首页改成“结论 → 变化 → IREN 重点观察 → 市场状态 → 策略/明细”的研究简报结构。
- 新模块使用平面分区、细分隔线和研究笔记式排版，减少所有内容都套白色圆角卡片的 SaaS 模板感。
- 保留现有品牌色、Logo、桌面侧栏、Market Regime、策略阈值和已验证的功能模块。
- 策略面板移除 `STRATEGY ENGINE ·` 英文眉题，仅保留“核心ETF三档加仓线”。

## PWA 策略

- `APP_VERSION / ASSET_VERSION` 保持 4.0.0，本轮不推动 PWA 功能版本。
- 不修改 `mobile-shell.js / pwa.js / sw.js / manifest.webmanifest`。
- 已有 PWA 能力保留，但后续开发优先级低于网站研究体验。

## 数据与隐私

- IREN 只作为公开研究标的，不展示真实持仓数量、成本或账户资产。
- IREN 即使不在 Supabase 观察池中，也会被固定加入研究抓取列表，以保证 Daily Brief 每日可生成。
- 真实期权和账户数据继续由 Supabase RLS 保护，不写入公开 `data.json`。
