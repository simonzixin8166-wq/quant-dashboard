# P1 批次 A（首验前，只读 / 测试）· 2026-10-12

依据 #133 6117308392。本批不修改每日自动研究生成器（`daily_research_job.py`）及其时点行为，也不改动定时工作流。
证据文件：
- `research/audit/p1_readiness.json`（`scripts/p1_readiness_audit.py` 生成）
- `research/audit/author_claim_contamination.json`
- `research/audit/module_manifest.json`
- `research/audit/sec_fact_reconciliation.json`

**Learning UNPROVEN / FINAL=NO**。

## 1. B1 历史先例：数据质量与时点审计（结果 → B1 实施规格）

| 项目 | 结果 |
|---|---|
| 来源 | `learning_engine.json` → `situation_memory[].similarity.matches`（5 年因果 Trend Pulse 状态进入事件研究；`historical_journal` 4,559 个事件，60 日已成熟 4,304 个） |
| 匹配总数 | 160（24 个标的） |
| **可用先例** | **84**：已成熟，且 60 日结果窗口在记忆日期之前结束 |
| 排除 | 未成熟 66；非股票类工具（VIX）10 |
| **look-ahead 违规** | **0** |
| 无可用先例的标的 | AMD、AMZN、AVGO、DRAM、HOOD、NBIS、SMH、TSM → B1 对这些标的写 `none`，不强行匹配 |
| 时点 | Daily 中研究步骤（daily.yml 第 169 行附近）**早于** learning_engine_core（第 195 行），因此研究读到的是**上一次提交**的记忆（as_of ≤ market_as_of）。每个先例都必须记录记忆的 `as_of` 和 `sha256` |
| 案例 ID | 记忆没有原生 ID；规则为 `<symbol>:<date>:<stage>`，加上 `historical_journal.json` 的 sha256 |
| 组合环境记忆 | 历史匹配 1，成熟 0 → `insufficient` |
| 方法记忆 | 9 个方法，其中有直接验证事件的：见 json；evidence_role=`legacy_descriptive_only` → 只引用失败示例作为 `error_attribution` 背景，并标注样本量 |

**B1 字段规格**（首验后实施）：
- `precedents[]`：`case_id`、`matched_symbol`、`date`、`stage`、`similarity`、`return_60`、`mae_60`、`outcome_window_closed`、`memory_as_of`、`memory_sha256`、`why_matched`、`supports_or_conflicts`（与当前立场对照）。
- `excluded[]`：每条附 `why_excluded`。
- `error_attribution`：方法记忆中同标的的失败示例，附样本量。
- `experience_input_status`：`used` / `none` / `unknown`。
- `used_in_decision=false`：**经验不改变立场或任何权重**。

**回放示例标的**：MSFT（10 个可用）、ORCL（5 个，当前偏空）、VGT（5 个，核心 ETF）；AMD 作为反例（0 个 → `none`）。

## 2. 六类 Outcome 质量清单（B2 接线依据）

| 记忆 | 观察 | 已成熟结果 | 质量问题 | 结论 |
|---|---|---|---|---|
| company_fundamental_outcome | 703 | 20 日 380 / 60 日 370；无重复键 | **335 个观察受污染**：12 个 NBIS 卢布计价，323 个营收/净利润用 YTD 期间（#203 同源缺陷） | **仅干净子集合格**：20 日 189 / 60 日 186（门槛每个周期 ≥30）；filed 日 = 可得日，结果窗口从申报后开始 |
| event_outcome | 721 | 0 | 归档从 10-06 开始；**222 个事件（31%）的标的不在免费行情库**，永远无法成熟 | pending（最早 5 日成熟：10-13） |
| support_volatility_outcome | 18 | 0 | — | pending（最早 20 日成熟：11-04） |
| options_opportunity_outcome | 32 | 0 | — | pending（最早 5 日成熟：10-14） |
| macro_outcome | 4 | 0 | **成熟计算需要 SPY 日线，规范行情库中没有 SPY** | **blocked**（不修就永远无法成熟） |
| market_state_outcome_scorecards | 历史记录 7 / 5 / 6 | 0 | 同上：依赖 anchor_spy 和 SPY 未来收盘价 | **blocked** |

B2 首批只接财报结果的干净子集，并在每条证据旁注明样本量。其余保持 `disconnected`，原因如上。

**更新（2026-10-12）**：owner 提供了 SPY 历史日线（2005-02-25 至 2026-10-09，5,439 行，已校验，来源记录见 `data/history/spy_provenance.json`），已加入行情库，macro / market_state 两类从 **blocked → pending**。本地试跑中，market_state 已有 4 个 5 日结果成熟。

## 3. B4 SEC 统一：消费者影响图与双跑设计

