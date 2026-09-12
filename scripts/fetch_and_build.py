import json, datetime, os, time
import urllib.request, urllib.parse

API_KEY = os.environ["TWELVE_DATA_KEY"]
BASE = "https://api.twelvedata.com"

CORE = {  # 核心策略仓：需要计算回撤触发
    "QQQM": 0.07, "VGT": 0.10, "QLD": 0.14, "TQQQ": None,
}
INDEX = ["QQQ", "SPY", "VOO", "SMH"]
STOCKS = ["SOFI", "IREN", "ORCL", "TSLA", "NVDA", "TSM", "LITE",
          "AVGO", "MRVL", "NBIS", "GOOG", "AMD", "HOOD", "DRAM", "SPCX"]

def http_get_json(url):
    with urllib.request.urlopen(url, timeout=20) as resp:
        return json.loads(resp.read().decode("utf-8"))

def fetch_time_series(symbol, outputsize=60):
    params = urllib.parse.urlencode({"symbol": symbol, "interval": "1day",
                                      "outputsize": outputsize, "apikey": API_KEY})
    payload = http_get_json(f"{BASE}/time_series?{params}")
    if payload.get("status") == "error":
        raise RuntimeError(payload.get("message", "time_series error"))
    return payload["values"]  # newest first

def fetch_quote(symbol):
    params = urllib.parse.urlencode({"symbol": symbol, "apikey": API_KEY})
    payload = http_get_json(f"{BASE}/quote?{params}")
    if payload.get("status") == "error" or payload.get("code"):
        raise RuntimeError(payload.get("message", f"quote error for {symbol}"))
    return payload

def prior_month_high(rows, today):
    first_of_this_month = today.replace(day=1)
    last_month_end = first_of_this_month - datetime.timedelta(days=1)
    last_month_start = last_month_end.replace(day=1)
    highs = []
    for r in rows:
        d = datetime.date.fromisoformat(r["datetime"][:10])
        if last_month_start <= d <= last_month_end:
            highs.append(float(r["high"]))
    return max(highs) if highs else None

def build_core(today):
    out = {}
    for name, threshold in CORE.items():
        try:
            rows = fetch_time_series(name, outputsize=60)
            latest = rows[0]
            close = float(latest["close"])
            high = prior_month_high(rows, today)
            drawdown = (close - high) / high if high else None
            triggered = bool(threshold is not None and drawdown is not None and -drawdown >= threshold)
            out[name] = {"date": latest["datetime"][:10], "close": close,
                         "prior_month_high": high, "drawdown": drawdown,
                         "threshold": threshold, "triggered": triggered}
        except Exception as e:
            out[name] = {"error": str(e)}
        time.sleep(1)
    return out

def build_quotes(symbols):
    out = {}
    count = 0
    for s in symbols:
        try:
            q = fetch_quote(s)
            fifty_two = q.get("fifty_two_week", {}) or {}
            high52 = float(fifty_two["high"]) if fifty_two.get("high") else None
            close = float(q["close"])
            dist52 = (close - high52) / high52 if high52 else None
            out[s] = {
                "name": q.get("name", s),
                "close": close,
                "percent_change": float(q["percent_change"]) if q.get("percent_change") not in (None, "") else None,
                "high52": high52,
                "dist_from_52w_high": dist52,
                "datetime": q.get("datetime"),
            }
        except Exception as e:
            out[s] = {"error": str(e)}
        count += 1
        time.sleep(1)
        if count % 8 == 0:
            time.sleep(55)  # respect 8 req/min free-tier limit
    return out

def build():
    today = datetime.date.today()
    return {
        "updated": today.isoformat(),
        "core": build_core(today),
        "index": build_quotes(INDEX),
        "stocks": build_quotes(STOCKS),
    }

def fmt_pct(x, digits=2):
    return f"{x*100:.{digits}f}%" if isinstance(x, (int, float)) else "-"

def card_core(name, r):
    if "error" in r:
        return f'<div class="card err"><div class="sym">{name}</div><div class="errmsg">数据获取失败</div></div>'
    flag = "🔴 触发加仓" if r["triggered"] else "🟢 正常"
    th = fmt_pct(r["threshold"]) if r["threshold"] is not None else "观察仓"
    return f'''<div class="card">
      <div class="sym">{name}</div>
      <div class="price">${r["close"]:.2f}</div>
      <div class="row"><span>回撤</span><span class="{"neg" if r["drawdown"] and r["drawdown"]<0 else ""}">{fmt_pct(r["drawdown"])}</span></div>
      <div class="row"><span>阈值</span><span>{th}</span></div>
      <div class="badge {"on" if r["triggered"] else "off"}">{flag}</div>
    </div>'''

