import json, datetime, os, time
import urllib.request, urllib.parse

API_KEY = os.environ.get("TWELVE_DATA_KEY", "demo")
BASE = "https://api.twelvedata.com"

# 策略阈值
CORE = {"QQQM": 0.07, "VGT": 0.10, "QLD": 0.14, "TQQQ": None}
INDEX = ["QQQ", "SPY", "VOO", "SMH", "SPX", "IXIC"] 
VIX_SYM = "VIX" 

# 个股配置字典
STOCK_META = {
    "SOFI": {"name": "SoFi", "target": 15.0},
    "IREN": {"name": "Iris Energy", "target": 35.0},
    "ORCL": {"name": "Oracle", "target": 130.0},
    "TSLA": {"name": "Tesla", "target": 250.0},
    "NVDA": {"name": "Nvidia", "target": 110.0},
    "TSM": {"name": "TSMC", "target": 160.0},
    "LITE": {"name": "Lumentum", "target": 45.0},
    "AVGO": {"name": "Broadcom", "target": 1400.0},
    "MRVL": {"name": "Marvell", "target": 65.0},
    "NBIS": {"name": "Nebius", "target": 25.0},
    "GOOG": {"name": "Google", "target": 150.0},
    "AMD": {"name": "AMD", "target": 130.0},
    "HOOD": {"name": "Robinhood", "target": 20.0},
    "DRAM": {"name": "DRAM ETF", "target": None},
    "SPCX": {"name": "SPAC ETF", "target": None}
}
STOCKS = list(STOCK_META.keys())

def http_get_json(url):
    with urllib.request.urlopen(url, timeout=20) as resp:
        return json.loads(resp.read().decode("utf-8"))

def throttle():
    time.sleep(8) 

def fetch_time_series(symbol, outputsize=260, retries=3):
    params = urllib.parse.urlencode({"symbol": symbol, "interval": "1day", 
                                     "outputsize": outputsize, "apikey": API_KEY})
    url = f"{BASE}/time_series?{params}"
    
    for attempt in range(retries):
        try:
            payload = http_get_json(url)
            if payload.get("status") == "error":
                code = payload.get("code")
                msg = payload.get("message", "time_series error")
                if code == 429:
                    print(f"[{symbol}] 触发速率限制，等待 15 秒后重试 (第 {attempt+1}/{retries} 次)...")
                    time.sleep(15)
                    continue
                raise RuntimeError(msg)
            return payload["values"] 
        except Exception as e:
            if attempt == retries - 1:
                raise e
            print(f"[{symbol}] 网络异常 ({e})，等待 10 秒后重试...")
            time.sleep(10)

def calc_rsi(closes, period=14):
    if len(closes) < period + 1: return None
    closes_asc = closes[::-1]
    gains, losses = [], []
    for i in range(1, len(closes_asc)):
        change = closes_asc[i] - closes_asc[i-1]
        gains.append(change if change > 0 else 0)
        losses.append(abs(change) if change < 0 else 0)
    
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    
    for i in range(period, len(closes_asc)-1):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
        
    if avg_loss == 0: return 100.0
    rs = avg_gain / avg_loss
    return 100.0 - (100.0 / (1.0 + rs))

def calc_sma(closes, period=200):
    if len(closes) < period: return None
    return sum(closes[:period]) / period

def calc_ytd_high(rows, today):
    current_year = str(today.year)
    highs = [float(r["high"]) for r in rows if r["datetime"].startswith(current_year)]
    return max(highs) if highs else None

def pct_change(latest, prior):
    return (latest - prior) / prior if prior else None

def analyze(symbol, rows, today, threshold=None, is_stock=False):
    closes = [float(r["close"]) for r in rows]
    latest_close = closes[0]
    prev_close = closes[1] if len(closes) > 1 else latest_close
    
    ytd_high = calc_ytd_high(rows, today)
    all_time_high = max([float(r["high"]) for r in rows]) if rows else None
    
    out = {
        "date": rows[0]["datetime"][:10],
        "close": latest_close,
        "prev_close": prev_close,
        "day_chg": pct_change(latest_close, prev_close),
        "ytd_high": ytd_high,
        "rsi": calc_rsi(closes, 14),
        "dist_200ma": pct_change(latest_close, calc_sma(closes, 200))
    }
    
    if is_stock:
        out.update({"open": float(rows[0]["open"]), "high": float(rows[0]["high"]), "low": float(rows[0]["low"])})
    else:
        drawdown = pct_change(latest_close, all_time_high)
        out.update({
            "drawdown": drawdown,
            "threshold": threshold,
            "triggered": bool(threshold is not None and drawdown is not None and -drawdown >= threshold)
        })
    return out

