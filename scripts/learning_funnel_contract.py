#!/usr/bin/env python3
"""P3-12 learning funnel contract: five engines (Market, Fundamental, Event, Options, Decision)
plus External Research as a sixth, separately reported pipeline.

One fixed, layered funnel per engine, counted from the persisted artifacts that already
exist, with a de-duplication key and an evidence path for every layer:

  discovered → canonical_persisted → interpretable → candidate_claim_or_state →
  effective_forward_eligible → independently_matured → benchmark_evaluated →
  downstream_consumer_count → validated_learning_applied

downstream_consumer_count only says which scripts *read* the engine's state; it is not proof
that learning changed anything. validated_learning_applied counts forward-validated methods
that actually changed a ranking/decision; null until provable.

Rules of the contract
- A layer that no artifact can prove is `null` with a reason (not_instrumented), never 0.
- Historical / backfill / descriptive outcomes are reported in a separate `historical`
  block and never flow into effective_forward_eligible or independently_matured.
- Shadow / candidate state is reported separately from Production.
- "Has outcomes" is not "learning active": learning_maturity is `proven` only when forward
  matured AND benchmark_evaluated AND validated_learning_applied are all > 0 (reader counts never qualify).
- Private engines (Decision, private Options) contribute aggregate counts that are already
  published by the sanitized server status; no ids, symbols or amounts are read here.

Read-only: writes docs/research/learning_funnel.json only.
"""
from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
R = ROOT / "research"
D = ROOT / "docs" / "research"
OUT = D / "learning_funnel.json"
LAYERS = ("discovered", "canonical_persisted", "interpretable", "candidate_claim_or_state",
          "effective_forward_eligible", "independently_matured", "benchmark_evaluated",
          "downstream_consumer_count", "validated_learning_applied")


def load(path, default=None):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:
        return {} if default is None else default


def jsonl(path):
    rows = []
    for p in sorted(Path(path).glob("*.jsonl")) if Path(path).is_dir() else [Path(path)]:
        try:
            rows += [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines() if x.strip()]
        except FileNotFoundError:
            pass
    return rows


def rel(p):
    return str(Path(p).relative_to(ROOT))


def layer(count, definition, evidence, dedup=None, reason=None):
    out = {"count": count, "definition": definition, "evidence": evidence}
    if dedup:
        out["dedup_key"] = dedup
    if count is None:
        out["reason"] = reason or "not_instrumented"
    return out


def coverage_domain(name):
    for d in load(D / "data_learning_coverage_audit.json").get("domains") or []:
        if d.get("domain") == name:
            return d
    return {}


def reuse_layer(*domains):
    rows = [coverage_domain(d) for d in domains]
    used = sorted({c for r in rows for c in (r.get("reused_by") or [])})
    known = any(r for r in rows)
    out = layer(len(used) if known else None,
                "distinct downstream scripts that READ this engine's state (readability, not proof of applied learning)",
                rel(D / "data_learning_coverage_audit.json"), "consumer script", None if known else "coverage_domain_missing")
    out["readable_by_downstream"] = used
    return out


def applied_layer():
    return layer(None, "forward-validated methods that actually changed a research ranking or decision",
                 rel(D / "learning_funnel.json"),
                 reason="no forward-validated method exists yet (genuine forward matured = 0); not provable")


def market():
    obs = {r.get("observation_id"): r for r in jsonl(R / "archive" / "macro_regime_observations.jsonl") if r.get("observation_id")}
    pit = [r for r in obs.values() if r.get("point_in_time_capable") is True and r.get("observed_at")]
    sc = load(D / "market_state_outcome_scorecards.json").get("counts") or {}
    mo = load(D / "macro_outcome_memory.json").get("counts") or {}
    ev = rel(R / "archive" / "macro_regime_observations.jsonl")
    return {
        "discovered": layer(len(obs), "macro/regime observations captured", ev, "observation_id"),
        "canonical_persisted": layer(len(obs), "append-only archived observations", ev, "observation_id"),
        "interpretable": layer(sum(1 for r in obs.values() if r.get("regime") and r.get("quality") not in (None, "bad")),
                               "observations with a regime and acceptable input quality", ev, "observation_id"),
        "candidate_claim_or_state": layer(len({r.get("regime_key") for r in obs.values() if r.get("regime_key")}),
                                          "distinct regime state entries", ev, "regime_key"),
        "effective_forward_eligible": layer(len(pit), "point-in-time capable live observations (observed_at recorded)", ev, "observation_id"),
        "independently_matured": layer(int(mo.get("outcomes") or 0), "matured macro outcomes on forward observations",
                                       rel(D / "macro_outcome_memory.json"), "observation_id×horizon"),
        "benchmark_evaluated": layer(int(sc.get("scorecards") or 0), "outcome scorecards vs benchmark",
                                     rel(D / "market_state_outcome_scorecards.json"), "scorecard_id"),
        "downstream_consumer_count": reuse_layer("macro_fred_alfred", "breadth_cross_asset_regime"),
        "validated_learning_applied": applied_layer(),
        "historical": {"market_price_history_mature_60": (coverage_domain("market_price_history").get("evidence") or {}).get("mature_60"),
                       "note": "historical price-event replay; descriptive, not forward learning"},
    }


