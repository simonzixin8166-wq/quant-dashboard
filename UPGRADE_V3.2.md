# myAlphaView V3.2 完整升级说明

V3.2 将期权模块改为“券商账户 → 正股/期权仓位 → 盈亏与展期纪律”的分层结构，并修复美股指数盘中涨跌幅可能被错误基准覆盖的问题。

## 本次完成内容

- 同一股票按券商账户隔离；一个账户的正股不能覆盖另一账户的 Call。
- 统一录入 Sell Put、Covered/Naked Call、Buy Call、Buy Put，账户为必填项。
- 期权持仓压缩为 9 列，明确每股成交价、Bid/Ask/Mid、整仓盈亏、Delta/IV、有效价和风险。
- Covered Call 使用 Roll Up；Sell Put 使用独立阈值的 Roll Down & Out。
- Sell Put 区分“愿意接货”和“避免指派”，不会把 `|Delta|=0.70/0.80` 当成所有 Put 的机械展期命令。
- 支持部分展期，例如 6 张只展期 2 张；旧仓剩余张数和费用按比例保留。
- 回填旧 Short 仓累计净权利金，修复展期卡片显示 `$0.00/股`。
- 修复纳指/标普盘中涨跌幅基准：必须使用上一交易日正式收盘，不再使用 Yahoo 5 日区间的 `chartPreviousClose`。

## 部署顺序（必须按顺序）

1. 在 GitHub 网页上传并覆盖压缩包内全部文件，提交到 `main`。
2. 打开 Supabase → SQL Editor，完整执行：
   `supabase/migrations/202609240001_multi_account_options.sql`
3. 打开 GitHub → Actions，确认 **Deploy Supabase Functions** 已自动运行且为绿色。该工作流需要仓库 Secrets：`SUPABASE_ACCESS_TOKEN` 与 `SUPABASE_PROJECT_REF`。若未配置，需在 Supabase CLI/控制台手工部署 `market-snapshot`。
   
   不完成此步时，前端会保留正确的收盘日线涨跌幅，但不会采用盘中涨跌幅。
4. 在 GitHub → Actions 手动运行 **Daily Dashboard Update**，等待绿色完成。
5. 浏览器执行强制刷新（Windows: `Ctrl+F5`；Mac: `Cmd+Shift+R`）。

## 首次使用

1. 登录私有看板，进入“期权持仓与风险监控 V3.2”。
2. 点击“账户管理”，只填写安全别名，例如“IBKR主账户”“Tradier账户”；不要填写登录密码或完整账户号码。
3. 升级前数据会自动归入“待分配账户”。
4. 对每笔旧期权点击“管理”→选择真实账户→“只更新账户”。
5. 对每个旧正股计划点击“编辑”，指定真实账户并保存。
6. 此后所有新期权成交必须选择账户；Covered Call 会校验该账户未被占用的正股数量。

## 数据口径

- Short 平仓估值优先使用 Ask；Long 平仓估值优先使用 Bid。
- 浮动盈亏按 `每股价差 × 合约乘数 × 张数 − 已录费用` 计算。
- 页面行情为免费延迟/参考行情，真正下单与展期仍以券商组合单 Bid/Ask 和实际成交价为准。
- 盘中 Delta 仅参考；展期纪律默认使用手工确认的收盘 Delta。
- Sell Put 是否展期还取决于接货意愿、现金覆盖、DTE、事件风险与价差，而不是单独依赖 Delta。

## 回退与数据安全

- 迁移只新增账户字段、账户表和 V3.2 展期函数，不删除现有期权记录。
- 旧记录先进入“待分配账户”，不会与新账户自动猜测合并。
- 上传前建议保留上一版完整 ZIP；如页面部署失败，可恢复前端文件，但已执行的新增数据库字段无需删除。
