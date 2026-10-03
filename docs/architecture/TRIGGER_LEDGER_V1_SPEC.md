# Playbook Trigger Ledger V1 Spec

状态：V6.10a 实施依据  
替代早期以“自由预测”为中心的 Prediction Ledger 语义。Forward 与 Replay 永久分离。

## 1. 记录对象

Trigger Ledger 记录预注册 Playbook 的状态变化，不记录自由文本研究观点。

事件类型：
- trigger_state_event：NEAR_TRIGGER / TRIGGERED / INVALIDATED 的状态变化。
- discipline_event：NO_CHASE，进入独立 Discipline Ledger。
- outcome：成熟的 5/20/60/120 交易日结果。
- correction：对历史记录的追加更正/注释，不覆盖原记录。
- audit_event：UNDETERMINED、heartbeat、数据质量失败、kill switch 等运维证据。

只有 TRIGGERED 是 Opportunity Scorecard 的主要可评分机会样本。
NEAR_TRIGGER / INVALIDATED 只用于状态生命周期分析。
UNDETERMINED 永不进入成绩样本。

## 2. Append-only

旧记录永不重写。
schema 可以 v1 -> v2，但新版本只作用于新记录。
规则变化产生新 rule_version / rule_hash，新旧成绩分开。

若 bug 修复影响已记录内容：
- 追加 correction。
- correction 引用 original_record_id。
- 保存原因、发现时间、影响范围。
- 原始记录保留。

## 3. Trigger Event 冻结字段

公共字段：
- schema_version
- record_type
- record_id
- prev_hash
- record_hash
- recorded_at
- playbook_id
- rule_version
- rule_hash
- commit_sha

Trigger 字段：
- symbol / scope
- market_date
- state
- previous_state
- event_date
- detected_at
- detection_delay_sessions
- late_detected
- baseline_close
- benchmark
- market_regime
- data_lineage
- source_snapshot_hash
- evidence_ids
- risk_band（仅比例，不含账户金额）

next_session_open 只能在下一交易日以追加 outcome/enrichment 记录补充，不能覆盖原 Trigger。

## 4. Data Quality Eligibility

正式 TRIGGERED 入账前必须通过：
- freshness / as_of
- missing-session detection
- split / adjustment consistency
- expected-run heartbeat

失败：
- Playbook state = UNDETERMINED。
- 追加 audit_event。
- 不创建可评分 Trigger Event。

若数据恢复后发现过去已经触发：
- event_date 保留真实市场日期。
- detected_at 使用实际发现时间。
- detection_delay_sessions 按交易所日历计算。
- late_detected=true。
禁止回写成“当日已识别”。

## 5. Outcome

5/20/60/120 trading-session outcome 分别成熟。

至少保存：
- maturity_session
- exit_close
- absolute_return
- benchmark_return
- excess_return
- MAE
- MFE
- unconditional_baseline
- lift
- scorer_version
- scored_at
- source / as_of

只有原 Trigger 真正包含预注册概率预测时才计算 Brier / calibration。

## 6. NO_CHASE Discipline Ledger

NO_CHASE 独立于 Opportunity Scorecard。

预注册反事实：
- planned_reference = 原 Trigger 的参考价格。
- chase_reference = 首次 NO_CHASE 判定当日收盘价。
- 比较 5/20 日 return、MAE、MFE。

该口径不得在查看实际结果后追溯改变。

## 7. Forward / Replay / Control

三套结果永久分离：
- Forward：规则冻结后的真实前瞻。
- Replay：历史回放。
- Control：无条件基准 / QQQ / SPY / broad-market control。

既有老规则的 Replay 必须标记 historical_replay_post_rule_design，不称为真正 OOS。
只有 Forward 属于 forward_out_of_sample。

## 8. 哈希链

每条 ledger record：
- prev_hash
- record_hash

canonical JSON + prev_hash 生成 record_hash。

按月分片，链跨分片延续。

公开仓库只发布：
- daily head hash
- record count
- schema version
- verify status

Telegram 可作为第二外部锚点。

## 9. 私有存储与失败隔离

原始 Trigger / Outcome / Discipline / Correction / Audit 数据必须进入私有存储，不进入公开 Pages。

若 private ledger write 失败：
- 网站日常构建继续。
- System Status = ledger_write_failed。
- 当次事件不得被视为有效 Forward 样本。
- audit/heartbeat 继续尝试记录。
- 禁止用公开摘要替代丢失的原始 Ledger。

## 10. 稳定期

正式启动后前 10 个交易日：
- 只允许 bug / security / data-integrity 修复。
- 不改业务语义、阈值、字段解释或评分口径。
- 语义变化必须新 schema_version 或新 rule_hash。
