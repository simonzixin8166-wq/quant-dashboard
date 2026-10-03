# V4.3.2 · Trend Pulse 历史验证工具

本版本不改变 Trend Pulse 实盘评分公式，只新增独立的历史事件研究工具。

## 新增
- `scripts/backtest_trend_pulse.py`
- `.github/workflows/trend-pulse-backtest.yml`
- `tests/test_trend_pulse_backtest.py`

## 回测对象
IREN / NVDA / ORCL / TSLA，默认最近 5 年日线。

## 事件
- 趋势启动
- 二次启动
- 趋势退潮

## 前瞻周期
5 / 10 / 20 / 60 个交易日。

## 防止未来函数
周线 bias 在每一个历史交易日都只使用当日以及之前的日线重新计算；不会使用当周未来交易日。

## 输出
GitHub Action 运行后生成：
- `docs/research/trend_pulse_backtest.json`
- `docs/research/trend_pulse_backtest.md`
- `docs/research/trend_pulse_events.csv`
- `docs/research/trend_pulse_summary.csv`

结果同时与同一股票所有可用交易日的同期 forward return baseline 对比。
