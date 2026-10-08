"""P2-11 consumer: >1 MiB feed via raw/blob, manifest verification, retries, fail-closed."""
import base64, hashlib, json, sys, urllib.error
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import source_intelligence_engine as si

def feed_bytes(n, updated="2026-10-08T00:00:00Z", extra=None):
    recs = [{"id": f"r{i}", "title": "t", "text": "x" * 1700} for i in range(n)] + (extra or [])
    return json.dumps({"version": 1, "updated_at": updated, "records": recs}, ensure_ascii=False, indent=2).encode()

def manifest_for(payload):
    d = json.loads(payload)
    return json.dumps({"version": 1, "feed_updated_at": d["updated_at"], "record_count": len(d["records"]),
                       "content_sha256": hashlib.sha256(payload).hexdigest()}).encode()

GOOD = feed_bytes(700)
assert len(GOOD) > 1024 * 1024
MAN = manifest_for(GOOD)

class Net:
    """Scripted fake network: route -> bytes | Exception | callable."""
    def __init__(self, routes):
        self.routes, self.calls = routes, []
    def __call__(self, url, headers):
        self.calls.append(url)
        for key, val in self.routes.items():
            if key in url:
                v = val() if callable(val) else val
                if isinstance(v, Exception):
                    raise v
                return v
        raise urllib.error.HTTPError(url, 404, "nf", None, None)

def blob_routes(feed, man=MAN):
    tree = {"tree": [{"path": "state/research_feed.json", "sha": "F"}, {"path": "state/research_feed_manifest.json", "sha": "M"}]}
    b = lambda p: json.dumps({"content": base64.b64encode(p).decode()}).encode()
    r = {"/git/ref/heads/main": json.dumps({"object": {"sha": "C1"}}).encode(), "/git/trees/C1": json.dumps(tree).encode(),
         "/git/blobs/F": b(feed)}
    if man is not None:
        r["/git/blobs/M"] = b(man)
    return r

# 1. >1 MiB via raw with a verifying manifest.
d = si.fetch_feed(baseline=700, get=Net({"research_feed_manifest.json": MAN, "research_feed.json": GOOD}))
assert d["_fetch_path"] == "raw" and d["_integrity"]["manifest_status"] == "verified" and d["_integrity"]["record_count"] == 700

# 2. raw 200 but invalid JSON -> independent blob fallback (pinned commit) succeeds.
d = si.fetch_feed(get=Net({"raw.githubusercontent.com/simonzixin8166-wq/wxc-bot/main/state/research_feed_manifest": MAN,
                           "raw.githubusercontent.com/simonzixin8166-wq/wxc-bot/main/state/research_feed.json": b"{\"records\": [",
                           **blob_routes(GOOD)}))
assert d["_fetch_path"] == "git_blob" and d["_integrity"]["commit"] == "C1" and d["_integrity"]["manifest_status"] == "verified"

# 3. raw truncated/torn content that contradicts a same-timestamp manifest -> rejected, blob used.
torn = feed_bytes(699)
torn = json.dumps(dict(json.loads(torn), updated_at="2026-10-08T00:00:00Z")).encode()
d = si.fetch_feed(get=Net({"raw.githubusercontent.com/simonzixin8166-wq/wxc-bot/main/state/research_feed_manifest": MAN,
                           "raw.githubusercontent.com/simonzixin8166-wq/wxc-bot/main/state/research_feed.json": torn,
                           **blob_routes(GOOD)}))
assert d["_fetch_path"] == "git_blob"

# 4. Both paths fail (raw corrupt, blob API down) -> fail closed, nothing returned.
try:
    si.fetch_feed(get=Net({"raw.githubusercontent.com": b"not json", "api.github.com": urllib.error.URLError("down")}))
    raise AssertionError("must fail closed")
except RuntimeError as e:
    assert "fail closed" in str(e) and "raw:" in str(e) and "git_blob:" in str(e)

# 5. Shrink vs last good count -> both paths reject -> fail closed.
small = feed_bytes(650)
try:
    si.fetch_feed(baseline=700, get=Net({"research_feed_manifest.json": manifest_for(small), "research_feed.json": small,
                                         **blob_routes(small, manifest_for(small))}))
    raise AssertionError("shrink must fail closed")
except RuntimeError as e:
    assert "shrink:700->650" in str(e)

# 6. Duplicate ids / record without id rejected by validate_feed.
for bad, why in ((feed_bytes(3, extra=[{"id": "r0"}]), "duplicate_ids"), (feed_bytes(3, extra=[{"title": "x"}]), "record_without_id")):
    try:
        si.validate_feed(bad); raise AssertionError(why)
    except si.FeedIntegrityError as e:
        assert why in str(e)

# 7. Stale manifest (other snapshot) is tolerated with structural checks; absent manifest = legacy mode.
stale_man = json.dumps({"feed_updated_at": "2026-10-07T00:00:00Z", "record_count": 1, "content_sha256": "x"}).encode()
assert si.validate_feed(GOOD, json.loads(stale_man))["_integrity"]["manifest_status"] == "stale"
assert si.validate_feed(GOOD, None)["_integrity"]["manifest_status"] == "absent"

# 8. Timeout on raw is retried (bounded) before falling back; 4xx is not retried.
real_urlopen = si.urllib.request.urlopen
class Resp:
    def __init__(self, b): self.b = b
    def read(self): return self.b
    def __enter__(self): return self
    def __exit__(self, *a): return False
seq = [TimeoutError("t1"), TimeoutError("t2"), GOOD]
def fake_urlopen(req, timeout=0):
    v = seq.pop(0)
    if isinstance(v, Exception): raise v
    return Resp(v)
si.urllib.request.urlopen = fake_urlopen
try:
    slept = []
    assert si._get_bytes("https://x", {}, attempts=3, sleep=slept.append) == GOOD and slept == [2, 4]
    seq[:] = [urllib.error.HTTPError("u", 404, "nf", None, None), GOOD]
    try:
        si._get_bytes("https://x", {}, attempts=3, sleep=slept.append); raise AssertionError("404 must not retry")
    except urllib.error.HTTPError:
        assert len(seq) == 1
finally:
    si.urllib.request.urlopen = real_urlopen

# 9. main(): integrity failure writes nothing; soft-fail mode exits 0 (Daily keeps publishing market data).
import os, tempfile
with tempfile.TemporaryDirectory() as td:
    out = Path(td) / "source_intelligence.json"
    out.write_text(json.dumps({"counts": {"records": 5}, "feed_integrity": {"record_count": 700}}))
    before = out.read_text()
    si.OUT, real_fetch = out, si.fetch_feed
    si.fetch_feed = lambda baseline=None, get=None: (_ for _ in ()).throw(RuntimeError("research feed unavailable; fail closed: x"))
    try:
        try:
            si.main(); raise AssertionError("hard mode must raise")
        except RuntimeError:
            pass
        os.environ["SOURCE_FEED_SOFT_FAIL"] = "1"
        assert si.main() == 0
        assert out.read_text() == before
    finally:
        os.environ.pop("SOURCE_FEED_SOFT_FAIL", None)
        si.fetch_feed = real_fetch

print("PASS P2-11 consumer: >1MiB raw/blob, manifest verify, shrink/dup guard, retry, fail-closed keeps last good")
