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
    spx = data["index"].get("SPX", {})
    ixic = data["index"].get("IXIC", {})
    vix = data.get("vix", {})

    def market_state(v):
        if not isinstance(v, (int, float)): return ("数据待更新", "neutral")
        if v < 15: return ("低波动", "good")
        if v < 20: return ("正常波动", "good")
        if v < 30: return ("波动升温", "warn")
        return ("高风险", "bad")

    def metric_card(label, value, change=None, note="", tone="neutral"):
        change_html = ""
        if isinstance(change, (int, float)):
            cls = "positive" if change >= 0 else "negative"
            sign = "+" if change >= 0 else ""
            change_html = f'<div class="metric-change {cls}">{sign}{fmt_pct(change)}</div>'
        return f'''<div class="metric-card"><div class="metric-top"><span>{label}</span><span class="metric-dot {tone}"></span></div><div class="metric-value">{value}</div>{change_html}<div class="metric-note">{note}</div></div>'''

    vix_value = vix.get("close") if "error" not in vix else None
    vix_state, vix_tone = market_state(vix_value)
    vix_display = fmt_num(vix_value) if vix_value is not None else "—"
    spx_value = f'${spx["close"]:,.2f}' if "error" not in spx else "—"
    ixic_value = f'${ixic["close"]:,.2f}' if "error" not in ixic else "—"
    spx_chg = spx.get("day_chg") if "error" not in spx else None
    ixic_chg = ixic.get("day_chg") if "error" not in ixic else None
    signal_count = sum(1 for v in data["core"].values() if v.get("triggered"))
    signal_text = f"{signal_count} 个策略点" if signal_count else "暂无触发"
    signal_tone = "bad" if signal_count else "good"
    chart_json = json.dumps(data.get("overview_charts", {}), ensure_ascii=False)

    return f'''<!DOCTYPE html><html lang="zh-CN"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"><meta name="description" content="公开版量化投资研究与市场观察平台。"><title>QuantScope · 量化投资研究平台</title><script src="https://cdn.jsdelivr.net/npm/chart.js@4"></script>
<style>
:root {{--bg:#f6f8fb;--surface:#fff;--surface2:#f8fafc;--ink:#162033;--muted:#718096;--line:#e7ebf1;--nav:#101827;--navmuted:#93a0b5;--accent:#4f46e5;--accent2:#7c3aed;--green:#0f9f6e;--red:#dc4c64;--amber:#c98508;--shadow:0 10px 30px rgba(15,23,42,.06)}}
*{{box-sizing:border-box;margin:0;padding:0}} body{{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,"PingFang SC","Microsoft YaHei",Arial,sans-serif;background:var(--bg);color:var(--ink);min-height:100vh}} .app{{display:flex;min-height:100vh}}
.sidebar{{width:248px;background:linear-gradient(180deg,#101827,#0d1522);color:#fff;padding:24px 16px;position:fixed;inset:0 auto 0 0;z-index:20}} .brand{{display:flex;align-items:center;gap:11px;padding:8px 10px 28px;border-bottom:1px solid rgba(255,255,255,.08)}} .brand-mark{{width:38px;height:38px;border-radius:11px;display:grid;place-items:center;background:linear-gradient(135deg,var(--accent),var(--accent2));font-size:18px;box-shadow:0 8px 20px rgba(79,70,229,.28)}} .brand strong{{display:block;font-size:17px}} .brand small{{display:block;color:#8e9bb0;margin-top:3px;font-size:11px}}
.nav-title{{color:#65738a;font-size:10px;font-weight:800;letter-spacing:1.3px;margin:25px 10px 8px}} .nav-menu{{list-style:none;display:grid;gap:4px}} .nav-menu li{{display:flex;align-items:center;gap:11px;padding:11px 12px;border-radius:10px;color:var(--navmuted);cursor:pointer;font-size:13px;font-weight:600;transition:.18s}} .nav-menu li:hover{{background:rgba(255,255,255,.06);color:#fff}} .nav-menu li.active{{color:#fff;background:linear-gradient(90deg,rgba(79,70,229,.28),rgba(79,70,229,.08));box-shadow:inset 3px 0 0 #818cf8}} .nav-icon{{width:18px;text-align:center}} .sidebar-footer{{position:absolute;left:26px;right:26px;bottom:24px;color:#65738a;font-size:10px;line-height:1.7}}
.main{{margin-left:248px;width:calc(100% - 248px);min-width:0}} .topbar{{height:68px;background:rgba(255,255,255,.9);backdrop-filter:blur(14px);border-bottom:1px solid var(--line);display:flex;align-items:center;justify-content:space-between;padding:0 34px;position:sticky;top:0;z-index:10}} .breadcrumb{{font-size:13px;color:var(--muted)}} .breadcrumb strong{{color:var(--ink)}} .top-meta{{display:flex;gap:16px;color:var(--muted);font-size:11px}} .live-dot{{width:7px;height:7px;border-radius:50%;background:#10b981;display:inline-block;margin-right:6px}}
.content{{max-width:1500px;margin:0 auto;padding:34px}} .hero{{display:flex;justify-content:space-between;gap:24px;align-items:flex-end;margin-bottom:26px}} .eyebrow{{color:var(--accent);font-size:11px;font-weight:800;letter-spacing:1.4px;margin-bottom:9px}} h1{{font-size:30px;line-height:1.2;letter-spacing:-.7px}} .hero p{{color:var(--muted);margin-top:9px;font-size:13px;line-height:1.7;max-width:680px}} .public-note{{flex:0 0 270px;background:linear-gradient(135deg,#eef2ff,#f5f3ff);border:1px solid #e3e6ff;border-radius:14px;padding:15px 17px;font-size:11px;color:#59627a;line-height:1.65}} .public-note strong{{color:#3730a3;display:block;margin-bottom:4px}}
.section{{margin-top:30px}} .section-head{{display:flex;justify-content:space-between;align-items:center;margin-bottom:13px}} .section-head h2{{font-size:16px}} .section-head p{{color:var(--muted);font-size:11px}} .metrics{{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:14px}} .metric-card{{background:var(--surface);border:1px solid var(--line);border-radius:15px;padding:17px 18px;box-shadow:var(--shadow);min-height:130px}} .metric-top{{display:flex;justify-content:space-between;color:var(--muted);font-size:11px;font-weight:700}} .metric-dot{{width:8px;height:8px;border-radius:50%;background:#a8b0bd}} .metric-dot.good{{background:#10b981}} .metric-dot.warn{{background:#f59e0b}} .metric-dot.bad{{background:#ef4444}} .metric-value{{font-size:25px;font-weight:800;letter-spacing:-.5px;margin-top:12px;font-variant-numeric:tabular-nums}} .metric-change{{font-size:12px;font-weight:700;margin-top:4px}} .positive{{color:var(--green)}} .negative{{color:var(--red)}} .metric-note{{color:var(--muted);font-size:10px;margin-top:8px}}
.dashboard-grid{{display:grid;grid-template-columns:minmax(0,1.65fr) minmax(280px,.75fr);gap:16px}} .panel{{background:var(--surface);border:1px solid var(--line);border-radius:16px;box-shadow:var(--shadow)}} .panel-head{{display:flex;justify-content:space-between;align-items:center;padding:17px 19px;border-bottom:1px solid var(--line)}} .panel-head strong{{font-size:13px}} .panel-head span{{color:var(--muted);font-size:10px}} .chart-wrap{{height:310px;padding:15px 18px 18px}} .chart-empty{{height:100%;display:grid;place-items:center;color:var(--muted);font-size:12px;background:var(--surface2);border-radius:10px}} .pulse-list{{padding:8px 18px 14px}} .pulse{{display:flex;align-items:center;justify-content:space-between;padding:15px 0;border-bottom:1px solid var(--line)}} .pulse:last-child{{border-bottom:0}} .pulse-label{{color:var(--muted);font-size:11px}} .pulse-main{{margin-top:4px;font-size:15px;font-weight:800}} .pulse-right{{text-align:right;font-size:11px;font-weight:700}}
.badge{{display:inline-flex;border-radius:999px;padding:5px 9px;font-size:10px;font-weight:800}} .badge.good{{background:#eaf8f2;color:#087f59}} .badge.warn{{background:#fff6df;color:#9a6500}} .badge.bad{{background:#fff0f2;color:#b62e47}} .badge.neutral{{background:#eef1f5;color:#667085}}
.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(250px,1fr));gap:14px}} .card{{background:var(--surface);border:1px solid var(--line);border-radius:15px;padding:17px;box-shadow:var(--shadow);transition:.18s}} .card:hover{{transform:translateY(-2px);box-shadow:0 14px 32px rgba(15,23,42,.09)}} .card-header{{display:flex;justify-content:space-between;align-items:center}} .sym{{font-weight:850;font-size:16px}} .price{{font-size:19px;font-weight:850;font-variant-numeric:tabular-nums}} .divider{{height:1px;background:var(--line);margin:14px 0}} .row{{display:flex;justify-content:space-between;gap:15px;font-size:11px;color:var(--muted);margin-bottom:9px}} .fw-bold{{color:var(--ink);font-weight:700}} .status-badge{{margin-top:14px;font-size:11px;font-weight:800;padding:8px 10px;border-radius:9px;text-align:center}} .alert-on{{background:#fff0f2;color:#b62e47;border:1px solid #ffd0d7}} .alert-off{{background:#eaf8f2;color:#087f59;border:1px solid #c8eddf}} .err{{border-style:dashed}} .errmsg{{color:var(--muted);font-size:11px;margin-top:14px}}
.table-container{{overflow:auto;background:var(--surface);border:1px solid var(--line);border-radius:15px;box-shadow:var(--shadow)}} table{{width:100%;border-collapse:collapse;text-align:right;white-space:nowrap;font-variant-numeric:tabular-nums}} th,td{{padding:12px 14px;border-bottom:1px solid var(--line);font-size:11px}} th{{background:#f8fafc;color:var(--muted);font-weight:700;position:sticky;top:0}} th:nth-child(1),td:nth-child(1),th:nth-child(2),td:nth-child(2){{text-align:left}} tr:hover td{{background:#fbfcfe}} tr:last-child td{{border-bottom:0}} .sub-text{{color:var(--muted)}} .footer{{color:#8993a4;font-size:10px;line-height:1.7;text-align:center;padding:30px 0 12px}} .tab-pane{{display:none;animation:fade .22s ease}} .tab-pane.active{{display:block}} @keyframes fade{{from{{opacity:0;transform:translateY(4px)}}to{{opacity:1;transform:none}}}}
@media(max-width:1000px){{.sidebar{{width:205px}}.main{{margin-left:205px;width:calc(100% - 205px)}}.metrics{{grid-template-columns:repeat(2,1fr)}}.dashboard-grid{{grid-template-columns:1fr}}.content{{padding:25px}}}} @media(max-width:700px){{.sidebar{{position:sticky;top:0;width:100%;height:auto;padding:10px 12px}}.app{{display:block}}.brand{{padding:3px 5px 10px;border:0}}.brand-mark{{width:32px;height:32px}}.nav-title,.sidebar-footer{{display:none}}.nav-menu{{display:flex;overflow-x:auto}}.nav-menu li{{flex:0 0 auto;padding:9px 11px;font-size:11px}}.main{{margin-left:0;width:100%}}.topbar{{height:54px;padding:0 16px}}.top-meta{{display:none}}.content{{padding:20px 14px}}.hero{{display:block}}h1{{font-size:25px}}.public-note{{margin-top:15px;width:100%}}.metrics{{grid-template-columns:1fr 1fr;gap:10px}}.metric-card{{min-height:118px;padding:14px}}.metric-value{{font-size:21px}}.chart-wrap{{height:250px}}}} @media(max-width:430px){{.metrics{{grid-template-columns:1fr}}}}
</style></head><body><div class="app"><aside class="sidebar"><div class="brand"><div class="brand-mark">◈</div><div><strong>QuantScope</strong><small>量化投资研究平台</small></div></div><div class="nav-title">MARKET RESEARCH</div><ul class="nav-menu"><li class="active" onclick="switchTab('tab-overview',this)"><span class="nav-icon">⌂</span>市场总览</li><li onclick="switchTab('tab-core',this)"><span class="nav-icon">◒</span>策略信号</li><li onclick="switchTab('tab-index',this)"><span class="nav-icon">◫</span>指数 & ETF</li><li onclick="switchTab('tab-stocks',this)"><span class="nav-icon">⌁</span>个股观察池</li></ul><div class="sidebar-footer">公开研究版 · 不展示个人真实资产<br>数据仅用于研究与策略演示</div></aside><main class="main"><header class="topbar"><div class="breadcrumb">QuantScope / <strong>市场总览</strong></div><div class="top-meta"><span><i class="live-dot"></i>数据状态正常</span><span>更新：{data['updated']}</span><span>Public Research</span></div></header><div class="content">
<div id="tab-overview" class="tab-pane active"><section class="hero"><div><div class="eyebrow">QUANTITATIVE MARKET INTELLIGENCE</div><h1>用数据观察市场，而不是展示账户。</h1><p>公开版投资研究面板：聚焦市场趋势、回撤、波动率与策略触发条件。个人真实资金、持仓数量与账户信息不在公开页面展示。</p></div><div class="public-note"><strong>🔒 公开展示模式</strong>这里展示的是研究指标与策略信号，不代表任何个人账户的实际仓位或收益。未来可在私有端预留 Portfolio 模块。</div></section><section class="section"><div class="section-head"><h2>市场核心指标</h2><p>昨日收盘 · 自动更新</p></div><div class="metrics">{metric_card('NASDAQ 综合指数',ixic_value,ixic_chg,'市场成长风格温度','good' if isinstance(ixic_chg,(int,float)) and ixic_chg>=0 else 'warn')}{metric_card('S&P 500',spx_value,spx_chg,'大盘风险偏好','good' if isinstance(spx_chg,(int,float)) and spx_chg>=0 else 'warn')}{metric_card('VIX 恐慌指数',vix_display,None,vix_state,vix_tone)}{metric_card('策略触发状态',signal_text,None,'仅显示规则信号，不显示资金规模',signal_tone)}</div></section><section class="section dashboard-grid"><div class="panel"><div class="panel-head"><strong>NASDAQ & S&P 500 · 近 30 个交易日</strong><span>历史走势</span></div><div class="chart-wrap"><canvas id="trendChart"></canvas><div id="chartEmpty" class="chart-empty" style="display:none">当前指数历史数据暂不可用，待下一次自动更新。</div></div></div><div class="panel"><div class="panel-head"><strong>Market Pulse</strong><span>研究状态</span></div><div class="pulse-list"><div class="pulse"><div><div class="pulse-label">波动环境</div><div class="pulse-main">{vix_state}</div></div><div class="pulse-right"><span class="badge {vix_tone}">VIX {vix_display}</span></div></div><div class="pulse"><div><div class="pulse-label">策略观察</div><div class="pulse-main">{signal_text}</div></div><div class="pulse-right"><span class="badge {signal_tone}">RULE BASED</span></div></div><div class="pulse"><div><div class="pulse-label">数据源</div><div class="pulse-main">Twelve Data</div></div><div class="pulse-right"><span class="badge neutral">API</span></div></div></div></div></section></div>
<div id="tab-core" class="tab-pane"><section class="hero"><div><div class="eyebrow">STRATEGY ENGINE</div><h1>策略信号</h1><p>用回撤、RSI 与长期均线观察核心 ETF 的风险与潜在策略触发点。这里不显示真实仓位。</p></div><div class="public-note"><strong>策略公开版</strong>未来可在私有端增加资金分配、最大仓位与账户级风控，但公开页面只保留信号层。</div></section><section class="section"><div class="section-head"><h2>核心策略观察</h2><p>规则驱动 · 不代表交易建议</p></div><div class="grid">{core_html}</div></section></div>
<div id="tab-index" class="tab-pane"><section class="hero"><div><div class="eyebrow">INDEX & ETF</div><h1>指数与行业 ETF</h1><p>从宽基指数到行业 ETF，快速观察价格、回撤、RSI 与 200 日均线距离。</p></div></section><section class="section"><div class="grid">{index_html}</div></section></div>
<div id="tab-stocks" class="tab-pane"><section class="hero"><div><div class="eyebrow">WATCHLIST</div><h1>个股观察池</h1><p>公开展示研究标的的市场数据与策略参考点，不展示个人成本、持仓数量或账户收益。</p></div></section><section class="section"><div class="table-container"><table><thead><tr><th>代码</th><th>名称</th><th>最新价</th><th>涨跌幅</th><th>昨收</th><th>开盘</th><th>最高</th><th>最低</th><th>年内最高</th><th>RSI(14)</th><th>距200MA</th><th>策略参考价</th></tr></thead><tbody>{stock_html}</tbody></table></div></section></div>
<div class="footer">QuantScope · Public Research Dashboard · {data['updated']}<br>市场数据与策略指标仅供研究、学习与信息参考，不构成投资建议。</div></div></main></div>
<script>const CHART_DATA={chart_json};function switchTab(id,el){{document.querySelectorAll('.tab-pane').forEach(t=>t.classList.remove('active'));document.querySelectorAll('.nav-menu li').forEach(l=>l.classList.remove('active'));document.getElementById(id).classList.add('active');el.classList.add('active');window.scrollTo({{top:0,behavior:'smooth'}})}}window.addEventListener('load',function(){{const c=document.getElementById('trendChart'),e=document.getElementById('chartEmpty'),ix=CHART_DATA.IXIC||[],sp=CHART_DATA.SPX||[];if(!ix.length||!sp.length){{c.style.display='none';e.style.display='grid';return}}const labels=ix.map(x=>x.d),iv=ix.map(x=>x.c),sv=sp.map(x=>x.c);new Chart(c,{{type:'line',data:{{labels,datasets:[{{label:'NASDAQ',data:iv,borderColor:'#4f46e5',backgroundColor:'rgba(79,70,229,.08)',fill:true,borderWidth:2,pointRadius:0,tension:.35,yAxisID:'y'}},{{label:'S&P 500',data:sv,borderColor:'#0f9f6e',backgroundColor:'transparent',borderWidth:2,pointRadius:0,tension:.35,yAxisID:'y1'}}]}},options:{{responsive:true,maintainAspectRatio:false,interaction:{{mode:'index',intersect:false}},plugins:{{legend:{{position:'top',align:'end'}}}},scales:{{x:{{grid:{{display:false}},ticks:{{maxTicksLimit:7}}}},y:{{position:'left',grid:{{color:'#eef1f5'}}}},y1:{{position:'right',grid:{{drawOnChartArea:false}}}}}}}}}})}});</script></body></html>'''

if __name__ == '__main__':
    data = build()
    out = os.path.join(os.path.dirname(__file__), '..', 'docs', 'data.json')
    with open(out, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    html = render_html(data)
    html_out = os.path.join(os.path.dirname(__file__), '..', 'docs', 'index.html')
    with open(html_out, 'w', encoding='utf-8') as f:
        f.write(html)
    print(f'Generated {html_out}')

