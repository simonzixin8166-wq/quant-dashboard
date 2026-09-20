import importlib.util
import json
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("market_events", ROOT / "scripts" / "update_market_events.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

with tempfile.TemporaryDirectory() as tmp:
    output = Path(tmp) / "market_events.json"
    payload = {
        "updated_at": "2026-09-19T00:00:00+00:00",
        "policy": "official_sources_only",
        "events": [
            {"type":"CPI","title":"CPI","datetime":"2026-10-14T08:30:00-04:00","source":"BLS"},
            {"type":"FOMC","title":"FOMC","datetime":"2026-10-28T14:00:00-04:00","source":"Federal Reserve"},
        ],
    }
    output.write_text(json.dumps(payload), encoding="utf-8")
    before = output.read_bytes()
    module.OUTPUT_PATH = str(output)
    module.fetch_text = lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("simulated 403"))
    module.main()
    assert output.read_bytes() == before, "403 fallback must retain the last verified official calendar byte-for-byte"

print("test_market_events.py: cached-official-calendar fallback passed")
