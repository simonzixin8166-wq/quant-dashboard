# V5.1.1 · Assistant Visibility & UI Consistency

- 首页 AI 投资助手在正常行情也显示“正常值守”，并展示最近扫描、四个 Agent 状态和“今天最重要的3件事”。
- 市场进入观察/大跌/极端时仍自动升级为机会/风险扫描，不重复轰炸。
- 观察池顶部数量与动态状态统一使用私有观察池实际条数，修复 21/22 不一致。
- 期权持仓/决策页主版本统一显示 Myalpha View V5.1.1；Options Engine 4.1 作为模块引擎版本小字保留。
- Knowledge 页面版本从 body data-app-version 动态读取，避免继续显示 V4.9.3。
- 不改核心ETF阈值、Trend Pulse 计算、期权估值模型或 Supabase schema。
