import json, datetime, os, time
import urllib.request, urllib.parse

API_KEY = os.environ["TWELVE_DATA_KEY"]
BASE = "https://api.twelvedata.com"

CORE = {"QQQM": 0.07, "VGT": 0.10, "QLD": 0.14, "TQQQ": None}
INDEX = ["QQQ", "SPY", "VOO", "SMH"]
STOCKS = ["SOFI", "IREN", "ORCL", "TSLA", "NVDA", "TSM", "LITE",
          "AVGO", "MRVL", "NBIS", "GOOG", "AMD", "HOOD", "DRAM", "SPCX"]
ALL_SYMBOLS = list(CORE.keys()) + INDEX + STOCKS
CHART_SYMBOLS = ["QQQ", "SPY"]  # used for the monthly-return comparison chart

def http_get_json(url):
    with urllib.request.urlopen(url, timeout=20) as resp:
        return json.loads(resp.read().decode("utf-8"))

def throttle():
    time.sleep(8)

def fetch_time_series(symbol, outputsize=260):
    params = urllib.parse.urlencode({"symbol": symbol, "interval": "1day",
                                      "outputsize": outputsize, "apikey": API_KEY})
    payload = http_get_json(f"{BASE}/time_series?{params}")
    if payload.get("status") == "error":
        raise RuntimeError(payload.get("message", "time_series error"))
    return payload["values"]  # newest first

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

def pct_change(rows, back):
    if len(rows) <= back:
        return None
    latest = float(rows[0]["close"])
    prior = float(rows[back]["close"])
    return (latest - prior) / prior

def analyze(symbol, rows, today, threshold=None, is_core=False):
    closes = [float(r["close"]) for r in rows]
    highs = [float(r["high"]) for r in rows]
    latest_close = closes[0]
    out = {
        "date": rows[0]["datetime"][:10],
        "close": latest_close,
        "day_chg": pct_change(rows, 1),
        "week_chg": pct_change(rows, 5),
        "month_chg": pct_change(rows, 21),
        "q_chg": pct_change(rows, 63),
        "year_chg": pct_change(rows, min(252, len(rows) - 1)) if len(rows) > 1 else None,
        "high52": max(highs) if highs else None,
    }
    out["dist_from_52w_high"] = ((latest_close - out["high52"]) / out["high52"]
                                  if out["high52"] else None)
    if is_core:
        high = prior_month_high(rows, today)
        drawdown = (latest_close - high) / high if high else None
        triggered = bool(threshold is not None and drawdown is not None and -drawdown >= threshold)
        out.update({"prior_month_high": high, "drawdown": drawdown,
                    "threshold": threshold, "triggered": triggered})
    return out

def build():
    today = datetime.date.today()
    core, index, stocks, chart_history = {}, {}, {}, {}
    for name, threshold in CORE.items():
        try:
            rows = fetch_time_series(name)
            core[name] = analyze(name, rows, today, threshold, is_core=True)
        except Exception as e:
            core[name] = {"error": str(e)}
        throttle()
    for name in INDEX:
        try:
            rows = fetch_time_series(name)
            index[name] = analyze(name, rows, today)
            if name in CHART_SYMBOLS:
                chart_history[name] = [{"d": r["datetime"][:10], "c": float(r["close"])} for r in rows]
        except Exception as e:
            index[name] = {"error": str(e)}
        throttle()
    for name in STOCKS:
        try:
            rows = fetch_time_series(name)
            stocks[name] = analyze(name, rows, today)
        except Exception as e:
            stocks[name] = {"error": str(e)}
        throttle()
    return {"updated": today.isoformat(), "core": core, "index": index,
            "stocks": stocks, "chart_history": chart_history}

def fmt_pct(x, digits=2):
    return f"{x*100:.{digits}f}%" if isinstance(x, (int, float)) else "-"

def badge(label, val):
    if not isinstance(val, (int, float)):
        return f'<div class="pbadge neu"><span>{label}</span><b>-</b></div>'
    cls = "pos" if val >= 0 else "neg"
    sign = "+" if val >= 0 else ""
    return f'<div class="pbadge {cls}"><span>{label}</span><b>{sign}{val*100:.2f}%</b></div>'