def card_quote(sym, r):
    if "error" in r:
        return f'<div class="card err"><div class="sym">{sym}</div><div class="errmsg">数据获取失败</div></div>'
    chg = r["percent_change"]
    chg_cls = "pos" if (chg or 0) >= 0 else "neg"
    chg_str = f'{"+" if (chg or 0)>=0 else ""}{chg:.2f}%' if chg is not None else "-"
    dist = r["dist_from_52w_high"]
    return f'''<div class="card">
      <div class="sym">{sym}</div>
      <div class="price">${r["close"]:.2f}</div>
      <div class="row"><span>今日</span><span class="{chg_cls}">{chg_str}</span></div>
      <div class="row"><span>距52周高点</span><span>{fmt_pct(dist)}</span></div>
    </div>'''

def render_html(data):
    core_html = "".join(card_core(k, v) for k, v in data["core"].items())
    index_html = "".join(card_quote(k, v) for k, v in data["index"].items())
    stock_html = "".join(card_quote(k, v) for k, v in data["stocks"].items())
    return f"""<!DOCTYPE html><html lang="zh"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>个人量化投资看板</title>
<style>
:root {{ --bg:#f5f6f8; --card:#ffffff; --ink:#1b1f28; --sub:#6b7280; --line:#e8eaee;
--pos:#0f9d58; --neg:#d93025; --accent:#2e5395; }}
* {{ box-sizing:border-box; }}
body {{ margin:0; font-family:-apple-system,"Microsoft YaHei",Helvetica,Arial,sans-serif;
background:var(--bg); color:var(--ink); padding:28px 32px 60px; }}
h1 {{ font-size:22px; margin:0 0 4px; }}
.meta {{ color:var(--sub); font-size:13px; margin-bottom:28px; }}
h2 {{ font-size:15px; color:var(--sub); text-transform:uppercase; letter-spacing:.06em;
margin:32px 0 12px; border-left:3px solid var(--accent); padding-left:8px; }}
.grid {{ display:grid; grid-template-columns:repeat(auto-fill,minmax(160px,1fr)); gap:14px; }}
.card {{ background:var(--card); border:1px solid var(--line); border-radius:12px; padding:16px;
box-shadow:0 1px 2px rgba(0,0,0,.04); }}
.card.err {{ opacity:.6; }}
.sym {{ font-weight:700; font-size:15px; margin-bottom:6px; }}
.price {{ font-size:20px; font-weight:700; margin-bottom:10px; }}
.row {{ display:flex; justify-content:space-between; font-size:12.5px; color:var(--sub); margin-bottom:4px; }}
.row span:last-child {{ color:var(--ink); font-weight:600; }}
.pos {{ color:var(--pos) !important; }} .neg {{ color:var(--neg) !important; }}
.badge {{ margin-top:8px; font-size:12px; font-weight:700; padding:4px 8px; border-radius:6px; display:inline-block; }}
.badge.on {{ background:#fdecea; color:var(--neg); }} .badge.off {{ background:#e6f4ea; color:var(--pos); }}
.errmsg {{ font-size:12px; color:var(--sub); }}
button {{ background:var(--accent); color:#fff; border:none; padding:9px 18px; border-radius:8px;
cursor:pointer; margin-top:36px; font-size:13px; }}
</style></head><body>
<h1>📊 个人量化投资看板</h1>
<div class="meta">数据更新至：{data['updated']}（数据源：Twelve Data，交易日收盘后自动更新，仅展示价格与信号，不含持仓明细）</div>

<h2>核心策略仓（回撤触发加仓）</h2>
<div class="grid">{core_html}</div>

<h2>宽基指数</h2>
<div class="grid">{index_html}</div>

<h2>个股观察</h2>
<div class="grid">{stock_html}</div>

<button onclick="exportData()">导出当日数据 (JSON)</button>
<script>
const DATA = {json.dumps(data, ensure_ascii=False)};
function exportData() {{
  const blob = new Blob([JSON.stringify(DATA,null,2)], {{type:"application/json"}});
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = "dashboard_" + DATA.updated + ".json";
  a.click();
}}
</script></body></html>"""

if __name__ == "__main__":
    data = build()
    os.makedirs("docs", exist_ok=True)
    with open("docs/index.html", "w", encoding="utf-8") as f:
        f.write(render_html(data))
    with open("docs/data.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print("done")
