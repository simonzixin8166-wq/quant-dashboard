#!/usr/bin/env python3
"""Learning progress: the charter's four measures, with denominators, on one public page.

Reads only aggregate public files (no positions, no amounts):
  config/understanding_scores.json              1. understanding (frozen tests, measured once per version)
  docs/research/forward_observation_status.json 2. independent judgments recorded
  docs/research/forward_scorecard.json          3. matured, scored outcomes (genuine forward, never pooled)
  docs/research/forward_attribution_weekly.json 4. error attribution
Writes:
  docs/research/learning_progress.json
  research/archive/learning_progress_history.jsonl  one row per NYSE session, append-only (4. trend)

This is a report, not a judge: it never upgrades the learning state. learning_state comes from the forward
files and stays UNPROVEN / FINAL=NO until they say otherwise; a trend needs >= MIN_TREND_WEEKS weeks.
"""
from __future__ import annotations

import json
import math
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCORES = ROOT / "config" / "understanding_scores.json"
OBS = ROOT / "docs" / "research" / "forward_observation_status.json"
CARD = ROOT / "docs" / "research" / "forward_scorecard.json"
ATTR = ROOT / "docs" / "research" / "forward_attribution_weekly.json"
OUT = ROOT / "docs" / "research" / "learning_progress.json"
HIST = ROOT / "research" / "archive" / "learning_progress_history.jsonl"
VERSION = "learning-progress-1.0"
MIN_TREND_WEEKS = 4


