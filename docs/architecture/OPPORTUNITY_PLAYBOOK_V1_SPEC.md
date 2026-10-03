# Opportunity Playbook V1 Spec

版本：v0.2  
状态：V6.10a 实施依据

## 1. 目标与红线

MyAlpha 从研究看板升级为机会捕捉与纪律系统：预先定义值得处理的情境，在状态变化时识别、记录、验证，再把高价值行动路由给用户。

三条永久红线：
1. 不自动下单。
2. 不自动修改仓位、核心配置或 TQQQ Hard Exit。
3. 未经验证的研究结论不得直接升级为 Production；Learning Engine 只能提出候选修改。

## 2. Cloud / Private 边界

Cloud Playbook 只依赖公开市场数据，可在 GitHub Actions 中计算。V6.10a 首批：
- CP-01 核心 ETF 回撤分档。
- CP-02 TQQQ / QQQ 回调杠杆情境。
- CP-03 LEAPS Opportunity，仅判断市场条件。

Private Playbook 依赖真实持仓，只在浏览器私有端计算：
- PP-01 Options / Roll / Assignment management。

私有期权状态不进入公开 Trigger Ledger；真实结果来自 Private Decision Journal。

## 3. Lifecycle 与 Evidence 必须分开

Lifecycle：
- Experimental
- Shadow
- Active
- Watch-only
- Retired

Evidence：
- unverified
- replay_support
- forward_support
- no_difference
- evidence_against

Active 仅表示正在使用，不代表统计上已验证。

## 4. Playbook 必填字段

- playbook_id
- name
- class: cloud/private
- assets
- lifecycle
- evidence
- near_trigger
- trigger
- entry_zone
- valid_sessions
- no_chase
- invalidation
- cooldown_sessions
- reentry_condition
- risk_band_per_event
- exposure_cap_total
- event_blackout
- conflicts_with
- rule_version
- rule_hash
- enabled
- notifications_enabled
- ledger_enabled

云端配置只包含比例、状态条件和风险带，不包含真实账户金额。

## 5. Trigger State Machine

状态：
- IDLE：正常/未触发基线状态。
- NEAR_TRIGGER：接近触发。
- TRIGGERED：正式条件成立。
- INVALIDATED：失效或超过有效期。
- NO_CHASE：曾触发但已超过不追上限。
- UNDETERMINED：数据过期、缺失、接口失败或价格序列完整性失败。

记录分层：
- 所有状态变化（含回到 IDLE）可进入 Trigger Event stream，用于生命周期审计。
- 只有 TRIGGERED 进入 Opportunity Scorecard 的可评分机会样本。
- NO_CHASE 进入独立 Discipline Ledger / Discipline Scorecard。
- NEAR_TRIGGER 与 INVALIDATED 保留为状态生命周期证据，不与 TRIGGERED 收益成绩混算。
- UNDETERMINED 只进入 append-only Audit Log，不进入成绩样本。

若先 UNDETERMINED、之后才确认触发：
- 保留真实 event_date。
- 记录 detected_at。
- 记录 detection_delay_sessions。
- late_detected=true。
不得伪装为准时识别。

所有有效期、冷却期、Outcome horizon 使用美股交易所交易日历，不使用自然日或简单周一至周五。

审计日志 V1 默认长期保留；在 V7.0 Review 前不自动清理。

## 6. 规则变更与稳定期

任何业务规则变化必须：
1. 写明 change_reason。
2. 产生新的 rule_version。
3. 产生新的 rule_hash。
4. 旧记录永不重写。
5. 新旧成绩分开统计。

账本启动后的前 10 个交易日为 stabilization window：
- 允许 bug、安全、数据完整性修复。
- 不允许改变业务语义、阈值、字段解释、评分口径。
- 如果修复影响已记录内容，只能追加 correction / annotation，引用原 record_id；不得覆盖旧记录。
- 如确需改变语义，必须新 schema_version 或新 rule_hash。

## 7. 最小数据质量门（先于 Silent Ledger）

创建正式 Trigger Event 前至少检查：
1. freshness / as_of；
2. 缺失交易日；
3. split / adjustment consistency；
4. expected run vs actual run heartbeat。

失败时状态为 UNDETERMINED，不创建可评分 Trigger Event。

Heartbeat 必须区分：
- scan_completed_zero_triggers
- scan_failed_or_missing

稀有 Playbook 长时间没有触发是正常情况，不等于系统故障。

## 8. Kill Switch

全局和单 Playbook 都必须支持：
- notifications_enabled
- ledger_enabled
- enabled

