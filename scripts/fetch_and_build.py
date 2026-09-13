import json, datetime, os, time
import urllib.request, urllib.parse

API_KEY = os.environ.get("TWELVE_DATA_KEY", "demo")
BASE = "https://api.twelvedata.com"

# 策略阈值（核心策略仓）
CORE = {"QQQM": 0.07, "VGT": 0.10, "QLD": 0.14, "TQQQ": None}
# 宽基指数：用可交易ETF代替不受支持的裸指数代码(SPX/IXIC在Twelve Data免费版404)
INDEX = ["QQQ", "SPY", "VOO", "SMH"]
# 波动率代理：VIX指数本身在Twelve Data不受支持，用VIXY(ETF)代替
VOL_PROXY_SYM = "VIXY"

# 个股配置字典（中文名称 + 策略参考价，参考价数值后续由你手动更新）
STOCK_META = {
    "SOFI": {"name": "SoFi Technologies", "target": 15.0},
    "IREN": {"name": "Iris Energy", "target": 35.0},
    "ORCL": {"name": "甲骨文", "target": 130.0},
    "TSLA": {"name": "特斯拉", "target": 330.0},
    "NVDA": {"name": "英伟达", "target": 190.0},
    "TSM":  {"name": "台积电", "target": 385.0},
    "LITE": {"name": "Lumentum", "target": 650.0},
    "AVGO": {"name": "博通", "target": 340.0},
    "MRVL": {"name": "美满电子", "target": 180.0},
    "NBIS": {"name": "Nebius", "target": 180.0},
    "GOOG": {"name": "谷歌", "target": 300.0},
    "AMD":  {"name": "超威半导体", "target": 400.0},
    "HOOD": {"name": "Robinhood", "target": 70.0},
    "DRAM": {"name": "Roundhill内存芯片ETF", "target": 45},
    "SPCX": {"name": "SpaceX代币化产品", "target": 109},
}
STOCKS = list(STOCK_META.keys())

def http_get_json(url):
    with urllib.request.urlopen(url, timeout=20) as resp:
        return json.loads(resp.read().decode("utf-8"))

def throttle():
    time.sleep(8)

YAHOO_SYMBOLS = {"SPX_REAL": "%5EGSPC", "IXIC_REAL": "%5EIXIC", "VIX_REAL": "%5EVIX"}

def fetch_yahoo_index(y_symbol, range_="1y"):
    """Best-effort real index data from Yahoo Finance's unofficial chart API.
    Returns rows in the same newest-first shape as fetch_time_series, or raises on failure."""
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{y_symbol}?interval=1d&range={range_}"
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    })
    with urllib.request.urlopen(req, timeout=15) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    result = payload["chart"]["result"][0]
    ts = result["timestamp"]
    q = result["indicators"]["quote"][0]
    rows = []
    for i in range(len(ts)):
        if q["close"][i] is None:
            continue
        d = datetime.datetime.utcfromtimestamp(ts[i]).date().isoformat()
        rows.append({
            "datetime": d,
            "close": str(q["close"][i]),
            "high": str(q["high"][i] if q["high"][i] is not None else q["close"][i]),
            "low": str(q["low"][i] if q["low"][i] is not None else q["close"][i]),
            "open": str(q["open"][i] if q["open"][i] is not None else q["close"][i]),
        })
    rows.reverse()  # newest first, matching Twelve Data's ordering
    if not rows:
        raise RuntimeError("Yahoo returned no rows")
    return rows

def fetch_real_index_or_proxy(y_symbol, proxy_symbol, today, proxy_rows_cache=None):
    """Try the real index via Yahoo; fall back to an ETF proxy via Twelve Data on any failure."""
    try:
        rows = fetch_yahoo_index(y_symbol)
        return analyze(y_symbol, rows, today), "yahoo_real", None
    except Exception as e:
        try:
            rows = proxy_rows_cache if proxy_rows_cache is not None else fetch_time_series(proxy_symbol)
            return analyze(proxy_symbol, rows, today), "etf_proxy", str(e)
        except Exception as e2:
            return {"error": str(e2)}, "failed", str(e)

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
                    time.sleep(15)
                    continue
                raise RuntimeError(msg)
            return payload["values"]
        except Exception as e:
            if attempt == retries - 1:
                raise e
            time.sleep(10)

