# 统一知识检索 · 只读设计包 v0.2（2026-11-03）

状态：DESIGNED ONLY。不改生产、不改 schema、不新增数据源或付费服务。
本版依据 GPT 审阅（#133 6594478717）修订 v0.1（6594443196）。Owner 已决定的边界（6594477482）作为前提：私有数据不进公开索引；验收题只用观察名单内的 26 只股票；实施放在续费后第一阶段。
对应成功标准：C3 记忆复用、S6 能研究。学习状态 UNPROVEN / FINAL=NO。

## 0. 相对 v0.1 的修改

| GPT 意见 | 修改 | 为什么 |
|---|---|---|
| 1 盘点没有可复核清单，2,862 与 2,977 的差额没有解释 | 新增**机器生成的盘点清单**（§2），列出记录数、唯一 ID、时间字段覆盖率和文件哈希；差额已按 ID 对账 | 盘点结果必须能被别人重算，否则检索的分母本身就不可信 |
| 1 v0.1 把"前瞻结果 82 条"写得像 genuine | 更正：82 条**全部**是 promoted 组 h=20 结果；genuine 组 0 条（11/5 起才有） | v0.1 的写法容易把晋升组结果误读成真实前瞻 |
| 2 `known_at` 用 session 收盘代替采集时间，会让时点提前 | 时间拆成 7 个字段，**结果单独按 `scored_at` 过滤**；时间未知的记录在严格回放中排除（fail closed） | 10/08 的记录可能在 10/09 才采集；到期日到了也不等于结果已经算出 |
| 2 单一 `evidence_role` 混了几个维度 | 拆成 4 个正交标签（§3.2） | "官方来源"和"真实前瞻"是不同维度，放在一条链上排序会排错 |
| 3 固定的证据排序不可靠 | 按**问题类型**选择排序方式（§4.2） | 问"SEC 有没有发 8-K"应以官方文件为先；问"系统当时怎么判断"应以账本为先 |
| 3 去重可能误合并，也不应删除来源 | 分 4 级重复，只建分组、**不删除**任何原始来源 | 保留作者和 URL 才能追溯；误合并会把不同观点算成一个 |
| 3 `no_evidence` 太笼统 | 7 个弃权原因码 | 文学城 403 是"来源受阻"，不等于"没有新帖" |
| 3 只返回最相似的结果会漏掉反证 | 研究类查询**分别检索**支持、反对和失效条件 | 只看正面材料会形成确认偏差 |
| 4 25 题太小，没有分母，容易对着考题调参 | 25 题降级为**冒烟回归集**；另设开发集和冻结盲测集；补充 12 类负向题；三项硬门槛 | 25 题不足以证明 S6 的 90% 准确率 |
| 5 BM25 是合理的起点 | **保留**；补充中文分词、代码与名称别名、分字段索引 | 关键词检索对中文和别名召回不足，先用词典和字段解决，再考虑更复杂的方法 |
| 6 只排除私有路径不够 | 改为**白名单**：未分类的数据不进入索引；构建前做敏感信息扫描 | 私有信息可能通过摘要、日志、路径间接泄露 |

## 1. 目的（不变）
研究或回答问题时，能查到**当时可知**的过去判断、结果、来源和反证，并附来源和时间；查不到时给出明确的原因码。目标是把自动研究中"引用过去案例"的比例从 8/79 提高。

## 2. 盘点清单（机器生成，可复核）
文件 `claude/retrieval_inventory_manifest_2026-11-03.json`，由只读脚本生成，基于 quant-dashboard main `e6f4b897` 和 wxc-bot main。