Kill Switch 不删除任何旧记录。

即使停止新 Trigger 记账：
- audit / heartbeat / correction 仍继续工作。
- System Center 必须显示人为暂停状态及变更时间。

## 9. Trigger Ledger / Audit / Discipline

原始私有数据：
- Trigger Ledger
- Outcome Ledger
- Audit Log
- Correction Events
- Discipline Ledger

旧记录 append-only。

公共仓库只发布：
- daily ledger head hash
- schema version
- record count
- verification status
- approved sanitized scorecard

私有内容第一次写入前必须位于私有存储；禁止先进入公开 Git 历史再迁移。

## 10. NO_CHASE 反事实口径

NO_CHASE 不与 Opportunity Scorecard 混算。

第一版反事实固定为：
- planned_reference：原 Trigger 的参考入场价格。
- chase_reference：首次进入 NO_CHASE 状态当日收盘价。
- 分别计算后续 5/20 日 return、MAE、MFE。
- Discipline Score 关注“追高价相对原计划价是否带来更差的未来收益/风险”。

在看到实际成绩前不得改变该定义。

## 11. Outcome 与基准

主要入场口径：
- signal-day close。

执行近似对照：
- next-trading-session open。

基准：
- 个股/纳指类默认 QQQ。
- broad-market regime 类默认 SPY。
- benchmark 在事件创建时冻结。

无条件基准：
同一标的、同一 horizon、同一统计区间内所有可用交易日的 forward return 分布。

必须报告：
- raw_n
- effective_n
- independent signal dates
- unconditional baseline
- lift
- absolute return
- benchmark excess return
- MAE / MFE
- confidence interval

只有真实概率预测才能计算 Brier / calibration。

## 12. Evidence Provenance

Replay 永远与 Forward 分开。

老规则（例如既有 TQQQ、核心 ETF 回撤规则）因为制定时已见过部分历史，Replay 标记：
- historical_replay_post_rule_design

不得称为真正 OOS。

只有规则冻结之后新增的 Forward 记录属于：
- forward_out_of_sample

## 13. Promotion / Demotion 预注册框架

在查看相关 Forward 成绩前冻结具体数值。

框架要求：
- 最低 effective_n。
- 最低独立信号日数。
- 最低观察跨度。
- 与 unconditional baseline 的差异。
- 风险/MAE 不恶化。
- 稀有纪律型规则允许长期保持“纪律工具，非统计结论”。

当前候选门槛（未最终冻结，不得用于自动晋级）：
- effective_n >= 30
- independent signal dates >= 20
- observation span >= 6 months
- lift 95% CI lower bound > 0
- MAE not worse than baseline

达到门槛也仅进入 human review；Production 不自动修改。

## 14. Range / Support

V6.10b 的 Estimated Volume Profile / Range Intelligence 仅是 Research Evidence。

在 V6.11 完成与随机/普通价格位、均线等对照检验前：
- 不参与 Production Trigger。
- 不改变正式 Playbook。
- 不因图形“看起来有效”而晋级。

SOFI 不建立专属一级 Playbook；只有可泛化并验证后的 Range / Box 规则才可申请成为未来通用 Playbook。

## 15. 验收与回滚

V6.9.x：
- 全量 QA 通过。
- Build Manifest 包含 component_versions。
- APP_VERSION 与组件版本规则明确。
- 根目录无 legacy UPGRADE 文档、pycache、临时 patch。
- Playbook Spec 与 Trigger Ledger Spec 冻结。

V6.10a：
- 缺失/过期/拆股一致性失败 => UNDETERMINED。
- 修改规则配置必然改变 rule_hash。
- 同一市场日重复执行幂等。
- 篡改旧账本可被 verify 检测。
- Heartbeat 能发现应运行而未运行。
- Cloud 与 Private Playbook 不混。
- 私有字段不进入公开输出。
- 任一新模块失败不阻断网站日常发布。

回滚：
- 先 Kill Switch 停通知或新 Trigger 记账。
- 代码回退到上一稳定 commit。
- Ledger 永不回滚或重写；问题通过 correction / annotation 追加。
- audit/heartbeat 保持运行。

## 16. V6.10a 之后

V6.10b：Range Research、四级提示、Browser Private Guardrail。  
V6.11：Replay、Statistical Honesty、Range 对照验证。  
V6.12：Decision Journal、Missed/False Positive Cost、Private Options Outcome。  
V6.13：Challenger、Promotion/Demotion、Method Rule Compiler。  
V6.14：Action Routing / Execution Board。
