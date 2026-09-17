# 期权决策台 V2.0 配置

## 已完成

- 所有金额统一按 `合约张数 × 合约乘数（默认100）` 计算。
- 支持目标日期、目标股价和 IV 相对变化的提前平仓估值。
- 到期盈亏与目标日期理论价值分开显示。
- 支持 Sell Put、Buy Put、Buy Call、Covered Call、Naked Call。
- 到期日、行权价、Bid/Mid/Ask、IV、Greeks 可由期权链选择并自动填入。
- 无行情密钥时仍可使用手动报价模式。
- 真实持仓不再写入公开的 `docs/data.json` 和 `docs/index.html`，登录后再读取 Supabase。

## 部署实时接口

1. 在 MarketData.app 创建 API Token。开发阶段可用免费计划，盘中决策必须使用实时期权计划。
2. 安装并登录 Supabase CLI。
3. 在项目根目录执行：

```bash
supabase secrets set MARKETDATA_API_TOKEN=你的Token
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
- 已选合约：美股盘中每30秒更新一次。
- 标普500、纳斯达克综合与VIX：`market-snapshot` 每30秒读取一次分钟行情；失败时只显示明确标注的 SPY/QQQ/VIXY 实时代理，不把代理价格冒充指数。
- 全市场宽度：必须基于完整收盘日线，每个美股交易日收盘后更新；盘中沿用上一收盘日结果。
- Edge Function 对相同请求缓存15秒。
- API Token只存在Supabase Secret中，不得写入HTML或GitHub仓库。

## 估值说明

目标日期估值采用 Black-Scholes 作为情景推演模型。美股个股期权通常为美式期权，因此结果是估算值，不能替代实际 Bid/Ask。Short仓位实际平仓成本应重点参考 Ask，Long仓位平仓价值应重点参考 Bid。

## 只用 GitHub Actions 部署 Edge Functions

GitHub 仓库 Settings → Secrets and variables → Actions 中增加：

- `SUPABASE_ACCESS_TOKEN`：Supabase Account Access Token。
- `SUPABASE_PROJECT_REF`：当前项目 ref，本项目为 `rhielbkvhgqbthcgztci`。

然后运行 `Deploy Supabase Functions` Action。日常数据仍运行 `Daily Dashboard Update`；两者职责不同。