| 资料 | 记录数 | 唯一 ID | 时间字段覆盖率 |
|---|---|---|---|
| wxc-bot 原始 feed | 2,862 | id 2,862 | published_at 0.988；captured_at 1.0 |
| 来源存储 | 2,977 | id 2,977 | published_at 0.988；first_fetched_at 1.0；captured_at 0.96 |
| 阅读理解 | 2,977 条来源 → **7,129 条命题** | source_id 2,977 | published_at 0.988 |
| 可检验规则 | 62 | — | published_at 1.0 |
| genuine 前瞻观察 | 464 | event_id 464 | captured_at、session、market_as_of 均为 1.0 |
| promoted 前瞻观察 | 130 | event_id 130 | session、market_as_of 均为 1.0 |
| 前瞻结果 | 82（**全部 promoted、h=20、matured**；genuine 0） | event_id 82 | scored_at、matures_on 均为 1.0 |
| 自动研究日志 | 1,210 | record_id 1,210 | generated_at、market_as_of 均为 1.0 |
| 知识契约案例 | 3 | case_id 3 | created_at 1.0 |
| 基本面观察 / 结果 | 867 / 1,713 | observation_id 867 / 860（一个观察对应多个窗口） | filed 1.0 |
| 事件结果 | 1,842 | outcome_id 1,842 | published_at 1.0 |
| 市场状态结果 / 宏观观察 | 58 / 29 | 58 / 29 | as_of 1.0 |
| 运维事故 | 70 | — | event_at 1.0 |
| **source outcome validation**（v0.1 遗漏） | 210 | event_id 210 | published_at 1.0 |
| **矛盾记录**（v0.1 遗漏） | 54 | — | **无时间字段** |
| 方法记忆 / 情境记忆 / 历史回放 | 9 / 26 / 600 | — | **无时间字段** |
| SEC 文件、thesis 修订、期权观察、行情历史 | 7 / 30 / 2 / 5 个文件 | — | 待逐文件展开 |

**2,862 与 2,977 的对账（按 ID）：**
- 只在来源存储中：118 条，全部是 BrightLine 博客（backfill 99 + initial migration 19，来自 2026 静态存档和历史回填）。
- 只在原始 feed 中：3 条论坛帖（bogbog 2、三心三意 1），尚未进入存储。
- 2,977 = 2,862 − 3 + 118。
- 命题 7,129 是在 2,977 条来源上做的一对多拆分。

**时间可信度：**
- 来源存储的 `timestamp_confidence`：unverified 2,757、high 185、missing 35。
- `ingest_type`：backfill 2,065、initial_migration 804、live 108。
- 也就是说，大部分来源帖子的发布时间**未经验证**。严格回放时，只能按系统实际获取时间 `first_fetched_at` 判断"当时是否可知"。

**不纳入公开索引的资料（Owner 决定）：** 浏览器决策日志、Supabase 操作记录、私有仓库持仓和账户。私有仓库标为 EXCLUDED，不是 MISSING。

**无时间字段的类别**（矛盾记录、方法记忆、情境记忆、历史回放）在严格回放中只能返回 `time_unknown`，直到上游补充时间字段为止。

## 3. 记录格式 kr-0.2

### 3.1 时间字段（7 个，含义不可互换）
| 字段 | 含义 |
|---|---|
| `published_at` | 作者或官方发布的时间（原始字符串和时区一并保留） |
| `first_seen_at` | 系统第一次实际获取该内容的时间（first_fetched_at / captured_at / generated_at） |
| `ingested_at` | 进入归档或索引的时间 |
| `valid_time` | 内容描述的市场时点（session / market_as_of / as_of / filed） |
| `matures_on` | 预期到期日（只是可见条件之一） |
| `outcome_known_at` | 结果实际计算出来的时间（scored_at） |
| `timestamp_quality` | verified / inferred / date_only / unknown |

**可见规则：** 查询时点为 T。
- 记录本身可见：要求 `first_seen_at ≤ T`。
- 结果字段可见：要求 `outcome_known_at ≤ T`；只满足 `matures_on ≤ T` 不够。
- `timestamp_quality = unknown`：在严格回放中不可见。
- 历史回填的旧文章：以回填时间为 `first_seen_at`，不使用原发布时间。

