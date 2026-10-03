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

def verify_records(records):
    prev=ZERO_HASH
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

    def append_many(self,stream,records,market_date):
        month=str(market_date)[:7]
        path=f"ledger/{stream}/{month}.jsonl"
        text,sha=self.read_text(path)
        lines=[line for line in text.splitlines() if line.strip()]
        parsed=[]
        for line in lines:
            parsed.append(json.loads(line))
        ok,verify=verify_records(parsed)
        if not ok: raise RuntimeError(f"Existing private ledger verification failed: {verify}")
        known={str(r.get("record_id")) for r in parsed}
        prev=verify["head_hash"]
        added=[]
        for raw in records:
            if str(raw.get("record_id")) in known:continue
            row=make_record(raw,prev)
            prev=row["record_hash"];known.add(str(row.get("record_id")));added.append(row)
        if not added:
            return AppendResult(stream,path,False,0,len(parsed),prev)
        body="\n".join(lines+[canonical_json(r) for r in added])+"\n"
        self.write_text(path,body,sha=sha,message=f"Append MyAlpha {stream} ledger {market_date}")
        return AppendResult(stream,path,True,len(added),len(parsed)+len(added),prev)

def aggregate_anchor(results):
    heads={r.stream:{"path":r.path,"count":r.record_count,"head_hash":r.head_hash} for r in results}
    root=hashlib.sha256(canonical_json(heads).encode("utf-8")).hexdigest()
    return {"root_hash":root,"streams":heads,"generated_at":datetime.now(timezone.utc).isoformat()}

if __name__=="__main__":
    writer=PrivateGitHubLedger.from_env()
    print(json.dumps({"configured":bool(writer),"repo":writer.repo if writer else None},ensure_ascii=False))