def calc_rsi(closes, period=14):
    if len(closes) < period + 1:
        return None
    closes_asc = closes[::-1]
    gains, losses = [], []
    for i in range(1, len(closes_asc)):
        change = closes_asc[i] - closes_asc[i-1]
        gains.append(change if change > 0 else 0)
        losses.append(abs(change) if change < 0 else 0)
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    for i in range(period, len(closes_asc) - 1):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100.0 - (100.0 / (1.0 + rs))

def calc_sma(closes, period=200):
    if len(closes) < period:
        return None
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
        "dist_200ma": pct_change(latest_close, calc_sma(closes, 200)),
    }
    if is_stock:
        out.update({"open": float(rows[0]["open"]), "high": float(rows[0]["high"]), "low": float(rows[0]["low"])})
    else:
        drawdown = pct_change(latest_close, all_time_high)
        out.update({
            "drawdown": drawdown,
            "threshold": threshold,
            "triggered": bool(threshold is not None and drawdown is not None and -drawdown >= threshold),
        })
    return out

def build():
    today = datetime.date.today()
    core, index, stocks, overview_charts = {}, {}, {}, {}

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
            if name in ("QQQ", "SPY"):  # 用于总览走势图（原SPX/IXIC位置）
                overview_charts[name] = [{"d": r["datetime"][:10], "c": float(r["close"])} for r in rows[:30][::-1]]
        except Exception as e:
            index[name] = {"error": str(e)}
        throttle()

    # 市场核心指标：优先拿雅虎财经的真实指数，失败则回退调用Twelve Data的ETF代理
    spx_data, spx_src, spx_err = fetch_real_index_or_proxy("%5EGSPC", "SPY", today)
    throttle()
    ixic_data, ixic_src, ixic_err = fetch_real_index_or_proxy("%5EIXIC", "QQQ", today)
    throttle()
    vix_data, vix_src, vix_err = fetch_real_index_or_proxy("%5EVIX", VOL_PROXY_SYM, today)
    throttle()
    vol_data = vix_data  # 命名沿用，兼容下面 render_html 的字段

    for name in STOCKS:
        try:
            stocks[name] = analyze(name, fetch_time_series(name), today, is_stock=True)
        except Exception as e:
            stocks[name] = {"error": str(e)}
        throttle()

    return {"updated": today.isoformat(), "core": core, "index": index,
            "stocks": stocks, "vol_proxy": vol_data, "overview_charts": overview_charts,
            "market_indicators": {
                "spx": spx_data, "spx_source": spx_src,
                "ixic": ixic_data, "ixic_source": ixic_src,
                "vix": vix_data, "vix_source": vix_src,
            }}

def fmt_pct(x, digits=2):
    return f"{x*100:.{digits}f}%" if isinstance(x, (int, float)) else "-"

def fmt_num(x, digits=2):
    return f"{x:.{digits}f}" if isinstance(x, (int, float)) else "-"

def card_etf(name, r, label=None):
    if "error" in r:
        return f'<div class="card err"><div class="sym">{label or name}</div><div class="errmsg">获取失败</div></div>'
    trigger_html = ""
    if r.get("threshold") is not None:
        flag = "触发加仓" if r["triggered"] else "正常观察"
        status_cls = "alert-on" if r["triggered"] else "alert-off"
        trigger_html = f'''<div class="row mt"><span>触发阈值</span><span class="fw-bold">{fmt_pct(r["threshold"])}</span></div>
                           <div class="status-badge {status_cls}">{flag}</div>'''
    drawdown_cls = "neg-text fw-bold" if r["drawdown"] and r["drawdown"] < 0 else "fw-bold"
    return f'''<div class="card">
      <div class="card-header"><span class="sym">{label or name}</span><span class="price">${r["close"]:.2f}</span></div>
      <div class="divider"></div>
      <div class="row"><span>年度最高</span><span class="fw-bold">${fmt_num(r["ytd_high"])}</span></div>
      <div class="row"><span>最高点回撤</span><span class="{drawdown_cls}">{fmt_pct(r["drawdown"])}</span></div>
      <div class="row"><span>RSI (14)</span><span class="fw-bold">{fmt_num(r["rsi"])}</span></div>
      <div class="row"><span>距 200MA</span><span class="fw-bold">{fmt_pct(r["dist_200ma"])}</span></div>
      {trigger_html}
    </div>'''