### 3.2 证据标签（4 个正交维度）
| 维度 | 取值 |
|---|---|
| `temporal_class` | genuine_forward / promoted_forward / historical_replay / backfill / descriptive |
| `source_authority` | official / primary_market_data / system_ledger / author_claim / secondary |
| `validation_state` | unvalidated / shadow / matured / independently_validated |
| `production_eligibility` | true / false；保留原文件中的状态字段，例如 `eligible_for_production`、`scoreable_as_method_performance`，不压扁 |

### 3.3 其他字段
`doc_id`（`<kind>:<原 ID>`）、`kind`、`symbols`、`author`（含别名表）、`url`、`text`（标题 + ≤ 360 字摘录 + 命题，分字段存储）、`stance`、`outcome`、`content_sha`、`source_file`、`source_commit`、`duplicate_group_id`、`duplicate_level`、`links`（观察 ↔ 结果 ↔ 研究日志 ↔ 来源），以及隐私字段 `data_classification`、`visibility`、`origin_repo`、`redaction_status`。

## 4. 检索规则

### 4.1 时间
采用双时间轴：`first_seen_at` 控制系统何时知道，`valid_time` 控制资料描述哪一天；结果按 `outcome_known_at` 单独过滤。

### 4.2 按问题类型选择排序方式
| 问题类型 | 优先 |
|---|---|
| 官方事实（有没有发 8-K） | official |
| 系统当时的判断 | system_ledger 中的 genuine_forward |
| 作者当时的观点 | 原始帖子（primary） |
| 结果复盘 | 已有 `outcome_known_at` 的结果记录 |
| 找反证 | 研究日志的 opposing / invalidation，以及矛盾记录 |

每条结果都显示 4 个证据标签，不只给一个混合分数。

### 4.3 去重（只建分组，不删除）
分 4 级：完全相同、近似相同、同一原始来源（转载）、同一主张。每级都保留全部作者、URL 和 provenance。统计"独立观点数"时按分组计；展示时可以展开。

### 4.4 弃权原因码
`no_evidence`、`source_blocked`、`not_indexed`、`stale_data`、`time_filtered_out`、`time_unknown`、`conflicting_evidence`、`insufficient_confidence`。

### 4.5 反证
研究类查询分别返回 supporting / opposing / invalidation 三组。资料互相冲突时，展示冲突，不合并成一个结论。

## 5. 验收

### 5.1 三套题
- **冒烟回归集：** v0.1 的 25 题，修订见 §5.3。每次改动都跑。
- **开发集：** 约 60 题，实现时可以看答案。
- **冻结盲测集：** 约 100 题，由 Owner 或 GPT 出题，实现者看不到答案，冻结后计算哈希。只有这套题的结果才能用来判断是否达到 S6 的 90%。

### 5.2 每题的金标准
必须返回的 doc_id 集合、可以接受的来源、禁止返回的未来记录、预期弃权原因码、正面证据和反面证据集合。

### 5.3 v0.1 冒烟题修订
- 第 1 题：按 symbol = IREN、session 10/08–11/02 计数 = 18 条 event_id。
- 第 3、4 题：结果可见以 `outcome_known_at` 为准，不以 `matures_on` 为准。
- 第 8 题：只取 `temporal_class = genuine_forward`，promoted 明确排除；另加一道 promoted 题，要求标签正确。

### 5.4 新增 12 类负向题
1. 同标题、不同文章；
2. 同一文章跨站转载；
3. 作者别名；
4. 跨时区导致日期差一天；
5. 已到期但尚未计算出结果；
6. 已回填但当时不可知；
7. 来源受阻与没有资料的区别；
8. 时间字段缺失；
9. 结果后来被修订；
10. 标的混淆（QLD 与 QQQ、GOOG 与 GOOGL）；
11. 反证召回；
12. 植入假的账户号、金额、交易决定和私有 URL，检查是否泄露。

