#!/usr/bin/env python3
"""Append-only private GitHub ledger storage for V6.10a.

Raw records are never written to the public dashboard repository. The caller
may publish only the returned aggregate anchor/head metadata.
"""
from __future__ import annotations
import base64, hashlib, json, os, urllib.error, urllib.parse, urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone

ZERO_HASH="0"*64

def canonical_json(value):
    return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(",",":"))

def hash_record(record,prev_hash):
    body={k:v for k,v in record.items() if k not in {"record_hash","prev_hash"}}
    return hashlib.sha256((prev_hash+"|"+canonical_json(body)).encode("utf-8")).hexdigest()

def verify_records(records,initial_prev=ZERO_HASH):
    prev=initial_prev
    seen=set()
    for index,row in enumerate(records):
        rid=str(row.get("record_id") or "")
        if not rid or rid in seen:return False,{"index":index,"reason":"duplicate_or_missing_record_id"}
        if row.get("prev_hash")!=prev:return False,{"index":index,"reason":"prev_hash_mismatch"}
        expected=hash_record(row,prev)
        if row.get("record_hash")!=expected:return False,{"index":index,"reason":"record_hash_mismatch"}
        seen.add(rid);prev=expected
    return True,{"records":len(records),"head_hash":prev}

def make_record(payload,prev_hash):
    row=dict(payload)
    row["prev_hash"]=prev_hash
    row["record_hash"]=hash_record(row,prev_hash)
    return row

@dataclass
class AppendResult:
    stream:str
    path:str
    changed:bool
    appended:int
    record_count:int
    head_hash:str
    reconciled:bool=False
    recovered_records:int=0

