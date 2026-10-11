#!/usr/bin/env python3
"""Owner-approved promotion of the 2026-09-29 … 2026-10-07 forward candidates (#133, owner decision
2026-10-11 15:44 Asia/Shanghai: "9/29–10/08 的 7 天直接晋升吧，我确认没问题").

10-08 already has server_daily observations captured before the next open, so nothing is promoted for
it. For the other six sessions every reviewed candidate (forward_candidate_review.jsonl) is copied into a
separate promoted ledger, append-only, with:
  capture = "owner_approved_historical_research", promoted = true, attested_forward = false,
  evidence_grade kept from the review (historically_attested_reconstruction → owner_approved_attested group,
  needs_evidence → owner_approved_needs_evidence reference group)
so promoted rows are scored but always reported separately from live server_daily rows; the original
records, late uploads, residual dependencies and the review file are never modified.
"""
from __future__ import annotations
import argparse, hashlib, json, sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import forward_observation_engine as foe  # noqa: E402

REVIEW = ROOT / "research" / "archive" / "forward_candidate_review.jsonl"
APPROVALS = ROOT / "research" / "archive" / "forward_promotions.jsonl"
PROMOTED = ROOT / "research" / "archive" / "forward_observations_promoted.jsonl"
SESSIONS = ("2026-09-29", "2026-09-30", "2026-10-02", "2026-10-05", "2026-10-06", "2026-10-07")
DECISION = {"approver": "owner", "decided_at": "2026-10-11T07:44:00Z", "channel": "chat",
            "statement": "9/29–10/08 的 7 天直接晋升吧，我确认没问题",
            "recorded_in": "https://github.com/simonzixin8166-wq/quant-dashboard/issues/133#issuecomment-6106815337"}
CLASS = "owner_approved_historical_research"
# evidence grade is kept from the review; it decides which statistics group a row may enter
GROUP = {"historically_attested_reconstruction": "owner_approved_attested",   # user-approved historical research sample
         "needs_evidence": "owner_approved_needs_evidence"}                   # reference only, explicit uncertainty


def build(review_rows):
    approvals, promoted = [], []
    for s in SESSIONS:
        cands = [r for r in review_rows if r["session"] == s and r.get("kind") == "forward_candidate_review"]
        if not cands:
            continue
        cls = {}
        for r in cands:
            cls[r["proposed_class"]] = cls.get(r["proposed_class"], 0) + 1
        pid = hashlib.sha256(f"{s}|owner-promotion-1".encode()).hexdigest()[:20]
        approvals.append({"kind": "forward_promotion", "promotion_id": pid, "session": s, **DECISION,
                          "scope": "all reviewed candidates of the session", "candidates": len(cands),
                          "review_ids": [r["review_id"] for r in cands], "proposed_classes_at_approval": cls,
                          "promoted_class": CLASS,
                          "limitations": sorted({d for r in cands for d in r["residual_dependencies"]}) +
                                         ["no independently saved contemporaneous signal content"],
                          "reported_separately_from_live": True})
        for r in cands:
            p = r["reconstructed_payload"]
            promoted.append({
                "event_id": foe.event_id(s, r["symbol"]), "session": s, "symbol": r["symbol"],
                "payload": p, "payload_sha": r["reconstructed_payload_sha"], "rule_hash": foe.RULE_HASH,
                "engine": foe.ENGINE_VERSION, "market": {"mode": r["market_mode"]},
                "market_as_of": r["input"]["market_as_of"], "source_sha": r["input"]["commit"],
                "data_json_blob": r["input"]["data_json_blob"], "published_at": r["published_at"],
                "capture": CLASS, "promoted": True, "attested_forward": False, "genuine_forward": False,
                "evidence_grade": r["proposed_class"], "stats_group": GROUP[r["proposed_class"]],
                "promotion_id": pid, "review_id": r["review_id"],
                "residual_dependencies": r["residual_dependencies"], "matures": r["matures"]})
    return approvals, promoted


def append_new(path, rows, key):
    have = set()
    if path.exists():
        have = {json.loads(x)[key] for x in path.read_text(encoding="utf-8").splitlines() if x.strip()}
    new = [r for r in rows if r[key] not in have]
    with path.open("a", encoding="utf-8") as fh:
        for r in new:
            fh.write(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n")
    return len(new)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true")
    a = ap.parse_args(argv)
    rows = [json.loads(x) for x in REVIEW.read_text(encoding="utf-8").splitlines() if x.strip()]
    approvals, promoted = build(rows)
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    for x in approvals:
        x["recorded_at"] = now
    print(json.dumps({"sessions": len(approvals), "promoted_observations": len(promoted),
                      "eligible": sum(1 for p in promoted if p["payload"]["eligible"])}, ensure_ascii=False))
    if a.write:
        print(json.dumps({"approvals_appended": append_new(APPROVALS, approvals, "promotion_id"),
                          "observations_appended": append_new(PROMOTED, promoted, "event_id")}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