def fundamental():
    obs = {r.get("observation_id"): r for r in jsonl(R / "archive" / "fundamental_observations.jsonl") if r.get("observation_id")}
    outs = jsonl(R / "archive" / "fundamental_outcomes.jsonl")
    mem = load(D / "company_fundamental_memory.json").get("counts") or {}
    ev = rel(R / "archive" / "fundamental_observations.jsonl")
    return {
        "discovered": layer(int(mem.get("archive_total") or 0), "XBRL facts captured (company_fundamental_memory archive)",
                            rel(D / "company_fundamental_memory.json"), "fact"),
        "canonical_persisted": layer(len(obs), "filing-level observations persisted", ev, "observation_id (accn)"),
        "interpretable": layer(sum(1 for r in obs.values() if r.get("metrics")), "observations with parsed metrics", ev, "observation_id"),
        "candidate_claim_or_state": layer(sum(1 for r in obs.values() if r.get("derived")), "observations with a derived fundamental state", ev, "observation_id"),
        "effective_forward_eligible": layer(None, "observations captured before their outcome window began", ev, "observation_id",
                                            "no capture timestamp on XBRL observations; historical filings are descriptive only"),
        "independently_matured": layer(None, "forward-eligible observations with matured outcomes",
                                       rel(R / "archive" / "fundamental_outcomes.jsonl"), "observation_id",
                                       "depends on effective_forward_eligible, which is not provable"),
        "benchmark_evaluated": layer(None, "outcomes measured against a benchmark", rel(R / "archive" / "fundamental_outcomes.jsonl"),
                                     reason="outcome rows carry raw return_pct only; no benchmark excess recorded"),
        "downstream_consumer_count": reuse_layer("financial_fundamentals_xbrl"),
        "validated_learning_applied": applied_layer(),
        "historical": {"descriptive_outcome_rows": len(outs),
                       "descriptive_matured_observations": len({o.get("observation_id") for o in outs if o.get("matured_at")}),
                       "note": "historical XBRL filings → descriptive/history outcomes, not Forward Edge"},
    }


def event():
    rows = {r.get("uuid") or r.get("archive_id"): r for r in jsonl(R / "archive" / "events") if (r.get("uuid") or r.get("archive_id"))}
    mem = load(D / "event_outcome_memory.json").get("counts") or {}
    ev = rel(R / "archive" / "events")

    def live(r):
        try:
            a = datetime.fromisoformat(str(r.get("archived_at")).replace("Z", "+00:00"))
            p = datetime.fromisoformat(str(r.get("published_at")).replace("Z", "+00:00"))
            return 0 <= (a - p).total_seconds() <= 2 * 86400
        except Exception:
            return False
    return {
        "discovered": layer(len(rows), "news/event items archived", ev, "uuid"),
        "canonical_persisted": layer(len(rows), "append-only monthly event shards", ev, "uuid"),
        "interpretable": layer(sum(1 for r in rows.values() if r.get("title") and r.get("url") and r.get("event_date")),
                               "items with title, url and event date", ev, "uuid"),
        "candidate_claim_or_state": layer(sum(1 for r in rows.values() if r.get("used_in_decision")),
                                          "items admitted as decision context", ev, "uuid"),
        "effective_forward_eligible": layer(sum(1 for r in rows.values() if r.get("used_in_decision") and live(r)),
                                            "decision-context items archived within 48h of publication (live, not backfilled)", ev, "uuid"),
        "independently_matured": layer(int(mem.get("outcomes") or 0), "event outcomes matured",
                                       rel(D / "event_outcome_memory.json"), "uuid×horizon"),
        "benchmark_evaluated": layer(int(mem.get("outcomes") or 0) if load(D / "event_outcome_memory.json").get("benchmark") else None,
                                     "event outcomes scored against the recorded benchmark", rel(D / "event_outcome_memory.json"),
                                     "uuid×horizon", "event outcome memory has no benchmark definition"),
        "downstream_consumer_count": reuse_layer("news_event_evidence"),
        "validated_learning_applied": applied_layer(),
    }


