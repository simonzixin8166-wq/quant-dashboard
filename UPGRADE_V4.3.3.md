# V4.3.3 — Trend Pulse 自动验证计划

## 目标
让 Trend Pulse 的当前状态每天随新收盘价更新，同时让 5 年事件研究在每个美股交易日收盘后自动重新验证统计表现。

## 自动化节奏
- `Daily Dashboard Update`：继续负责网站最新行情、Trend Pulse 当前值和页面生成。
- `Trend Pulse 5Y Backtest`：UTC 22:30（北京时间次日 06:30）周一至周五自动执行，也保留手动 `workflow_dispatch`。
- 周末/节假日没有新的完整日K时，回测脚本比较上一次报告中的各标的 `coverage.end`，若全部未变化则不重写报告、不提交无意义更新。

## 数据纪律
- 回测使用 `yfinance(auto_adjust=True)` 的拆股/分红调整日线。
- 历史周线状态逐日 walk-forward 重算，避免未来函数。
- 只统计状态进入日，并保留 10 个交易日同类信号冷却。
- 当前实时/日常 Trend Pulse 与历史有效性统计分开：当前状态每日更新，历史统计只在出现新完成日K后更新。

## 输出
`docs/research/`：
- `trend_pulse_backtest.md`
- `trend_pulse_backtest.json`
- `trend_pulse_events.csv`
- `trend_pulse_summary.csv`
