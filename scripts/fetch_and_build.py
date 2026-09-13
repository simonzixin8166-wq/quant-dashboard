import json, datetime, os, time
import urllib.request, urllib.parse

API_KEY = os.environ.get("TWELVE_DATA_KEY", "demo")
BASE = "https://api.twelvedata.com"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
FUND_HEADERS = {"User-Agent": HEADERS["User-Agent"], "Referer": "http://fund.eastmoney.com/"}

# ================= 美股配置 =================
CORE = {"QQQM": 0.07, "VGT": 0.10, "QLD": 0.14, "TQQQ": None}
INDEX = ["QQQ", "SPY", "VOO", "SMH"]
VOL_PROXY_SYM = "VIXY"

STOCK_META = {
    "SOFI": {"name": "SoFi Technologies", "target": 15.0},
    "IREN": {"name": "Iris Energy", "target": 35.0},
    "ORCL": {"name": "甲骨文", "target": 130.0},
    "TSLA": {"name": "特斯拉", "target": 250.0},
    "NVDA": {"name": "英伟达", "target": 110.0},
    "TSM":  {"name": "台积电", "target": 160.0},
    "LITE": {"name": "Lumentum", "target": 45.0},
    "AVGO": {"name": "博通", "target": 340.0},
    "MRVL": {"name": "美满电子", "target": 65.0},
    "NBIS": {"name": "Nebius", "target": 25.0},
    "GOOG": {"name": "谷歌", "target": 150.0},
    "AMD":  {"name": "超威半导体", "target": 130.0},
    "HOOD": {"name": "Robinhood", "target": 20.0},
    "DRAM": {"name": "Roundhill内存芯片", "target": None},
    "SPCX": {"name": "SpaceX代币化产品", "target": None},
}
STOCKS = list(STOCK_META.keys())

# ================= A股/港股配置 =================
CN_HK_SYMBOLS = {
    "sh000001": "上证指数",
    "sh000300": "沪深300",
    "sz159307": "红利低波100 ETF",
    "hk03086": "华夏纳指 (港股)",
    "hk03416": "国指备兑 (港股)",
}
OTC_FUNDS = {"021550": "红利低波100联接 (场外)"}
TENCENT_URL = "http://qt.gtimg.cn/q={symbols}"
FUND_EST_URL = "http://fundgz.1234567.com.cn/js/{code}.js"

# ================= 核心抓取逻辑 =================
def http_get_json(url):
    with urllib.request.urlopen(url, timeout=20) as resp:
        return json.loads(resp.read().decode("utf-8"))

def throttle():
    time.sleep(8)

def fetch_yahoo_index(y_symbol, range_="1y"):
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{y_symbol}?interval=1d&range={range_}"
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=15) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    result = payload["chart"]["result"][0]
    ts = result["timestamp"]
    q = result["indicators"]["quote"][0]
    rows = []
    for i in range(len(ts)):
        if q["close"][i] is None: continue
        d = datetime.datetime.utcfromtimestamp(ts[i]).date().isoformat()
        rows.append({
            "datetime": d, "close": str(q["close"][i]),
            "high": str(q["high"][i] if q["high"][i] is not None else q["close"][i]),
            "low": str(q["low"][i] if q["low"][i] is not None else q["close"][i]),
            "open": str(q["open"][i] if q["open"][i] is not None else q["close"][i]),
        })
    rows.reverse() 
    if not rows: raise RuntimeError("Yahoo returned no rows")
    return rows

def fetch_real_index_or_proxy(y_symbol, proxy_symbol, today, proxy_rows_cache=None):
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
    params = urllib.parse.urlencode({"symbol": symbol, "interval": "1day", "outputsize": outputsize, "apikey": API_KEY})
    url = f"{BASE}/time_series?{params}"
    for attempt in range(retries):
        try:
            payload = http_get_json(url)
            if payload.get("status") == "error":
                code = payload.get("code")
                if code == 429:
                    time.sleep(15)
                    continue
                raise RuntimeError(payload.get("message", "error"))
            return payload["values"]
        except Exception as e:
            if attempt == retries - 1: raise e
            time.sleep(10)