def build():
    today = datetime.date.today()
    core, index, stocks, vix_data, overview_charts = {}, {}, {}, {}, {}
    
    for name, threshold in CORE.items():
        try:
            core[name] = analyze(name, fetch_time_series(name), today, threshold)
        except Exception as e:
            core[name] = {"error": str(e)}
        throttle()
        
    for name in INDEX:
        try:
            rows = fetch_time_series(name)
            index[name] = analyze(name, rows, today)
            # 专门为标普和纳指提取最近30天的收盘价用于总览绘图
            if name in ["SPX", "IXIC"]:
                overview_charts[name] = [{"d": r["datetime"][:10], "c": float(r["close"])} for r in rows[:30][::-1]]
        except Exception as e:
            index[name] = {"error": str(e)}
        throttle()
        
    try:
        vix_data = analyze(VIX_SYM, fetch_time_series(VIX_SYM), today)
    except Exception as e:
        vix_data = {"error": str(e)}
    throttle()
        
    for name in STOCKS:
        try:
            stocks[name] = analyze(name, fetch_time_series(name), today, is_stock=True)
        except Exception as e:
            stocks[name] = {"error": str(e)}
        throttle()
        
    return {"updated": today.isoformat(), "core": core, "index": index, "stocks": stocks, "vix": vix_data, "overview_charts": overview_charts}

def fmt_pct(x, digits=2): return f"{x*100:.{digits}f}%" if isinstance(x, (int, float)) else "-"
def fmt_num(x, digits=2): return f"{x:.{digits}f}" if isinstance(x, (int, float)) else "-"

def card_etf(name, r):
    if "error" in r: return f'<div class="card err"><div class="sym">{name}</div><div class="errmsg">获取失败</div></div>'
    trigger_html = ""
    if r.get("threshold") is not None:
        flag = "🔴 触发加仓" if r["triggered"] else "🟢 正常观察"
        status_cls = "alert-on" if r["triggered"] else "alert-off"
        trigger_html = f'''<div class="row mt"><span>触发阈值</span><span class="fw-bold">{fmt_pct(r["threshold"])}</span></div>
                           <div class="status-badge {status_cls}">{flag}</div>'''
    drawdown_cls = "neg-text fw-bold" if r["drawdown"] and r["drawdown"] < 0 else "fw-bold"
    
    return f'''<div class="card">
      <div class="card-header"><span class="sym">{name}</span><span class="price">${r["close"]:.2f}</span></div>
      <div class="divider"></div>
      <div class="row"><span>年度最高</span><span class="fw-bold">${fmt_num(r["ytd_high"])}</span></div>
      <div class="row"><span>最高点回撤</span><span class="{drawdown_cls}">{fmt_pct(r["drawdown"])}</span></div>
      <div class="row"><span>RSI (14)</span><span class="fw-bold">{fmt_num(r["rsi"])}</span></div>
      <div class="row"><span>距 200MA</span><span class="fw-bold">{fmt_pct(r["dist_200ma"])}</span></div>
      {trigger_html}
    </div>'''

