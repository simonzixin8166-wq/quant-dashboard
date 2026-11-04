#!/usr/bin/env python3
"""C3 (GPT #133 6621145320): smoke / development / blind question sets are disjoint, and no blind answer exists in
the repo. Prints counts and hashes only, never question or answer text of the blind set.

Disjointness keys: question_id, and sha256 of the canonical question text (NFC, CRLF->LF, whitespace collapsed,
casefolded). The blind set contributes only its committed per-question text hashes (blind_set_hashes.json); while it
is BLOCKED (not authored) it contributes nothing and the check reports BLOCKED for the blind side.
"""
import hashlib
import json
import re
import sys
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
QS = ROOT / "research" / "specs" / "retrieval" / "question_sets"
BLIND = ROOT / "research" / "specs" / "retrieval" / "blind_set_hashes.json"
ANSWER_KEYS = {"expect", "abstain_code", "required_doc_ids", "forbidden_doc_ids", "gold", "gold_answer", "answer"}


def canon_text(t: str) -> str:
    t = unicodedata.normalize("NFC", t.replace("\r\n", "\n").replace("\r", "\n"))
    return re.sub(r"\s+", " ", t).strip().casefold()


def text_hash(t: str) -> str:
    return hashlib.sha256(canon_text(t).encode("utf-8")).hexdigest()


def check_disjoint(sets: dict) -> list:
    """sets: name -> list of (question_id, text_hash). Returns a list of collisions (empty = disjoint)."""
    out, seen_id, seen_h = [], {}, {}
    for name, items in sets.items():
        ids_here = set()
        for qid, h in items:
            if qid is not None:
                if qid in ids_here:
                    out.append(("duplicate_id_within_set", name, qid))
                ids_here.add(qid)
                if qid in seen_id and seen_id[qid] != name:
                    out.append(("id_across_sets", seen_id[qid], name, qid))
                seen_id.setdefault(qid, name)
            if h in seen_h and seen_h[h] != name:
                out.append(("text_across_sets", seen_h[h], name, h[:12]))
            seen_h.setdefault(h, name)
    return out


def load_sets():
    sets = {}
    for f in sorted(QS.glob("*.json")):
        d = json.loads(f.read_text(encoding="utf-8"))
        assert d.get("set") in {"smoke", "development"}, f"{f.name}: only smoke/development sets may live in the repo"
        for q in d["questions"]:
            assert not (ANSWER_KEYS & set(q)), f"{f.name}:{q.get('question_id')} carries answer fields"
        sets[d["version"]] = [(q["question_id"], text_hash(q["text"])) for q in d["questions"]]
    b = json.loads(BLIND.read_text(encoding="utf-8"))
    blind_status = "BLOCKED" if b.get("frozen_at") is None else "FROZEN"
    if blind_status == "FROZEN":
        for k in ("questions_sha256", "answers_sha256", "owner_authorization", "question_text_hashes"):
            assert b.get(k), f"blind set frozen without {k}"
        sets[b["version"]] = [(None, h) for h in b["question_text_hashes"]]
    return sets, blind_status


YAML_BLIND = re.compile(r"(?mi)^\s*[\"']?set[\"']?\s*[:=]\s*[\"']?blind[\"']?\s*,?\s*$")
ANSWER_LINE = re.compile(r"(?mi)^\s*[-*]?\s*[\"']?(?:" + "|".join(sorted(ANSWER_KEYS)) + r")[\"']?\s*[:=]")


def answer_hashes() -> set:
    """Per-answer canonical text hashes, committed only after the blind set is frozen (none today)."""
    b = json.loads(BLIND.read_text(encoding="utf-8"))
    return set(b.get("answer_text_hashes") or [])