def fetch_tencent_quotes(symbols):
    joined = ",".join(symbols)
    req = urllib.request.Request(TENCENT_URL.format(symbols=joined), headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            raw = resp.read().decode("gbk", errors="ignore")
    except Exception as e:
        return {sym: {"error": str(e)} for sym in symbols}
    
    out = {}
    for line in raw.strip().split(";"):
        line = line.strip()
        if not line or "=" not in line: continue
        var_part, val_part = line.split("=", 1)
        sym = var_part.replace("v_", "").strip()
        val = val_part.strip().strip('"')
        fields = val.split("~")
        if len(fields) < 5:
            out[sym] = {"error": "Format error"}
            continue
        try:
            name, price, prev_close = fields[1], float(fields[3]), float(fields[4])
            pct_change = (price - prev_close) / prev_close if prev_close else None
            out[sym] = {"name": name, "price": price, "prev_close": prev_close, "day_chg": pct_change}
        except Exception as e:
            out[sym] = {"error": str(e)}
    return out

def fetch_fund_estimate(fund_code):
    req = urllib.request.Request(FUND_EST_URL.format(code=fund_code), headers=FUND_HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            raw = resp.read().decode("utf-8", errors="ignore")
        json_str = raw[raw.find("{"):raw.rfind("}") + 1]
        data = json.loads(json_str)
        est_pct = float(data.get("gszzl", 0)) / 100.0 if data.get("gszzl") else 0
        return {
            "name": data.get("name"), "price": float(data.get("gsz", 0)), 
            "day_chg": est_pct, "time": data.get("gztime")
        }
    except Exception as e:
        return {"error": str(e)}

# ================= 指标计算 =================
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
    for i in range(period, len(closes_asc) - 1):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
    if avg_loss == 0: return 100.0
    rs = avg_gain / avg_loss
    return 100.0 - (100.0 / (1.0 + rs))

def calc_sma(closes, period=200):
    if len(closes) < period: return None
    return sum(closes[:period]) / period

def pct_change(latest, prior):
    return (latest - prior) / prior if prior else None

def analyze(symbol, rows, today, threshold=None, is_stock=False):
    closes = [float(r["close"]) for r in rows]
    latest_close = closes[0]
    prev_close = closes[1] if len(closes) > 1 else latest_close
    current_year = str(today.year)
    highs = [float(r["high"]) for r in rows if r["datetime"].startswith(current_year)]
    ytd_high = max(highs) if highs else None
    all_time_high = max([float(r["high"]) for r in rows]) if rows else None
    out = {
        "date": rows[0]["datetime"][:10], "close": latest_close, "prev_close": prev_close,
        "day_chg": pct_change(latest_close, prev_close), "ytd_high": ytd_high,
        "rsi": calc_rsi(closes, 14), "dist_200ma": pct_change(latest_close, calc_sma(closes, 200)),
    }
    if is_stock:
        out.update({"open": float(rows[0]["open"]), "high": float(rows[0]["high"]), "low": float(rows[0]["low"])})
    else:
        drawdown = pct_change(latest_close, all_time_high)
        out.update({
            "drawdown": drawdown, "threshold": threshold,
            "triggered": bool(threshold is not None and drawdown is not None and -drawdown >= threshold),
        })
    return out

# ================= 核心构建与渲染 =================
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
            if name in ("QQQ", "SPY"): 
                overview_charts[name] = [{"d": r["datetime"][:10], "c": float(r["close"])} for r in rows[:30][::-1]]
        except Exception as e:
            index[name] = {"error": str(e)}
        throttle()

    spx_data, spx_src, _ = fetch_real_index_or_proxy("%5EGSPC", "SPY", today)
    throttle()
    ixic_data, ixic_src, _ = fetch_real_index_or_proxy("%5EIXIC", "QQQ", today)
    throttle()
    vix_data, vix_src, _ = fetch_real_index_or_proxy("%5EVIX", VOL_PROXY_SYM, today)
    throttle()

    for name in STOCKS:
        try:
            stocks[name] = analyze(name, fetch_time_series(name), today, is_stock=True)
        except Exception as e:
            stocks[name] = {"error": str(e)}
        throttle()
        
    cn_hk_data = {}
    try:
        cn_hk_data.update(fetch_tencent_quotes(list(CN_HK_SYMBOLS.keys())))
    except: pass
    try:
        for code in OTC_FUNDS.keys():
            cn_hk_data[code] = fetch_fund_estimate(code)
    except: pass

    return {"updated": today.isoformat(), "core": core, "index": index,
            "stocks": stocks, "overview_charts": overview_charts,
            "cn_hk": cn_hk_data,
            "market_indicators": {
                "spx": spx_data, "spx_source": spx_src,
                "ixic": ixic_data, "ixic_source": ixic_src,
                "vix": vix_data, "vix_source": vix_src,
            }}

def fmt_pct(x, digits=2): return f"{x*100:.{digits}f}%" if isinstance(x, (int, float)) else "-"
def fmt_num(x, digits=2): return f"{x:.{digits}f}" if isinstance(x, (int, float)) else "-"

def engine_item(name, r):
    if "error" in r: return f'<div class="engine-item"><div class="k">{name}</div><div class="v">-</div><div class="pt">数据获取失败</div></div>'
    is_hit = r.get("triggered", False)
    hit_cls = "hit" if is_hit else ""
    drawdown_str = fmt_pct(r.get("drawdown"))
    thresh_str = fmt_pct(r.get("threshold")) if r.get("threshold") else "无阈值"
    note = f"≤ -{thresh_str} → 命中" if is_hit else "未触发"
    return f'''<div class="engine-item {hit_cls}"><div class="k">{name} 回撤</div><div class="v">{drawdown_str}</div><div class="pt">{note}</div></div>'''

def card_etf(name, r):
    if "error" in r: return f'<div class="card err"><div class="sym">{name}</div><div class="errmsg">获取失败</div></div>'
    drawdown_cls = "neg-text fw-bold" if r["drawdown"] and r["drawdown"] < 0 else "fw-bold"
    return f'''<div class="card">
      <div class="card-header"><span class="sym">{name}</span><span class="price">${r["close"]:.2f}</span></div>
      <div class="divider"></div>
      <div class="row"><span>年度最高</span><span class="fw-bold">${fmt_num(r["ytd_high"])}</span></div>
      <div class="row"><span>最高点回撤</span><span class="{drawdown_cls}">{fmt_pct(r["drawdown"])}</span></div>
      <div class="row"><span>RSI (14)</span><span class="fw-bold">{fmt_num(r["rsi"])}</span></div>
      <div class="row"><span>距 200MA</span><span class="fw-bold">{fmt_pct(r["dist_200ma"])}</span></div>
    </div>'''

def row_stock(sym, r):
    if "error" in r: return f'<tr class="err"><td><b>{sym}</b></td><td colspan="10">获取数据失败</td></tr>'
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

def mkt_card_a(title, data):
    if not data or "error" in data:
        return f'<div class="mkt-card"><div class="name">{title}</div><div class="val" style="font-size:14px;color:var(--muted);margin-top:12px">接口拦截/闭市</div></div>'
    price = data.get("price", 0)
    chg = data.get("day_chg", 0)
    chg_str = f"+{fmt_pct(chg)}" if chg >= 0 else fmt_pct(chg)
    color_cls = "positive" if chg >= 0 else "negative"
    return f'<div class="mkt-card"><div class="name">{title}</div><div class="val">{price:,.3f}</div><div class="chg {color_cls}">{chg_str}</div></div>'


# ===== myAlphaView V1.1 Step 2 — Market Regime Engine =====
def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None

def _latest_close(rows):
    if not rows:
        return None
    for row in reversed(rows):
        v = _num(row.get("close") if isinstance(row, dict) else None)
        if v is not None:
            return v
    return None

def _latest_rsi(rows):
    if not rows:
        return None
    for row in reversed(rows):
        v = _num(row.get("rsi") if isinstance(row, dict) else None)
        if v is not None:
            return v
    return None

def _latest_sma200(rows):
    if not rows:
        return None
    for row in reversed(rows):
        for key in ("sma200", "SMA200", "ma200"):
            v = _num(row.get(key) if isinstance(row, dict) else None)
            if v is not None:
                return v
    return None

def _latest_drawdown(rows):
    if not rows:
        return None
    for row in reversed(rows):
        for key in ("drawdown", "dd", "Drawdown"):
            v = _num(row.get(key) if isinstance(row, dict) else None)
            if v is not None:
                return v
    return None

def calculate_market_regime(nasdaq_rows=None, sp500_rows=None, vix_value=None):
    """
    Transparent 100-point scoring model.
    Trend  : 0-40
    Risk   : 0-30
    Momentum: 0-30

    The model intentionally avoids pretending to be a trading oracle.
    It is a research classification layer for the public dashboard.
    """
    nasdaq_rows = nasdaq_rows or []
    sp500_rows = sp500_rows or []

    trend_points = 0
    momentum_points = 0
    risk_points = 0
    evidence = []

    # Trend: compare latest close to 200-day moving average.
    for name, rows in (("NASDAQ", nasdaq_rows), ("S&P 500", sp500_rows)):
        close = _latest_close(rows)
        sma = _latest_sma200(rows)
        if close is not None and sma is not None:
            if close > sma:
                trend_points += 20
                evidence.append(f"{name} > 200MA")
            else:
                evidence += []
    if not evidence:
        trend_points = 20
    elif trend_points == 40:
        trend_points = 40
    else:
        trend_points = 20

    # Momentum: RSI for both indices, neutral when unavailable.
    rsi_values = []
    for rows in (nasdaq_rows, sp500_rows):
        r = _latest_rsi(rows)
        if r is not None:
            rsi_values.append(r)
    if rsi_values:
        avg_rsi = sum(rsi_values) / len(rsi_values)
        if avg_rsi >= 60:
            momentum_points = 30
        elif avg_rsi >= 50:
            momentum_points = 22
        elif avg_rsi >= 40:
            momentum_points = 12
        else:
            momentum_points = 5
    else:
        momentum_points = 15

    # Risk: VIX. Lower VIX gets more points.
    vix = _num(vix_value)
    if vix is None:
        risk_points = 15
    elif vix < 16:
        risk_points = 30
    elif vix < 20:
        risk_points = 24
    elif vix < 25:
        risk_points = 16
    elif vix < 30:
        risk_points = 8
    else:
        risk_points = 0

    score = trend_points + risk_points + momentum_points

    if vix is not None and vix >= 30:
        regime = "STRESS"
        regime_cn = "压力"
    elif score >= 75:
        regime = "RISK-ON"
        regime_cn = "风险偏好"
    elif score >= 50:
        regime = "NEUTRAL"
        regime_cn = "中性"
    else:
        regime = "RISK-OFF"
        regime_cn = "风险规避"

    return {
        "regime": regime,
        "regime_cn": regime_cn,
        "score": score,
        "trend": trend_points,
        "risk": risk_points,
        "momentum": momentum_points,
        "vix": vix,
        "method": "Trend 40 + Risk 30 + Momentum 30",
        "evidence": evidence,
    }


def render_html(data):
    engine_html = "".join(engine_item(k, v) for k, v in data["core"].items())
    index_html = "".join(card_etf(k, v) for k, v in data["index"].items())
    stock_html = "".join(row_stock(k, v) for k, v in data["stocks"].items())

    mi = data.get("market_indicators", {})
    cn = data.get("cn_hk", {})
    spy, qqq, vol = mi.get("spx", {}), mi.get("ixic", {}), mi.get("vix", {})
    src_label = lambda s: "真实指数(Yahoo)" if s == "yahoo_real" else "ETF代理"

    def market_state(v):
        if not isinstance(v, (int, float)): return ("数据待更新", "neutral")
        if v < 15: return ("低波动", "good")
        if v < 25: return ("正常波动", "good")
        if v < 35: return ("波动升温", "warn")
        return ("高风险", "bad")

    def metric_card(label, value, change=None, note="", tone="neutral"):
        change_html = ""
        if isinstance(change, (int, float)):
            cls = "positive" if change >= 0 else "negative"
            sign = "+" if change >= 0 else ""
            change_html = f'<div class="metric-change {cls}">{sign}{fmt_pct(change)}</div>'
        return f'''<div class="metric-card"><div class="metric-top">{label}<span class="metric-dot {tone}"></span></div><div class="metric-value">{value}</div>{change_html}<div class="metric-note">{note}</div></div>'''

    vol_value = vol.get("close") if "error" not in vol else None
    vol_state, vol_tone = market_state(vol_value)
    vol_display = fmt_num(vol_value) if vol_value is not None else "—"
    spy_value = f'{spy["close"]:,.2f}' if "error" not in spy else "—"
    qqq_value = f'{qqq["close"]:,.2f}' if "error" not in qqq else "—"
    spy_chg, qqq_chg = spy.get("day_chg"), qqq.get("day_chg")
    
    spy_note = f"大盘风险偏好 · {src_label(mi.get('spx_source'))}"
    qqq_note = f"成长/科技风格温度 · {src_label(mi.get('ixic_source'))}"
    vix_note = f"{src_label(mi.get('vix_source'))}"

    sz159307 = cn.get("sz159307", {})
    sz_val = f'{sz159307.get("price", 0):,.3f}' if "price" in sz159307 else "—"
    sz_chg = sz159307.get("day_chg")

    chart_json = json.dumps(data.get("overview_charts", {}), ensure_ascii=False)

    return f'''<!DOCTYPE html><html lang="zh-CN"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"><title>myAlphaView · Market Intelligence</title>
<meta name="author" content="Simon">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,380;9..144,520;9..144,620&family=Inter:wght@400;500;600;700;800&display=swap" rel="stylesheet">
<script src="https://cdn.jsdelivr.net/npm/chart.js@4"></script>
<!-- 引入 Supabase JS SDK -->
<script src="https://cdn.jsdelivr.net/npm/@supabase/supabase-js@2"></script>
<script>
// 提取 V1.1 Step 2 的计算逻辑，保持你的 Regime 显示
function rowsFor(obj){{
  if(!obj) return [];
  if(Array.isArray(obj)) return obj;
  for(const k of ["history","data","values","series"]) if(Array.isArray(obj[k])) return obj[k];
  return [];
}}
function latestNum(rows, keys){{
  for(let i=rows.length-1;i>=0;i--){{
    for(const k of keys){{
      const n=Number(rows[i]?.[k]);
      if(Number.isFinite(n)) return n;
    }}
  }}
  return null;
}}
function sourceByNames(names){{
  for(const name of names){{
    if(DATA && DATA[name]) return DATA[name];
  }}
  return null;
}}
function calculateRegimeClient(){{
  const nasObj=sourceByNames(["NASDAQ","IXIC","nasdaq"]);
  const spObj=sourceByNames(["SPX","SP500","S&P 500","sp500"]);
  const nas=rowsFor(nasObj), sp=rowsFor(spObj);
  let trend=0;
  let foundTrend=0;
  for(const rows of [nas,sp]){{
    const close=latestNum(rows,["close","Close","price"]);
    const sma=latestNum(rows,["sma200","SMA200","ma200"]);
    if(close!==null && sma!==null){{foundTrend++; if(close>sma) trend+=20;}}
  }}
  if(foundTrend===0) trend=20;
  else if(foundTrend===1) trend=trend;
  let rsis=[];
  for(const rows of [nas,sp]){{
    const r=latestNum(rows,["rsi","RSI"]);
    if(r!==null) rsis.push(r);
  }}
  let momentum=15;
  if(rsis.length){{
    const r=rsis.reduce((a,b)=>a+b,0)/rsis.length;
    momentum=r>=60?30:r>=50?22:r>=40?12:5;
  }}
  const vixObj=sourceByNames(["VIX","vix"]);
  const vix=Number(vixObj?.close ?? vixObj?.price ?? vixObj?.value ?? vixObj);
  let risk=15;
  if(Number.isFinite(vix)) risk=vix<16?30:vix<20?24:vix<25?16:vix<30?8:0;
  const score=trend+risk+momentum;
  let state="NEUTRAL";
  if(Number.isFinite(vix)&&vix>=30) state="STRESS";
  else if(score>=75) state="RISK-ON";
  else if(score<50) state="RISK-OFF";
  const cn={{["RISK-ON"]:"风险偏好",NEUTRAL:"中性",["RISK-OFF"]:"风险规避",STRESS:"压力"}}[state];
  
  const elState = document.getElementById("regimeState");
  if(elState) elState.textContent=state+" · "+cn;
}}
window.addEventListener('load', calculateRegimeClient);
</script>
<style>
:root{{
  --bg:#f4f2ec; --surface:#ffffff; --surface2:#ebe8df;
  --ink:#14161c; --muted:#696d76; --line:#e1ddd0;
  --nav:#11162a; --nav2:#0a0d1a; --navmuted:#8d93ab; --navline:rgba(255,255,255,.08);
  --brass:#b8863a; --brass-soft:#e8d3ab; --navy:#1f2b52;
  --green:#1c7a4c; --green-soft:#e5f1e9;
  --red:#b23b2e; --red-soft:#f6e6e2;
  --amber:#c07f2e; --amber-soft:#f6ecd8;
  --shadow:0 12px 32px rgba(15,15,10,.07);
  --serif:'Fraunces',ui-serif,Georgia,serif; --sans:'Inter',-apple-system,"PingFang SC","Microsoft YaHei",sans-serif;
  --mav-ink:#102033; --mav-indigo:#5969f5; --mav-violet:#7659df; --mav-cyan:#36b9c9;
}}
*{{box-sizing:border-box;margin:0;padding:0}} body{{font-family:var(--sans);background:var(--bg);color:var(--ink);min-height:100vh;-webkit-font-smoothing:antialiased}} .app{{display:flex;min-height:100vh}}
.sidebar{{width:252px;background:linear-gradient(190deg,var(--nav),var(--nav2));color:#fff;padding:24px 16px;position:fixed;inset:0 auto 0 0;z-index:20;display:flex;flex-direction:column}}
.brand{{display:flex;align-items:center;gap:12px;padding:6px 8px 24px;border-bottom:1px solid var(--navline)}}
.mav-brand-mark{{width:38px;height:38px;border-radius:12px;display:inline-grid;place-items:center;color:#fff;font-weight:800;letter-spacing:-1px;background:linear-gradient(135deg,var(--mav-indigo),var(--mav-violet) 58%,var(--mav-cyan));box-shadow:0 8px 22px rgba(89,105,245,.24);}}
.brand strong{{display:block;font-family:var(--serif);font-size:17px;font-weight:600;letter-spacing:.2px}} .brand small{{display:block;color:var(--navmuted);margin-top:2px;font-size:11px}}
.nav-group{{margin-top:22px}} .nav-title{{color:#5c6178;font-size:10.5px;font-weight:600;letter-spacing:.5px;margin:0 10px 8px}}
.nav-menu{{list-style:none;display:grid;gap:3px}} .nav-menu li{{display:flex;align-items:center;gap:11px;padding:10px 12px;border-radius:9px;color:var(--navmuted);cursor:pointer;font-size:13.5px;font-weight:500;transition:.16s}}
.nav-menu li:hover{{background:rgba(255,255,255,.06);color:#fff}} .nav-menu li.active{{color:#fff;background:rgba(184,134,58,.16);box-shadow:inset 2.5px 0 0 var(--brass)}} .nav-icon{{width:18px;text-align:center;font-size:14px}}
.nav-menu li .tag{{margin-left:auto;font-size:9px;background:rgba(255,255,255,.1);color:var(--navmuted);padding:2px 6px;border-radius:99px;font-weight:600}}
.sidebar-footer{{margin-top:auto;color:#565b71;font-size:10.5px;line-height:1.7;padding-top:16px;border-top:1px solid var(--navline)}}
.auth-btn {{ display:block; width:100%; text-align:left; background:transparent; border:1px solid var(--navline); color:#8d93ab; padding:8px 12px; border-radius:6px; cursor:pointer; margin-top:12px; font-size:12px; transition:0.2s; }}
.auth-btn:hover {{ background:rgba(255,255,255,0.05); color:#fff; }}
.main{{margin-left:252px;width:calc(100% - 252px)}} .topbar{{height:64px;background:rgba(244,242,236,.9);backdrop-filter:blur(14px);border-bottom:1px solid var(--line);display:flex;align-items:center;justify-content:space-between;padding:0 32px;position:sticky;top:0;z-index:10}}
.breadcrumb{{font-size:13px;color:var(--muted)}} .breadcrumb strong{{color:var(--ink);font-weight:600}} .top-meta{{display:flex;gap:18px;color:var(--muted);font-size:11.5px;align-items:center}} .live-dot{{width:7px;height:7px;border-radius:50%;background:var(--green);display:inline-block;margin-right:6px}}
.content{{max-width:1440px;margin:0 auto;padding:36px 32px 40px}}
.hero{{display:flex;justify-content:space-between;gap:28px;align-items:flex-end;margin-bottom:28px}} .hero h1{{font-family:var(--serif);font-size:34px;font-weight:560;line-height:1.18;letter-spacing:-.2px;max-width:640px}} .hero p{{color:var(--muted);margin-top:12px;font-size:13.5px;line-height:1.75;max-width:600px}}
.public-note{{flex:0 0 260px;background:var(--surface);border:1px solid var(--line);border-left:3px solid var(--brass);border-radius:4px;padding:14px 16px;font-size:11.5px;color:#555;line-height:1.65}} .public-note b{{color:var(--ink);display:block;margin-bottom:4px;font-size:12px}}
.section{{margin-top:32px}} .section-head{{display:flex;justify-content:space-between;align-items:baseline;margin-bottom:14px}} .section-head h2{{font-family:var(--serif);font-size:19px;font-weight:560}} .section-head p{{color:var(--muted);font-size:11.5px}}
.metrics{{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:14px}} .metric-card{{background:var(--surface);border:1px solid var(--line);border-radius:12px;padding:18px 19px;box-shadow:var(--shadow)}} .metric-top{{display:flex;justify-content:space-between;color:var(--muted);font-size:11.5px;font-weight:600}} .metric-dot{{width:7px;height:7px;border-radius:50%;background:#c9c2ac}} .metric-dot.good{{background:var(--green)}} .metric-dot.warn{{background:var(--amber)}} .metric-dot.bad{{background:var(--red)}}
.metric-value{{font-family:var(--serif);font-size:27px;font-weight:560;margin-top:13px;font-variant-numeric:tabular-nums}} .metric-change{{font-size:12px;font-weight:600;margin-top:5px}} .positive{{color:var(--green)}} .negative{{color:var(--red)}} .metric-note{{color:var(--muted);font-size:10.5px;margin-top:9px}}

.engine{{margin-top:20px;background:var(--nav);border-radius:16px;padding:26px 28px;color:#fff;position:relative;overflow:hidden;box-shadow:0 20px 40px rgba(10,12,25,.25)}} .engine::after{{content:"";position:absolute;right:-60px;top:-60px;width:260px;height:260px;border-radius:50%;background:radial-gradient(circle,rgba(184,134,58,.25),transparent 70%)}}
.engine-top{{display:flex;justify-content:space-between;align-items:flex-start;gap:20px;position:relative}} .engine-label{{font-size:11px;color:var(--navmuted);letter-spacing:.3px}} .engine-title{{font-family:var(--serif);font-size:24px;margin-top:6px;font-weight:560}}
.engine-badge{{font-size:12px;font-weight:700;padding:8px 16px;border-radius:99px;white-space:nowrap}} .engine-badge.normal{{background:rgba(255,255,255,.1);color:#cfd3e0}} .engine-badge.t2{{background:rgba(184,134,58,.35);color:#ffdca0}}
.engine-grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px, 1fr));gap:10px;margin-top:22px;position:relative}}
.engine-item{{background:rgba(255,255,255,.045);border:1px solid rgba(255,255,255,.08);border-radius:10px;padding:12px 13px}} .engine-item .k{{font-size:10.5px;color:var(--navmuted)}} .engine-item .v{{font-family:var(--serif);font-size:17px;margin-top:5px}} .engine-item.hit{{border-color:rgba(184,134,58,.5);background:rgba(184,134,58,.1)}} .engine-item .pt{{font-size:10px;color:var(--brass-soft);margin-top:3px}}
.engine-foot{{margin-top:16px;font-size:11px;color:var(--navmuted);position:relative}}

.dashboard-grid{{display:grid;grid-template-columns:minmax(0,1.6fr) minmax(280px,.8fr);gap:16px}} .panel{{background:var(--surface);border:1px solid var(--line);border-radius:14px;box-shadow:var(--shadow)}} .panel-head{{display:flex;justify-content:space-between;align-items:center;padding:16px 19px;border-bottom:1px solid var(--line)}} .panel-head strong{{font-size:13px;font-weight:600}} .panel-head span{{color:var(--muted);font-size:10.5px}}
.chart-wrap{{height:300px;padding:14px 18px 18px}} .pulse-list{{padding:6px 19px 14px}} .pulse{{display:flex;align-items:center;justify-content:space-between;padding:14px 0;border-bottom:1px solid var(--line)}} .pulse:last-child{{border-bottom:0}} .pulse-label{{color:var(--muted);font-size:11px}} .pulse-main{{margin-top:4px;font-size:15px;font-weight:700}} .pulse-right{{text-align:right;font-size:11px;font-weight:600}}
.badge{{display:inline-flex;border-radius:99px;padding:4px 9px;font-size:10px;font-weight:700}} .badge.good{{background:var(--green-soft);color:var(--green)}} .badge.warn{{background:var(--amber-soft);color:var(--amber)}} .badge.bad{{background:var(--red-soft);color:var(--red)}} .badge.neutral{{background:var(--surface2);color:var(--muted)}}

.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:14px}} .card{{background:var(--surface);border:1px solid var(--line);border-radius:12px;padding:18px;box-shadow:var(--shadow)}} .card-header{{display:flex;justify-content:space-between;align-items:center}} .sym{{font-weight:700;font-size:16px}} .price{{font-size:20px;font-weight:700;font-family:var(--serif)}} .divider{{height:1px;background:var(--line);margin:14px 0}} .row{{display:flex;justify-content:space-between;font-size:12px;color:var(--muted);margin-bottom:10px}} .fw-bold{{color:var(--ink);font-weight:600}} .pos-text{{color:var(--green)}} .neg-text{{color:var(--red)}} .alert-text{{color:var(--red)}} 
.table-container{{overflow-x:auto;background:var(--surface);border:1px solid var(--line);border-radius:12px;box-shadow:var(--shadow)}} table{{width:100%;border-collapse:collapse;text-align:right;white-space:nowrap;font-variant-numeric:tabular-nums}} th,td{{padding:14px;border-bottom:1px solid var(--line);font-size:13px}} th{{background:var(--surface2);color:var(--muted);font-weight:600;font-size:11.5px}} th:nth-child(1),td:nth-child(1),th:nth-child(2),td:nth-child(2){{text-align:left}} tr:hover td{{background:#fbfbfb}}

.opt-grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(250px,1fr));gap:14px}} .mkt-card{{background:var(--surface);border:1px solid var(--line);border-radius:13px;padding:17px 18px;box-shadow:var(--shadow)}} .mkt-card .name{{font-size:12.5px;color:var(--muted);display:flex;justify-content:space-between}} .mkt-card .val{{font-family:var(--serif);font-size:21px;margin-top:8px}} .mkt-card .chg{{font-size:11.5px;font-weight:600;margin-top:4px}} .soon{{font-size:9.5px;background:var(--surface2);color:var(--muted);padding:2px 7px;border-radius:99px;font-weight:600}}
.footer{{color:#9a9484;font-size:10.5px;line-height:1.7;text-align:center;padding:34px 0 10px}}
.tab-pane{{display:none;animation:fade .3s ease}} .tab-pane.active{{display:block}} @keyframes fade{{from{{opacity:0;transform:translateY(5px)}}to{{opacity:1;transform:none}}}}
</style></head><body><div class="app">

<aside class="sidebar"><div class="brand"><div class="brand-mark"><span class="mav-brand-mark">A</span></div><div><strong>myAlphaView</strong><small>myAlphaView · myalphaview.com</small></div></div>
<div class="nav-group"><div class="nav-title">美股 · 宏观</div><ul class="nav-menu">
  <li class="active" onclick="switchTab('tab-overview',this)"><span class="nav-icon">◆</span>市场总览</li>
  <li onclick="switchTab('tab-engine',this)"><span class="nav-icon">◒</span>策略引擎</li>
  <li onclick="switchTab('tab-index',this)"><span class="nav-icon">◫</span>指数 & ETF</li>
</ul></div>
<div class="nav-group"><div class="nav-title">A股 · 港股 · 红利</div><ul class="nav-menu">
  <li onclick="switchTab('tab-cn-hk',this)"><span class="nav-icon">◇</span>大盘 & 红利低波 <span class="tag">NEW</span></li>
</ul></div>
<div class="nav-group"><div class="nav-title">观察 & 持仓</div><ul class="nav-menu">
  <li onclick="switchTab('tab-stocks',this)"><span class="nav-icon">⌁</span>个股观察池</li>
  <li onclick="switchTab('tab-options',this)"><span class="nav-icon">⚑</span>期权自查清单</li>
</ul></div>
<div class="sidebar-footer">
  公开研究版 · 不展示个人真实资产<br>数据仅供研究演示
  <!-- 魔法链接登录入口 -->
  <button id="authBtn" class="auth-btn" onclick="handleAuth()">🔐 登录私有看板</button>
</div>
</aside>

<main class="main"><header class="topbar"><div class="breadcrumb">myAlphaView / <strong id="bc-title">市场总览</strong></div><div class="top-meta"><span id="liveStatus"><i class="live-dot"></i><span id="liveStatusText">数据抓取成功</span></span><span id="updateTime">更新: {data['updated']}</span></div></header><div class="content">

<!-- TAB 1: 市场总览 -->
<div id="tab-overview" class="tab-pane active">
<section class="hero"><div><h1>看清市场在说什么，而不是账户在做什么。</h1><p>公开版投资研究面板：聚焦市场趋势、回撤、波动率与策略触发条件。</p></div><div class="public-note"><b id="modeTitle">公开展示模式</b><span id="modeDesc">这里展示的是研究指标与策略信号，不代表任何个人账户的实际仓位或收益。</span></div></section>
<section class="section"><div class="section-head"><h2>市场核心指标</h2><p>自动更新</p></div><div class="metrics">{metric_card('纳斯达克综合指数',qqq_value,qqq_chg,qqq_note,'good' if isinstance(qqq_chg,(int,float)) and qqq_chg>=0 else 'warn')}{metric_card('标普500指数',spy_value,spy_chg,spy_note,'good' if isinstance(spy_chg,(int,float)) and spy_chg>=0 else 'warn')}{metric_card('VIX恐慌指数',vol_display,None,vix_note,vol_tone)}{metric_card('红利低波100 (159307)',sz_val,sz_chg,'A股红利代理 · 腾讯行情','good')}</div></section>

<section class="section"><div class="section-head"><h2>QQQ & SPY · 近 30 个交易日</h2><p>历史走势</p></div><div class="dashboard-grid"><div class="panel"><div class="panel-head"><strong>趋势对比</strong><span>收盘价</span></div><div class="chart-wrap"><canvas id="trendChart"></canvas></div></div><div class="panel"><div class="panel-head"><strong>Market Pulse</strong><span>研究状态</span></div><div class="pulse-list">
<div class="pulse"><div><div class="pulse-label">波动环境</div><div class="pulse-main">{vol_state}</div></div><div class="pulse-right"><span class="badge {vol_tone}">VIX {vol_display}</span></div></div>
<div class="pulse"><div><div class="pulse-label">策略观察</div><div class="pulse-main">指标运作中</div></div><div class="pulse-right"><span class="badge neutral">RULE BASED</span></div></div>
<div class="pulse"><div><div class="pulse-label">全球资产</div><div class="pulse-main">中美资产跟踪</div></div><div class="pulse-right"><span class="badge good">已接入</span></div></div></div></div></div></section>
</div>

<!-- TAB 2: 策略引擎 -->
<div id="tab-engine" class="tab-pane">
<section class="hero"><div><h1>核心策略信号</h1><p>用回撤、RSI 与长期均线观察核心 ETF 的风险与潜在策略触发点。</p></div></section>
<section class="section"><div class="engine"><div class="engine-top"><div><div class="engine-label">STRATEGY ENGINE · 核心资产宽幅与回撤联动</div><div class="engine-title">当前状态：实时监测</div></div><div class="engine-badge normal">当前得分 0 · 未触发加仓分级</div></div>
<div class="engine-grid">{engine_html}</div><div class="engine-foot">分级规则：基于各大宽基指数及杠杆 ETF 的极值回撤触发。此处展示已整合的规则与信号，不展示实盘资金规模。</div></div></section>
</div>

<!-- TAB 3: 指数与 ETF -->
<div id="tab-index" class="tab-pane"><section class="hero"><div><h1>指数与行业 ETF</h1><p>从宽基指数到行业 ETF，快速观察价格、回撤、RSI 与 200 日均线距离。</p></div></section><section class="section"><div class="grid">{index_html}</div></section></div>

<!-- TAB 4: A股 & 港股 & 红利 -->
<div id="tab-cn-hk" class="tab-pane">
<section class="hero"><div><h1>A股港股 & 红利低波</h1><p>自动同步腾讯行情与天天基金盘中估值。部分场外基金如遇防爬拦截，将显示获取失败状态。</p></div></section>
<section class="section"><div class="section-head"><h2>大盘与红利核心池</h2><p>腾讯行情实时同步</p></div><div class="opt-grid">
{mkt_card_a("上证指数", cn.get("sh000001"))}
{mkt_card_a("沪深300", cn.get("sh000300"))}
{mkt_card_a("红利低波100 ETF (159307)", cn.get("sz159307"))}
{mkt_card_a("红利低波100 场外联接 (021550)", cn.get("021550"))}
</div></section>
<section class="section"><div class="section-head"><h2>港股跨境池</h2><p>腾讯行情实时同步</p></div><div class="opt-grid">
{mkt_card_a("华夏纳指 (港股)", cn.get("hk03086"))}
{mkt_card_a("国指备兑 (港股)", cn.get("hk03416"))}
</div></section>
</div>

<!-- TAB 5: 个股观察池 -->
<div id="tab-stocks" class="tab-pane"><section class="hero"><div><h1>个股观察池</h1><p>包含中英文名称对照及核心技术指标监控。</p></div></section><section class="section"><div class="table-container"><table><thead><tr><th>代码</th><th>名称</th><th>最新价</th><th>涨跌幅</th><th>开盘</th><th>最高</th><th>最低</th><th>年内最高</th><th>RSI(14)</th><th>距200MA</th><th>策略参考价</th></tr></thead><tbody id="stocksTableBody">{stock_html}</tbody></table></div></section></div>

<!-- TAB 6: 期权自查 -->
<div id="tab-options" class="tab-pane"><section class="hero"><div><h1>期权持仓自查清单</h1><p>静态监控清单：在持有期权头寸期间，重点审视的希腊字母与风控指标。</p></div></section><section class="section"><div class="opt-grid">
<div class="mkt-card"><h3>⏳ 剩余到期天数 (DTE)</h3><p style="font-size:12px;color:var(--muted);margin-top:8px">越接近到期，Theta 衰减越快。最后30天内加速明显。</p></div>
<div class="mkt-card"><h3>🎯 距行权价的距离</h3><p style="font-size:12px;color:var(--muted);margin-top:8px">决定合约是价内(ITM)、价平(ATM)还是价外(OTM)。</p></div>
<div class="mkt-card"><h3>📈 隐含波动率 (IV)</h3><p style="font-size:12px;color:var(--muted);margin-top:8px">IV 飙升或回落会显著影响期权权利金。</p></div>
<div class="mkt-card"><h3>Δ Delta (方向风险)</h3><p style="font-size:12px;color:var(--muted);margin-top:8px">标的每变动$1，期权价格大致的变动幅度。</p></div>
<div class="mkt-card"><h3>Γ Gamma (加速风险)</h3><p style="font-size:12px;color:var(--muted);margin-top:8px">临近到期且处于 ATM 附近时，Gamma 风险极大。</p></div>
<div class="mkt-card"><h3>⚖️ 盈亏平衡价</h3><p style="font-size:12px;color:var(--muted);margin-top:8px">买入/卖出：行权价 ± 权利金。判断到期防御位置。</p></div>
</div></section></div>

<div class="footer">© 2026 myAlphaView · Built by Simon · Public Research Dashboard<br>市场数据与策略指标仅供研究、学习与信息参考，不构成投资建议。</div>
</div></main></div>

<script>
// 图表与菜单切换逻辑
const DATA = {chart_json};
function switchTab(id,el){{
    document.querySelectorAll('.tab-pane').forEach(t=>t.classList.remove('active'));
    document.querySelectorAll('.nav-menu li').forEach(l=>l.classList.remove('active'));
    document.getElementById(id).classList.add('active');
    el.classList.add('active');
    document.getElementById('bc-title').innerText = el.innerText.replace('NEW', '').replace(/^[◆◒◫◇⌁⚑]/, '').trim();
    window.scrollTo({{top:0,behavior:'smooth'}});
}}
window.addEventListener('load',function(){{
    const c=document.getElementById('trendChart');
    const qq=DATA.QQQ||[], sp=DATA.SPY||[];
    if(!qq.length||!sp.length) return;
    const labels=qq.map(x=>x.d), qv=qq.map(x=>x.c), sv=sp.map(x=>x.c);
    new Chart(c,{{type:'line',data:{{labels,datasets:[
        {{label:'QQQ',data:qv,borderColor:'#b8863a',backgroundColor:'rgba(184,134,58,.08)',fill:true,borderWidth:2,pointRadius:0,tension:.35,yAxisID:'y'}},
        {{label:'SPY',data:sv,borderColor:'#1c7a4c',backgroundColor:'transparent',borderWidth:2,pointRadius:0,tension:.35,yAxisID:'y1'}}
    ]}},options:{{responsive:true,maintainAspectRatio:false,interaction:{{mode:'index',intersect:false}},plugins:{{legend:{{position:'top',align:'end'}}}},scales:{{x:{{grid:{{display:false}},ticks:{{maxTicksLimit:6}}}},y:{{position:'left',grid:{{color:'#eee9dc'}}}},y1:{{position:'right',grid:{{drawOnChartArea:false}}}}}}}}}});
}});

// ================= Supabase 魔法链接身份验证逻辑 =================
// ⚠️ 注意：在这里替换成你刚才获取的 URL 和 anon key
const SUPABASE_URL = 'https://rhielbkvhgqbthcgztci.supabase.co';
const SUPABASE_ANON_KEY = 'sb_publishable_7_S0qA1oh31fHiihhx07PA_1LPAighW';

const supabaseClient = supabase.createClient(SUPABASE_URL, SUPABASE_ANON_KEY);
const authBtn = document.getElementById('authBtn');

async function checkSession() {{
    const {{ data: {{ session }} }} = await supabaseClient.auth.getSession();
    if (session) {{
        authBtn.innerHTML = "🔓 退出私有模式";
        document.getElementById('modeTitle').innerText = "🔥 资金与策略模型已解锁";
        document.getElementById('modeTitle').style.color = "var(--red)";
        document.getElementById('modeDesc').innerText = "您已安全登录，当前正在展示包含实时计算和私有阈值的高级量化策略信号。";
        document.getElementById('liveStatusText').innerText = "连接云端数据库";
    }} else {{
        authBtn.innerHTML = "🔐 登录私有看板";
    }}
}}

// 处理登录/登出点击事件
async function handleAuth() {{
    const {{ data: {{ session }} }} = await supabaseClient.auth.getSession();
    if (session) {{
        // 如果已登录，则登出
        await supabaseClient.auth.signOut();
        alert('已退出登录，恢复为公开展示模式。');
        window.location.reload();
    }} else {{
        // 如果未登录，则发起魔法链接请求
        const email = prompt("请输入您的管理员邮箱地址以获取安全链接：");
        if (!email) return;
        
        authBtn.innerHTML = "⏳ 正在发送...";
        const {{ error }} = await supabaseClient.auth.signInWithOtp({{
            email: email,
            options: {{
                // 魔法链接重定向地址，指向你的 GitHub Pages 域名
                emailRedirectTo: window.location.origin + window.location.pathname
            }}
        }});

        if (error) {{
            alert("发送失败: " + error.message);
            authBtn.innerHTML = "🔐 登录私有看板";
        }} else {{
            alert("✅ 魔法验证链接已发送至 " + email + "，请查收邮件并点击链接登录！");
            authBtn.innerHTML = "✉️ 请查收邮件";
        }}
    }}
}}

// 页面加载时检查登录状态
window.addEventListener('load', checkSession);

// 监听魔法链接回调返回的状态变化
supabaseClient.auth.onAuthStateChange((event, session) => {{
    if (event === 'SIGNED_IN') checkSession();
}});
</script></body></html>'''

def push_to_supabase(data):
    supabase_url = os.environ.get("SUPABASE_URL")
    supabase_key = os.environ.get("SUPABASE_KEY")
    
    if not supabase_url or not supabase_key:
        print("注意：未找到 Supabase 环境变量，跳过数据库同步。")
        return
        
    endpoint = f"{supabase_url.rstrip('/')}/rest/v1/market_data"
    headers = {
        "apikey": supabase_key,
        "Authorization": f"Bearer {supabase_key}",
        "Content-Type": "application/json",
        "Prefer": "return=minimal"
    }
    # 将抓取到的全量 JSON 数据装入 payload 字段
    body = json.dumps({"payload": data}).encode("utf-8")
    
    req = urllib.request.Request(endpoint, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            print(f"✅ 成功将最新数据推送到 Supabase 数据库！状态码: {resp.status}")
    except Exception as e:
        print(f"❌ 推送 Supabase 失败: {e}")

if __name__ == '__main__':
    data = build()
    
    # 1. 生成并保存本地静态文件 (保留，用作未登录状态下的公开预览版)
    out = os.path.join(os.path.dirname(__file__), '..', 'docs', 'data.json')
    with open(out, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        
    html = render_html(data)
    html_out = os.path.join(os.path.dirname(__file__), '..', 'docs', 'index.html')
    with open(html_out, 'w', encoding='utf-8') as f:
        f.write(html)
    print(f'Generated {html_out}')
    
    # 2. 将数据推送到 Supabase 的 market_data 表，实现云端备份和防休眠
    push_to_supabase(data)
