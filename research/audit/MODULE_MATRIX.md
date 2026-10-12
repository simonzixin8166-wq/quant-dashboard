# MyAlpha 全模块矩阵（只读审计）· 2026-10-12

依据：`research/audit/module_manifest.json`（`scripts/module_manifest_audit.py` 生成，读取方角色逐个脚本审阅、带代码行号）与 `research/audit/sec_fact_reconciliation.json`（#203）。
读法：**研究/决策消费者** 指真正用该产物形成或排序研究判断、或生成面向 owner 的行动状态的代码；**监控/展示** 只是被状态页、QA、契约或网页读取 —— 这**不算**学习。
未成熟样本一律 pending；工程 QA PASS ≠ Learning PASS；**Learning UNPROVEN / FINAL=NO**。

## 结论先行（断链矩阵）

| # | 断点 | 证据 | 影响 |
|---|---|---|---|
| B1 | **每日自动研究不读取任何经验**：auto_research_journal 63 条假设，引用历史案例 / 错误归因 **0** 条；`daily_research_job.py` 不读 method / situation / regime / outcome 任何记忆 | manifest `experience_citation.status = not yet wired` | 衡量 3/4：经验无法进入新判断 |
| B2 | **6 个到期结果记忆没有任何研究消费者**：macro_outcome_memory、market_state_outcome_scorecards、company_fundamental_outcome_memory、event_outcome_memory、support_volatility_outcome_memory、options_opportunity_outcome_memory —— 只被 coverage audit / funnel 计数 | manifest `outcome_without_research` | 20/60/120 结果存在但"无人阅读"，积累 ≠ 学习 |
| B3 | **两套研究判断流互不相通**：V6 规划器/执行器（`research_execution.json`）使用情境/方法/组合记忆，但只到页面展示、不 append-only、不跨日复核、不到期评分；自动研究日志相反 | manifest `duplicates.research_judgment_streams` | 一个"会用经验但不被检验"，一个"被检验但不用经验" |
| B4 | **重复 SEC 事实源且旧源有缺陷**：交集 7 只，营收一致 2/7；旧源概念切换停更（GOOG）、卢布未换算（NBIS）、YTD 当单季（SOFI/SPCX/TSLA） | #203 对账 | 基本面证据可信度 |
| B5 | **Candidate 链 8 个产物均未到达研究或决策**（只到监控），其中 candidate_rule_family_status 无任何消费者 | manifest | 大量计算无下游 |
| B6 | **fo-1.0 Genuine Forward 状态只被决策日志页面展示**，到期结果尚无（最早 2026-11-05），未连接任何复盘消费者 | manifest | 待成熟后接 outcome |
| B7 | **作者信号（author_action_signals / author_intelligence）只到页面**，未作为研究证据被引用（自动研究日志另走 wxc-bot `author_claims_hp.json`，experimental） | manifest | 来源重复，口径不同 |

已接通（真实存在、代码可见）的学习 → 研究链路共 13 个学习产物，**全部只流向 V6 规划器/执行器**（另历史日志 → playbook 决策）：
`controlled_learning_policy → planner`（±5 分优先级）、`method_memory / regime_combination_memory / learning_engine / evidence_attribution / event_window_attribution / source_reading_memory → planner, executor`、`playbook_outcome_shadow / walk_forward_replay / self_improvement → controlled_learning_policy → planner`、`historical_journal → playbook_engine`。

## 三条前瞻轨道（分开统计，绝不相加）

| 轨道 | 样本 | 交易日 | 最早 20 日成熟 |
|---|---|---|---|
| Genuine Forward fo-1.0 | 48 条观察（19 eligible） | 2026-10-08、10-09 | 2026-11-05 |
| 晋升前瞻（owner 批准，独立统计组） | 130 条 | 09-29 至 10-07 共 6 日 | 2026-10-27 |
| Auto Research Shadow | 63 条假设记录 / 21 个"标的×交易日" | 2026-10-09 | 2026-11-06（forward_eligible=false） |

## 模块矩阵（7 问）

