# MyAlpha Prediction Ledger V1 — 设计规格

状态：**APPROVED FOR V6.10 IMPLEMENTATION**  
本规格定义 V6.10 Prediction Ledger 的唯一第一版口径。V6.9.x 只冻结设计，不生成伪历史预测，不回填事后“预测”。

## 1. 目标

Prediction Ledger 只回答一件事：

> MyAlpha 在不知道未来结果时，当时明确产生了什么可证伪判断，后来结果如何？

它与 Historical Journal 分工不同：

- Historical Journal：历史先验与相似情境。
- Prediction Ledger：真实前瞻预测成绩。
- Replay Ledger：严格 walk-forward 的历史外样本回放；必须与前瞻账本物理分离。
- Decision Journal：用户实际是否采纳建议；不得写入公开预测账本。

## 2. V1 哪些事件允许入账

V1 **只记录机器可重复、可证伪的状态进入事件**，不记录自由文本研究观点。

允许：
- Trend Pulse 状态/阶段进入事件。
- Breadth Intelligence 状态翻转。
- Cross-Asset Divergence 状态翻转。
- Regime Combination 状态翻转。

暂不允许：
- 自由文本 Autonomous Research 结论。
- 无明确规则的博客观点。
- 私有持仓/期权操作。
- 人工事后挑选的“看起来重要”事件。

外部方法只有在转成明确的 machine-testable rule 后，才可获得 method_id 并进入后续版本账本。

## 3. 事件触发口径

采用 **state-entry event**，不是每日快照。

默认沿用 Historical Journal 的状态进入/冷却思想：
- 仅状态首次进入或满足重新进入条件时生成 prediction。
- 同一 symbol + signal_id + state_id 在冷却期内不重复记账。
- 默认冷却：10 个交易日；具体信号可在规则注册表中覆盖。
- 同一交易日多次 workflow 运行不得重复产生同一 prediction_id。

目的：避免重叠窗口把名义样本膨胀成虚假独立样本。

## 4. 不可变预测记录字段

每个 prediction 必须在事件产生当时冻结以下字段：

### Identity
- schema_version
- prediction_id
- created_at_utc
- market_date
- symbol / scope
- signal_id
- method_id（若有）
- state_id
- regime_id

### Frozen rule
- rule_version
- rule_hash
- app_version
- git_commit_sha

### Forecast
- forecast_type
- direction: bullish / bearish / neutral
- probability（只有模型确实能输出经定义概率时才填写；不得用“置信度标签”伪造概率）
- benchmark
- horizons: 5 / 20 / 60 / 120 trading days
- baseline_close
- next_open（后续可获得时作为执行近似口径补充，不覆盖 baseline_close）

### Evidence snapshot
- supporting_evidence_ids
- counter_evidence_ids
- unknowns
- source_snapshot_hash

### Minimum data lineage
对所有参与该 prediction 的关键数据至少冻结：
- source
- as_of
- freshness: fresh / cached / delayed / failed
- used_in_decision
- confirmed_by（若有）

**只有满足账本 eligibility 的数据才允许创建正式 prediction。** 缓存数据可作为上下文，但默认不得产生新的正式预测记录。

## 5. 价格与收益口径

为保证与 Historical Journal 可比：

主统计口径：
- signal-day close → horizon close

执行近似口径：
- next-trading-day open → horizon close

两套结果必须分开存放，不相互覆盖。

基准：
- 个股默认 QQQ，同时保留 absolute return。
- Broad-market / breadth / regime 类信号默认 SPY。
- benchmark 必须在 prediction 创建时冻结。

## 6. Outcome 规则

预测记录本身 append-only，不允许覆盖历史字段。

成熟结果以独立 outcome event 追加，引用 prediction_id：
- horizon
- maturity_date
- exit_price
- absolute_return
- benchmark_return
- excess_return
- MAE
- MFE
- directional_hit
- brier_score（仅 probability 合法存在时）
- scorer_version
- scored_at
- source/as_of

5/20/60/120 日各自独立成熟。

禁止：
- 未到期提前记“成功”。
- 因未来结果修改原 prediction。
- 将 Replay 结果写入 Forward Ledger。

## 7. 文件与持久化

