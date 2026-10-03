# V3.1 一次性升级：期权展期管理

## 更新顺序

1. 用本压缩包完整覆盖 GitHub 仓库根目录并提交。
2. 在 Supabase Dashboard → SQL Editor 打开并执行：
   `supabase/migrations/202609230001_option_roll_manager.sql`
3. 打开 GitHub Actions，手动运行 `Daily Dashboard Update`。
4. Actions 成功后，浏览器强制刷新网站。

SQL 迁移只需执行一次，使用 `if not exists`，重复执行不会重复建表。

## IREN 初始化

1. 登录私有看板，进入“期权持仓与风险监控”。
2. 在“Covered Call / Sell Put 展期管理”点击“载入IREN示例”。
3. 核对：600股、成本51、Covered Call观察/紧急Delta 0.70/0.80、Sell Put观察/紧急绝对Delta 0.50/0.70、接货偏好和两档减仓计划，然后保存。
4. 点击“为IREN录入Covered Call”，按IBKR真实成交填写：Sell Call、65、12/18、3.85、3张、乘数100、Covered。
5. 每次收盘后从IBKR录入Delta；盘中数字请选择“盘中Delta”，系统不会据此触发收盘纪律。

## 展期记账

- Covered Call：新行权价通常向上，工具显示有效卖出价。
- Sell Put：新行权价通常向下并延后到期，工具显示有效接货成本。
- 先在IBKR用组合单成交，再点击“确认IBKR已成交并记账”。
- 系统会在同一数据库事务中关闭旧仓、建立新仓、写入净收/付和完整展期链。

V3.1只支持整笔展期。若计划分批Roll，请从首次建仓开始拆成多笔持仓，以免一笔记录同时表示多个不同合约。
