# MyAlpha 全站数据→学习闭环审计主报告
日期：2026-10-07
官方产品版本：V6.9.0（本审计不改变 APP_VERSION）

## 1. 审计原则
完整学习闭环：Capture → Persistent Archive → Structured Understanding → Reusable Memory → Outcome → Evaluation → Reuse。
永久存储与学习输入不得按记录数淘汰；UI 展示和单次批处理可以有限，但必须与 Canonical Archive / Learning Store 分离；未处理数据必须有 backlog/cursor。

统一状态：Learning Active / Partial Learning / Context Only / Display Only / Not Implemented / Intentionally Static。

## 2. 当前全站矩阵

### Learning Active
- 市场价格历史 / STOOQ / Trend Pulse：本地历史、状态进入、5/20/60/120、MAE/MFE、QQQ 相对结果均存在；recent_events 仅用于展示，聚合使用完整事件集合。
- Production Playbook Forward / Replay：Forward state transition 写入私有 ledger；Outcome 读取真实 Forward trigger 并验证 baseline；Historical Replay 明确隔离，不混入 Forward。
- 外部作者研究主链：research feed → Source Reading → Method / Candidate / Forward / Family / Promotion 已存在；Historical 与 Genuine Forward 分离。

### Partial Learning
- 博客 / 论坛 / YouTube：内容可以进入 Source Reading，但 intake completeness 仍需 cursor/backlog 证明；尤其论坛固定页数、YouTube latest-N 窗口需要继续整改。
- SEC Official Evidence：有 SEC EDGAR、Auto Thesis、Fundamental Outcome，但当前仍偏最近 filing current view，缺 canonical append-only filing archive。
- 新闻 / Event Evidence：有来源分层、事件归因，但每标的 current news view 不能替代永久 Event Archive。
- Auto Thesis：能由 SEC / Event 构建证据化草稿，但缺 Thesis revision history。
- FRED / ALFRED：有 point-in-time / vintage 处理，并进入 Cross Asset / Regime，但缺 Macro State → Future Outcome 的成熟闭环。
- Breadth / Cross Asset / Regime：已有历史并已去掉 240/300/360 条 destructive cap，但样本仍年轻，尚缺成熟 state→outcome scorecard。
- 私有期权持仓学习：Supabase 有 option_learning_observations / option_learning_outcomes，按状态进入记录，真实 final status 形成 outcome；样本仍少。
- Decision Journal / Operator Decisions：有私有持久化 Schema，但公共仓库无法证明每次建议、执行/不执行都已完整进入结果归因。

### Context Only / Context-heavy
- Support / Resistance / Volume Profile：当前能计算并供 Options Opportunity 使用，但没有 dated observation → touch/bounce/break → MAE/MFE 的长期 Outcome Memory。
- GARCH / RV：能计算 RV20/RV60 和 GARCH 20-session forecast，但没有 forecast snapshot → future realized vol → error/bias 的学习。
- Options Opportunity：有研究筛选，LITE/NVDA 已设 SELL PUT primary research preference，但尚缺完整 IV Rank/Percentile、Skew、Term Structure 与 opportunity outcome memory。
- Range Intelligence：明确是 descriptive decision context，不写 Forward Ledger，不改 Production；作为 Context Only 属于正确设计。

### Not Implemented / 重大缺口
- Structured Fundamental Learning / SEC XBRL CompanyFacts：未发现完整 Revenue、Margin、EPS、FCF、Cash、Debt、SBC、Shares Outstanding、Dilution、CapEx、Guidance、Backlog/RPO 的 longitudinal Company Fundamental Memory。
- Canonical Event Archive：当前 Event Evidence 主要是 current snapshot。
- Thesis Revision Memory：缺少不可覆盖的 Thesis 历史版本与变更原因。
- Support/Volatility Outcome Memory：缺支撑命中/跌破与 GARCH forecast error 的长期 ledger。

## 3. 已发现并修复的 Retention 问题
- wxc-bot MAX_FEED=1200 destructive cap：已去除。
- Source Reading 800 条学习上限：已去除。
- Source Outcome 只读取有限 operation_cases：已改为完整 source stream。
- Method Memory 只读取 presentation records：已改为完整 source stream。
- Autonomous Planner queue[:30]：已改为保留完整 backlog。
- 论坛单作者 [:60]：已去除。
- 博客日常 max_articles=40：已去除。
- Cross Asset history 240 条淘汰：已去除。
- Breadth history 300 条淘汰：已去除。
- Regime history 360 条淘汰：已去除。
- Candidate Replay events[:80]：已去除。

UI Top-N、latest-N 可以保留，只要不再被下游 Learning 当成 canonical source。单次 Executor 限量也可以保留，但 backlog 必须持久。

## 4. 仍需重点验证的 Intake Completeness
- Forum：固定 list page 扫描必须升级为 cursor / last-confirmed boundary / partial status / resume。
- Blog：需要证明高频作者和异常恢复期不会因时间窗遗漏。
- YouTube：需要 scan-until-seen-anchor、persistent cursor/backlog；找不到 anchor 时不能宣布 complete；pending transcript 必须持续重试。

## 5. Learning Coverage Contract
1. captured = canonical + duplicate + excluded/error。
2. canonical = processed + explicit_backlog。
3. canonical 记录不得因记录数增长被永久删除。
4. Presentation View 绝不能作为唯一 Learning Source。
5. 每个 continuous learning 模块必须能给出 input / processed / memory / outcome mature / backlog / errors。
6. workflow green 不等于 learning green。
7. captured > processed 且无 backlog/error 解释时，应报 LEARNING_COVERAGE_GAP。

## 6. 下一阶段优先级
### P0 Intake / Retention
- YouTube cursor/backlog
- Forum cursor/backlog
- Blog completeness proof
- Canonical Event Archive
- Canonical SEC Filing Archive

### P1 真正学习缺口
1. SEC XBRL Company Fundamental Memory
2. Event Archive → Event Outcome
3. Thesis Revision Memory
4. Support Observation → Outcome
5. GARCH Forecast → Realized Vol Error
6. Options Opportunity Snapshot → Accept/Reject/No Trade → Outcome

### P2 学习质量深化
- Macro state outcome
- Breadth/Cross Asset/Regime mature scorecards
- author-method contradiction/evolution
- company fundamental vs regime interaction
- option IV Rank/Percentile / skew / term structure history

## 7. Production Boundary
- 不自动修改 TQQQ / Core ETF / LEAPS Production Rule。
- 不自动下单。
- 不把博客/视频结论直接晋升 Production。
- 不用 Historical Replay 冒充 Genuine Forward。
- 不用 GARCH / Support 单一指标生成交易动作。
- 不把 private holdings 写入 public docs。

## 8. Claude 独立复核
Claude 明日应以最新 main 独立验证本报告，不接受本报告结论为既定事实。
输出必须包含 BLOCKER / P1 / P2 / False Learning Claims / Retention Violations / Missing Coverage / Data→Learning Matrix / FINAL=YES|NO。
重点寻找：遗漏的数据域、隐藏 truncation、未被下游消费的 Memory、没有 Outcome 的预测、metadata 与真实实现不一致之处。