def repo_has_blind_answers(root: Path = None) -> list:
    """kr-0.3.2 (GPT 6624784358 C3): every UTF-8 file in the repo (Markdown, text, YAML, code, logs, JSON/JSONL), not
    only JSON: (1) blind_answers* file names; (2) JSON/JSONL objects with set=blind carrying answer fields; (3) any
    text file that marks itself set: blind and also has answer-key lines; (4) once answer hashes are committed, any
    line whose canonical text hash equals a blind answer hash."""
    root = root or ROOT
    hits, ah = [], answer_hashes()
    for p in root.rglob("*"):
        if ".git" in p.parts or not p.is_file():
            continue
        rel = str(p.relative_to(root))
        if re.match(r"(?i)blind[_-]?answers?", p.name):
            hits.append(rel)
            continue
        if p.stat().st_size > 30_000_000 or p == BLIND:
            continue
        try:
            txt = p.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue  # binaries are covered by the privacy gate's binary review
        if ah and any(text_hash(line) in ah for line in txt.splitlines() if line.strip()):
            hits.append(rel)
            continue
        if "blind" not in txt:
            continue
        if p.suffix in (".json", ".jsonl"):
            try:
                docs = [json.loads(x) for x in txt.splitlines() if x.strip()] if p.suffix == ".jsonl" else [json.loads(txt)]
            except ValueError:
                docs = []
            stack, found = list(docs), False
            while stack and not found:
                x = stack.pop()
                if isinstance(x, dict):
                    if x.get("set") == "blind" and (ANSWER_KEYS & set(x) or any(isinstance(v, list) and v and isinstance(v[0], dict) and ANSWER_KEYS & set(v[0]) for v in x.values())):
                        found = True
                    stack.extend(x.values())
                elif isinstance(x, list):
                    stack.extend(x)
            if found:
                hits.append(rel)
                continue
        if YAML_BLIND.search(txt) and ANSWER_LINE.search(txt):
            hits.append(rel)
    return hits


if __name__ == "__main__":
    sets, blind_status = load_sets()
    col = check_disjoint(sets)
    assert not col, col
    hits = repo_has_blind_answers()
    assert not hits, f"blind answers found in the repo: {hits}"
    # negative tests: a duplicated question across sets must be caught, by text (even reformatted) and by id
    neg_text = check_disjoint({"smoke": [("S-1", text_hash("LITE 在 11/2 前一天怎么判断"))],
                               "development": [("D-1", text_hash("  lite 在 11/2   前一天怎么判断\r\n"))]})
    neg_id = check_disjoint({"smoke": [("Q-7", text_hash("a"))], "development": [("Q-7", text_hash("b"))]})
    neg_blind = check_disjoint({"smoke": [("S-1", text_hash("同一题"))], "blind_v1": [(None, text_hash("同一题"))]})
    assert neg_text and neg_text[0][0] == "text_across_sets", neg_text
    assert neg_id and neg_id[0][0] == "id_across_sets", neg_id
    assert neg_blind and neg_blind[0][0] == "text_across_sets", neg_blind
    probe = ROOT / "tests" / "_tmp_blind_probe"
    try:  # negative: a planted blind-answer file (by name, and by content) must be found
        probe.mkdir(exist_ok=True)
        (probe / "blind_answers_v1.json").write_text("[]", encoding="utf-8")
        (probe / "leak.json").write_text(json.dumps({"set": "blind", "questions": [{"question_id": "B-1", "expect": "answer"}]}), encoding="utf-8")
        (probe / "leak.md").write_text("# notes\nset: blind\n- question_id: B-2\n  expect: answer\n", encoding="utf-8")
        (probe / "leak.yaml").write_text("set: 'blind'\nquestions:\n  - gold_answer: x\n", encoding="utf-8")
        (probe / "leak.log").write_text("run 1\n\"set\": \"blind\",\n\"answer\": \"x\"\n", encoding="utf-8")
        (probe / "ok.md").write_text("The blind set stays BLOCKED until it is authored outside the repo.\n", encoding="utf-8")
        found = repo_has_blind_answers()
        for leak in ("blind_answers_v1.json", "leak.json", "leak.md", "leak.yaml", "leak.log"):
            assert any(f.endswith(leak) for f in found), (leak, found)
        assert not any(f.endswith("ok.md") for f in found), found
        # once per-answer hashes are committed, a pasted answer line in any file is found
        real_ah = answer_hashes
        answer_hashes = lambda: {text_hash("The secret answer is 42")}
        (probe / "pasted.py").write_text("x = 1\n   the SECRET answer   is 42  \n", encoding="utf-8")
        assert any(f.endswith("pasted.py") for f in repo_has_blind_answers()), "answer-hash leak not found"
        answer_hashes = real_ah
    finally:
        for f in probe.glob("*"):
            f.unlink()
        probe.rmdir()
    assert not repo_has_blind_answers()
    print(json.dumps({"sets": {k: len(v) for k, v in sets.items()}, "blind_status": blind_status,
                      "collisions": 0, "blind_answer_files_in_repo": 0,
                      "smoke_text_hashes_sha256": hashlib.sha256("".join(h for _, h in sets.get("smoke_v1", [])).encode()).hexdigest(),
                      "negative_tests": "text / id / blind-hash duplicates; planted blind-answer leaks by name, JSON, Markdown, YAML, log and (once frozen) answer hash all detected"}, ensure_ascii=False))
    print(f"PASS question-set isolation (blind side {blind_status}: not authored yet, nothing to compare)")
    sys.exit(0)
