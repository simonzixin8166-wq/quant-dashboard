#!/usr/bin/env python3
"""SEC CompanyFacts/XBRL longitudinal fundamental memory.

Research-only. Persists point-in-time filed observations append-only and emits a
small current summary. It never mutates Production trading rules.
"""
from __future__ import annotations
import hashlib,json,os,time,urllib.request
from datetime import datetime,timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
OFFICIAL=ROOT/"docs"/"research"/"official_evidence.json"
OUT=ROOT/"docs"/"research"/"company_fundamental_memory.json"
ARCH=ROOT/"research"/"archive"/"fundamentals"
BASE="https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json"

CONCEPTS={
 "revenue":["RevenueFromContractWithCustomerExcludingAssessedTax","Revenues","SalesRevenueNet"],
 "gross_profit":["GrossProfit"],
 "operating_income":["OperatingIncomeLoss"],
 "net_income":["NetIncomeLoss","ProfitLoss"],
 "eps_diluted":["EarningsPerShareDiluted"],
 "operating_cash_flow":["NetCashProvidedByUsedInOperatingActivities"],
 "capex":["PaymentsToAcquirePropertyPlantAndEquipment"],
 "cash":["CashAndCashEquivalentsAtCarryingValue","CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents"],
 "debt_current":["ShortTermBorrowings","LongTermDebtCurrent"],
 "debt_noncurrent":["LongTermDebtNoncurrent"],
 "shares_outstanding":["CommonStocksIncludingAdditionalPaidInCapitalMember" ,"EntityCommonStockSharesOutstanding"],
 "sbc":["ShareBasedCompensation"],
}

def load(path,default=None):
    try:return json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:return {} if default is None else default

def get_json(url,ua):
    req=urllib.request.Request(url,headers={"User-Agent":ua,"Accept":"application/json","Accept-Encoding":"identity"})
    with urllib.request.urlopen(req,timeout=20) as r:return json.loads(r.read().decode("utf-8"))

def obs_id(symbol,concept,u):
    raw="|".join(str(x or "") for x in (symbol,concept,u.get("end"),u.get("filed"),u.get("accn"),u.get("form"),u.get("fy"),u.get("fp"),u.get("val")))
    return hashlib.sha256(raw.encode()).hexdigest()[:24]

def concept_units(payload,names):
    facts=((payload.get("facts") or {}).get("us-gaap") or {})
    for name in names:
        node=facts.get(name)
        if not node:continue
        for unit,rows in (node.get("units") or {}).items():
            if rows:return name,unit,rows
    return None,None,[]

def normalize_rows(symbol,key,payload):
    name,unit,rows=concept_units(payload,CONCEPTS[key])
    out=[]
    for u in rows:
        form=str(u.get("form") or "")
        if form not in {"10-Q","10-K","20-F","40-F"}:continue
        if u.get("val") is None or not u.get("filed") or not u.get("end"):continue
        out.append({
          "observation_id":obs_id(symbol,key,u),"symbol":symbol,"metric":key,
          "concept":name,"unit":unit,"value":u.get("val"),"start":u.get("start"),"end":u.get("end"),
          "filed":u.get("filed"),"form":form,"accn":u.get("accn"),"fy":u.get("fy"),"fp":u.get("fp"),
          "frame":u.get("frame"),"source":"SEC CompanyFacts","point_in_time_available_at":u.get("filed"),
        })
    out.sort(key=lambda x:(str(x.get("filed")),str(x.get("end")),str(x.get("accn"))))
    return out

def read_known(path):
    ids=set()
    if not path.exists():return ids
    for line in path.read_text(encoding="utf-8").splitlines():
        try:ids.add(str(json.loads(line).get("observation_id")))
        except Exception:pass
    return ids

def append_symbol(symbol,rows):
    ARCH.mkdir(parents=True,exist_ok=True)
    p=ARCH/f"{symbol}.jsonl";known=read_known(p);new=0
    with p.open("a",encoding="utf-8") as f:
        for row in rows:
            if row["observation_id"] in known:continue
            f.write(json.dumps(row,ensure_ascii=False,sort_keys=True)+"\n");known.add(row["observation_id"]);new+=1
    return new,len(known)

def latest_by_metric(rows):
    out={}
    for row in rows:
        cur=out.get(row["metric"])
        if cur is None or (str(row.get("filed")),str(row.get("end")))>(str(cur.get("filed")),str(cur.get("end"))):
            out[row["metric"]]=row
    return out

def build(official,fetcher=get_json,ua=None):
    ua=ua or os.getenv("SEC_USER_AGENT","MyAlphaView/6.9 research-agent myalphaview.com")
    now=datetime.now(timezone.utc).isoformat();symbols={};total_new=0;total_obs=0
    for symbol,node in (official.get("symbols") or {}).items():
        cik=node.get("cik")
        if not cik:continue
        try:
            payload=fetcher(BASE.format(cik=int(cik)),ua)
            rows=[]
            for key in CONCEPTS:rows.extend(normalize_rows(symbol,key,payload))
            added,total=append_symbol(symbol,rows);total_new+=added;total_obs+=total
            symbols[symbol]={
              "status":"ok","cik":cik,"company_name":payload.get("entityName") or node.get("company_name"),
              "latest":latest_by_metric(rows),"observations_seen":len(rows),"archive_total":total,"archive_added":added,
              "fetched_at":now,
            }
            time.sleep(0.10)
        except Exception as exc:
            symbols[symbol]={"status":"error","cik":cik,"error":str(exc)[:180],"latest":{}}
    return {
      "version":"1.0","generated_at":now,"source":"SEC CompanyFacts/XBRL",
      "symbols":symbols,
      "counts":{"symbols":len(symbols),"ok":sum(x.get("status")=="ok" for x in symbols.values()),"archive_added":total_new,"archive_total":total_obs},
      "learning_status":"partial_learning",
      "guardrails":[
        "Every observation keeps its SEC filed date; later revisions are separate observations and never overwrite old point-in-time facts.",
        "This is longitudinal fundamental fact memory, not a trading signal.",
        "Derived margins/growth/thesis changes require explicit point-in-time comparison and are not fabricated when source concepts are absent."
      ],
    }

def main():
    out=build(load(OFFICIAL,{}))
    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps(out,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(out["counts"],ensure_ascii=False))

if __name__=="__main__":main()