def options():
    obs = jsonl(R / "archive" / "options_opportunity_observations")
    sup = {r.get("observation_id") for r in jsonl(R / "archive" / "options_opportunity_supersessions.jsonl")}
    live = [r for r in obs if r.get("observation_id") not in sup]
    mem = load(D / "options_opportunity_outcome_memory.json").get("counts") or {}
    ctx = load(D / "options_opportunity_context.json")
    priv = load(D / "server_action_status.json").get("option_learning") or {}
    ev = rel(R / "archive" / "options_opportunity_observations")
    return {
        "discovered": layer(len(ctx.get("records_list") or ctx.get("records") or []), "symbols scanned for option opportunity context",
                            rel(D / "options_opportunity_context.json"), "symbol"),
        "canonical_persisted": layer(len({r.get("observation_id") for r in obs}), "opportunity observations persisted (incl. superseded)", ev, "observation_id"),
        "interpretable": layer(len({r.get("observation_id") for r in live}), "observations with aligned price/support inputs (not superseded)", ev, "observation_id"),
        "candidate_claim_or_state": layer(len({(r.get("symbol"), r.get("state")) for r in live}), "distinct symbol×state entries", ev, "symbol×state"),
        "effective_forward_eligible": layer(int(mem.get("observations") or 0), "aligned forward observations eligible for outcome tracking",
                                            rel(D / "options_opportunity_outcome_memory.json"), "observation_id"),
        "independently_matured": layer(int(mem.get("matured") or 0), "matured opportunity outcomes",
                                       rel(D / "options_opportunity_outcome_memory.json"), "observation_id×horizon"),
        "benchmark_evaluated": layer(None, "matured outcomes compared with a benchmark", rel(D / "options_opportunity_outcome_memory.json"),
                                     reason="no matured outcomes yet; benchmark comparison not instrumented"),
        "downstream_consumer_count": reuse_layer("options_opportunity"),
        "validated_learning_applied": applied_layer(),
        "shadow_or_private": {"private_position_state_entries_present": bool(priv.get("observations")),
                              "private_mature_outcomes_present": bool(priv.get("mature_outcomes")),
                              "superseded_legacy_observations": len(sup),
                              "note": "private option positions: aggregate only, from the sanitized server status"},
    }


def presence_layer(flag, definition, evidence):
    """Private engines: the public snapshot only says whether something exists (0/1)."""
    return {"count": None, "presence": bool(flag), "definition": definition, "evidence": evidence,
            "reason": "private engine: public snapshot is presence-only (exact counts stay in the RLS domain)"}


def decision():
    dl = load(D / "server_action_status.json").get("decision_learning") or {}
    ev = rel(D / "server_action_status.json")
    return {
        "discovered": presence_layer(dl.get("persisted"), "operator decisions recorded by the cockpit", ev),
        "canonical_persisted": presence_layer(dl.get("persisted"), "persisted in private operator_decisions (RLS)", ev),
        "interpretable": presence_layer(dl.get("attributed"), "decisions with an attribution label", ev),
        "candidate_claim_or_state": presence_layer(dl.get("with_user_action"), "decisions with a recorded user action", ev),
        "effective_forward_eligible": presence_layer(dl.get("with_user_action"), "user-confirmed actions timestamped before outcomes", ev),
        "independently_matured": layer(None, "user actions with matured outcomes", ev,
                                       reason="decision outcome maturation not yet instrumented"),
        "benchmark_evaluated": layer(None, "decision outcomes vs do-nothing baseline", ev, reason="not_instrumented"),
        "downstream_consumer_count": reuse_layer("decision_journal_user_actions"),
        "validated_learning_applied": applied_layer(),
        "note": "No user actions are inferred; Decision Learning waits for explicit owner confirmation.",
    }


def interpretable_layer(reading):
    """Only records that carry body text count; title-only rows are 'read' but not understood."""
    depth = (load(ROOT / "docs" / "data" / "source_intelligence.json").get("feed_integrity") or {}).get("text_depth")
    if not depth:
        out = layer(None, "records with body text (excerpt or full text) available to Source Reading",
                    rel(ROOT / "docs" / "data" / "source_intelligence.json"), "feed id",
                    "text depth not yet recorded by source_intelligence_engine")
    else:
        out = layer(int(depth.get("excerpt", 0)) + int(depth.get("full_text", 0)),
                    "records with body text available (excerpt ≤360 chars or full text ≥1000); title-only excluded",
                    rel(ROOT / "docs" / "data" / "source_intelligence.json"), "feed id")
        out["text_depth"] = depth
    out["records_processed_by_source_reading"] = int(reading.get("source_records") or 0)
    out["note"] = "processed ≠ understood: most forum rows reach Source Reading as title/excerpt only"
    return out


