# V4.7.2 — Daily Action & UI Control Audit

- 重排“今日行动摘要”核心ETF为三行紧凑列表，避免子卡片遮挡。
- 修复“查看期权持仓”跳转，使用稳定的 `openDashboardTab()`。
- Trend Pulse 数据状态与信息按钮分栏，避免“ⓘ”遮挡。
- 私有模式从无功能按钮改为状态标签，消除假按钮。
- 新增 UI 控件静态契约测试，核对页面按钮是否存在事件绑定或明确操作语义。
- 不修改 Trend Pulse、ETF 阈值、期权计算与数据源逻辑。