def row_stock(sym, r):
    if "error" in r:
        return f'<tr class="err"><td><b>{sym}</b></td><td colspan="10">获取数据失败</td></tr>'
    target = STOCK_META.get(sym, {}).get("target")
    name = STOCK_META.get(sym, {}).get("name", sym)
    target_str = f"${target:.2f}" if target else "-"
    action_html = '<span class="alert-text fw-bold ml">(信号触发!)</span>' if target and r["close"] <= target else ""
    chg_cls = "pos-text" if (r["day_chg"] or 0) >= 0 else "neg-text"
    chg_sign = "+" if (r["day_chg"] or 0) >= 0 else ""
    return f'''<tr>
        <td><b>{sym}</b></td><td class="sub-text">{name}</td>
        <td class="fw-bold">${r["close"]:.2f}</td><td class="{chg_cls}">{chg_sign}{fmt_pct(r["day_chg"])}</td>
        <td>${r["open"]:.2f}</td><td>${r["high"]:.2f}</td><td>${r["low"]:.2f}</td>
        <td>${fmt_num(r["ytd_high"])}</td><td>{fmt_num(r["rsi"])}</td><td>{fmt_pct(r["dist_200ma"])}</td>
        <td><b>{target_str}</b> {action_html}</td>
    </tr>'''

