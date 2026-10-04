import copy
import importlib.util
import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]

def load_module(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    mod=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

import sys
sys.path.insert(0,str(ROOT/"scripts"))
import playbook_config as pc
import trading_calendar as tc
import private_ledger as pl
import playbook_engine as pe

# --- Registry / rule-hash contract ---
assert pc.CORE_TIERS["QQQM"]=={"t1":0.12,"t2":0.18,"t3":0.25}
assert pc.CORE_TIERS["VGT"]=={"t1":0.15,"t2":0.20,"t3":0.30}
assert pc.CORE_TIERS["QLD"]=={"t1":0.25,"t2":0.35,"t3":0.50}
assert pc.TQQQ_RULES["hard_exit"]["vix_ma50_gt"]==26
assert pc.TQQQ_RULES["tier1"]["vix_3d_change_gt"]==0.20
assert pc.LEAPS_RULES["candidate"]=={"rsi_lte":35,"drawdown63_lte":-0.08,"logic":"AND"}
assert len(pc.rule_hash("CP-01"))==64
legacy_cp01_hash="ad5eab7a409996693a01eea24dfeb9a2f070a27f535092a7cd079acee14972b9"
assert pc.rule_hash("CP-01")!=legacy_cp01_hash  # canonicalization correction, not a threshold change
original_t1=pc.CORE_TIERS["QQQM"]["t1"]
hash_before=pc.rule_hash("CP-01")
pc.CORE_TIERS["QQQM"]["t1"]=original_t1+0.001
assert pc.rule_hash("CP-01")!=hash_before
pc.CORE_TIERS["QQQM"]["t1"]=original_t1
assert pc.PLAYBOOKS["PP-01"]["class"]=="private"
assert pc.PLAYBOOKS["PP-01"]["ledger_enabled"] is False

# --- NYSE trading-session calendar ---
assert not tc.is_session(datetime(2026,7,3).date())  # Independence Day observed
assert not tc.is_session(datetime(2026,4,3).date())  # Good Friday
assert tc.is_session(datetime(2026,10,2).date())
assert tc.expected_latest_completed_session(datetime(2026,10,3,12,0,tzinfo=timezone.utc)).isoformat()=="2026-10-02"
assert tc.add_sessions("2026-10-02",1).isoformat()=="2026-10-05"
assert tc.is_session(datetime(2021,12,31).date())  # NYSE was open; New Year Saturday is not observed on prior Friday
assert tc.is_session(datetime(2027,12,31).date())
assert not tc.is_session(datetime(2018,12,5).date())  # one-off national day of mourning

# --- Ledger hash-chain tamper detection ---
base={"schema_version":"1.0","record_type":"trigger_state_event","record_id":"a","playbook_id":"CP-01"}
r1=pl.make_record(base,pl.ZERO_HASH)
r2=pl.make_record({**base,"record_id":"b"},r1["record_hash"])
ok,meta=pl.verify_records([r1,r2])
assert ok and meta["records"]==2 and meta["head_hash"]==r2["record_hash"]
tampered=copy.deepcopy([r1,r2]);tampered[0]["playbook_id"]="CP-X"
ok,_=pl.verify_records(tampered)
assert not ok

# A monthly shard must verify from the previous month's head, not ZERO_HASH.
prior_head="a"*64
m1=pl.make_record({**base,"record_id":"oct-1"},prior_head)
m2=pl.make_record({**base,"record_id":"oct-2"},m1["record_hash"])
ok,meta=pl.verify_records([m1,m2],prior_head)
assert ok and meta["head_hash"]==m2["record_hash"]
ok,_=pl.verify_records([m1,m2],pl.ZERO_HASH)
assert not ok



# --- Partial-write reconciliation: verified monthly file may repair stale _heads metadata ---
class MemoryLedger(pl.PrivateGitHubLedger):
    def __init__(self,files):
        super().__init__("owner/private","token","main")
        self.files=dict(files)
    def read_text(self,path):
        return self.files.get(path,""), ("sha-"+path if path in self.files else None)
    def write_text(self,path,text,sha=None,message=""):
        self.files[path]=text
        return {"content":{"sha":"new-"+path}}

rr1=pl.make_record({**base,"record_id":"recover-1"},pl.ZERO_HASH)
rr2=pl.make_record({**base,"record_id":"recover-2"},rr1["record_hash"])
recover_path="ledger/trigger/2026-10.jsonl"
recover_heads={"version":1,"streams":{"trigger":{
    "head_hash":rr1["record_hash"],"record_count":1,"last_month":"2026-10",
    "month_start_hash":pl.ZERO_HASH,"month_record_count":1,"last_path":recover_path
}}}
mem=MemoryLedger({
    recover_path:pl.canonical_json(rr1)+"\n"+pl.canonical_json(rr2)+"\n",
    "ledger/_heads.json":json.dumps(recover_heads),
})
res=mem.append_many("trigger",[],"2026-10-02")
assert res.reconciled is True and res.recovered_records==1 and res.record_count==2
heads_after=json.loads(mem.files["ledger/_heads.json"])
assert heads_after["streams"]["trigger"]["head_hash"]==rr2["record_hash"]
assert heads_after["streams"]["trigger"]["record_count"]==2

bad_heads=copy.deepcopy(recover_heads)
bad_heads["streams"]["trigger"]["head_hash"]="b"*64
bad=MemoryLedger({
    recover_path:pl.canonical_json(rr1)+"\n"+pl.canonical_json(rr2)+"\n",
    "ledger/_heads.json":json.dumps(bad_heads),
})
try:
    bad.append_many("trigger",[],"2026-10-02")
    raise AssertionError("unrelated stale head must fail closed")
except RuntimeError as exc:
    assert "does not match verified month chain" in str(exc)

# --- Synthetic Playbook state mapping and data-quality gate ---
def asset(close=100,prev=99,date="2026-10-02",**extra):
    row={"date":date,"close":close,"prev_close":prev,"ath_validation":"PASS","strategy_drawdown":-0.01,"level":0}
    row.update(extra);return row

data={
 "spy_date":"2026-10-02",
 "core":{
   "QQQM":asset(close=90,prev=91,strategy_drawdown=-0.13,level=1),
   "VGT":asset(close=120,prev=119,strategy_drawdown=-0.02,level=0),
   "QLD":asset(close=80,prev=79,strategy_drawdown=-0.04,level=0),
 },
 "index":{
   "QQQ":asset(close=700,prev=695),
   "SMH":asset(close=600,prev=590),
   "TQQQ":asset(close=80,prev=79),
 },
 "tqqq_x2":{
   "available":True,"date":"2026-10-02","rule":"tier1","target_position":33,"target_daily_exposure":0.99,
   "snapshot":{"date":"2026-10-02","qqq":700,"vix":21},
 },
 "leaps_radar":{"assets":[
   {"symbol":"QQQ","available":True,"date":"2026-10-02","close":700,"status":"watch","drawdown63":-0.06,"rsi14":39,"trend_risk":False,"vix_risk":False},
   {"symbol":"SMH","available":True,"date":"2026-10-02","close":600,"status":"candidate","drawdown63":-0.09,"rsi14":34,"trend_risk":False,"vix_risk":False},
   {"symbol":"VGT","available":True,"date":"2026-10-02","close":120,"status":"normal","drawdown63":-0.01,"rsi14":55,"trend_risk":False,"vix_risk":False},
 ]},
}
history={"update":{"quarantined":[]}}
now=datetime(2026,10,3,12,0,tzinfo=timezone.utc)
gate,rows=pe.evaluate(data,history,now)
assert gate["fresh"] is True
mapped={(r["playbook_id"],r["symbol"]):(r["state"],r["detail"]) for r in rows}
assert mapped[("CP-01","QQQM")]==("TRIGGERED","tier1")
assert mapped[("CP-01","VGT")]==("IDLE","normal")
assert mapped[("CP-02","TQQQ")]==("TRIGGERED","tier1")
assert mapped[("CP-03","QQQ")]==("NEAR_TRIGGER","watch")
assert mapped[("CP-03","SMH")]==("TRIGGERED","candidate")
assert mapped[("CP-03","VGT")]==("IDLE","normal")

# Common split/reverse-split ratios must be quarantined before Forward logging.
for close,prev in ((50,100),(100/3,100),(25,100),(200,100),(300,100),(400,100)):
    split_data=copy.deepcopy(data)
    split_data["index"]["QQQ"]["close"]=close
    split_data["index"]["QQQ"]["prev_close"]=prev
    _,split_rows=pe.evaluate(split_data,history,now)
    cp02=next(r for r in split_rows if r["playbook_id"]=="CP-02")
    assert cp02["state"]=="UNDETERMINED", (close,prev,cp02)
    assert "split_or_adjustment_candidate" in cp02["quality"]["reasons"]

# --- First Forward run establishes baseline, never backfills an existing state ---
class FakeWriter:
    def __init__(self): self.calls=[]
    def append_many(self,stream,records,market_date):
        self.calls.append((stream,[dict(x) for x in records],market_date))
        head=("f"*64) if records else pl.ZERO_HASH
        return pl.AppendResult(stream,f"ledger/{stream}/{market_date[:7]}.jsonl",bool(records),len(records),len(records),head)

with tempfile.TemporaryDirectory() as td:
    td=Path(td)
    old=(pe.DATA,pe.HISTORY,pe.STATUS_OUT,pe.ANCHOR_OUT)
    try:
        pe.DATA=td/"data.json";pe.HISTORY=td/"history.json";pe.STATUS_OUT=td/"status.json";pe.ANCHOR_OUT=td/"anchor.json"
        pe.DATA.write_text(json.dumps(data),encoding="utf-8")
        pe.HISTORY.write_text(json.dumps(history),encoding="utf-8")
        writer=FakeWriter()
        status,_=pe.build(now=now,writer=writer)
        assert status["storage"]["forward_clock_active"] is True
        assert status["stabilization"]=={"start_market_date":"2026-10-02","completed_sessions":1,"target_sessions":10,"complete":False}
        # Existing current states become baseline; no fake trigger event is created.
        first_trigger_records=[x for stream,records,_ in writer.calls if stream=="trigger" for x in records]
        assert first_trigger_records==[]

        # Same data on the same market date remains idempotent.
        writer2=FakeWriter()
        status2,_=pe.build(now=now,writer=writer2)
        second_trigger_records=[x for stream,records,_ in writer2.calls if stream=="trigger" for x in records]
        assert second_trigger_records==[]

        # A real state change after baseline creates one scoreable trigger event.
        changed=copy.deepcopy(data)
        changed["core"]["VGT"]["level"]=1
        changed["core"]["VGT"]["strategy_drawdown"]=-0.16
        pe.DATA.write_text(json.dumps(changed),encoding="utf-8")
        writer3=FakeWriter()
        pe.build(now=now,writer=writer3)
        events=[x for stream,records,_ in writer3.calls if stream=="trigger" for x in records]
        vgt=[x for x in events if x.get("entity_key")=="CP-01:VGT"]
        assert len(vgt)==1 and vgt[0]["state"]=="TRIGGERED" and vgt[0]["scoreable"] is True
    finally:
        pe.DATA,pe.HISTORY,pe.STATUS_OUT,pe.ANCHOR_OUT=old



# --- Legacy CP-01 hash correction must never masquerade as a Forward trigger ---
with tempfile.TemporaryDirectory() as td:
    td=Path(td)
    old=(pe.DATA,pe.HISTORY,pe.STATUS_OUT,pe.ANCHOR_OUT)
    try:
        pe.DATA=td/"data.json";pe.HISTORY=td/"history.json";pe.STATUS_OUT=td/"status.json";pe.ANCHOR_OUT=td/"anchor.json"
        pe.DATA.write_text(json.dumps(data),encoding="utf-8")
        pe.HISTORY.write_text(json.dumps(history),encoding="utf-8")
        legacy_rows=copy.deepcopy(pe.evaluate(data,history,now)[1])
        for row in legacy_rows:
            if row["playbook_id"]=="CP-01":
                row["rule_hash"]=pe.LEGACY_CP01_HASH
            row["committed_state_key"]=row["state_key"]
        pe.STATUS_OUT.write_text(json.dumps({"storage":{"forward_clock_active":True},"playbooks":legacy_rows}),encoding="utf-8")
        writer=FakeWriter()
        pe.build(now=now,writer=writer)
        triggers=[x for stream,records,_ in writer.calls if stream=="trigger" for x in records]
        corrections=[x for stream,records,_ in writer.calls if stream=="correction" for x in records]
        assert triggers==[]
        assert any(x.get("kind")=="rule_hash_canonicalization_correction" and x.get("semantic_change") is False for x in corrections)
    finally:
        pe.DATA,pe.HISTORY,pe.STATUS_OUT,pe.ANCHOR_OUT=old

workflow=(ROOT/".github/workflows/daily.yml").read_text(encoding="utf-8")
assert "vars.MYALPHA_LEDGER_REPO" in workflow
assert "simonzixin8166-wq/myalpha-ledger-private" in workflow  # compatibility fallback
assert "secrets.MYALPHA_LEDGER_TOKEN" in workflow

print("PASS V6.10a Playbook engine / data gate / silent ledger contract")