Forward Ledger：
- ledger/forward/YYYY-MM.jsonl

Outcome：
- ledger/outcomes/YYYY-MM.jsonl

Replay：
- ledger/replay/...（独立目录，绝不与 forward 混合）

按月分片，避免单文件无限增长。

Prediction Ledger 是不可再生资产，不放在 docs 生成目录中。站点只读取派生摘要，不直接编辑账本。

## 8. 哈希链与外部锚点

每条记录包含：
- prev_hash
- record_hash

record_hash 基于 canonical JSON + prev_hash。

哈希链主要防止无意修改；不能单独抵御有写权限者整体重写。

因此 V1 同时要求：
- 每日链头 hash 写入自动提交信息或独立 manifest。
- 每周生成 Release/不可变快照锚点。
- Telegram 外部锚点可作为后续增强，不作为 V1 启动硬依赖。

## 9. Failure isolation

Ledger 是关键学习资产，但不能让站点因账本写入故障而完全停止更新。

规则：
- Ledger append/verify 失败 → System Status 红灯 + Autonomous QA FAIL。
- Daily 页面构建可继续，但不得生成新的“学习成功/准确率提升”结论。
- 账本异常期间 Prediction creation 必须暂停。
- 禁止自动重建或覆盖损坏账本。

## 10. 第一版评分

第一版必须至少报告：
- raw_n
- matured_n
- directional hit rate
- unconditional baseline hit rate
- lift vs unconditional baseline
- average absolute return
- average excess return vs benchmark
- MAE / MFE

若存在合法 probability：
- Brier Score
- calibration buckets

不能只显示命中率。

## 11. 统计诚实度

V6.11 延伸，但 V1 预留字段：

- raw_n != effective_n
- 同一 signal-date 的同板块相关标的不得被误认为完全独立。
- 未来 effective_n 应按时间窗口与行业/板块聚类估算。
- 当前 S&P 500 constituent 文件只能作为“当前成分股对照”，不能宣称消除幸存者偏差。

## 12. Shadow Challenger

V6.12 才启用预测型 Challenger。

必须：
- challenger 规则先注册并冻结 rule_hash。
- Production 与 Challenger 对相同事件同时产生预测。
- 同时活跃 challenger 原则上 <= 3。
- 晋升比较使用配对差异，不用各自独立胜率。
- 看前瞻表现、风险/MAE、有效独立样本，不看 workflow 次数。
- 达到门槛仍需 human_review_required。
- 必须同时定义降权/退役规则。

## 13. Shadow 计数口径（V6.9.x 已先修正）

区分：
- workflow_runs：引擎执行次数，仅用于运维。
- shadow_market_days：候选存在过的不同市场日数量。
- shadow_predictions：未来预测型候选产生的独立预测数。
- shadow_matured_predictions：已成熟预测数。

Promotion Gate 不再把同一市场日重复 workflow 当作独立 Shadow 证据。

## 14. Data Confidence Decay

P4 不需要在 V6.10 做复杂指数函数。

Ledger V1 只冻结 lineage/freshness。

后续盘中 UI/期权建议可按事件环境设置离散 TTL：
- normal
- event
- high-volatility

日线账本本身以已完成交易日数据为主，不被盘中 15–30 分钟 TTL 混淆。

## 15. 明确不在 V6.10 做的事

- 不自动下单。
- 不自动改变 position size。
- 不自动改变 core allocation。
- 不自动改变 Hard Exit。
- 不直接建立完整 Shadow Portfolio。
- 不自动根据少量样本改变 Production 权重。
- 不把自由文本观点强行转换成概率。
- 不回填“历史上系统本来会预测什么”到 Forward Ledger。

---

## V6.10 Definition of Done

只有同时满足以下条件才算完成：

1. Forward Ledger append-only + hash chain。
2. 状态进入事件去重/冷却。
3. rule_hash + commit SHA + schema_version。
4. minimum data lineage。
5. 5/20/60/120 outcome maturation。
6. Forward 与 Replay 物理隔离。
7. baseline/lift + MAE/MFE；概率存在时才计算 Brier/Calibration。
8. Ledger verify 测试与损坏检测。
9. failure isolation。
10. Daily / Autonomous QA 接入。
11. 不改变任何正式交易规则。
