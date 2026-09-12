import csv, io, json, datetime, os
import urllib.request, urllib.parse

API_KEY = os.environ["TWELVE_DATA_KEY"]

TICKERS = {
    "QQQM": {"threshold": 0.07},
    "VGT":  {"threshold": 0.10},
    "QLD":  {"threshold": 0.14},
    "TQQQ": {"threshold": None},
}

def fetch_history(symbol):
    params = urllib.parse.urlencode({
        "symbol": symbol,
        "interval": "1day",
        "outputsize": 60,
        "apikey": API_KEY,
    })
    url = f"https://api.twelvedata.com/time_series?{params}"
    with urllib.request.urlopen(url, timeout=20) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    if payload.get("status") == "error":
        raise RuntimeError(payload.get("message", "unknown Twelve Data error"))
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

def build():
    today = datetime.date.today()
    results = {}
    for name, cfg in TICKERS.items():
        try:
            rows = fetch_history(name)
            latest = rows[0]
            close = float(latest["close"])
            high = prior_month_high(rows, today)
            drawdown = (close - high) / high if high else None
            threshold = cfg["threshold"]
            triggered = bool(threshold is not None and drawdown is not None and -drawdown >= threshold)
            results[name] = {
                "date": latest["datetime"][:10], "close": close,
                "prior_month_high": high, "drawdown": drawdown,
                "threshold": threshold, "triggered": triggered,
            }
        except Exception as e:
            results[name] = {"error": str(e)}
    return {"updated": today.isoformat(), "assets": results}

def render_html(data):
    rows_html = ""
    for name, r in data["assets"].items():
        if "error" in r:
            rows_html += f"<tr><td>{name}</td><td colspan=5>数据获取失败：{r['error']}</td></tr>"
            continue
        dd = r["drawdown"]
        dd_str = f"{dd*100:.2f}%" if dd is not None else "-"
        flag = "🔴 触发加仓" if r["triggered"] else "🟢 正常"
        rows_html += f"""<tr><td>{name}</td><td>{r['date']}</td><td>${r['close']:.2f}</td>
        <td>${r['prior_month_high']:.2f}</td><td>{dd_str}</td><td>{flag}</td></tr>"""
    return f"""<!DOCTYPE html><html lang="zh"><head><meta charset="UTF-8"><title>量化看板</title>
<style>
body {{ font-family:-apple-system,"Microsoft YaHei",sans-serif; background:#0f1c3f; color:#fff; padding:24px; }}
table {{ width:100%; border-collapse:collapse; background:#16264f; border-radius:8px; overflow:hidden; }}
th,td {{ padding:12px; text-align:center; border-bottom:1px solid #2a3b6b; }}
th {{ background:#1f3864; }} button {{ background:#2e5395; color:#fff; border:none; padding:8px 16px; border-radius:6px; cursor:pointer; margin-top:16px; }}
.meta {{ color:#9fb3d9; font-size:13px; margin-bottom:16px; }}
</style></head><body>
<h1>📊 多资产量化管理平台 — 每日自动看板</h1>
<div class="meta">数据更新至：{data['updated']}（数据源：Twelve Data，交易日收盘后自动更新）</div>
<table><tr><th>资产</th><th>日期</th><th>收盘价</th><th>上月最高收盘</th><th>回撤幅度</th><th>状态</th></tr>
{rows_html}</table>
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
