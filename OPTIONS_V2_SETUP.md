# myAlphaView V2.3 · Alpaca 配置

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

## 第一次升级必须执行：期权持仓权限

仅把代码上传到 GitHub 不会自动执行 Supabase 数据库迁移。请打开 Supabase Dashboard → SQL Editor，复制并执行项目根目录的：

`SUPABASE_FIX_OPTIONS.sql`

看到最后查询返回已有持仓后，再回网页刷新。之后新增持仓会在保存时立即读回验证，不再显示临时假行。

## 必须检查的数据库安全设置

项目已经提供迁移文件：

`supabase/migrations/202609170001_options_private.sql`

执行：

```bash
supabase db push
```

迁移会启用 RLS、增加 `user_id`，并把已有持仓归属给当前管理员邮箱对应的用户。不要只依靠前端邮箱判断权限。

## 数据刷新规则

- 完整期权链：仅在选择股票、到期日或 Call/Put 时请求。
- 已选合约：页面每15分钟刷新，浏览器缓存1分钟；完整期权链缓存10分钟。
- 标普500、纳斯达克综合与VIX：`market-snapshot` 每30秒读取一次分钟行情；失败时只显示明确标注的 SPY/QQQ/VIXY 实时代理，不把代理价格冒充指数。
- 全市场宽度：必须基于完整收盘日线，每个美股交易日收盘后更新；盘中沿用上一收盘日结果。
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