| 模块 | 1 存在意义 | 2 输入可信度 | 3 实际产出（样例/运行） | 4 研究/决策消费者 vs 监控/展示 | 5 学习/复核 | 6 协同 | 7 建议与验收 |
|---|---|---|---|---|---|---|---|
| **Market / Trend Pulse**（local_history_agent、learning_engine、breadth、cross-asset、regime） | 指数核心与杠杆仓位的趋势/环境判断 | STOOQ 规范归档（hash）、FRED；缺失→unavailable | historical_journal、regime_combination_memory 等；Daily 38011875102（schedule，10-09 交易日） | 研究：planner/executor/agent、playbook_engine；trend_pulse_backtest、assistant_rule_validation 仅页面/监控 | historical_journal 含 60 日成熟统计；market_state_outcome_scorecards **无研究消费者（B2）** | 与宏观共同构成 regime 状态 | **保留**；修 B2：把 scorecards 接入自动研究的"历史相似环境"证据；验收：研究记录出现 `precedents` 字段且可回放 |
| **Fundamental / SEC** | 公司财务事实作为正反证据 | SEC companyfacts 免费官方；新源有期间/新鲜度/异常门禁；旧源有缺陷（B4） | sec_fundamentals（auto research 读取）；company_fundamental_memory（仅监控） | 研究：daily_research_job ← sec_fundamentals；旧源及其 outcome memory **无研究消费者** | company_fundamental_outcome_memory 存在但无人读（B2） | 与事件/文件（official_evidence）互补 | **合并**（P1-A 步骤 2/3：统一抓取器 Shadow 双跑 → 兼容迁移）；验收：两源一致率 100% 或差异全部有分类 |
| **FRED / 宏观** | 实际利率、利差等折现率背景 | ALFRED `realtime_start` 时点；无 key 时 unavailable | macro_context（daily_research_job、cross_asset 读取） | 研究：2 处；macro_outcome_memory **无研究消费者** | 结果记忆未接（B2） | 宏观 × 宽度 → regime | **保留**；接 macro_outcome_memory；验收同上 |
| **事件 / 新闻 / WXC-BOT** | 外部观点与事件证据，区分"作者说了什么"与"市场发生了什么" | Yahoo 公开搜索、文学城/视频（只存 ≤360 字摘录+hash；15 个无效转录排除） | event_evidence、source_reading_memory、method_memory；wxc-bot tg-bot 38194271127（schedule） | 研究：planner/executor/thesis；event_outcome_memory、source_rule_lifecycle 仅监控/页面；作者信号仅页面（B7） | method_memory 来自已验证结果并被 planner 使用；主张抽取 experimental（test v2 P=0.50） | 作者主张 → 自动研究"兼容性"注释（不当证据） | **保留并收敛**：作者信号统一为一条口径；继续 M1 盲标；验收：冻结测试集精确率/召回率达标前保持 shadow |
| **Options**（support/volatility、opportunity context、server action） | 期权研究提示与持仓风险（不下单） | 免费行情、私有持仓经 RLS；fail-closed | server_action_status（schedule 38195708790） | 决策：server_action_engine → 页面；options_opportunity_context 仅页面/学习；两份 outcome memory **无研究消费者** | 5/20 日结果记忆存在未被读（B2） | 支撑/波动 → 机会排序 | **保留**；把 support_volatility / options outcome 接入下一次排序的"历史命中"说明；验收：排序理由中出现成熟样本数与命中率 |
| **Portfolio / 风险** | 每日风险待办、私有持仓分账户 | Supabase RLS（owner-only）；不公开 | 私有面板（不在公开 artifacts） | 决策/展示；不进入公开研究 | 无学习回路（正确：私有数据不进公开学习） | 与 options/server action 共用 | **保留**；无改动 |
| **Decision Journal** | 记录 owner 决策与前瞻观察 | 本地/私有 + fo-1.0 状态 | 页面读取 forward_observation_status、historical_journal、assistant_rule_validation | 仅展示 | 无成熟评分回读 | — | **修复**：fo-1.0 成熟后显示结果；验收：11-05 后出现真实 20 日结果 |
| **Situation / Error / Method Memory** | 把历史情境、错误归因、方法表现变成可复用经验 | 来自已验证结果；作者是证据来源而非结论 | learning_engine、evidence_attribution、method_memory | 研究：V6 planner/executor（真实使用）；**自动研究未使用（B1）** | 接通于 V6，未接通于自动研究 | 三者共同生成 V6 研究简报 | **接线（下一 PR）**：自动研究读取同标的情境记忆与方法失败记录，写入 `precedents`/`error_attribution`；验收：可回放样例 2–3 只 |
| **Forward Outcome 20/60/120** | 唯一能证明学习的成熟评价 | append-only、rule_hash、genuine/promoted/shadow 分组 | fo-1.0 48 条；晋升 130 条；shadow 63 条 | 状态仅页面（B6） | 全部 pending（最早 10-27 晋升组、11-05 fo-1.0、11-06 shadow） | 未来回读到 method/situation memory | **保留**；成熟后接回 method_memory；验收：首批成熟结果按组分别计分 |
| **Autonomous Agent（V6）** | 研究排序与简报 | 内部产物 | research_planner、research_execution | 规划器结果被 executor 与证据引擎使用；执行简报只到页面（B3） | 使用记忆，但简报不被检验 | 与自动研究重复（B3） | **整合**：执行简报的支持/反证作为自动研究的输入或二者合并为一条可检验流；验收：一条研究流同时"用经验 + 被复核 + 到期评分" |
| **Candidate 链**（compiler → replay → families → scorecard → promotion） | 把来源规则编译为可检验候选 | shadow，研究专用 | 8 个状态文件 | 无研究/决策消费者（B5） | 候选前瞻未成熟 | — | **冻结入口、保留证据**：停止新增功能，先回答"谁消费"；验收：明确消费者或标记 frozen（不删除） |
| **Guardian / QA** | 无人值守可靠性 | Actions API、生产页面 | Guardian 38071516195（schedule）；生产 QA 38153142070（workflow_dispatch，overall=PASS，research_row=desktop:ok(21)/mobile:ok(21)，vendor_libs=ok） | 监控（正确定位） | operational_incident_memory 记录事件开闭（系统学习，不是研究学习） | 发现漏跑与 404 | **保留** |
| **Watchlist / 个股** | 观察池研究提示 | 免费行情 + 论点草稿 | 页面读取 auto_thesis_drafts、support_volatility_intelligence | 展示 | — | — | **保留**；后续在个股页引用自动研究假设（不新增卡片） |
| **首页行动提醒 / 今日研究行** | 一屏告诉 owner 今天关注什么 | 各模块状态 + digest | 研究行 `正常 · 10-09 · 新增21/失效0/弃权2` | 展示（终点） | 依赖上游 | — | **保留精简**；不加大卡片 |
| **黄金 / 定投** | 保护核心纪律（只提醒） | 公开行情 | investment_actions_status → 页面 | 决策输出（终点） | 规则型，无学习需求 | — | **保留不动** |

