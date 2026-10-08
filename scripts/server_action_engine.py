#!/usr/bin/env python3
"""Server-side Daily Action Engine.

Reads private option positions through Supabase, fetches only held-contract
quotes through the existing options-market Edge Function, applies fail-closed
risk/event rules, optionally delivers a concise alert, and writes only a
sanitized public health summary (never symbols/accounts/position details).
"""
from __future__ import annotations
import json,os,urllib.request,urllib.parse,hashlib,sys
from datetime import datetime,timezone,timedelta
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
import trading_calendar
EVENTS=ROOT/"docs"/"data"/"market_events.json"
DATA=ROOT/"docs"/"data.json"
SYSTEM=ROOT/"docs"/"research"/"system_status.json"
AUTO_THESIS=ROOT/"docs"/"research"/"auto_thesis_drafts.json"
PUBLIC_OUT=ROOT/"docs"/"research"/"server_action_status.json"
DEFAULT_EDGE="https://rhielbkvhgqbthcgztci.supabase.co/functions/v1/options-market"
# Learning Quality write-path verification trigger: private state-entry/outcome ledgers; final closure run.

def load(path):
    try:return json.loads(path.read_text(encoding="utf-8"))
    except Exception:return {}

def req_json(url,headers=None,timeout=15):
    req=urllib.request.Request(url,headers=headers or {"User-Agent":"MyAlpha-Server-Action"})
    with urllib.request.urlopen(req,timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def write_usage_ledger(rows):
    """Best-effort service-role ledger. Failure never blocks risk checks."""
    base=os.getenv("SUPABASE_URL");key=os.getenv("SUPABASE_KEY")
    if not base or not key or not rows:
        return False
    try:
        url=f"{base.rstrip('/')}/rest/v1/request_usage_ledger"
        body=json.dumps(rows).encode()
        req=urllib.request.Request(url,data=body,method="POST",headers={
            "apikey":key,"Authorization":f"Bearer {key}",
            "Content-Type":"application/json","Prefer":"return=minimal",
            "User-Agent":"MyAlpha-Server-Action",
        })
        with urllib.request.urlopen(req,timeout=12) as r:
            r.read()
        return True
    except Exception:
        return False

def supabase_rows(table):
    base=os.getenv("SUPABASE_URL");key=os.getenv("SUPABASE_KEY")
    if not base or not key:return None
    url=f"{base.rstrip('/')}/rest/v1/{table}?select=*"
    return req_json(url,{"apikey":key,"Authorization":f"Bearer {key}","User-Agent":"MyAlpha-Server-Action"})

def write_option_learning_observations(rows):
    """Best-effort private state-entry ledger; never affects risk decisions."""
    base=os.getenv("SUPABASE_URL");key=os.getenv("SUPABASE_KEY")
    if not base or not key or not rows:return False
    try:
        url=f"{base.rstrip('/')}/rest/v1/option_learning_observations"
        body=json.dumps(rows).encode()
        req=urllib.request.Request(url,data=body,method="POST",headers={
            "apikey":key,"Authorization":f"Bearer {key}",
            "Content-Type":"application/json",
            "Prefer":"return=minimal",
            "User-Agent":"MyAlpha-Server-Action",
        })
        with urllib.request.urlopen(req,timeout=12) as r:r.read()
        return True
    except Exception:
        # Migration may not be applied yet; learning persistence is fail-soft
        # and must never alter the fail-closed risk decision path.
        return False

def latest_option_states(rows):
    latest={}
    for row in rows or []:
        pid=str(row.get("position_id"))
        stamp=parse_dt(row.get("observed_at") or row.get("created_at"))
        if not pid or not stamp:continue
        prev=latest.get(pid)
        prev_stamp=parse_dt(prev.get("observed_at") or prev.get("created_at")) if prev else None
        if prev is None or prev_stamp is None or stamp>prev_stamp:
            latest[pid]=row
    return latest

def should_record_option_state(position,risk,latest):
    current=option_state_fingerprint(position,risk)
    prev=(latest or {}).get(str(position.get("id"))) or {}
    return prev.get("state_fingerprint")!=current

def option_state_fingerprint(position,risk):
    # State-entry identity only. DTE/Delta/spot are observation payload, not
    # state identity; otherwise an unchanged risk state would append daily.
    material={
      "position_id":position.get("id"),
      "level":risk.get("level"),
      "reason":risk.get("reason"),
    }
    return hashlib.sha256(json.dumps(material,sort_keys=True).encode()).hexdigest()[:24]


def occ_symbol(p):
    root=str(p.get("symbol") or "").upper()
    expiry=str(p.get("expiry") or "")[:10].replace("-","")[2:]
    typ="P" if str(p.get("opt_type") or "").lower()=="put" else "C"
    try:strike=f"{int(round(float(p.get('strike'))*1000)):08d}"
    except Exception:return None
    return f"{root}{expiry}{typ}{strike}" if root and len(expiry)==6 else None

def edge_quote(option_symbol):
    key=os.getenv("SUPABASE_KEY") or ""
    endpoint=os.getenv("OPTIONS_MARKET_ENDPOINT") or DEFAULT_EDGE
    url=endpoint+"?"+urllib.parse.urlencode({"action":"quote","optionSymbol":option_symbol})
    headers={"User-Agent":"MyAlpha-Server-Action"}
    if key:
        headers.update({"apikey":key,"Authorization":f"Bearer {key}"})
    return req_json(url,headers)

def first(row,key):
    v=row.get(key)
    return v[0] if isinstance(v,list) and v else None

def parse_dt(v):
    if not v:return None
    try:return datetime.fromisoformat(str(v).replace("Z","+00:00")).astimezone(timezone.utc)
    except Exception:return None

def upcoming_events(hours=48):
    now=datetime.now(timezone.utc);end=now+timedelta(hours=hours);rows=[]
    for e in load(EVENTS).get("events") or []:
        dt=parse_dt(e.get("datetime"))
        if dt and now<=dt<=end:rows.append({**e,"at":dt})
    return sorted(rows,key=lambda x:x["at"])

def system_trust(now=None):
    now=now or datetime.now(timezone.utc)
    s=load(SYSTEM);data=load(DATA)
    excluded=((s.get("decision_data_contract") or {}).get("excluded_artifacts") or [])
    guard=(s.get("resource_guard") or {}).get("mode","unknown")
    overall=s.get("overall","unknown")
    expected=trading_calendar.expected_latest_completed_session(now).isoformat()
    market_as_of=str(data.get("spy_date") or ((data.get("index") or {}).get("SPY") or {}).get("date") or "")
    generated=parse_dt(s.get("generated_at"))
    age_hours=None if not generated else max(0.0,(now-generated).total_seconds()/3600)
    status_fresh=age_hours is not None and age_hours<=30
    market_fresh=bool(market_as_of) and market_as_of==expected
    ok=overall in {"ok","running"} and not excluded and status_fresh and market_fresh
    return {
        "ok":ok,"overall":overall,"excluded":excluded,"resource_mode":guard,
        "market_as_of":market_as_of or None,"expected_market_date":expected,
        "system_status_age_hours":None if age_hours is None else round(age_hours,2),
    }

def judgment_basis(trust, credentials_configured=True, actions=None):
    """Why the sanitized status is what it is.

    Separates "the server never evaluated positions" (missing private
    credentials) from "positions were evaluated against stale/untrusted market
    data". Neither case may be presented as a judgment; both stay cannot_judge.
    """
    trust=trust or {}
    if not credentials_configured:
        return "credentials_not_configured"
    market_as_of=trust.get("market_as_of")
    if not market_as_of or market_as_of!=trust.get("expected_market_date"):
        return "market_data_stale"
    if not trust.get("ok"):
        return "system_status_untrusted"
    if any((a or {}).get("level")=="unknown" for a in (actions or [])):
        return "position_quote_unknown"
    return "evaluated"

def thesis_review_actions(notes):
    drafts=(load(AUTO_THESIS).get("symbols") or {})
    out=[]
    for note in notes or []:
        symbol=str(note.get("symbol") or "").upper()
        if not symbol or symbol not in drafts:
            continue
        updated=parse_dt(note.get("updated_at"))
        if not updated:
            continue
        latest=None
        src=drafts[symbol].get("sources") or {}
        for x in src.get("official") or []:
            if x.get("evidence_class") not in {None,"direct_company"}:
                continue
            d=parse_dt((x.get("date") or "")+"T00:00:00Z")
            latest=max(latest,d) if latest and d else (d or latest)
        # Media/peer/sector/macro evidence is context only and cannot directly
        # trigger a thesis state change or review action.
        if latest and latest>updated:
            out.append({
                "level":"review",
                "symbol":symbol,
                "reason":"new evidence arrived after thesis update",
                "invalidation_defined":bool(str(note.get("invalidation") or "").strip()),
                "evidence_at":latest.isoformat(),
            })
    return out

def quote_freshness_cutoff(now=None):
    """Minimum acceptable held-option quote timestamp.

    During regular trading hours use a rolling 45-minute window. Outside regular
    hours, compare against the last regular-session close minus 45 minutes so a
    valid closing quote does not become "stale" merely because the market is shut.
    """
    now=now or datetime.now(timezone.utc)
    local=now.astimezone(trading_calendar.ET)
    minutes=local.hour*60+local.minute
    if trading_calendar.is_session(local.date()) and 570<=minutes<960:
        return now-timedelta(minutes=45)
    if trading_calendar.is_session(local.date()) and minutes>=960:
        session=local.date()
    else:
        session=trading_calendar.previous_session(local.date())
    close_local=datetime(session.year,session.month,session.day,16,0,tzinfo=trading_calendar.ET)
    return close_local.astimezone(timezone.utc)-timedelta(minutes=45)

def risk_for(p,q,events,now=None):
    now_dt=now or datetime.now(timezone.utc)
    today=now_dt.date()
    try:expiry=datetime.fromisoformat(str(p.get("expiry"))[:10]).date();dte=(expiry-today).days
    except Exception:dte=None
    spot=first(q,"underlyingPrice") if q else None
    bid=first(q,"bid") if q else None;ask=first(q,"ask") if q else None;mid=first(q,"mid") if q else None
    delta=first(q,"delta") if q else None;updated=first(q,"updated") if q else None
    try:
        strike=float(p.get("strike"));spot=float(spot) if spot is not None else None
    except Exception:strike=None;spot=None
    stale=True
    if updated:
        try:stale=datetime.fromtimestamp(float(updated),timezone.utc)<quote_freshness_cutoff(now_dt)
        except Exception:stale=True
    if dte is None:return {"level":"unknown","reason":"expiry unavailable","dte":None}
    if q is None or spot is None or stale:return {"level":"unknown","reason":"quote unavailable or stale","dte":dte}
    typ=str(p.get("opt_type") or "").lower()
    itm=(spot<strike) if typ=="put" else (spot>strike)
    dist=abs(spot/strike-1) if strike else None
    spread=((float(ask)-float(bid))/float(mid)) if bid is not None and ask is not None and mid not in (None,0) else None
    level="l1";reason="no server risk trigger"
    if dte<0:level,reason="l3","expired / settlement required"
    elif dte<=7 and (itm or (dist is not None and dist<=.01)):level,reason="l3","near expiry and ATM/ITM"
    elif dte<=14 and (itm or (dist is not None and dist<=.05)):level,reason="l2","near assignment risk zone"
    elif spread is not None and spread>.15:level,reason="l2","wide bid/ask spread"
    elif events:level,reason="l2","major macro event inside 48h review window"
    return {"level":level,"reason":reason,"dte":dte,"spot":spot,"delta":delta,"spread":spread}

def build():
    trust=system_trust()
    usage_rows=[]
    positions=supabase_rows("options_positions")
    usage_rows.append({"provider":"supabase","request_kind":"options_positions_read","request_count":1,"paid":False,"source":"server_action_engine"})
    notes=supabase_rows("stock_research_notes")
    usage_rows.append({"provider":"supabase","request_kind":"stock_research_notes_read","request_count":1,"paid":False,"source":"server_action_engine"})
    learning_outcomes=supabase_rows("option_learning_outcomes")
    usage_rows.append({"provider":"supabase","request_kind":"option_learning_outcomes_read","request_count":1,"paid":False,"source":"server_action_engine"})
    learning_observations=supabase_rows("option_learning_observations")
    usage_rows.append({"provider":"supabase","request_kind":"option_learning_observations_read","request_count":1,"paid":False,"source":"server_action_engine"})
    operator_rows=supabase_rows("operator_decisions")
    usage_rows.append({"provider":"supabase","request_kind":"operator_decisions_read","request_count":1,"paid":False,"source":"server_action_engine"})
    if positions is None:
        return {"status":"cannot_judge","trust":trust,"reason":"Supabase credentials unavailable","actions":[],"quote_failures":0,
                "judgment_basis":judgment_basis(trust,credentials_configured=False)}
    open_rows=[p for p in positions if str(p.get("status") or "open") in {"open","pending_settlement"}]
    events=upcoming_events(48);actions=[];quote_failures=0;learning_rows=[]
    latest_states=latest_option_states(learning_observations or [])
    thesis_actions=thesis_review_actions(notes or [])
    for p in open_rows:
        occ=occ_symbol(p);q=None
        if occ:
            try:
                q=edge_quote(occ)
                usage_rows.append({"provider":"alpaca_via_supabase_edge","request_kind":"held_option_quote","request_count":1,"paid":False,"source":"server_action_engine"})
            except Exception:
                quote_failures+=1
        risk=risk_for(p,q,events)
        if p.get("id") is not None and p.get("user_id") and should_record_option_state(p,risk,latest_states):
            learning_rows.append({
              "user_id":p.get("user_id"),
              "position_id":p.get("id"),
              "broker_account_id":p.get("broker_account_id"),
              "symbol":p.get("symbol"),
              "opt_type":p.get("opt_type"),
              "side":p.get("side"),
              "strike":p.get("strike"),
              "expiry":str(p.get("expiry") or "")[:10],
              "observed_at":datetime.now(timezone.utc).isoformat(),
              "risk_level":risk.get("level") or "unknown",
              "risk_reason":risk.get("reason") or "",
              "dte":risk.get("dte"),
              "underlying_price":risk.get("spot"),
              "delta":risk.get("delta"),
              "spread_ratio":risk.get("spread"),
              "state_fingerprint":option_state_fingerprint(p,risk),
            })
        if risk["level"] in {"l2","l3"}:
            actions.append({"level":risk["level"],"symbol":p.get("symbol"),"expiry":p.get("expiry"),"reason":risk["reason"],"dte":risk.get("dte")})
        elif risk["level"]=="unknown":
            actions.append({"level":"unknown","symbol":p.get("symbol"),"expiry":p.get("expiry"),"reason":risk["reason"],"dte":risk.get("dte")})
    actions.extend(thesis_actions)
    learning_write_ok=write_option_learning_observations(learning_rows)
    cannot=not trust["ok"] or any(a["level"]=="unknown" for a in actions)
    status="cannot_judge" if cannot else ("action_required" if any(a["level"] in {"l2","l3","review"} for a in actions) else "clear")
    write_usage_ledger(usage_rows)
    learning_rows_count=len(learning_observations or [])+(len(learning_rows) if learning_write_ok else 0)
    mature_outcomes=sum(1 for x in (learning_outcomes or []) if x.get("outcome_mature") is True)
    operator_total=len(operator_rows or [])
    operator_attributed=sum(1 for x in (operator_rows or []) if x.get("attribution") not in {None,"","pending"})
    operator_actions=sum(1 for x in (operator_rows or []) if x.get("user_action") not in {None,"","unrecorded"})
    return {"status":status,"trust":trust,"judgment_basis":judgment_basis(trust,True,actions),
            "positions_checked":len(open_rows),"event_count_48h":len(events),"actions":actions,"quote_failures":quote_failures,
            "option_learning":{"observations":learning_rows_count,"mature_outcomes":mature_outcomes},
            "decision_learning":{"persisted":operator_total,"with_user_action":operator_actions,"attributed":operator_attributed}}

def stable_trust(trust):
    return {k:v for k,v in (trust or {}).items() if k!="system_status_age_hours"}

def fingerprint(result):
    material={
      "status":result.get("status"),
      "trust":stable_trust(result.get("trust")),
      "events":result.get("event_count_48h"),
      "actions":[
        {k:a.get(k) for k in ("level","symbol","expiry","reason","dte")}
        for a in result.get("actions") or []
      ],
    }
    return hashlib.sha256(json.dumps(material,sort_keys=True,ensure_ascii=False).encode()).hexdigest()[:20]

def notify(result, previous=None):
    if result["status"]=="clear":return "not_needed"
    fp=fingerprint(result)
    if previous and previous.get("alert_fingerprint")==fp:
        return "suppressed_duplicate"
    if not telegram_configured():return "not_configured"
    if result["status"]=="cannot_judge":
        title="MyAlpha：今日无法可靠判断"
    else:title="MyAlpha：有需要处理的事项"
    lines=[title]
    for a in result["actions"][:8]:
        lines.append(f"- {a['level'].upper()} {a.get('symbol','?')} {a.get('expiry','')}：{a.get('reason','')}")
    if result.get("event_count_48h"):lines.append(f"- 48小时内宏观事件：{result['event_count_48h']} 项")
    return send_telegram("\n".join(lines),raise_errors=True)

def telegram_configured():
    return bool(os.getenv("MYALPHA_TG_BOT_TOKEN") and os.getenv("MYALPHA_TG_CHAT_ID"))

def send_telegram(text,raise_errors=False):
    """Single MyAlpha Telegram sender shared by the action engine and Investment Watch."""
    token=os.getenv("MYALPHA_TG_BOT_TOKEN");chat=os.getenv("MYALPHA_TG_CHAT_ID")
    if not token or not chat:return "not_configured"
    body=urllib.parse.urlencode({"chat_id":chat,"text":text}).encode()
    req=urllib.request.Request(f"https://api.telegram.org/bot{token}/sendMessage",data=body,method="POST")
    try:
        with urllib.request.urlopen(req,timeout=12) as r:r.read()
    except Exception as e:
        if raise_errors:raise
        return f"failed:{type(e).__name__}"
    return "sent"

def main():
    result=build()
    previous=load(PUBLIC_OUT)
    fp=fingerprint(result)
    delivery=notify(result,previous)
    checked_at=datetime.now(timezone.utc)
    public={
      "version":"6.15-p012",
      "generated_at":checked_at.isoformat(),
      "last_checked_at":checked_at.isoformat(),
      "status":result["status"],
      "judgment_basis":result.get("judgment_basis") or judgment_basis(result.get("trust")),
      "positions_checked":result.get("positions_checked",0),
      "action_counts":{
        "l3":sum(1 for x in result["actions"] if x["level"]=="l3"),
        "l2":sum(1 for x in result["actions"] if x["level"]=="l2"),
        "unknown":sum(1 for x in result["actions"] if x["level"]=="unknown"),
        "thesis_review":sum(1 for x in result["actions"] if x["level"]=="review"),
      },
      "event_count_48h":result.get("event_count_48h",0),
      "quote_failures":result.get("quote_failures",0),
      "option_learning":result.get("option_learning") or {"observations":0,"mature_outcomes":0},
      "decision_learning":result.get("decision_learning") or {"persisted":0,"with_user_action":0,"attributed":0},
      "data_trust":result["trust"],
      "delivery":delivery,
      "alert_fingerprint":fp,
      "privacy":"sanitized public summary only; symbols/accounts/private position details are never written here",
    }
    PUBLIC_OUT.parent.mkdir(parents=True,exist_ok=True)
    same=bool(previous and previous.get("alert_fingerprint")==fp and previous.get("status")==public.get("status") and previous.get("judgment_basis")==public.get("judgment_basis") and previous.get("action_counts")==public.get("action_counts") and previous.get("option_learning")==public.get("option_learning") and previous.get("decision_learning")==public.get("decision_learning") and stable_trust(previous.get("data_trust"))==stable_trust(public.get("data_trust")))
    if same:
        prior_checked=parse_dt(previous.get("last_checked_at") or previous.get("generated_at"))
        if prior_checked and checked_at-prior_checked<timedelta(hours=6):
            public=previous
        else:
            public["generated_at"]=previous.get("generated_at") or public["generated_at"]
    PUBLIC_OUT.write_text(json.dumps(public,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    if result["status"]=="cannot_judge":
        print("::warning::Server Action cannot_judge; sanitized status remains fail-closed")
    print(json.dumps(public,ensure_ascii=False))
    return 0

if __name__=="__main__":raise SystemExit(main())
