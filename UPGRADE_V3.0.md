# myAlphaView V3.0 · 一次性升级说明

V3.0 以决策效率、口径一致和数据可解释性为核心。本版本基于已通过回归测试的 V2.9 内部基线一次性完成，不要求先安装 V2.9。

## 最终界面

- 首页压缩为“市场与风险驾驶舱”，首屏直接显示核心指标、风险待办和数据状态。
- 个股观察池固定为7个决策列，开高低、YTD高点和日线日期折叠在名称下方。
- 个股状态使用固定优先级：已触发、接近策略价、超卖观察、趋势偏弱、过热、正常观察。
- 个股可按状态筛选，按策略价距离、YTD回撤或RSI排序；移动端自动切换为决策卡片。
- 指数模块分为核心指数、卫星及杠杆、另类资产。
- 只有通过历史ATH校验并配置 `CORE_TIERS` 的资产才产生正式触发价。
- 无三档策略资产明确显示“不参与核心ETF加仓信号”。
- 策略卡片合并当前状态、下一档触发价、行动说明和该资产预留资金。

## 保持稳定的部分

- Alpaca Indicative 期权报价链路不变。
- Supabase 私有持仓、策略价和预算表结构不变。
- `options-market`、`market-snapshot` Edge Function 无需重新部署。
- 期权生命周期、年化ROC、休市报价和手动报价降级继续保留。
- 本次没有新增数据库迁移，也不需要执行SQL。

## GitHub网页更新

不需要先上传V2.9。解压完整V3.0包后，按原目录覆盖仓库。若选择逐个更新，至少覆盖：

1. `scripts/fetch_and_build.py`
2. `docs/index.html`
3. `docs/assets/dashboard-v2.2.js`
4. `docs/assets/dashboard-v2.2.css`
5. `docs/assets/strategy-budget.js`
6. `tests/test_build_contract.py`
7. `tests/test_decision_ui.py`
8. `.github/workflows/daily.yml`
9. `OPTIONS_V2_SETUP.md`
10. `UPGRADE_V3.0.md`

提交后运行一次 `Daily Dashboard Update`。Action成功后强制刷新浏览器，确认页面源代码包含 `data-app-version="3.0"`。

## 验收重点

- 个股表默认只有7列。
- VOO三档阈值为 `7.5% / 10.0% / 15.0%`。
- 黄金、比特币和SMH不会产生正式核心ETF加仓信号。
- 数据不可用时显示不可用，不参与评分或触发。
- 手机端观察池为卡片布局，不依赖横向滚动。
