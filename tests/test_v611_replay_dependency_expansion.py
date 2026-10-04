import json
import sys
import tempfile
import zipfile
from pathlib import Path
from datetime import datetime, timezone

import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))

import walk_forward_replay as wr
import bootstrap_replay_history as brh
from opportunity_strategy import build_tqqq_x2_strategy, build_leaps_radar

def frame(prices,start="2024-01-02"):
    idx=pd.bdate_range(start=start,periods=len(prices))
    return pd.DataFrame({
        "open":prices,
        "high":[x*1.01 for x in prices],
        "low":[x*0.99 for x in prices],
        "close":prices,
        "volume":[1000]*len(prices),
    },index=idx)

# Long benign trend followed by stress / recovery so CP-02 and CP-03 produce states.
n=320
qqq_prices=[]
for i in range(n):
    if i<240: qqq_prices.append(100+i*0.15)
    elif i<260: qqq_prices.append(136-(i-239)*1.4)
    elif i<280: qqq_prices.append(108+(i-259)*0.7)
    else: qqq_prices.append(122+(i-279)*0.5)

vix_prices=[]
for i in range(n):
    if i<238: vix_prices.append(15.0)
    elif i<260: vix_prices.append(18.0+(i-237)*0.8)
    elif i<278: vix_prices.append(max(17.0,36.0-(i-259)*1.0))
    else: vix_prices.append(17.0)

smh_prices=[x*(1.0 if i<240 else (1.0-0.001*(i-239))) for i,x in enumerate(qqq_prices)]
vgt_prices=[x*0.95 for x in qqq_prices]
qld_prices=[x*0.8 for x in qqq_prices]
qqqm_prices=[x*0.98 for x in qqq_prices]
tqqq_prices=[x*0.6 for x in qqq_prices]

store={
    "QQQ":frame(qqq_prices),
    "VIX":frame(vix_prices),
    "SMH":frame(smh_prices),
    "VGT":frame(vgt_prices),
    "QLD":frame(qld_prices),
    "QQQM":frame(qqqm_prices),
    "TQQQ":frame(tqqq_prices),
}

out=wr.build(store=store,now=datetime(2026,10,4,4,0,tzinfo=timezone.utc))
assert out["coverage"]["CP-01"]["status"]=="complete"
assert out["coverage"]["CP-02"]["status"]=="complete"
assert out["coverage"]["CP-03"]["status"]=="complete"
assert out["summary"]["replayable_playbooks"]==3
assert out["summary"]["blocked_playbooks"]==0

# CP-02 must use the same formal rule sequence as production strategy code.
qqq_rows=wr._rows_from_df(store["QQQ"])
vix_rows=wr._rows_from_df(store["VIX"])
prod=build_tqqq_x2_strategy(qqq_rows,vix_rows)
assert prod["available"] is True
prod_by_date={x["date"]:x["rule"] for x in prod["history"]}
cp02=wr.cp02_events(store["QQQ"],store["VIX"])
assert cp02
for e in cp02:
    if e["event_date"] in prod_by_date:
        assert e["state_detail"]==prod_by_date[e["event_date"]]
        assert e["evaluation_asset"]=="QQQ"
        assert e["evidence_provenance"]=="historical_replay_post_rule_design"
        if e["state_detail"] in {"hard_exit","tier2","tier1"}:
            assert e["expected_direction"]=="bearish"
            assert e["objective_group"]=="risk_reduction"
        else:
            assert e["expected_direction"]=="bullish"
            assert e["objective_group"]=="risk_restore"
        for h in ("5","20","60"):
            o=e["outcomes"].get(h)
            if o:
                assert o["benchmark_return"] is None
                assert o["excess_vs_benchmark"] is None

# CP-03 trigger reconstruction shares production thresholds.
asset_rows={k:wr._rows_from_df(store[k]) for k in ("QQQ","SMH","VGT")}
latest_vix=float(store["VIX"].iloc[-1]["close"])
prod_leaps=build_leaps_radar(asset_rows,vix_value=latest_vix)
latest_status={x["symbol"]:x["status"] for x in prod_leaps["assets"]}
for sym in ("QQQ","SMH","VGT"):
    ev=wr.cp03_events(sym,store[sym],store["QQQ"],store["VIX"])
    # If current production state is candidate/strong, last replay transition must agree.
    if latest_status[sym] in {"candidate","strong"}:
        assert ev and ev[-1]["state_detail"]==latest_status[sym]
    for e in ev:
        assert e["evaluation_asset"]==sym
        assert e["expected_direction"]=="bullish"
        assert "option_pnl" not in json.dumps(e)
        assert e["risk_context"]["vix_available"] is True

# One-time bootstrap filename contract and archive detection.
with tempfile.TemporaryDirectory() as td:
    old=brh.ARCHIVE
    try:
        brh.ARCHIVE=Path(td)/"hist.zip"
        with zipfile.ZipFile(brh.ARCHIVE,"w") as z:
            z.writestr("qqq_us_d.csv","Date,Open,High,Low,Close,Volume\n2026-10-02,1,1,1,1,1\n")
            z.writestr("vix_us_d.csv","Date,Open,High,Low,Close,Volume\n2026-10-02,1,1,1,1,1\n")
        assert brh.existing_symbols()=={"QQQ","VIX"}
        assert brh.symbol_from_member("tqqq_us_d.csv")=="TQQQ"
    finally:
        brh.ARCHIVE=old

workflow=(ROOT/".github/workflows/daily.yml").read_text(encoding="utf-8")
assert "Bootstrap / refresh Replay history dependencies" in workflow
assert "python scripts/bootstrap_replay_history.py" in workflow
assert workflow.index("- name: Bootstrap / refresh Replay history dependencies") < workflow.index("- name: Update local STOOQ history and autonomous learning")
assert "continue-on-error: true" in workflow

print("PASS V6.11.1 replay dependency expansion / production-rule parity / free-first bootstrap")
