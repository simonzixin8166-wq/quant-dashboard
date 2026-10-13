#!/usr/bin/env python3
"""Runtime-only full-text verification of an owner-supplied article file (#133, PR #231 follow-up).

Reads a locally supplied HTML file (never committed), extracts the article body (wenxuecity
`articalContent` block; scripts/styles/navigation/comments excluded), and prints ONLY:
file sha256, paragraph count, body character counts, normalized paragraph-text sha256,
section headings, and one sha256 per paragraph. No article text is written anywhere.

usage: python -I scripts/source_fulltext_verify.py <file.html>   (prints JSON to stdout)
Normalization: each paragraph → whitespace collapsed to single spaces, stripped, NFC; joined with "\\n".
"""
from __future__ import annotations
import hashlib, json, re, sys, unicodedata
from html.parser import HTMLParser

BLOCK = ("p", "br", "div", "h1", "h2", "h3", "h4", "li")


class _Body(HTMLParser):
    def __init__(self):
        super().__init__()
        self.paras, self.cur, self.skip = [], [], 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self.skip += 1
        if tag in BLOCK:
            self.flush()

    def handle_endtag(self, tag):
        if tag in ("script", "style"):
            self.skip -= 1
        if tag in BLOCK:
            self.flush()

    def handle_data(self, data):
        if not self.skip:
            self.cur.append(data)

    def flush(self):
        t = "".join(self.cur).replace("\xa0", " ").strip()
        self.cur = []
        if t:
            self.paras.append(t)


def norm(p):
    return unicodedata.normalize("NFC", re.sub(r"\s+", " ", p).strip())


def extract(raw: str):
    s = raw.index('class="articalContent"')
    s = raw.index(">", s) + 1
    e = raw.index('id="postManageBar"', s)
    e = raw.rfind("<div", s, e)
    p = _Body()
    p.feed(raw[s:e])
    p.flush()
    return p.paras


def verify(path):
    data = open(path, "rb").read()
    raw = data.decode("utf-8", errors="replace")
    paras = extract(raw)
    t = re.search(r'<h1[^>]*class="titleName[^"]*"[^>]*>([^<]+)</h1>', raw)
    ts = re.search(r'<span class="time[^"]*">\(([^)]+)\)</span>', raw)
    return {
        "file_sha256": hashlib.sha256(data).hexdigest(), "file_bytes": len(data),
        "title": t.group(1).strip() if t else None, "page_published_at": ts.group(1) if ts else None,
        "paragraphs": len(paras), "body_chars_with_ws": sum(len(x) for x in paras),
        "body_chars_no_ws": sum(len(re.sub(r"\s", "", x)) for x in paras),
        "normalized_paragraph_sha256": hashlib.sha256("\n".join(norm(x) for x in paras).encode()).hexdigest(),
        "section_headings": [x for x in paras if re.match(r"^[一二三四五六七八九十]+、", x)],
        "paragraph_sha256": [hashlib.sha256(norm(x).encode()).hexdigest()[:16] for x in paras],
        "paragraph_chars": [len(x) for x in paras],
        "extractor": "scripts/source_fulltext_verify.py (articalContent block; script/style excluded)",
    }


if __name__ == "__main__":
    print(json.dumps(verify(sys.argv[1]), ensure_ascii=False, indent=1))
