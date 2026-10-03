# myAlphaView V4.3.1 — Trend Pulse Data Integrity

- Trend Pulse research guidance is gated by input integrity.
- Twelve Data is the primary daily OHLC source; Yahoo Finance is used as a batch secondary close/date cross-check.
- PASS requires valid OHLC, current data, at least 220 daily bars, and a latest-close mismatch no greater than 1.5%.
- CHECK renders descriptive metrics but suppresses research guidance.
- FAIL suppresses Trend Pulse conclusions.
- Each symbol now includes analysis, risk watch, research guidance, and explicit validation status.
