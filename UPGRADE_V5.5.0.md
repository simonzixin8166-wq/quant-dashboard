# myAlphaView V5.5.0 — Autonomous Investment Research Agent

## Goal

V5.5 moves Myalpha View from a passive analysis tool toward an autonomous research assistant.

The system is expected to:
- wake up on scheduled or meaningful market changes;
- scan covered holdings and watchlist assets without waiting for a user question;
- identify material changes;
- explain why the change matters;
- produce a clear timing plan: today / tomorrow / continue monitoring;
- keep a research audit trail;
- never place orders automatically.

## Two-brain architecture

### Public Research Agent
Runs in GitHub Actions and only uses information safe for public static outputs.

Inputs:
- docs/data.json
- V5.4 Learning Engine
- macro context
- Trend Pulse
- watchlist / core ETF state

Output:
- docs/research/autonomous_agent.json

Responsibilities:
- change detection;
- watchlist attention ranking;
- anomaly discovery inside the currently covered universe;
- today / tomorrow / quiet timing classification;
- contradiction-aware research reminders.

### Private Position Agent
Runs only in the authenticated browser.

Inputs:
- Supabase RLS-protected options_positions;
- Alpaca option quotes;
- bid / ask / mid;
- Delta / IV / DTE;
- current P&L;
- known macro events.

Responsibilities:
- scan every open option position;
- calculate remaining position value;
- identify profit-capture, expiry, assignment and liquidity conditions;
- generate explicit research plans such as:
  - 今天优先平仓
  - 今天评估展期
  - 明天复查
  - 继续持有并自动监控

Private positions are never written into public docs/data.json or autonomous_agent.json.

## Attention levels

- Quiet: record only; do not disturb the investor.
- Watch: place into the next review queue.
- Review: investigate today and explain the evidence.
- Action Required: give a clear current plan and timing.

The system must always explain:
1. what changed;
2. why it matters;
3. what the current plan is;
4. when to act or re-check;
5. what evidence would invalidate the plan.

## V5.5 Phase 1 implementation

Implemented:
- autonomous_research_agent.py;
- public watchlist change detector;
- anomaly discovery for the currently covered universe;
- autonomous_agent.json;
- private options Position Agent;
- all-position scan through Supabase + Alpaca;
- remaining profit / DTE / Delta / IV / spread-aware option prompts;
- Agent Attention Center on the dashboard;
- Daily Dashboard Update integration;
- deployment manifest integration;
- Autonomous QA coverage;
- deterministic contract tests.

## Option examples

For a profitable short put, the Position Agent may produce:

- Today: prioritize closing if most of the premium has already been captured and execution spread is reasonable.
- Tomorrow: re-check if the remaining reward is small but today's bid/ask spread is abnormally wide.
- Continue: hold when the position still has meaningful remaining reward and no expiry/event risk condition is triggered.

This is research guidance only. It does not submit orders.

## Discovery roadmap

Phase 1 only discovers abnormal moves in the market universe already covered by Myalpha View.

The next V5.5 expansion will attach broader event discovery sources:
- SEC filings;
- company investor-relations releases;
- FDA / clinical biotech events;
- earnings / guidance events;
- broader abnormal price and volume scanning;
- news clustering and event attribution;
- options-flow anomaly inputs where reliable data is available.

All of these feed the same Attention Engine rather than creating separate noisy alert lists.

## Guardrails

The autonomous agent may:
- research;
- classify;
- prioritize;
- explain;
- schedule re-checks;
- propose a plan;
- learn from outcomes.

It may not:
- place trades;
- change core QQQM/VGT/QLD thresholds by itself;
- expose private positions in public static files;
- convert a news headline or blogger opinion directly into a trading rule;
- treat a large price move as proof of a buy signal.