### 5.5 门槛
- **硬门槛（一票否决）：** 时间穿越 = 0；隐私泄露 = 0；伪造引用 = 0。
- **分层报告：** 按类别报告 Recall@5、Precision@5、引用正确率、误合并率、误拆分率、弃权准确率、反证召回率，并给出分母和置信区间。不只看总分。
- **Owner 抽查：** 时间穿越、来源引用、去重、隐私 4 类高风险样本。

## 6. 技术方案
- 结构化过滤（标的、作者、类型、4 个证据标签、时间）+ BM25，纯 Python，不接付费嵌入。
- 中文分词与规范化；股票代码与公司中英文名称别名表；作者别名表。
- 标题、摘录、命题、反证、失效条件**分字段索引**，每个字段有自己的权重；结果始终能回链到原文件。
- 只有在冻结盲测显示某类问题召回持续不足、并且词典和字段调整都无效时，才评估免费的本地语义方案。

## 7. 隐私（白名单，fail closed）
- 只有明确标为 public / research-safe 的来源可以进入公开索引；未分类的一律拒绝，并记录拒绝原因。
- 摘要、命题、URL、日志和错误信息都要做敏感信息扫描；每次构建都记录来源清单、过滤数量和产物哈希。
- 持仓、账户、交易决定、个人金额、Supabase 表和私人笔记永久不进入公开索引。将来如果需要，另建私有索引，与公开索引分开存储、分开授权。

## 8. 实施顺序（续费后第一阶段）
1. 把盘点清单脚本放进仓库，每次构建都重新对账。
2. 生成索引 kr-0.2：只读派生，挂在现有流程之后，不新增 cron。
3. 实现查询工具，包括原因码和反证分组。
4. 依次运行冒烟集、开发集和冻结盲测集，并在 #133 报告分层结果。
5. **盲测通过后**，才给自动研究日志增加 `past_cases`。网页入口、生产接入和付费 API 都不在本阶段范围内。

## 9. 不变的边界
只读；不自动学习、不晋升策略；不保存第三方全文；不使用付费服务。学习状态 UNPROVEN / FINAL=NO。

备注：项目文档（`claude/...`）保存在 Claude 项目空间，不在 GitHub 仓库里，所以 GPT 在默认分支上找不到。实施时，盘点脚本、题集和索引都会作为 PR 提交到仓库，可以按提交追溯。

---

# v0.2.1 补充（2026-11-04，回应 GPT 复核 #133 6594555129 的 5 个准入条件）

| GPT 条件 | 处理 |
|---|---|
| 1 时间可信度要按字段记录；修订过的结果要有版本 | 见 A |
| 2 `matured` 要从 `validation_state` 拆出；backfill 与 historical_replay 的关系要说清 | 见 B |
| 3 盘点清单要能复算，并固定两个仓库的提交号和逐条差异 | 见 C |
| 4 冻结 S6 的 90% 计算口径和零容忍规则 | 见 D |
| 5 实施先限定为只读、隔离、仅研究用，白名单默认拒绝 | 见 E |

## A. 字段级时间契约
- **每个时间字段**（published_at / first_seen_at / ingested_at / valid_time / matures_on / outcome_known_at）都配三项附属信息：
  - `<field>_raw`：原始字符串；
  - `<field>_source`：取自哪个文件的哪个字段；
  - `<field>_quality`：verified / inferred / date_only / unknown。
  
  不再用一个记录级的 `timestamp_quality` 代替。
- **严格回放**只认 `first_seen_at_quality ∈ {verified, inferred}` 的记录。`published_at` 是否可信，不影响"系统当时知不知道"这一判断。
- **不得冒充：** 缺少真实首次获取时间的类别，不允许用 `published_at`、`created_at` 或索引构建时间来顶替。这类记录在严格回放中返回 `time_unknown`。
- **结果版本：** 结果记录带 `outcome_version` 和 `supersedes`，只追加不覆盖。查询时点 T 只能看到 `outcome_known_at ≤ T` 的最新版本。目前 `forward_outcomes.jsonl` 本身就是只追加的；如果以后出现修订，按这条规则处理。

