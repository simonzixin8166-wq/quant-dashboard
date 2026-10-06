from pathlib import Path
import importlib.util
from datetime import datetime, timezone

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location("sa",ROOT/"scripts"/"server_action_engine.py")
sa=importlib.util.module_from_spec(spec);spec.loader.exec_module(sa)

def p(**kw):
    base={"symbol":"TEST","opt_type":"put","strike":100,"expiry":"2099-12-31","status":"open"}
    base.update(kw);return base

q={"underlyingPrice":[120],"bid":[1],"ask":[1.1],"mid":[1.05],"delta":[-.1],"updated":[4102444800]}
r=sa.risk_for(p(),q,[])
assert r["level"]=="l1"
r2=sa.risk_for(p(expiry="2000-01-01"),q,[])
assert r2["level"]=="l3"
r3=sa.risk_for(p(),None,[])
assert r3["level"]=="unknown"

# A valid closing quote must remain usable after hours/weekends; wall-clock age alone is not staleness.
after_close=datetime(2026,10,6,22,0,tzinfo=timezone.utc)  # 18:00 ET
closing_quote={**q,"updated":[datetime(2026,10,6,19,45,tzinfo=timezone.utc).timestamp()]}
assert sa.risk_for(p(),closing_quote,[],now=after_close)["level"]=="l1"
weekend=datetime(2026,10,10,15,0,tzinfo=timezone.utc)
friday_close_quote={**q,"updated":[datetime(2026,10,9,19,45,tzinfo=timezone.utc).timestamp()]}
assert sa.risk_for(p(),friday_close_quote,[],now=weekend)["level"]=="l1"

# During the live session the rolling 45-minute cutoff still applies.
live=datetime(2026,10,6,19,0,tzinfo=timezone.utc)  # 15:00 ET
old_live_quote={**q,"updated":[datetime(2026,10,6,18,0,tzinfo=timezone.utc).timestamp()]}
assert sa.risk_for(p(),old_live_quote,[],now=live)["level"]=="unknown"
assert sa.occ_symbol(p(expiry="2026-12-18",strike=65))=="TEST261218P00065000"

src=(ROOT/"scripts"/"server_action_engine.py").read_text(encoding="utf-8")
assert "sanitized public summary only" in src
assert "MYALPHA_TG_BOT_TOKEN" in src
assert "cannot_judge" in src
assert "quote_freshness_cutoff" in src
assert "last_checked_at" in src
assert "trading_calendar.expected_latest_completed_session" in src
assert "symbols/accounts/private position details are never written here" in src

# Heartbeat age must not change alert fingerprint or same-state comparison semantics.
base_result={"status":"clear","trust":{"ok":True,"overall":"ok","market_as_of":"2026-10-05","expected_market_date":"2026-10-05","system_status_age_hours":0.04},"event_count_48h":0,"actions":[]}
later_result={"status":"clear","trust":{**base_result["trust"],"system_status_age_hours":0.54},"event_count_48h":0,"actions":[]}
assert sa.fingerprint(base_result)==sa.fingerprint(later_result)
assert sa.stable_trust(base_result["trust"])==sa.stable_trust(later_result["trust"])

# Thesis Review authority: only direct-company official evidence may trigger review.
old_auto=sa.AUTO_THESIS
try:
    import tempfile, json
    from pathlib import Path as _P
    with tempfile.TemporaryDirectory() as td:
        auto=_P(td)/"auto.json"
        sa.AUTO_THESIS=auto
        auto.write_text(json.dumps({"symbols":{"TEST":{"sources":{
            "official":[{"date":"2026-10-05","evidence_class":"direct_company"}],
            "events":[{"published_at":"2026-10-06T00:00:00Z","evidence_class":"media"}]
        }}}}),encoding="utf-8")
        notes=[{"symbol":"TEST","updated_at":"2026-10-04T00:00:00Z","invalidation":"x"}]
        assert len(sa.thesis_review_actions(notes))==1
        notes2=[{"symbol":"TEST","updated_at":"2026-10-05T12:00:00Z","invalidation":"x"}]
        assert sa.thesis_review_actions(notes2)==[]  # newer media alone cannot trigger review
finally:
    sa.AUTO_THESIS=old_auto

print("PASS V6.15 server action engine")