def card_core(name, r):
    if "error" in r:
        return f'<div class="card err"><div class="sym">{name}</div><div class="errmsg">数据获取失败</div></div>'
    flag = "🔴 触发加仓" if r["triggered"] else "🟢 正常"
    th = fmt_pct(r["threshold"]) if r["threshold"] is not None else "观察仓"
    return f'''<div class="card">
      <div class="sym">{name}</div>
      <div class="price">${r["close"]:.2f}</div>
      <div class="row"><span>较上月高点回撤</span><span class="{"neg" if r["drawdown"] and r["drawdown"]<0 else ""}">{fmt_pct(r["drawdown"])}</span></div>
      <div class="row"><span>触发阈值</span><span>{th}</span></div>
      <div class="badge {"on" if r["triggered"] else "off"}">{flag}</div>
    </div>'''

def card_quote(sym, r):
    if "error" in r:
        return f'<div class="card err"><div class="sym">{sym}</div><div class="errmsg">数据获取失败</div></div>'
    return f'''<div class="card">
      <div class="sym">{sym}</div>
      <div class="price">${r["close"]:.2f}</div>
      <div class="pbadges">
        {badge("周", r["week_chg"])}{badge("月", r["month_chg"])}{badge("季", r["q_chg"])}{badge("年", r["year_chg"])}
      </div>
      <div class="row small"><span>距52周高点</span><span>{fmt_pct(r["dist_from_52w_high"])}</span></div>
    </div>'''

def monthly_returns(history):
    """Compute last 12 calendar-month total returns from a newest-first close series."""
    by_month = {}
    for pt in history:
        ym = pt["d"][:7]
        by_month.setdefault(ym, []).append(pt["c"])
    months = sorted(by_month.keys())[-13:]
    out = []
    for i in range(1, len(months)):
        cur_vals = by_month[months[i]]
        prev_vals = by_month[months[i-1]]
        cur_close = cur_vals[0]
        prev_close = prev_vals[0]
        ret = (cur_close - prev_close) / prev_close
        out.append({"month": months[i], "ret": ret})
    return out

