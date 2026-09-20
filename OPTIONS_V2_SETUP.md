# myAlphaView V2.5 · Alpaca 与风险驾驶舱配置

## 已完成

- 所有金额统一按 `合约张数 × 合约乘数（默认100）` 计算。
- 支持目标日期、目标股价和 IV 相对变化的提前平仓估值。
- 到期盈亏与目标日期理论价值分开显示。
- 支持 Sell Put、Buy Put、Buy Call、Covered Call、Naked Call。
- 到期日、行权价、Bid/Mid/Ask、IV、Greeks 可由期权链选择并自动填入。
- 无行情密钥时仍可使用手动报价模式。
- 真实持仓不再写入公开的 `docs/data.json` 和 `docs/index.html`，登录后再读取 Supabase。
- 增加理论行权资金、DTE/虚实值/价差联合风险提示，以及官方 FOMC/CPI 日历。
- 增加深色模式、紧凑登录首屏、骨架屏与非阻塞错误提示。
- Cash-Secured Short Put 增加按真实建仓日计算的年化 ROC；旧持仓不猜测日期，显示“待补建仓日期”。
- 核心 ETF 保留各自三档回撤阈值，新增每个资产独立的预留加仓资金（20%/30%/50%）。
- 标普500宽度必须达到至少450只且90%覆盖率；不合格时不参与9分制评分。
- 风险提示统一为 L1（蓝灰）/ L2（琥珀）/ L3（珊瑚红）。
- 暂缓组合 Greeks 与 IV Rank，避免在行情源不稳定或历史 IV 不足时显示误导性精确数字。

## 部署 Alpaca 参考行情接口

1. 在 Alpaca 创建 Trading API（Paper 或 Live）Key。免费 Basic 期权数据为 Indicative Feed：成交可能延迟且报价经过调整，只能作为模拟与监控参考。
2. 安装并登录 Supabase CLI。
3. 在项目根目录执行：

```bash
supabase secrets set ALPACA_API_KEY=你的Key ALPACA_API_SECRET=你的Secret
supabase functions deploy options-market
supabase functions deploy market-snapshot --no-verify-jwt
```

4. 确认 Supabase Auth 与现有网页使用同一个项目。
5. 登录私有看板后进入“策略推演沙盒”，输入股票代码并点击“读取到期日”。

## 第一次升级必须执行：数据库字段与权限

仅把代码上传到 GitHub 不会自动执行 Supabase 数据库迁移。请打开 Supabase Dashboard → SQL Editor，复制并执行项目根目录的：

`SUPABASE_FIX_OPTIONS.sql`

该文件现已同时包含 V2.5 的 `entry_date`、`collateral_mode` 和私有 `strategy_budgets` 表。看到最后查询返回已有持仓后，再回网页刷新。已有持仓可在持仓表点击“补ROC”补录真实建仓日期与担保方式；系统不会用 `opened_at` 猜测。

## 必须检查的数据库安全设置

项目已经提供迁移文件：

`supabase/migrations/202609170001_options_private.sql`、`202609200001_options_lifecycle.sql`、`202609200002_strategy_budgets_and_option_roc.sql`

执行：

```bash
supabase db push
```

迁移会启用 RLS、增加 `user_id`，并把已有持仓归属给当前管理员邮箱对应的用户。不要只依靠前端邮箱判断权限。

## 数据刷新规则

- 完整期权链：仅在选择股票、到期日或 Call/Put 时请求。
- 已选合约：页面每15分钟刷新，浏览器缓存1分钟；完整期权链缓存10分钟。
- 标普500、纳斯达克综合与VIX：`market-snapshot` 每30秒读取一次分钟行情；失败时只显示明确标注的 SPY/QQQ/VIXY 实时代理，不把代理价格冒充指数。
- 全市场宽度：必须基于完整收盘日线，每个美股交易日收盘后更新；至少450只有效成分股、90%覆盖率和211个有效交易日，否则沿用上次成功值且不把残缺样本计分。
- Edge Function 对相同请求缓存15秒。
- API Token只存在Supabase Secret中，不得写入HTML或GitHub仓库。
- GitHub Action 每日从 Federal Reserve 与 BLS 官方来源更新 FOMC/CPI 日历；抓取失败时保留上次成功文件，不生成推测日期。

## Alpaca 数据口径与报错说明

- `401`：通常是 Key/Secret 填错，或 Paper Key 与接口环境不匹配。函数会自动尝试 Paper 与 Live 合约目录。
- `403`：账户没有相应数据权限；不再采用 MarketData 的五分钟封锁逻辑。
- `429`：达到免费层请求频率；页面保留最近一次浏览器缓存并允许手动报价。
- 免费层固定请求 `feed=indicative`，页面不得写成“OPRA实时行情”或“可成交价格”。
- 正股参考价来自 Alpaca Basic 的 IEX Snapshot，不等于全市场综合报价；推演时可手动改成 IBKR 当前正股价。
- Alpaca Option Snapshot 当前不提供可靠的 Open Interest 字段时，页面显示 `—`，不会生成猜测值。
- Short 持仓盈亏优先按 Ask 估算平仓成本；Long 持仓优先按 Bid 估算卖出价值。

## 估值说明

目标日期估值采用 Black-Scholes 作为情景推演模型。美股个股期权通常为美式期权，因此结果是估算值，不能替代实际 Bid/Ask。Short仓位实际平仓成本应重点参考 Ask，Long仓位平仓价值应重点参考 Bid。

## 只用 GitHub Actions 部署 Edge Functions

GitHub 仓库 Settings → Secrets and variables → Actions 中增加：

- `SUPABASE_ACCESS_TOKEN`：Supabase Account Access Token。
- `SUPABASE_PROJECT_REF`：当前项目 ref，本项目为 `rhielbkvhgqbthcgztci`。

然后运行 `Deploy Supabase Functions` Action。日常数据仍运行 `Daily Dashboard Update`；两者职责不同。
