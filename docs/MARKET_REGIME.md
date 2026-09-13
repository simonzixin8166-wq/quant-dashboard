# Market Regime — V1.1 Step 2

## Purpose
Classify the public market environment into:
- RISK-ON / 风险偏好
- NEUTRAL / 中性
- RISK-OFF / 风险规避
- STRESS / 压力

## Score
- Trend: 40 points
  - NASDAQ > 200MA: +20
  - S&P 500 > 200MA: +20
- Risk: 30 points, based on VIX
  - <16: 30
  - 16–<20: 24
  - 20–<25: 16
  - 25–<30: 8
  - >=30: 0
- Momentum: 30 points, based on average RSI
  - >=60: 30
  - 50–<60: 22
  - 40–<50: 12
  - <40: 5

## Regime
- VIX >= 30 → STRESS
- score >= 75 → RISK-ON
- score >= 50 → NEUTRAL
- score < 50 → RISK-OFF

This is a transparent research classification, not an automatic trading recommendation.