def render_html(data):
    core_html = "".join(card_core(k, v) for k, v in data["core"].items())
    index_html = "".join(card_quote(k, v) for k, v in data["index"].items())
    stock_html = "".join(card_quote(k, v) for k, v in data["stocks"].items())

    chart_data = {}
    for sym, hist in data["chart_history"].items():
        chart_data[sym] = monthly_returns(hist)

    return f"""<!DOCTYPE html><html lang="zh"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>个人量化投资看板</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4"></script>
<style>
:root {{ --bg:#f4f5f8; --card:#ffffff; --ink:#1b1f28; --sub:#6b7280; --line:#eceef2;
--pos:#0f9d58; --neg:#d93025; --accent:#2e5395; --accent2:#5b7fd6; }}
* {{ box-sizing:border-box; }}
body {{ margin:0; font-family:-apple-system,"Microsoft YaHei",Helvetica,Arial,sans-serif;
background:var(--bg); color:var(--ink); padding:0 0 60px; }}
.hero {{ background:linear-gradient(120deg,#1c2b52,#2e5395 60%,#4f74c9); color:#fff;
padding:36px 32px 28px; margin-bottom:28px; }}
.hero h1 {{ font-size:24px; margin:0 0 6px; }}
.hero .meta {{ color:#cdd8f2; font-size:13px; }}
.wrap {{ padding:0 32px; }}
h2 {{ font-size:15px; color:var(--sub); text-transform:uppercase; letter-spacing:.06em;
margin:32px 0 12px; border-left:3px solid var(--accent); padding-left:8px; }}
.grid {{ display:grid; grid-template-columns:repeat(auto-fill,minmax(195px,1fr)); gap:14px; }}
.card {{ background:var(--card); border:1px solid var(--line); border-radius:12px; padding:16px;
box-shadow:0 1px 2px rgba(0,0,0,.04); }}
.card.err {{ opacity:.6; }}
.sym {{ font-weight:700; font-size:15px; margin-bottom:6px; }}
.price {{ font-size:20px; font-weight:700; margin-bottom:10px; }}
.row {{ display:flex; justify-content:space-between; font-size:12.5px; color:var(--sub); margin-bottom:4px; }}
.row.small {{ margin-top:8px; }}
.row span:last-child {{ color:var(--ink); font-weight:600; }}
.pos {{ color:var(--pos) !important; }} .neg {{ color:var(--neg) !important; }}
.badge {{ margin-top:8px; font-size:12px; font-weight:700; padding:4px 8px; border-radius:6px; display:inline-block; }}
.badge.on {{ background:#fdecea; color:var(--neg); }} .badge.off {{ background:#e6f4ea; color:var(--pos); }}
.errmsg {{ font-size:12px; color:var(--sub); }}
.pbadges {{ display:grid; grid-template-columns:repeat(4,1fr); gap:4px; margin-bottom:6px; }}
.pbadge {{ border-radius:7px; padding:5px 2px; text-align:center; font-size:10px; }}
.pbadge span {{ display:block; color:var(--sub); font-size:9.5px; margin-bottom:2px; }}
.pbadge b {{ font-size:10.5px; white-space:nowrap; }}
.pbadge.pos {{ background:#e6f4ea; }} .pbadge.pos b {{ color:var(--pos); }}
.pbadge.neg {{ background:#fdecea; }} .pbadge.neg b {{ color:var(--neg); }}
.pbadge.neu {{ background:#f1f2f4; }} .pbadge.neu b {{ color:var(--sub); }}
.chart-box {{ background:var(--card); border:1px solid var(--line); border-radius:12px; padding:20px;
margin-top:12px; }}
.chart-box h3 {{ margin:0 0 4px; font-size:14px; }}
.chart-box .sub {{ color:var(--sub); font-size:12px; margin-bottom:12px; }}
button {{ background:var(--accent); color:#fff; border:none; padding:9px 18px; border-radius:8px;
cursor:pointer; margin-top:36px; font-size:13px; }}
</style></head><body>
<div class="hero">
  <h1>📊 个人量化投资看板</h1>
  <div class="meta">数据更新至：{data['updated']}　|　数据源：Twelve Data，交易日收盘后自动更新　|　仅展示价格与信号，不含持仓明细</div>
</div>
<div class="wrap">

<h2>核心策略仓（回撤触发加仓）</h2>
<div class="grid">{core_html}</div>

<div class="chart-box">
  <h3>QQQ vs SPY · 月度涨跌幅对比</h3>
  <div class="sub">最近12个自然月，收盘价涨跌幅</div>
  <canvas id="monthlyChart" height="90"></canvas>
</div>

<h2>宽基指数</h2>
<div class="grid">{index_html}</div>

<h2>个股观察</h2>
<div class="grid">{stock_html}</div>

<button onclick="exportData()">导出当日数据 (JSON)</button>
</div>
<script>
const DATA = {json.dumps(data, ensure_ascii=False)};
const CHART_DATA = {json.dumps(chart_data, ensure_ascii=False)};
function exportData() {{
  const blob = new Blob([JSON.stringify(DATA,null,2)], {{type:"application/json"}});
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = "dashboard_" + DATA.updated + ".json";
  a.click();
}}
(function() {{
  const labels = (CHART_DATA.QQQ || []).map(x => x.month);
  const qqq = (CHART_DATA.QQQ || []).map(x => +(x.ret*100).toFixed(2));
  const spy = (CHART_DATA.SPY || []).map(x => +(x.ret*100).toFixed(2));
  new Chart(document.getElementById('monthlyChart'), {{
    type: 'bar',
    data: {{ labels, datasets: [
      {{ label: 'QQQ', data: qqq, backgroundColor: '#2e5395' }},
      {{ label: 'SPY', data: spy, backgroundColor: '#9db6e8' }},
    ]}},
    options: {{ responsive:true, plugins:{{legend:{{position:'bottom'}}}},
      scales: {{ y: {{ ticks: {{ callback: v => v + '%' }} }} }} }}
  }});
}})();
</script>
</body></html>"""

if __name__ == "__main__":
    data = build()
    os.makedirs("docs", exist_ok=True)
    with open("docs/index.html", "w", encoding="utf-8") as f:
        f.write(render_html(data))
    with open("docs/data.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print("done")
