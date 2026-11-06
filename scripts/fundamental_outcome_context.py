#!/usr/bin/env python3
from __future__ import annotations
import json,sys
from datetime import datetime,timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
from local_history_agent import read_archive
AUTO=ROOT/"docs/research/auto_thesis_drafts.json"
OUT=ROOT/"docs/research/fundamental_outcome_context.json"
OFFICIAL=ROOT/"docs/research/official_evidence.json"

def load(path):
    try:return json.loads(path.read_text(encoding="utf-8"))
    except Exception:return {}

def upstream_status(auto,official):
    """Make a stale upstream visible instead of a silent 0 (#133 6458368830 §E). The failure seen on 10/28: SEC
    filings were available in official_evidence.json but auto_thesis_drafts.json had been built from an older
    evidence file, so every direct-company count read 0."""
    filed={k for k,v in ((official or {}).get("symbols") or {}).items() if (v or {}).get("filings")}
    direct={k for k,v in ((auto or {}).get("symbols") or {}).items()
            if any(e.get("evidence_class")=="direct_company" for e in ((v or {}).get("sources") or {}).get("official") or [])}
    a,o=str((auto or {}).get("generated_at") or ""),str((official or {}).get("generated_at") or "")
    stale=bool(filed) and not direct
    return {"status":"stale_upstream" if stale else "ok",
            "auto_thesis_generated_at":a or None,"official_evidence_generated_at":o or None,
            "official_symbols_with_filings":len(filed),"auto_thesis_direct_symbols":len(direct),
            "auto_thesis_older_than_official":bool(a and o and a<o)}

def build(auto,store,official=None):
    rows=[]
    for symbol,item in (auto.get("symbols") or {}).items():
        df=store.get(symbol)
        if df is None or df.empty:continue
        seen=set()
        for ev in ((item.get("sources") or {}).get("official") or []):
            if ev.get("evidence_class")!="direct_company":continue
            date=str(ev.get("date") or "")[:10]
            if not date or date in seen:continue
            seen.add(date)
            future=df[df.index > date]
            if future.empty:continue
            start=future.index[0];pos=df.index.get_loc(start);base=float(df.loc[start,"open"])
            horizons={}
            for h in (5,20,60):
                if pos+h>=len(df):horizons[str(h)]=None;continue
                path=df.iloc[pos:pos+h+1]
                horizons[str(h)]={"date":path.index[-1].date().isoformat(),"return":float(path.iloc[-1]["close"]/base-1),"mae":float(path["low"].min()/base-1),"mfe":float(path["high"].max()/base-1)}
            rows.append({"symbol":symbol,"evidence_date":date,"form":ev.get("form"),"baseline_date":start.date().isoformat(),"outcomes":horizons})
    return {"version":1,"generated_at":datetime.now(timezone.utc).isoformat(),"summary":{"linked_direct_events":len(rows),"symbols":len({x["symbol"] for x in rows}),"mature_5":sum(bool(x["outcomes"]["5"]) for x in rows),"mature_20":sum(bool(x["outcomes"]["20"]) for x in rows),"mature_60":sum(bool(x["outcomes"]["60"]) for x in rows)},"rows":rows,"upstream":upstream_status(auto,official),"guardrail":"descriptive only; post-filing returns are not thesis-correctness scores"}

def main():
    out=build(load(AUTO),read_archive(),load(OFFICIAL))
    up=out["upstream"]
    if up["status"]!="ok":
        print(f"::warning title=Fundamental outcome context::stale_upstream - official evidence has filings for "
              f"{up['official_symbols_with_filings']} symbols but auto_thesis_drafts has no direct-company evidence "
              f"(auto {up['auto_thesis_generated_at']} vs official {up['official_evidence_generated_at']}); counts are not a real 0")
    OUT.write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps(out["summary"],ensure_ascii=False))

if __name__=="__main__":main()
