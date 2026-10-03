# Prediction Ledger V1 Spec — superseded

本早期规格已被 `TRIGGER_LEDGER_V1_SPEC.md` 取代。

原因：V6.10a 将 Forward 记录对象从“泛化预测”收敛为**预注册 Opportunity Playbook 的 Trigger Event**。自由文本研究仍留在 Autonomous Research / Method Memory，不直接进入可评分 Forward Ledger。

历史设计原则仍保留：
- append-only；
- Forward / Replay 分离；
- rule_hash / commit SHA / schema_version；
- minimum data lineage；
- 5/20/60/120 outcome；
- 不回填伪历史预测。

正式实施以 `OPPORTUNITY_PLAYBOOK_V1_SPEC.md` 与 `TRIGGER_LEDGER_V1_SPEC.md` 为准。
