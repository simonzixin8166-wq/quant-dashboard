# 错误归因格式 fea-0.2（冻结版 · 2026-10-31）

依据：草案 fea-0.1（#133 6512922683）→ GPT 审阅 6513028156 → Claude 修订 6513057000 → Owner 批准 6513072588。
看到真实前瞻结果之后，本版不再修改；要改只能发新版本，并与本版并列使用。

## 1. 原则
1. 归因不改变判分。hit / miss 只由冻结的 fsc 口径决定。
2. 判对和判错的行跑同一套检查。
3. 原因说不清时写 R0（未能归因），并报告 R0 的占比。
4. 无法观测的情况写 unknown，不写成“无”。

## 2. 范围
- 只适用于 h=20；60、120、180 日以后另立版本。
- 只处理 status=matured 且已判分的行。genuine 与 promoted 分开归因。
- unavailable 行只记 D3。“继续观察”属于弃权，不做归因。

## 3. 代码与判定（按此顺序检查；第一个命中的为主因，其后命中的列为次因）
| 代码 | 含义 | 判定条件 |
|---|---|---|
| S1 | 系统缺陷 | 有已确认的缺陷记录（lessons_learned 或运维事故编号） |
| D1 | 判断时输入不可信 | 记录的 market_as_of ≠ session，或数据可信检查失败 |
| D2 | 打分输入有误 | 打分器给出了 unavailable 原因 |
| M2 | 与基准同指数 | 标的为 QQQ 或 QQQM |
| M1 | 噪声带 | \|最终超额\| < 1.0%（这是预先定义的阈值，不是统计结论） |
| E1 | 财报 | 见下方“E1 补充” |
| E2 | 大盘冲击 | 窗口内某日 QQQ 跌幅 ≥ 3%；当日超额与最终超额同号，且 \|当日超额\| ≥ 0.5 × \|最终超额\|。最终超额落在噪声带内时不适用 |
| R4 | 时机 | 第 5、10、15 日中至少 2 个满足 hit_if，第 20 日不满足，且最终超额不在噪声带内 |
| R3 | 环境切换 | 见下方“R3 补充” |
| R0 | 未能归因 | 以上都不成立。所有检查都可观测时记为 CONFIRMED，否则记为 UNKNOWN |

**E1 补充：**
- 财报日取 8-K Item 2.02 的申报日；窗口为申报日的前一交易日到后一交易日（截断到持有窗口内）。
- 判定为 E1 需同时满足：事件超额与最终超额同号，且 \|事件超额\| ≥ 0.5 × \|最终超额\|。
- 申报日与事件日历日期相差超过 1 个交易日时，记为 unavailable(event_time_conflict)。
- 取不到事件数据时记为 unknown。最终超额落在噪声带内时，E1 不适用。

**R3 补充：**
- mode_share = 与判断日 mode 不同的交易日数 ÷ 可分类的交易日数，≥ 25% 即判定为 R3。
- 缺失的交易日既不计入分子，也不计入分母。可分类交易日少于 15 天时，记为 unavailable(insufficient_regime_coverage)。

**hit_if 方向**（取自 fsc-1.0）：

| 类别 | 判对条件 |
|---|---|
| 修复候选 / 大跌机会候选 | 超额 > 0 |
| 等待修复 | 超额 < 0 |
| 高位观察 | 超额 ≤ 0 |

U1（理解错误）暂不启用。宽基对宽基（SPY、VOO、QLD、TQQQ）只加一个描述性标记 broad_index_vs_broad_index，不作为主因。

## 4. process_ok
以下五项都有证据时记为 true，任一缺少记为 unknown：
- data_trust ok，且 market_as_of = session；
- source_sha；
- rule_hash；
- run_id；
- 时间对齐。

## 5. informative
- 只有 M1、M2 表示“这个判断本身没有信息量”。
- 汇总指标：attribution_coverage、unattributed_rate、informative_hit、uninformative_hit。

## 6. 记录格式
- 文件：research/archive/forward_errors.jsonl，只追加，唯一键为 (outcome_id, attribution_version)。修订时追加新行并用 supersedes 指向原行。
- 先跑自动检查，Claude 复核 HYPOTHESIS 和 UNKNOWN 的行，Owner 每批抽查 min(10, 错题数) 行。
- 本文件为公开研究数据，不含持仓信息。

## 7. 反馈去向
| 代码 | 去向 |
|---|---|
| S、D | 工程错题本 + 回归测试 |
| U | 加入开发集，不进测试集 |
| R4 / R3 / R0 | 按规则家族累计，n ≥ 20 后才可提出影子实验 |
| E1 / E2 | 作为事件感知的影子假设 |
| M | 只计数 |

任何情况下都不改正式阈值，也不自动晋升。

## 8. 实现
离线脚本 `fwd_cohort_report.py`（项目 claude/tools/）。11/5 首批只出离线报告，不写生产文件。