def load(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:
        return None


def wilson(k, n, z=1.96):
    if not n:
        return None
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return [round(max(0.0, c - h), 2), round(min(1.0, c + h), 2)]


def ratio(k, n):
    return {"k": k, "n": n, "value": round(k / n, 3) if n else None, "ci95": wilson(k, n)}


def understanding(scores):
    if not scores:
        return {"status": "unavailable", "rows": []}
    sets = scores.get("test_sets") or {}
    rows = []
    for r in scores.get("results") or []:
        m, p, g = r.get("matched"), r.get("pred_pairs"), r.get("gold_pairs")
        if not all(isinstance(x, int) for x in (m, p, g)):
            continue
        rows.append({
            "extractor": r.get("extractor"), "role": r.get("role"), "set": r.get("set"),
            "set_label_zh": (sets.get(r.get("set")) or {}).get("label_zh"),
            "status": r.get("status"), "answered_posts": r.get("answered_posts"),
            "precision": ratio(m, p), "recall": ratio(m, g),
            "measured_at": r.get("measured_at"), "evidence": r.get("evidence"), "note_zh": r.get("note_zh"),
        })
    prod = next((r for r in rows if r["role"] == "production" and r["status"] == "complete"), None)
    return {"status": "ok" if rows else "unavailable", "unit_zh": scores.get("unit_zh"), "test_sets": sets,
            "rows": rows, "production": prod, "dev_only": scores.get("dev_only") or [], "note_zh": scores.get("note_zh")}


def genuine_cells(card, h):
    return [c for c in (card or {}).get("cells") or [] if c.get("group") == "genuine_forward" and c.get("h") == h]


def total(cells, key):
    return sum(int(c.get(key) or 0) for c in cells)


def judgments(obs, card):
    if not obs:
        return {"status": "unavailable"}
    cells = genuine_cells(card, 20)
    return {
        "status": "ok",
        "sessions": obs.get("sessions"), "observations": obs.get("observations"),
        "first_session": obs.get("first_session"), "latest_session": obs.get("latest_session"),
        "continuity": obs.get("continuity"), "gaps": len(obs.get("gaps") or []),
        "matured_20": total(cells, "matured"), "abstain_20": total(cells, "abstain"),
        "independent_episodes_20": total(cells, "independent_episodes"),
        "note_zh": "判断由系统规则在开盘前自动记录（只追加）；“继续观察”是弃权，不计分。不是复述作者观点。",
    }


def experience(obs, card):
    if not card:
        return {"status": "unavailable"}
    cells = genuine_cells(card, 20)
    scored, hits = total(cells, "scored"), total(cells, "hits")
    cats = [{"decision": c.get("decision"), "eligible": c.get("eligible"), "scored": c.get("scored"),
             "hits": c.get("hits"), "abstain": c.get("abstain"), "status": c.get("status")} for c in cells]
    horizons = {}
    for h, row in ((obs or {}).get("horizons") or {}).items():
        horizons[h] = {"matured": row.get("matured_attested"), "earliest_maturity": row.get("earliest_maturity")}
    promoted = [c for c in card.get("cells") or [] if c.get("group") == "promoted" and c.get("h") == 20]
    return {
        "status": "ok", "as_of_session": card.get("as_of_session"),
        "h20": {"matured": total(cells, "matured"), "scored": scored, "hits": hits, "hit_rate": ratio(hits, scored),
                "episode_scored": total(cells, "episode_scored")},
        "horizons": horizons, "categories": cats,
        "categories_reportable": sum(1 for c in cells if c.get("status") != "INSUFFICIENT"),
        "categories_total": len(cells),
        "promoted_separate": {"scored": total(promoted, "scored"), "hits": total(promoted, "hits"),
                              "note_zh": "Owner 批准的历史重建样本，不是真实前瞻，不合并进上面的分母。"},
        "note_zh": "n≥20 只是最低报告门槛，不代表已证明有预测能力；命中率需要按类别、独立样本和到期周数看。",
    }


def reliability(history, attr):
    weeks = sorted({iso_week(r["session"]) for r in history if r.get("session")})
    enough = len(weeks) >= MIN_TREND_WEEKS
    out = {
        "status": "ok" if history else "unavailable",
        "weeks_recorded": len(weeks), "min_weeks": MIN_TREND_WEEKS,
        "trend_state": "DESCRIPTIVE_ONLY" if enough else "INSUFFICIENT",
        "series": history[-60:],
        "note_zh": f"至少 {MIN_TREND_WEEKS} 周的记录才描述趋势；描述趋势也不等于证明能力提升。",
    }
    if attr:
        d = attr.get("denominators_including_qqq_qqqm") or {}
        out["attribution"] = {"sessions": attr.get("sessions"), "scored": d.get("scored"), "misses": attr.get("misses"),
                              "misses_by_primary": attr.get("misses_by_primary"),
                              "coverage": attr.get("attribution_coverage"),
                              "investment_validity": attr.get("investment_validity")}
    return out


def iso_week(session):
    y, w, _ = date.fromisoformat(session).isocalendar()
    return f"{y}-W{w:02d}"


def history_row(u, j, e):
    prod = u.get("production") or {}
    h = e.get("h20") or {}
    return {"session": e.get("as_of_session") or j.get("latest_session"), "observations": j.get("observations"),
            "matured_20": h.get("matured"), "scored_20": h.get("scored"), "hits_20": h.get("hits"),
            "production_recall": (prod.get("recall") or {}).get("value"),
            "production_extractor": prod.get("extractor")}


def read_history(path):
    rows = []
    try:
        for line in Path(path).read_text(encoding="utf-8").splitlines():
            if line.strip():
                rows.append(json.loads(line))
    except FileNotFoundError:
        pass
    return rows


def append_history(path, rows, row):
    """Append-only: one row per session; an existing session is never rewritten."""
    if not row.get("session") or any(r.get("session") == row["session"] for r in rows):
        return rows
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
    return rows + [row]


def build(scores, obs, card, attr, history, hist_path=None, now=None):
    u, j, e = understanding(scores), judgments(obs, card), experience(obs, card)
    history = list(history)
    if hist_path is not None and e.get("status") == "ok" and j.get("status") == "ok":
        history = append_history(hist_path, history, history_row(u, j, e))
    state = (obs or {}).get("learning_state") or "UNPROVEN"
    return {
        "version": VERSION,
        "generated_at": (now or datetime.now(timezone.utc)).isoformat(timespec="seconds"),
        "learning_state": state, "final": (obs or {}).get("final") or "NO",
        "measures": {"understanding": u, "judgments": j, "experience": e, "reliability": reliability(history, attr)},
        "principle_zh": "四项衡量都带分母；缺数据显示“不可用”；开发集不当证据；历史重建不并入真实前瞻；只报告，不升级学习状态。",
    }


def main():
    report = build(load(SCORES), load(OBS), load(CARD), load(ATTR), read_history(HIST), hist_path=HIST)
    j, e = report["measures"]["judgments"], report["measures"]["experience"]
    history = report["measures"]["reliability"]["series"]
    state = report["learning_state"]
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"learning_progress: state={state} obs={j.get('observations')} scored20={(e.get('h20') or {}).get('scored')} "
          f"history={len(history)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