def row_stock(sym, r):
    if "error" in r: return f'<tr class="err"><td><b>{sym}</b></td><td colspan="11">获取数据失败</td></tr>'
    target = STOCK_META.get(sym, {}).get("target")
    name = STOCK_META.get(sym, {}).get("name", sym)
    
    target_str = f"${target:.2f}" if target else "-"
    action_html = f'<span class="alert-text fw-bold ml">(信号触发!)</span>' if target and r["close"] <= target else ""
    chg_cls = "pos-text" if (r["day_chg"] or 0) >= 0 else "neg-text"
    chg_sign = "+" if (r["day_chg"] or 0) >= 0 else ""
    
    return f'''<tr>
        <td><b>{sym}</b></td><td class="sub-text">{name}</td>
        <td class="fw-bold">${r["close"]:.2f}</td><td class="{chg_cls}">{chg_sign}{fmt_pct(r["day_chg"])}</td>
        <td>${r["prev_close"]:.2f}</td><td>${r["open"]:.2f}</td><td>${r["high"]:.2f}</td><td>${r["low"]:.2f}</td>
        <td>${fmt_num(r["ytd_high"])}</td><td>{fmt_num(r["rsi"])}</td><td>{fmt_pct(r["dist_200ma"])}</td>
        <td><b>{target_str}</b> {action_html}</td>
    </tr>'''

def render_overview_card(title, data, prefix="$"):
    if not data or "error" in data: return ""
    chg = data.get("day_chg", 0)
    color = "pos-text" if chg >= 0 else "neg-text"
    sign = "+" if chg >= 0 else ""
    return f'''
    <div class="overview-stat-card">
      <div class="title">{title}</div>
      <div class="val">{prefix}{data["close"]:.2f}</div>
      <div class="chg {color}">{sign}{fmt_pct(chg)}</div>
    </div>'''

