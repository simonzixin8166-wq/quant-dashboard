#!/usr/bin/env python3
"""ERR-01 / E-11: print the exact command lists CI and Daily run, straight from the workflow files.

    python scripts/dev_check_lists.py v56            # every python/node command of the PR validation workflow
    python scripts/dev_check_lists.py daily-verify   # the 'Verify generated dashboard contract' step of daily.yml

Regenerate the list on every branch before a local run (a list copied from another branch once pointed at
test files that did not exist there). Plain-text parsing on purpose: no PyYAML, which CI does not install (E-03).
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WF = ROOT / ".github" / "workflows"


def v56_commands(text=None):
    text = text if text is not None else (WF / "v56-pr-validation.yml").read_text(encoding="utf-8")
    return [m.group(1).strip() for m in re.finditer(r"^\s+((?:python|node) .+)$", text, re.M)]


def step_run_lines(text, step_name):
    """Lines of a `run: |` block of the step with this exact name (comments and blanks dropped)."""
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if re.match(rf"^\s*- name: {re.escape(step_name)}\s*$", line):
            for j in range(i + 1, min(i + 8, len(lines))):
                m = re.match(r"^(\s*)run: \|\s*$", lines[j])
                if m:
                    indent, out = len(m.group(1)), []
                    for body in lines[j + 1:]:
                        if body.strip() and len(body) - len(body.lstrip()) <= indent:
                            break
                        s = body.strip()
                        if s and not s.startswith("#"):
                            out.append(s)
                    return out
    return []


def daily_verify_commands(text=None):
    text = text if text is not None else (WF / "daily.yml").read_text(encoding="utf-8")
    return step_run_lines(text, "Verify generated dashboard contract")


if __name__ == "__main__":
    which = sys.argv[1] if len(sys.argv) > 1 else "v56"
    cmds = {"v56": v56_commands, "daily-verify": daily_verify_commands}[which]()
    if not cmds:
        sys.exit(f"no commands found for {which}")
    print("set -e")
    print("\n".join(cmds))