| 产物 | 生产者 | 消费者（角色） |
|---|---|---|
| `docs/research/sec_fundamentals.json`（新，已带门禁） | sec_fundamentals.py | **daily_research_job（研究）**、weekly_research_report（监控） |
| `docs/research/company_fundamental_memory.json`（旧） | company_fundamental_memory.py | data_learning_coverage_audit、learning_funnel_contract（均为监控） |
| `research/archive/fundamentals/*.jsonl`（旧，append-only） | company_fundamental_memory.py | **company_fundamental_outcome_memory（学习）** → fundamental_observations / outcomes → learning_funnel_contract（监控） |

**双跑设计**（首验后实施，分 3 个 PR）：
1. 统一抓取器（以 sec_fundamentals 为基础）新增 append-only 时点归档 `research/archive/fundamentals_v2/`：
   - 收录所有候选概念，只收 USD；每条带 `period_kind`、`filed`、`accn`、`concept`、`quality_flags`。
   - 覆盖两边并集（补入旧源独有的 CRWV、INTC、META、MU、NOW）。
   - 同时写出旧 schema 的影子文件，用 `sec_fact_reconcile` 每日对比。**旧文件和旧归档不动**。
2. 至少比较 1 个真实交易日：差异全部可分类，旧源缺陷类为预期差异；新源不得有未解释差异。之后用兼容适配器把 `company_fundamental_outcome_memory` 的输入切到 v2；旧观察只追加质量标记，不覆写。
3. 两个监控消费者切换到新产物；旧脚本保留为只读归档。

## 4. Candidate 链：价值与冻结清单（不删除）
当前状态：5 个候选；1 个 machine-ready；4 个需要补定义（参数队列 5 项）；forward-eligible 为 0；下游 EventScore、家族评分、晋升均为 0。
- **保留**：candidate_rule_status、candidate_rule_replay、candidate_parameter_queue（上游；真正的阻塞点是参数定义）。
- **冻结**：candidate_eventscore_status、candidate_family_scorecard_status、candidate_evidence_promotion_status、candidate_forward_status、candidate_rule_family_status。下游阶段目前只产出空结果。冻结 = 停止扩展、周审时跳过；有候选变为 forward-eligible 时解冻。

## 5. #205 跨消费者合同测试
- 新增 `tests/test_author_claim_contract.py`：任何读取作者复盘、失败候选或自有操作的脚本，必须带门禁（legacy 标记、learning_eligible 过滤或"未经核实"标注）。
- **合同测试当场发现 #205 漏掉的一个消费者**：`event_window_attribution.py`（把作者复盘样本与 SEC / 新闻对齐，供执行器失败简报使用）。现已对每行标注 `verification_status` 和 `learning_eligible`；执行器把它们写入 unknowns，注明"未经核实的作者自述样本（仅背景）"。
- 污染审计现在共检查 7 条路径，`all_gated=true`。

## 6. WXC provenance QA（复用 wxc-bot 既有审计结果，不重复扫描）
- `state/provenance_audit.json`（2026-10-12 03:25 UTC）：1,659 条记录，其中 1,226 条没有记录采集方式。按首次 git 出现时间推断：near_publication_observed 339、backfill_proven 864、delayed_capture 23；未发现标为 live 但间隔超过 72 小时的冲突。
- 视频：provider 导航页 17 个（此前为 15 个）、有摘录的 4 个；`source_quality_flags` 排除 17 个。
- 博客连续性：wxc-bot #54 已改为每天采集 + 13:10 UTC 补跑；**新 cron 尚待 schedule 证据**。

## 7. 工作看板（以交易日 / 依赖事件为节点）

| 任务 | 状态 | 节点 / 原因 |
|---|---|---|
| 批次 A（本文件各项） | **Done**（本 PR） | — |
| P0-B 首个真实 schedule + 跨日 revisit | Waiting for market data | 10-12 收盘 → Daily 21:30 UTC / 兜底 00:35 UTC；10-13 01:30 UTC 云端核查 |
| wxc-bot 新 cron 首次 schedule 证据 | Waiting | 10-12 13:10 UTC、22:30 UTC |
| B1 precedents / error_attribution | Ready（规格见第 1 节） | 需在首验后合并（会改研究生成器） |
| SPY 加入行情库（解锁 macro / market_state） | **Done**（owner 提供数据） | 每日增量来自 data.json stocks.SPY（完整 OHLC），10-13 核验 |
| TQQQ 等仅 core/index 标的被合成平坦 K 线（H=L=C；TQQQ 近 30 日中有 5 根） | Ready | 修改 append_latest 或在 core 中补 OHLC → 首验后 |
| B2 接线：财报结果干净子集 | Ready | 首验后，排在 B1 之后 |
| event / options outcome | Waiting for market data | 10-13 / 10-14 首批 5 日成熟 |
| B4 SEC 双跑（3 个 PR） | Ready（设计见第 3 节） | 首验后 |
| B3 共享证据契约 | Not started | 依赖 B1 / B4 的证据引用字段 |
| Candidate 下游冻结（实施） | Ready | 只是工作流或周审标记，低风险，首验后 |
| 后台执行机制 | Done | 每小时云端指令监视 + 10-13 01:30 UTC 一次性云端核查；**不承诺会话之外无限期自动开发**：监视任务只在有新 owner 指令时才执行 |