def render_html(data):
    core_html = "".join(card_etf(k, v) for k, v in data["core"].items())
    index_html = "".join(card_etf(k, v) for k, v in data["index"].items())
    stock_html = "".join(row_stock(k, v) for k, v in data["stocks"].items())
    
    spx_card = render_overview_card("S&P 500 (标普)", data["index"].get("SPX"))
    ixic_card = render_overview_card("NASDAQ (纳指)", data["index"].get("IXIC"))
    
    vix = data.get("vix", {})
    vix_val = vix.get("close", 0)
    v_color = "pos-text" if vix_val < 15 else "warn-text" if vix_val < 20 else "alert-text" if vix_val < 30 else "neg-text"
    v_status = "🟢 低波动环境" if vix_val < 15 else "🟡 正常波动环境" if vix_val < 20 else "🟠 恐慌升温" if vix_val < 30 else "🔴 极端恐慌"
    vix_card = f'''<div class="overview-stat-card"><div class="title">VIX 恐慌指数</div><div class="val {v_color}">{vix_val:.2f}</div><div class="chg" style="color:var(--sub)">{v_status}</div></div>''' if "error" not in vix else ""

    return f"""<!DOCTYPE html><html lang="zh"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>个人量化复盘面板</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4"></script>
<style>
:root {{ 
  --bg:#f3f4f6; --card:#ffffff; --ink:#0f172a; --sub:#64748b; --line:#e2e8f0;
  --sidebar-bg:#0f172a; --sidebar-hover:#1e293b; --sidebar-txt:#94a3b8; --sidebar-active:#3b82f6;
  --pos:#10b981; --neg:#ef4444; --pos-bg:#d1fae5; --neg-bg:#fee2e2;
  --warn:#f59e0b; --alert:#ea580c; --accent:#2563eb; 
}}
* {{ box-sizing:border-box; margin:0; padding:0; }}
body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Arial, sans-serif; background: var(--bg); color: var(--ink); display: flex; height: 100vh; overflow: hidden; }}

/* 侧边栏 */
.sidebar {{ width: 220px; background: var(--sidebar-bg); color: #fff; display: flex; flex-direction: column; flex-shrink: 0; }}
.brand {{ padding: 24px 20px; font-size: 18px; font-weight: 700; border-bottom: 1px solid #1e293b; letter-spacing: 0.5px; }}
.nav-menu {{ list-style: none; margin-top: 12px; }}
.nav-menu li {{ padding: 14px 24px; cursor: pointer; color: var(--sidebar-txt); font-size: 15px; font-weight: 500; transition: all 0.2s; }}
.nav-menu li:hover {{ background: var(--sidebar-hover); color: #fff; }}
.nav-menu li.active {{ background: var(--sidebar-hover); color: #fff; border-left: 4px solid var(--sidebar-active); }}

/* 主内容区 */
.main-wrapper {{ flex: 1; display: flex; flex-direction: column; overflow: hidden; }}
.topbar {{ background: #fff; padding: 16px 24px; border-bottom: 1px solid var(--line); display: flex; justify-content: space-between; font-size: 13px; color: var(--sub); flex-shrink: 0; }}
.content {{ flex: 1; padding: 24px; overflow-y: auto; }}
.tab-pane {{ display: none; animation: fadeIn 0.3s; }}
.tab-pane.active {{ display: block; }}
@keyframes fadeIn {{ from {{ opacity: 0; transform: translateY(5px); }} to {{ opacity: 1; transform: translateY(0); }} }}

h2 {{ font-size: 18px; font-weight: 600; margin-bottom: 20px; display: flex; align-items: center; gap: 8px; }}
h2::before {{ content: ''; display: block; width: 4px; height: 18px; background: var(--accent); border-radius: 2px; }}

/* 总览卡片 */
.overview-grid {{ display: flex; gap: 20px; margin-bottom: 24px; }}
.overview-stat-card {{ background: #fff; padding: 20px; border-radius: 12px; border: 1px solid var(--line); flex: 1; box-shadow: 0 1px 2px rgba(0,0,0,0.05); }}
.overview-stat-card .title {{ font-size: 13px; color: var(--sub); text-transform: uppercase; margin-bottom: 8px; }}
.overview-stat-card .val {{ font-size: 28px; font-weight: 700; font-variant-numeric: tabular-nums; margin-bottom: 4px; }}
.overview-stat-card .chg {{ font-size: 14px; font-weight: 600; }}
.chart-box {{ background: #fff; padding: 24px; border-radius: 12px; border: 1px solid var(--line); box-shadow: 0 1px 2px rgba(0,0,0,0.05); }}

/* 卡片网格 */
.grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(260px, 1fr)); gap: 20px; }}
.card {{ background: var(--card); border: 1px solid var(--line); border-radius: 12px; padding: 20px; box-shadow: 0 1px 2px rgba(0,0,0,0.05); }}
.card-header {{ display: flex; justify-content: space-between; align-items: baseline; }}
.sym {{ font-weight: 700; font-size: 18px; }}
.price {{ font-size: 22px; font-weight: 800; font-variant-numeric: tabular-nums; }}
.divider {{ height: 1px; background: var(--line); margin: 12px 0; }}
.row {{ display: flex; justify-content: space-between; font-size: 13px; color: var(--sub); margin-bottom: 8px; }}
.row.mt {{ margin-top: 12px; }}
.fw-bold {{ color: var(--ink); font-weight: 600; }}
.ml {{ margin-left: 6px; }}

/* 颜色 */
.pos-text {{ color: var(--pos) !important; font-weight: 600; }}
.neg-text {{ color: var(--neg) !important; font-weight: 600; }}
.warn-text {{ color: var(--warn) !important; font-weight: 600; }}
.alert-text {{ color: var(--alert) !important; font-weight: 600; }}
.status-badge {{ margin-top: 12px; font-size: 13px; font-weight: 600; padding: 8px; border-radius: 8px; text-align: center; }}
.alert-on {{ background: var(--neg-bg); color: var(--neg); border: 1px solid #fca5a5; }} 
.alert-off {{ background: var(--pos-bg); color: var(--pos); border: 1px solid #6ee7b7; }}

/* 表格 */
.table-container {{ overflow-x: auto; background: var(--card); border: 1px solid var(--line); border-radius: 12px; }}
table {{ width: 100%; border-collapse: collapse; text-align: right; white-space: nowrap; font-variant-numeric: tabular-nums; }}
th, td {{ padding: 14px 16px; border-bottom: 1px solid var(--line); font-size: 13px; }}
th {{ background: #f8fafc; color: var(--sub); font-weight: 600; text-align: right; }}
th:nth-child(1), td:nth-child(1), th:nth-child(2), td:nth-child(2) {{ text-align: left; }}
tr:hover {{ background: #f1f5f9; }}
tr:last-child td {{ border-bottom: none; }}
</style></head><body>

<div class="sidebar">
  <div class="brand">📊 量化复盘</div>
  <ul class="nav-menu">
    <li class="active" onclick="switchTab('tab-overview', this)">大盘总览</li>
    <li onclick="switchTab('tab-core', this)">核心策略仓</li>
    <li onclick="switchTab('tab-index', this)">宽基指数</li>
    <li onclick="switchTab('tab-stocks', this)">个股观察池</li>
  </ul>
</div>

<div class="main-wrapper">
  <div class="topbar">
    <span>当前数据更新日期: {data['updated']}</span>
    <span>数据源: Twelve Data API</span>
  </div>
  
  <div class="content">
    <!-- 总览 Tab -->
    <div id="tab-overview" class="tab-pane active">
      <h2>昨日收盘行情总览</h2>
      <div class="overview-grid">
        {ixic_card}
        {spx_card}
        {vix_card}
      </div>
      <div class="chart-box">
        <h3 style="font-size:15px; margin-bottom: 16px; color:var(--ink);">纳指 (IXIC) & 标普 (SPX) · 近30日走势</h3>
        <canvas id="trendChart" height="80"></canvas>
      </div>
    </div>
    
    <!-- 核心仓 Tab -->
    <div id="tab-core" class="tab-pane">
      <h2>核心策略仓 (回撤加仓机制)</h2>
      <div class="grid">{core_html}</div>
    </div>
    
    <!-- 宽基 Tab -->
    <div id="tab-index" class="tab-pane">
      <h2>宽基指数及行业ETF</h2>
      <div class="grid">{index_html}</div>
    </div>
    
    <!-- 个股 Tab -->
    <div id="tab-stocks" class="tab-pane">
      <h2>个股观察矩阵</h2>
      <div class="table-container">
        <table>
          <thead>
            <tr><th>代码</th><th>名称</th><th>最新价</th><th>涨跌幅</th><th>昨收</th><th>开盘</th><th>最高</th><th>最低</th><th>年内最高</th><th>RSI(14)</th><th>距200MA</th><th>目标加仓价 (策略点)</th></tr>
          </thead>
          <tbody>{stock_html}</tbody>
        </table>
      </div>
    </div>
  </div>
</div>

<script>
const CHART_DATA = {json.dumps(data.get("overview_charts", {}), ensure_ascii=False)};

// 标签页切换逻辑
function switchTab(tabId, el) {{
  document.querySelectorAll('.tab-pane').forEach(t => t.classList.remove('active'));
  document.querySelectorAll('.nav-menu li').forEach(l => l.classList.remove('active'));
  document.getElementById(tabId).classList.add('active');
  el.classList.add('active');
}}

// 渲染总览走势图
window.onload = function() {{
  if(!CHART_DATA.IXIC || !CHART_DATA.SPX) return;
  const labels = CHART_DATA.IXIC.map(x => x.d);
  const ixic_vals = CHART_DATA.IXIC.map(x => x.c);
  const spx_vals = CHART_DATA.SPX.map(x => x.c);
  
  Chart.defaults.font.family = '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto';
  
  new Chart(document.getElementById('trendChart'), {{
    type: 'line',
    data: {{
      labels: labels,
      datasets: [
        {{ label: 'NASDAQ', data: ixic_vals, borderColor: '#2563eb', backgroundColor: 'rgba(37, 99, 235, 0.1)', borderWidth: 2, tension: 0.3, yAxisID: 'y' }},
        {{ label: 'S&P 500', data: spx_vals, borderColor: '#10b981', backgroundColor: 'transparent', borderWidth: 2, borderDash: [5, 5], tension: 0.3, yAxisID: 'y1' }}
      ]
    }},
    options: {{
      responsive: true,
      interaction: {{ mode: 'index', intersect: false }},
      plugins: {{ legend: {{ position: 'top', align: 'end' }} }},
      scales: {{
        x: {{ grid: {{ display: false }} }},
        y: {{ type: 'linear', display: true, position: 'left', grid: {{ color: '#f1f5f9' }} }},
        y1: {{ type: 'linear', display: true, position: 'right', grid: {{ drawOnChartArea: false }} }}
      }}
    }}
  }});
}}
</script>
</body></html>"""

if __name__ == "__main__":
    data = build()
    os.makedirs("docs", exist_ok=True)
    with open("docs/index.html", "w", encoding="utf-8") as f:
        f.write(render_html(data))
    with open("docs/data.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print("UI布局已更新为单页侧边栏 Dashboard！")