## 其他发现
- `weekly_research_report.json`、`autonomous_intelligence_status.json`、`candidate_rule_family_status.json` 无任何消费者。
- `gemini-api-smoke-test.yml`、`gemini-youtube-probe.yml` 只有 push / workflow_dispatch 触发，无定时；最后运行 2026-10-07（37584915361、37585820367）。不是持续依赖；是否涉及付费额度需 owner 确认 GEMINI_API_KEY 的计费方式（零新增付费 API 原则）。

## 下一批小 PR（按「数据可信 → 跨模块融合 → 经验被引用 → 提醒呈现 → 瘦身」）
1. **B1 接线（not yet wired → wired）**：`daily_research_job` 为每条假设附 `precedents`（同标的历史情境记忆 + 同环境 regime 成熟统计）与 `error_attribution`（method_memory 中同方法失败记录），只作证据、不改规则；2–3 只真实标的可回放演示。
2. **B2 接线**：把 6 个 outcome memory 的成熟样本数/命中率作为对应证据的"历史可靠度"附注（未成熟写 pending）。
3. **B4 SEC 统一**（首个定时运行验收后）。
4. **B3 整合**、B5 冻结入口、B7 作者口径统一。
5. 把 `module_manifest_audit.py` 接入每周任务，追踪断链数量随时间下降。
