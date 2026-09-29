# V5.2.0 · Decision Journal & Validation Engine

## 目标
把 V5.1 的自动扫描从“发现与解释”推进到“记录 → 验证 → 复盘 → 改进排序”，同时保持人工最终决策权。

## 本版变化

### 1. Trend Pulse 统一显示口径
- 所有主要页面使用同一整数显示规则。
- 接近 0 的值显示为 `0`，不再出现 `-0`。
- 内部原始分数不改，只统一展示层。

### 2. AI 提醒直接行动
- 首页“今天最重要的3件事”增加直接入口：研究卡 / 趋势 / 期权决策台。
- 市场触发后的个股候选卡也可以直接进入研究卡、Trend Pulse 或期权方案。

### 3. 减少首页重复
- IREN 首页仅保留价格、关键结论、Trend Pulse摘要与跳转入口。
- 完整趋势证据放到 Trend Pulse；Thesis / 催化剂 / 失效条件放到个股研究卡。

### 4. Agent 扫描状态更透明
- 正常和触发状态都显示最近扫描时间、扫描节奏和下一次预计检查时间。
- 继续保留状态变化提醒，避免每5分钟重复轰炸。

### 5. Decision Journal
新增“决策复盘”页面：
- 自动记录市场级别、VIX、候选个股、当时价格、Trend Pulse阶段与当时判断。
- 本地私有保存，不进入公开站点数据。
- 自动补齐 20 / 60 / 120 个交易日后的标的价格结果。
- 样本少时明确标注，不把少量结果包装成“胜率”。

### 6. 真正的历史自我验证
新增 `scripts/backtest_assistant_rules.py`：
- 使用过去5年 NASDAQ / S&P 500 / VIX / QQQ 数据。
- 按 V5.1 的“观察 / 大跌 / 极端”状态升级规则做事件研究。
- 统计 QQQ 5 / 20 / 60 交易日后表现及20日最大不利波动。
- 只验证“市场提醒后标的表现”，不伪造历史期权权利金、IV、指派或点差结果。

Daily Dashboard Update 会尝试生成：
`docs/research/assistant_rule_validation.json`

### 7. 历史日线接口
`stock-market` Edge Function 新增 `scope=history`，用于 Decision Journal 精确按交易日补齐结果。

## 边界
- AI 可：记录、统计、比较、排序、发现规则在什么环境更稳定。
- AI 不可：自动修改核心ETF回撤阈值、把博主观点直接变成交易规则、自动下单。
- Sell Put 30–45 DTE / Delta 0.16–0.20 仍是经验初筛参数；没有可靠历史期权链时不宣称已完成期权策略回测。

## 部署
1. 完整覆盖当前项目。
2. 运行 `Deploy Supabase Functions`（本版 `stock-market` 新增历史日线接口）。
3. 运行 `Daily Dashboard Update`。
4. 打开“决策复盘”，检查历史规则验证与本地 Journal。
