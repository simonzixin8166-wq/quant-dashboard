# myAlphaView V4.3.0 — Trend Pulse

## 本次目标
- 网站优先；PWA/APP 不新增功能。
- 降低各模块标题字号，保留正文可读性。
- IREN Daily Brief 改为横向紧凑研究摘要，解决左侧过窄、模块过长。
- 新增 `Trend Pulse V1` 个股趋势跟踪引擎。

## Trend Pulse V1
Trend Pulse 是 myAlphaView 自研指标，借鉴公开的“动态曲线 + 多周期共振”研究理念，但不复制或声称等同于第三方 TCDS / DeepWave 未公开公式。

组成：
- EMA20 / EMA50 趋势结构
- Supertrend(10,3)
- ADX / +DI / -DI
- MACD Histogram
- RSI(14)
- 20日 HH/HL / LH/LL 价格结构
- OBV / MFI（有成交量时）
- 周线趋势共振

输出：-100 ~ +100 连续脉冲、5日/20日斜率、周线状态和七类趋势状态。

## 与现有策略的边界
- Market Regime：全市场风险环境
- Drawdown Engine：ETF 回撤与三档加仓线
- Trend Pulse：个股趋势变化
- Daily Intelligence：新闻/基本面信息
- Options Engine：期权仓位管理

Trend Pulse 不改变任何现有回撤阈值，也不自动下单。