class PrivateGitHubLedger:
    def __init__(self,repo,token,branch="main"):
        self.repo=repo
        self.token=token
        self.branch=branch or "main"

    @classmethod
    def from_env(cls):
        repo=os.getenv("MYALPHA_LEDGER_REPO","").strip()
        token=os.getenv("MYALPHA_LEDGER_TOKEN","").strip()
        branch=os.getenv("MYALPHA_LEDGER_BRANCH","main").strip() or "main"
        return cls(repo,token,branch) if repo and token else None

    def _request(self,url,method="GET",payload=None):
        headers={
            "Accept":"application/vnd.github+json",
            "Authorization":f"Bearer {self.token}",
            "X-GitHub-Api-Version":"2022-11-28",
            "User-Agent":"MyAlpha-Private-Ledger",
        }
        data=None
        if payload is not None:
            data=json.dumps(payload).encode("utf-8")
            headers["Content-Type"]="application/json"
        req=urllib.request.Request(url,data=data,headers=headers,method=method)
        try:
            with urllib.request.urlopen(req,timeout=30) as resp:
                return resp.status,json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            body=exc.read().decode("utf-8",errors="replace")
            if exc.code==404:return 404,{}
            raise RuntimeError(f"GitHub ledger API {exc.code}: {body[:500]}") from exc

    def _contents_url(self,path):
        encoded="/".join(urllib.parse.quote(part,safe="") for part in path.split("/"))
        return f"https://api.github.com/repos/{self.repo}/contents/{encoded}"

    def read_text(self,path):
        status,data=self._request(self._contents_url(path)+f"?ref={urllib.parse.quote(self.branch,safe='')}")
        if status==404:return "",None
        raw=base64.b64decode(data.get("content","")).decode("utf-8")
        return raw,data.get("sha")

    def write_text(self,path,text,sha=None,message="Append MyAlpha private ledger"):
        payload={"message":message,"content":base64.b64encode(text.encode("utf-8")).decode("ascii"),"branch":self.branch}
        if sha:payload["sha"]=sha
        status,data=self._request(self._contents_url(path),"PUT",payload)
        if status not in {200,201}:raise RuntimeError(f"Unexpected ledger write status {status}")
        return data

    def _heads(self):
        text,sha=self.read_text("ledger/_heads.json")
        data=json.loads(text) if text.strip() else {"version":1,"streams":{}}
        data.setdefault("version",1);data.setdefault("streams",{})
        return data,sha

    def append_many(self,stream,records,market_date):
        month=str(market_date)[:7]
        path=f"ledger/{stream}/{month}.jsonl"
        heads,heads_sha=self._heads()
        meta=dict((heads.get("streams") or {}).get(stream) or {})
        previous_global_head=meta.get("head_hash",ZERO_HASH)
        same_month=meta.get("last_month")==month
        month_start_hash=meta.get("month_start_hash",ZERO_HASH) if same_month else previous_global_head

        text,sha=self.read_text(path)
        lines=[line for line in text.splitlines() if line.strip()]
        parsed=[json.loads(line) for line in lines]
        ok,verify=verify_records(parsed,month_start_hash)
        if not ok:
            raise RuntimeError(f"Existing private ledger verification failed: {verify}")

        # Reconcile the safe partial-write case: the monthly file was committed
        # but ledger/_heads.json failed afterwards. The file is authoritative
        # only when the full chain verifies from the frozen month_start_hash and
        # the stale metadata head is either the month start or an earlier record
        # in that same verified chain. Any unrelated head remains fail-closed.
        current_file_head=verify["head_hash"]
        head_before=meta.get("head_hash",month_start_hash)
        chain_heads={month_start_hash}|{str(r.get("record_hash")) for r in parsed}
        reconciled=False
        recovered_records=0
        if parsed and head_before!=current_file_head:
            if head_before not in chain_heads:
                raise RuntimeError("Private ledger head metadata does not match verified month chain")
            prior_month_count=int(meta.get("month_record_count") or 0) if same_month else 0
            if prior_month_count>len(parsed):
                raise RuntimeError("Private ledger month count exceeds verified file length")
            recovered_records=len(parsed)-prior_month_count
            reconciled=True

        known={str(r.get("record_id")) for r in parsed}
        prev=current_file_head
        added=[]
        for raw in records:
            if str(raw.get("record_id")) in known:continue
            row=make_record(raw,prev)
            prev=row["record_hash"];known.add(str(row.get("record_id")));added.append(row)

        if added:
            body="\n".join(lines+[canonical_json(r) for r in added])+"\n"
            self.write_text(path,body,sha=sha,message=f"Append MyAlpha {stream} ledger {market_date}")

        total_before=int(meta.get("record_count") or 0)
        month_before=int(meta.get("month_record_count") or 0) if same_month else 0
        recovered_for_total=recovered_records if reconciled else 0
        new_meta={
            "head_hash":prev,
            "record_count":total_before+recovered_for_total+len(added),
            "last_month":month,
            "month_start_hash":month_start_hash,
            "month_record_count":len(parsed)+len(added),
            "last_path":path,
        }
        if new_meta!=meta:
            heads["streams"][stream]=new_meta
            self.write_text(
                "ledger/_heads.json",
                json.dumps(heads,ensure_ascii=False,indent=2)+"\n",
                sha=heads_sha,
                message=f"Update MyAlpha {stream} ledger head {market_date}",
            )
        return AppendResult(stream,path,bool(added),len(added),new_meta["record_count"],prev,reconciled,recovered_records)

def aggregate_anchor(results):
    heads={r.stream:{"path":r.path,"count":r.record_count,"head_hash":r.head_hash} for r in results}
    recovery={r.stream:{"reconciled":True,"recovered_records":int(r.recovered_records)} for r in results if r.reconciled}
    root=hashlib.sha256(canonical_json(heads).encode("utf-8")).hexdigest()
    return {"root_hash":root,"streams":heads,"reconciliation":recovery,"generated_at":datetime.now(timezone.utc).isoformat()}

if __name__=="__main__":
    writer=PrivateGitHubLedger.from_env()
    print(json.dumps({"configured":bool(writer),"repo":writer.repo if writer else None},ensure_ascii=False))