def external_research():
    store = load(R / "store" / "source_store.json")
    rows = store.get("records") or []
    reading = load(D / "source_reading_memory.json").get("counts") or {}
    health = load(R / "reports" / "forward_intake_health.json").get("counts") or {}
    life = load(D / "source_rule_lifecycle.json").get("counts") or {}
    ev = rel(R / "store" / "source_store.json")
    keys = {r.get("source_key") for r in rows if r.get("source_key")}
    return {
        "discovered": layer(len(keys), "distinct canonical source keys (forum/blog/YouTube)", ev, "source_key"),
        "canonical_persisted": layer(len(rows), "Source Store records (append-only)", ev, "source_key"),
        "interpretable": interpretable_layer(reading),
        "candidate_claim_or_state": layer(int(reading.get("records_with_testable_rules") or 0), "records yielding a testable rule/claim",
                                          rel(D / "source_reading_memory.json"), "source_key"),
        "effective_forward_eligible": layer(sum(1 for r in rows if r.get("effective_forward_eligible") is True),
                                            "genuine forward sources (timestamp-verified live capture)", ev, "source_key"),
        "independently_matured": layer(int(health.get("scoreable_forward_events") or 0), "matured, scoreable genuine-forward events",
                                       rel(R / "reports" / "forward_intake_health.json"), "event_id"),
        "benchmark_evaluated": layer(0 if not int(health.get("scoreable_forward_events") or 0) else None,
                                     "forward events with benchmark excess (0 while nothing has matured)",
                                     rel(R / "reports" / "forward_intake_health.json"), "event_id",
                                     "benchmark excess for forward source events not instrumented"),
        "downstream_consumer_count": reuse_layer("blog_forum_video_sources"),
        "validated_learning_applied": applied_layer(),
        "historical": {"lifecycle_rules_mature_60": (life.get("by_state") or {}).get("mature_60"),
                       "lifecycle_rules_mature_20": (life.get("by_state") or {}).get("mature_20"),
                       "note": "author-rule outcomes on backfill/legacy sources: historical/descriptive, not Genuine Forward"},
    }


def check(engine, f):
    """Funnel sanity: known counts must not increase from candidate→forward→matured→benchmark."""
    issues = []
    chain = ["effective_forward_eligible", "independently_matured", "benchmark_evaluated"]
    vals = [f[k]["count"] for k in chain]
    for (a, va), (b, vb) in zip(zip(chain, vals), zip(chain[1:], vals[1:])):
        if va is not None and vb is not None and vb > va:
            issues.append(f"{b}({vb}) > {a}({va})")
    return issues


def maturity(f):
    m, b, a = (f[k]["count"] for k in ("independently_matured", "benchmark_evaluated", "validated_learning_applied"))
    if m and b and a:
        return "proven_candidate"  # still needs independent review before any production use
    if any(f[k]["count"] for k in ("effective_forward_eligible",)):
        return "forward_collecting"
    if f["candidate_claim_or_state"]["count"]:
        return "unproven_no_forward_samples"
    return "context_only"


def build():
    engines = {"market": market(), "fundamental": fundamental(), "event": event(), "options": options(),
               "decision": decision(), "external_research": external_research()}
    summary = {}
    for name, f in engines.items():
        summary[name] = {"learning_maturity": maturity(f), "funnel_issues": check(name, f),
                         **{k: f[k]["count"] for k in LAYERS}}
    forward_matured = sum((s["independently_matured"] or 0) for s in summary.values())
    return {
        "version": "p3-12.1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "layers": list(LAYERS),
        "contract": {
            "null_means": "not provable from persisted artifacts (reason given); never silently 0",
            "historical_separate": "historical/backfill/descriptive outcomes live under 'historical' and never feed forward layers",
            "maturity_rule": "proven requires forward matured AND benchmark_evaluated AND validated_learning_applied > 0; outcomes or readers alone are not learning",
            "engines": "five engines (market, fundamental, event, options, decision) + external_research reported separately",
            "privacy": "decision/private options: presence-only flags from the sanitized server status; exact counts stay private",
        },
        "summary": summary,
        "engines": engines,
        "tracks": {
            "learning_maturity": "UNPROVEN" if not forward_matured else "COLLECTING",
            "genuine_forward_matured_total": forward_matured,
        },
    }


def main():
    out = build()
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    line = " ".join(f"{k}:{v['learning_maturity']}/fwd={v['effective_forward_eligible']}/mat={v['independently_matured']}"
                    for k, v in out["summary"].items())
    print(f"::notice title=Learning funnel (P3-12)::{out['tracks']['learning_maturity']} {line}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
