#!/usr/bin/env python3
"""Master Execution Plan: validate docs/development/master_plan.json and render MASTER_EXECUTION_PLAN.md (#133 6117671408).

  python scripts/master_plan.py validate   # exit 1 on missing required tasks / bad fields
  python scripts/master_plan.py render     # rewrite the Markdown from the JSON (the JSON is the source of truth)
Hand-maintained from real PRs and runs; its counts are project-management numbers, never learning metrics.
"""
from __future__ import annotations
import json, sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PLAN = ROOT / "docs" / "development" / "master_plan.json"
MD = ROOT / "docs" / "development" / "MASTER_EXECUTION_PLAN.md"
ISSUE = "https://github.com/simonzixin8166-wq/quant-dashboard/issues/133#issuecomment-"
REQUIRED = {"P0-01", "P0-02", "P0-04", "P0-05", "P0-06", "B1-01", "B1-02", "D-01", "D-02", "D-03", "D-04", "D-05", "D-06", "D-07",
            "B2-01", "B2-02", "B2-03", "B4-01", "B4-02", "B4-03", "B3-01", "M-01", "M-02", "M-03", "M-04", "W-01"}
FIELDS = ("id", "title", "area", "priority", "status", "stages", "instructions", "depends_on", "evidence", "acceptance", "next", "last_verified")


def load():
    return json.loads(PLAN.read_text(encoding="utf-8"))


def validate(plan):
    errs = []
    ids = [t["id"] for t in plan["tasks"]]
    if len(ids) != len(set(ids)):
        errs.append("duplicate task ids")
    missing = REQUIRED - set(ids)
    if missing:
        errs.append(f"required tasks missing: {sorted(missing)}")
    known_instr = {i["id"] for i in plan["instructions"]}
    for t in plan["tasks"]:
        for f in FIELDS:
            if f not in t:
                errs.append(f"{t.get('id')}: missing field {f}")
        if t.get("status") not in plan["statuses"]:
            errs.append(f"{t['id']}: bad status {t.get('status')}")
        if not set(t.get("stages", [])) <= set(plan["stages"]):
            errs.append(f"{t['id']}: bad stage")
        if t.get("status") == "Done" and not (t["evidence"].get("prs") or t["evidence"].get("runs")):
            errs.append(f"{t['id']}: Done without evidence")
        if t.get("status") == "Done" and "code_merged" not in t.get("stages", []) and t["evidence"].get("prs"):
            errs.append(f"{t['id']}: Done with PRs but not code_merged")
        if t.get("status") == "Waiting" and not (t.get("waiting_for") or t["area"] == "Owner decisions"):
            errs.append(f"{t['id']}: Waiting without waiting_for")
        if t.get("status") == "Blocked" and not t.get("blocked_by"):
            errs.append(f"{t['id']}: Blocked without blocked_by")
        if "oos_validated" in t.get("stages", []):
            errs.append(f"{t['id']}: oos_validated claimed — learning stays UNPROVEN until matured out-of-sample evidence exists")
        for i in t.get("instructions", []):
            if i not in known_instr:
                errs.append(f"{t['id']}: unknown instruction {i}")
        for d in t.get("depends_on", []):
            if d not in ids:
                errs.append(f"{t['id']}: unknown dependency {d}")
    for i in plan["instructions"]:
        if not any(i["id"] in t.get("instructions", []) for t in plan["tasks"]):
            errs.append(f"instruction {i['id']} is not mapped to any task")
    return errs


def render(plan):
    c = Counter(t["status"] for t in plan["tasks"])
    L = [f"# {plan['title']}", "",
         f"Source of truth: `docs/development/master_plan.json` (this file is rendered by `scripts/master_plan.py render`). "
         f"Last updated {plan['last_updated']}. Issue: {plan['issue']}. Charter: {plan['charter']}.", "",
         "Status counts: " + " · ".join(f"{s} {c.get(s, 0)}" for s in plan["statuses"] if c.get(s)), "",
         "Stages per task: instruction_published → claude_acked → code_merged → schedule_verified → oos_validated "
         "(oos_validated is never claimed while Learning is UNPROVEN).", "",
         "## Working method", "",
         "Unified ledger → continuous development by dependency → batch acceptance → update remaining tasks → next batch. "
         "Every new owner instruction is added here first (mapped to tasks, superseded items marked), never silently dropped.", "",
         "## Guardrails", ""] + [f"- {g}" for g in plan["guardrails"]] + ["",
         "## Execution capability (truthful limits)", ""] + [f"- **{k}**: {v}" for k, v in plan["execution_capability"].items()] + ["",
         "## Owner instructions", "", "| comment | summary | status |", "|---|---|---|"]
    L += [f"| [{i['id']}]({ISSUE}{i['id']}) | {i['summary']} | {i['status']} |" for i in plan["instructions"]]
    order = {"Blocked": 0, "In progress": 1, "Waiting": 2, "Not started": 3, "Done": 4, "Superseded": 5}
    for area in dict.fromkeys(t["area"] for t in plan["tasks"]):
        L += ["", f"## {area}", "", "| ID | task | status | stages | depends on | evidence (PR / run) | acceptance | next / waiting / blocked | verified |", "|---|---|---|---|---|---|---|---|---|"]
        for t in sorted((x for x in plan["tasks"] if x["area"] == area), key=lambda x: (order.get(x["status"], 9), x["id"])):
            ev = "; ".join(t["evidence"].get("prs", []) + t["evidence"].get("runs", [])) or "—"
            nxt = t.get("blocked_by") and f"**blocked:** {t['blocked_by']}" or t.get("waiting_for") and f"{t['next']} (waiting: {t['waiting_for']})" or t["next"]
            if t.get("disclosure"):
                nxt += f" — *disclosure:* {t['disclosure']}"
            L.append(f"| {t['id']} | {t['title']} | **{t['status']}** | {', '.join(s.replace('instruction_published','published').replace('claude_acked','acked').replace('code_merged','merged').replace('schedule_verified','schedule✓') for s in t['stages'])} | "
                     f"{', '.join(t['depends_on']) or '—'} | {ev} | {t['acceptance']} | {nxt} | {t['last_verified']} |")
    L += ["", "Engineering QA PASS ≠ Learning PASS. **Learning UNPROVEN / FINAL=NO.**", ""]
    return "\n".join(L)


def main(argv):
    plan = load()
    errs = validate(plan)
    if errs:
        print("\n".join(errs)); return 1
    if argv[1:2] == ["render"]:
        MD.write_text(render(plan), encoding="utf-8")
    c = Counter(t["status"] for t in plan["tasks"])
    print(f"master plan OK: {len(plan['tasks'])} tasks — " + ", ".join(f"{k} {v}" for k, v in sorted(c.items())))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