## B. 标签语义
- 新增独立字段 `maturity_state`：pending / matured_h20 / matured_h60 / matured_h120 / unavailable。
- `validation_state` 只描述验证阶段：unvalidated / shadow / independently_validated。
- 已到期 ≠ 已验证：一条结果可以已经到期，但仍处于 unvalidated。
- `ingestion_mode`（新增，描述资料怎样进入系统）：live / backfill / initial_migration / manual_forward。
- `temporal_class`（描述与当时市场时点的关系）：genuine_forward / promoted_forward / historical_replay / descriptive。
- 这两个维度互相独立，可以任意组合。例如：backfill + descriptive 是回填进来的旧帖子；live + genuine_forward 是每日账本。
- **冲突时默认拒绝：** 原文件的生产资格字段（`eligible_for_production`、`scoreable_as_method_performance` 等）只要有一个是 false 或缺失，`production_eligibility` 就取 false。

## C. 可复算盘点（项目文档 `claude/retrieval_inventory_manifest_2026-11-04.json`，sha256 前 16 位 `a004199db570bc8f`）
- **固定提交：** quant-dashboard `8ae72dfb30a079b3790258cb59f0fdc36cf9c14b`；wxc-bot `f54bd0a7c8408de02cce5638cd6c870b7365ac45`。
- **来源对账：** 2,978 = 2,863 − 3 + 118。清单逐条列出了"只在存储中"的 118 个 ID 和"只在 feed 中"的 3 个 ID。
- **前瞻结果：** 现在是 106 条，全部为 promoted、h=20、matured。genuine 组 11/5 起才会有。
- **盘点脚本**会随实施 PR 一起进入仓库，每次构建都重算并对账。
- **实施时补充：**
  - SEC、thesis、期权、行情历史按文件逐个展开；
  - 统计 source / event / outcome 之间的孤儿记录、重复记录和一对多关系，并由 Owner 抽查；
  - 无法取得时间字段的类别不计入"可回放"的分母。

## D. S6 评分口径（冻结前不调参）
- **主指标："事实准确率"。** 盲测每题由评审按金标准判定：
  - 答案引用的每个 doc_id 都真实存在、时间合法，并且支持答案中的结论 → 正确；
  - 应弃权的题给出了正确的原因码 → 正确；
  - 其余情况 → 错误。
  
  事实准确率 = 正确题数 ÷ 盲测总题数。按题微平均，并给出 Wilson 95% 区间。
- **初步达标：** 点估计 ≥ 0.90，且各类别（每类 ≥ 10 题）的点估计都 ≥ 0.80。不足 10 题的类别标 INSUFFICIENT_N。
- **辅助指标（报告但不作门槛）：** Recall@5、Precision@5、引用正确率、弃权准确率、反证召回率。每项都写明分母，按类别和总体分别报告宏平均与微平均。
- **零容忍：** 时间穿越、隐私泄露、伪造引用，任何一项出现一次即判不通过，不能用总分抵消。这三项同时在代码层面防护：时间过滤写在查询层；构建时执行白名单；引用在返回前必须能回链到真实 doc_id。
- **流程：** 盲测题、金标准和答案由 Owner 或 GPT 准备，在开始调参前冻结并计算哈希；实现者只使用开发集和冒烟集。
- **措辞：** 100 题的结果只能称为"初步离线验收"，不能称为"已证明 90% 的真实研究准确率"。扩大样本，以及跨时段、跨来源复测，是后续的晋级条件。
- **范围：** 观察名单之外的标的只能返回"仅有提及"或弃权（Owner 11/3 决定）。

## E. 实施范围（续费后第一阶段）
- 只读、隔离、仅研究用。索引放在 `research/index/`，不被任何生产步骤读取。
- 白名单默认拒绝：未分类的来源不进入索引；私有仓库和 Supabase 永久排除。
- 盲测通过前，不写入 `past_cases`，不接入生产研究链，不新增网页入口；不改变任何策略、阈值或前瞻账本。

学习状态：UNPROVEN / FINAL=NO。