def render_html(data):
    core_html = "".join(card_etf(k, v) for k, v in data["core"].items())
    index_html = "".join(card_etf(k, v) for k, v in data["index"].items())
    stock_html = "".join(row_stock(k, v) for k, v in data["stocks"].items())

    mi = data.get("market_indicators", {})
    spy = mi.get("spx", {})
    qqq = mi.get("ixic", {})
    vol = mi.get("vix", data.get("vol_proxy", {}))
    spy_src = mi.get("spx_source", "etf_proxy")
    qqq_src = mi.get("ixic_source", "etf_proxy")
    vix_src = mi.get("vix_source", "etf_proxy")
    src_label = lambda s: "真实指数(Yahoo)" if s == "yahoo_real" else "ETF代理"

    def market_state(v):
        if not isinstance(v, (int, float)):
            return ("数据待更新", "neutral")
        if v < 15:
            return ("低波动", "good")
        if v < 25:
            return ("正常波动", "good")
        if v < 35:
            return ("波动升温", "warn")
        return ("高风险", "bad")

    def metric_card(label, value, change=None, note="", tone="neutral"):
        change_html = ""
        if isinstance(change, (int, float)):
            cls = "positive" if change >= 0 else "negative"
            sign = "+" if change >= 0 else ""
            change_html = f'<div class="metric-change {cls}">{sign}{fmt_pct(change)}</div>'
        return f'''<div class="metric-card"><div class="metric-top"><span>{label}</span><span class="metric-dot {tone}"></span></div><div class="metric-value">{value}</div>{change_html}<div class="metric-note">{note}</div></div>'''

    vol_value = vol.get("close") if "error" not in vol else None
    vol_state, vol_tone = market_state(vol_value)
    vol_display = fmt_num(vol_value) if vol_value is not None else "—"
    spy_value = f'${spy["close"]:,.2f}' if "error" not in spy else "—"
    qqq_value = f'${qqq["close"]:,.2f}' if "error" not in qqq else "—"
    spy_chg = spy.get("day_chg") if "error" not in spy else None
    qqq_chg = qqq.get("day_chg") if "error" not in qqq else None
    spy_note = f"大盘风险偏好 · {src_label(spy_src)}"
    qqq_note = f"成长/科技风格温度 · {src_label(qqq_src)}"
    vix_note = f"{vol_state} · {src_label(vix_src)}"
    signal_count = sum(1 for v in data["core"].values() if v.get("triggered"))
    signal_text = f"{signal_count} 个策略点" if signal_count else "暂无触发"
    signal_tone = "bad" if signal_count else "good"
    chart_json = json.dumps(data.get("overview_charts", {}), ensure_ascii=False)

    return f'''<!DOCTYPE html><html lang="zh-CN"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"><meta name="description" content="SIMON的投资分析平台 · 公开研究看板"><title>SIMON的投资分析平台</title><script src="https://cdn.jsdelivr.net/npm/chart.js@4"></script>
<style>
:root {{--bg:#faf6ee;--surface:#fffdf8;--surface2:#f5efe2;--ink:#1c1c1a;--muted:#7a7568;--line:#e9e2d1;--nav:#0f2a1e;--navmuted:#a9bdae;--accent:#7a1f1a;--accent2:#0f2a1e;--green:#1e7d4a;--red:#a3271f;--amber:#a56a1a;--shadow:0 10px 30px rgba(20,20,10,.06)}}
*{{box-sizing:border-box;margin:0;padding:0}} body{{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,"PingFang SC","Microsoft YaHei",Arial,sans-serif;background:var(--bg);color:var(--ink);min-height:100vh}} .app{{display:flex;min-height:100vh}}
.sidebar{{width:248px;background:linear-gradient(180deg,#0f2a1e,#0b2018);color:#fff;padding:24px 16px;position:fixed;inset:0 auto 0 0;z-index:20}} .brand{{display:flex;align-items:center;gap:11px;padding:8px 10px 28px;border-bottom:1px solid rgba(255,255,255,.1)}} .brand-mark{{width:38px;height:38px;border-radius:11px;display:grid;place-items:center;background:linear-gradient(135deg,#7a1f1a,#a3271f);font-size:18px;box-shadow:0 8px 20px rgba(122,31,26,.35);color:#fff}} .brand strong{{display:block;font-size:16px}} .brand small{{display:block;color:#8fa595;margin-top:3px;font-size:11px}}
.nav-title{{color:#6f8578;font-size:10px;font-weight:800;letter-spacing:1.3px;margin:25px 10px 8px}} .nav-menu{{list-style:none;display:grid;gap:4px}} .nav-menu li{{display:flex;align-items:center;gap:11px;padding:11px 12px;border-radius:10px;color:var(--navmuted);cursor:pointer;font-size:13px;font-weight:600;transition:.18s}} .nav-menu li:hover{{background:rgba(255,255,255,.07);color:#fff}} .nav-menu li.active{{color:#fff;background:linear-gradient(90deg,rgba(163,39,31,.35),rgba(163,39,31,.08));box-shadow:inset 3px 0 0 #c94a3e}} .nav-icon{{width:18px;text-align:center}} .sidebar-footer{{position:absolute;left:26px;right:26px;bottom:24px;color:#6f8578;font-size:10px;line-height:1.7}}
.main{{margin-left:248px;width:calc(100% - 248px);min-width:0}} .topbar{{height:68px;background:rgba(250,246,238,.92);backdrop-filter:blur(14px);border-bottom:1px solid var(--line);display:flex;align-items:center;justify-content:space-between;padding:0 34px;position:sticky;top:0;z-index:10}} .breadcrumb{{font-size:13px;color:var(--muted)}} .breadcrumb strong{{color:var(--ink)}} .top-meta{{display:flex;gap:16px;color:var(--muted);font-size:11px}} .live-dot{{width:7px;height:7px;border-radius:50%;background:var(--green);display:inline-block;margin-right:6px}}
.content{{max-width:1500px;margin:0 auto;padding:34px}} .hero{{display:flex;justify-content:space-between;gap:24px;align-items:flex-end;margin-bottom:26px}} .eyebrow{{color:var(--accent);font-size:11px;font-weight:800;letter-spacing:1.4px;margin-bottom:9px}} h1{{font-size:30px;line-height:1.2;letter-spacing:-.7px}} .hero p{{color:var(--muted);margin-top:9px;font-size:13px;line-height:1.7;max-width:680px}} .public-note{{flex:0 0 270px;background:linear-gradient(135deg,#f3ece0,#eee4d2);border:1px solid #e3d8bf;border-radius:14px;padding:15px 17px;font-size:11px;color:#5c574a;line-height:1.65}} .public-note strong{{color:var(--accent);display:block;margin-bottom:4px}}
.section{{margin-top:30px}} .section-head{{display:flex;justify-content:space-between;align-items:center;margin-bottom:13px}} .section-head h2{{font-size:16px}} .section-head p{{color:var(--muted);font-size:11px}} .metrics{{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:14px}} .metric-card{{background:var(--surface);border:1px solid var(--line);border-radius:15px;padding:17px 18px;box-shadow:var(--shadow);min-height:130px}} .metric-top{{display:flex;justify-content:space-between;color:var(--muted);font-size:11px;font-weight:700}} .metric-dot{{width:8px;height:8px;border-radius:50%;background:#c9c2ac}} .metric-dot.good{{background:var(--green)}} .metric-dot.warn{{background:var(--amber)}} .metric-dot.bad{{background:var(--red)}} .metric-value{{font-size:25px;font-weight:800;letter-spacing:-.5px;margin-top:12px;font-variant-numeric:tabular-nums}} .metric-change{{font-size:12px;font-weight:700;margin-top:4px}} .positive{{color:var(--green)}} .negative{{color:var(--red)}} .metric-note{{color:var(--muted);font-size:10px;margin-top:8px}}
.dashboard-grid{{display:grid;grid-template-columns:minmax(0,1.65fr) minmax(280px,.75fr);gap:16px}} .panel{{background:var(--surface);border:1px solid var(--line);border-radius:16px;box-shadow:var(--shadow)}} .panel-head{{display:flex;justify-content:space-between;align-items:center;padding:17px 19px;border-bottom:1px solid var(--line)}} .panel-head strong{{font-size:13px}} .panel-head span{{color:var(--muted);font-size:10px}} .chart-wrap{{height:310px;padding:15px 18px 18px}} .chart-empty{{height:100%;display:grid;place-items:center;color:var(--muted);font-size:12px;background:var(--surface2);border-radius:10px}} .pulse-list{{padding:8px 18px 14px}} .pulse{{display:flex;align-items:center;justify-content:space-between;padding:15px 0;border-bottom:1px solid var(--line)}} .pulse:last-child{{border-bottom:0}} .pulse-label{{color:var(--muted);font-size:11px}} .pulse-main{{margin-top:4px;font-size:15px;font-weight:800}} .pulse-right{{text-align:right;font-size:11px;font-weight:700}}
.badge{{display:inline-flex;border-radius:999px;padding:5px 9px;font-size:10px;font-weight:800}} .badge.good{{background:#e7f3ea;color:var(--green)}} .badge.warn{{background:#f7ecd9;color:var(--amber)}} .badge.bad{{background:#f7e6e4;color:var(--red)}} .badge.neutral{{background:#efe9db;color:var(--muted)}}
.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(250px,1fr));gap:14px}} .card{{background:var(--surface);border:1px solid var(--line);border-radius:15px;padding:17px;box-shadow:var(--shadow);transition:.18s}} .card:hover{{transform:translateY(-2px);box-shadow:0 14px 32px rgba(20,20,10,.09)}} .card-header{{display:flex;justify-content:space-between;align-items:center}} .sym{{font-weight:850;font-size:16px}} .price{{font-size:19px;font-weight:850;font-variant-numeric:tabular-nums}} .divider{{height:1px;background:var(--line);margin:14px 0}} .row{{display:flex;justify-content:space-between;gap:15px;font-size:11px;color:var(--muted);margin-bottom:9px}} .fw-bold{{color:var(--ink);font-weight:700}} .pos-text{{color:var(--green)}} .neg-text{{color:var(--red)}} .alert-text{{color:var(--red)}} .status-badge{{margin-top:14px;font-size:11px;font-weight:800;padding:8px 10px;border-radius:9px;text-align:center}} .alert-on{{background:#f7e6e4;color:var(--red);border:1px solid #ecc9c5}} .alert-off{{background:#e7f3ea;color:var(--green);border:1px solid #c9e4d1}} .err{{border-style:dashed}} .errmsg{{color:var(--muted);font-size:11px;margin-top:14px}}
.table-container{{overflow:auto;background:var(--surface);border:1px solid var(--line);border-radius:15px;box-shadow:var(--shadow)}} table{{width:100%;border-collapse:collapse;text-align:right;white-space:nowrap;font-variant-numeric:tabular-nums}} th,td{{padding:14px 16px;border-bottom:1px solid var(--line);font-size:13px}} th{{background:var(--surface2);color:var(--muted);font-weight:700;position:sticky;top:0;font-size:11.5px}} th:nth-child(1),td:nth-child(1),th:nth-child(2),td:nth-child(2){{text-align:left}} tr:hover td{{background:#fbf7ee}} tr:last-child td{{border-bottom:0}} .sub-text{{color:var(--muted)}} .footer{{color:#9a9484;font-size:10px;line-height:1.7;text-align:center;padding:30px 0 12px}} .tab-pane{{display:none;animation:fade .22s ease}} .tab-pane.active{{display:block}} @keyframes fade{{from{{opacity:0;transform:translateY(4px)}}to{{opacity:1;transform:none}}}}
.opt-grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:14px}} .opt-card{{background:var(--surface);border:1px solid var(--line);border-radius:15px;padding:18px;box-shadow:var(--shadow)}} .opt-card h3{{font-size:13px;margin-bottom:8px;color:var(--accent)}} .opt-card p{{font-size:12px;color:var(--muted);line-height:1.7}}
@media(max-width:1000px){{.sidebar{{width:205px}}.main{{margin-left:205px;width:calc(100% - 205px)}}.metrics{{grid-template-columns:repeat(2,1fr)}}.dashboard-grid{{grid-template-columns:1fr}}.content{{padding:25px}}}} @media(max-width:700px){{.sidebar{{position:sticky;top:0;width:100%;height:auto;padding:10px 12px}}.app{{display:block}}.brand{{padding:3px 5px 10px;border:0}}.brand-mark{{width:32px;height:32px}}.nav-title,.sidebar-footer{{display:none}}.nav-menu{{display:flex;overflow-x:auto}}.nav-menu li{{flex:0 0 auto;padding:9px 11px;font-size:11px}}.main{{margin-left:0;width:100%}}.topbar{{height:54px;padding:0 16px}}.top-meta{{display:none}}.content{{padding:20px 14px}}.hero{{display:block}}h1{{font-size:25px}}.public-note{{margin-top:15px;width:100%}}.metrics{{grid-template-columns:1fr 1fr;gap:10px}}.metric-card{{min-height:118px;padding:14px}}.metric-value{{font-size:21px}}.chart-wrap{{height:250px}}}} @media(max-width:430px){{.metrics{{grid-template-columns:1fr}}}}
</style></head><body><div class="app"><aside class="sidebar"><div class="brand"><div class="brand-mark">◈</div><div><strong>SIMON</strong><small>的投资分析平台</small></div></div><div class="nav-title">MARKET RESEARCH</div><ul class="nav-menu"><li class="active" onclick="switchTab('tab-overview',this)"><span class="nav-icon">⌂</span>市场总览</li><li onclick="switchTab('tab-core',this)"><span class="nav-icon">◒</span>策略信号</li><li onclick="switchTab('tab-index',this)"><span class="nav-icon">◫</span>指数 & ETF</li><li onclick="switchTab('tab-stocks',this)"><span class="nav-icon">⌁</span>个股观察池</li><li onclick="switchTab('tab-options',this)"><span class="nav-icon">⚑</span>期权持仓</li></ul><div class="sidebar-footer">公开研究版 · 不展示个人真实资产<br>数据仅用于研究与策略演示</div></aside><main class="main"><header class="topbar"><div class="breadcrumb">SIMON / <strong>市场总览</strong></div><div class="top-meta"><span><i class="live-dot"></i>数据状态正常</span><span>更新：{data['updated']}</span><span>Public Research</span></div></header><div class="content">
<div id="tab-overview" class="tab-pane active"><section class="hero"><div><div class="eyebrow">QUANTITATIVE MARKET INTELLIGENCE</div><h1>用数据观察市场，而不是展示账户。</h1><p>公开版投资研究面板：聚焦市场趋势、回撤、波动率与策略触发条件。个人真实资金、持仓数量与账户信息不在公开页面展示。</p></div><div class="public-note"><strong>🔒 公开展示模式</strong>这里展示的是研究指标与策略信号，不代表任何个人账户的实际仓位或收益。</div></section><section class="section"><div class="section-head"><h2>市场核心指标</h2><p>昨日收盘 · 自动更新</p></div><div class="metrics">{metric_card('纳斯达克综合指数',qqq_value,qqq_chg,qqq_note,'good' if isinstance(qqq_chg,(int,float)) and qqq_chg>=0 else 'warn')}{metric_card('标普500指数',spy_value,spy_chg,spy_note,'good' if isinstance(spy_chg,(int,float)) and spy_chg>=0 else 'warn')}{metric_card('VIX恐慌指数',vol_display,None,vix_note,vol_tone)}{metric_card('策略触发状态',signal_text,None,'仅显示规则信号，不显示资金规模',signal_tone)}</div></section><section class="section dashboard-grid"><div class="panel"><div class="panel-head"><strong>QQQ & SPY · 近 30 个交易日</strong><span>历史走势</span></div><div class="chart-wrap"><canvas id="trendChart"></canvas><div id="chartEmpty" class="chart-empty" style="display:none">当前历史数据暂不可用，待下一次自动更新。</div></div></div><div class="panel"><div class="panel-head"><strong>Market Pulse</strong><span>研究状态</span></div><div class="pulse-list"><div class="pulse"><div><div class="pulse-label">波动环境</div><div class="pulse-main">{vol_state}</div></div><div class="pulse-right"><span class="badge {vol_tone}">VIX {vol_display}</span></div></div><div class="pulse"><div><div class="pulse-label">策略观察</div><div class="pulse-main">{signal_text}</div></div><div class="pulse-right"><span class="badge {signal_tone}">RULE BASED</span></div></div><div class="pulse"><div><div class="pulse-label">数据源</div><div class="pulse-main">Yahoo优先 / Twelve Data兜底</div></div><div class="pulse-right"><span class="badge neutral">API</span></div></div></div></div></section></div>
<div id="tab-core" class="tab-pane"><section class="hero"><div><div class="eyebrow">STRATEGY ENGINE</div><h1>策略信号</h1><p>用回撤、RSI 与长期均线观察核心 ETF 的风险与潜在策略触发点。这里不显示真实仓位。</p></div></section><section class="section"><div class="section-head"><h2>核心策略观察</h2><p>规则驱动 · 不代表交易建议</p></div><div class="grid">{core_html}</div></section></div>
<div id="tab-index" class="tab-pane"><section class="hero"><div><div class="eyebrow">INDEX & ETF</div><h1>指数与行业 ETF</h1><p>从宽基指数到行业 ETF，快速观察价格、回撤、RSI 与 200 日均线距离。</p></div></section><section class="section"><div class="grid">{index_html}</div></section></div>
<div id="tab-stocks" class="tab-pane"><section class="hero"><div><div class="eyebrow">WATCHLIST</div><h1>个股观察池</h1><p>公开展示研究标的的市场数据与策略参考点，不展示个人成本、持仓数量或账户收益。</p></div></section><section class="section"><div class="table-container"><table><thead><tr><th>代码</th><th>名称</th><th>最新价</th><th>涨跌幅</th><th>开盘</th><th>最高</th><th>最低</th><th>年内最高</th><th>RSI(14)</th><th>距200MA</th><th>策略参考价</th></tr></thead><tbody>{stock_html}</tbody></table></div></section></div>
<div id="tab-options" class="tab-pane"><section class="hero"><div><div class="eyebrow">OPTIONS WATCHLIST</div><h1>期权持仓监控清单</h1><p>公开版暂不接入实时期权行情（免费数据源普遍不支持及时的期权Greeks），先提供持有期权期间需要重点盯防的指标清单，作为自查参考。</p></div></section><section class="section"><div class="opt-grid">
<div class="opt-card"><h3>⏳ 剩余到期天数 (DTE)</h3><p>越接近到期，时间价值(Theta)衰减越快，尤其是最后30天内加速明显。</p></div>
<div class="opt-card"><h3>🎯 距行权价的距离</h3><p>标的价与行权价的百分比差距，判断合约是价内(ITM)、价平(ATM)还是价外(OTM)。</p></div>
<div class="opt-card"><h3>📈 隐含波动率 (IV) / IV Rank</h3><p>IV突然飙升或回落会显著影响期权价格，尤其在财报、FOMC等事件前后。</p></div>
<div class="opt-card"><h3>Δ Delta</h3><p>标的价每变动$1，期权价格大致的变动幅度，也约等于到期时处于价内的概率。</p></div>
<div class="opt-card"><h3>Θ Theta（时间价值衰减）</h3><p>每天因时间流逝损失的权利金金额，临近到期会加速。</p></div>
<div class="opt-card"><h3>Γ Gamma</h3><p>Delta本身的变化速度，临近到期或价平附近时Gamma风险最大。</p></div>
<div class="opt-card"><h3>💰 内在价值 vs 时间价值</h3><p>内在价值 = 标的价与行权价的实际价差；剩余部分是时间价值，到期归零。</p></div>
<div class="opt-card"><h3>⚖️ 盈亏平衡价</h3><p>买入认购：行权价+权利金；买入认沽：行权价-权利金，判断到期需要标的价到哪里才不亏。</p></div>
<div class="opt-card"><h3>📅 关键事件日历</h3><p>财报日、除息日、宏观数据发布日，都可能造成标的价或IV的剧烈跳动。</p></div>
</div></section></div>
<div class="footer">SIMON的投资分析平台 · Public Research Dashboard · {data['updated']}<br>市场数据与策略指标仅供研究、学习与信息参考，不构成投资建议。</div></div></main></div>
<script>const CHART_DATA={chart_json};function switchTab(id,el){{document.querySelectorAll('.tab-pane').forEach(t=>t.classList.remove('active'));document.querySelectorAll('.nav-menu li').forEach(l=>l.classList.remove('active'));document.getElementById(id).classList.add('active');el.classList.add('active');window.scrollTo({{top:0,behavior:'smooth'}})}}window.addEventListener('load',function(){{const c=document.getElementById('trendChart'),e=document.getElementById('chartEmpty'),qq=CHART_DATA.QQQ||[],sp=CHART_DATA.SPY||[];if(!qq.length||!sp.length){{c.style.display='none';e.style.display='grid';return}}const labels=qq.map(x=>x.d),qv=qq.map(x=>x.c),sv=sp.map(x=>x.c);new Chart(c,{{type:'line',data:{{labels,datasets:[{{label:'QQQ',data:qv,borderColor:'#7a1f1a',backgroundColor:'rgba(122,31,26,.08)',fill:true,borderWidth:2,pointRadius:0,tension:.35,yAxisID:'y'}},{{label:'SPY',data:sv,borderColor:'#1e7d4a',backgroundColor:'transparent',borderWidth:2,pointRadius:0,tension:.35,yAxisID:'y1'}}]}},options:{{responsive:true,maintainAspectRatio:false,interaction:{{mode:'index',intersect:false}},plugins:{{legend:{{position:'top',align:'end'}}}},scales:{{x:{{grid:{{display:false}},ticks:{{maxTicksLimit:7}}}},y:{{position:'left',grid:{{color:'#eee6d4'}}}},y1:{{position:'right',grid:{{drawOnChartArea:false}}}}}}}}}})}});</script></body></html>'''

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
