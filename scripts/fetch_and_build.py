import json, datetime, os, time, math
import urllib.request, urllib.parse
import yfinance as yf
import pandas as pd
import warnings

warnings.filterwarnings("ignore")

API_KEY = os.environ.get("TWELVE_DATA_KEY", "demo")
BASE = "https://api.twelvedata.com"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
FUND_HEADERS = {"User-Agent": HEADERS["User-Agent"], "Referer": "http://fund.eastmoney.com/"}

# ================= 1. 智能节流阀 =================
LAST_TD_REQUEST_TIME = 0.0

def throttle():
    """精确控制 Twelve Data 请求频率不超过 8次/分钟"""
    global LAST_TD_REQUEST_TIME
    now = time.time()
    elapsed = now - LAST_TD_REQUEST_TIME
    target_interval = 7.6 
    if elapsed < target_interval:
        time.sleep(target_interval - elapsed)
    LAST_TD_REQUEST_TIME = time.time()

# ================= 2. 资产池配置 =================
CORE_TIERS = {
    "QQQM": {"t1": 0.12, "t2": 0.18, "t3": 0.25},
    "QQQ":  {"t1": 0.12, "t2": 0.18, "t3": 0.25},
    "VGT":  {"t1": 0.15, "t2": 0.20, "t3": 0.30},
    "QLD":  {"t1": 0.25, "t2": 0.35, "t3": 0.50},
    "TQQQ": {"t1": 0.40, "t2": 0.50, "t3": 0.70},
    "VOO":  {"t1": 0.075, "t2": 0.10, "t3": 0.15},
}

INDEX = ["QQQ", "SPY", "VOO", "SMH", "TQQQ", "GCMAIN", "BTC/USD"]
DISPLAYED_INDEX = ["QQQ", "VOO", "SMH", "TQQQ", "GCMAIN", "BTC/USD"]
VOL_PROXY_SYM = "VIXY"

STOCK_META = {
    "SOFI": {"name": "SoFi Technologies"}, "IREN": {"name": "Iris Energy"}, "ORCL": {"name": "甲骨文"},
    "TSLA": {"name": "特斯拉"}, "NVDA": {"name": "英伟达"}, "TSM":  {"name": "台积电"},
    "LITE": {"name": "Lumentum"}, "AVGO": {"name": "博通"}, "MRVL": {"name": "美满电子"},
    "NBIS": {"name": "Nebius"}, "GOOG": {"name": "谷歌"}, "AMD":  {"name": "超威半导体"},
    "HOOD": {"name": "Robinhood"}, "DRAM": {"name": "Roundhill内存芯片"}, "SPCX": {"name": "SpaceX代币化"},
    "QQQM": {"name": "纳指100(QQQM)"}, "QLD":  {"name": "纳指2倍做多(QLD)"}, "VGT":  {"name": "信息技术ETF(VGT)"},
    "QQQ":  {"name": "纳指100(QQQ)"}, "VOO":  {"name": "标普500(VOO)"},
}
STOCKS = list(STOCK_META.keys())

CN_HK_SYMBOLS = {
    "sh000001": "上证指数", "sh000300": "沪深300", "sz159307": "红利低波100 ETF",
    "hk03086": "华夏纳指 (港股)", "hk03416": "国指备兑 (港股)",
}
OTC_FUNDS = {}
TENCENT_URL = "http://qt.gtimg.cn/q={symbols}"
FUND_EST_URL = "http://fundgz.1234567.com.cn/js/{code}.js"

# ================= 3. ATH 强复权校验 (Integrity Layer) =================
def get_core_ath_metrics(symbols):
    """使用 yf.download 确保分子分母均通过 auto_adjust 复权，防御拆股 Bug"""
    result = {}
    print("\n========== [ATH CHECK (yf.download)] ==========")
    for sym in symbols:
        try:
            df = yf.download(sym, period="max", auto_adjust=True, progress=False)
            if df.empty: raise ValueError("Empty DataFrame from yfinance")

            high_col, close_col = df["High"], df["Close"]
            if isinstance(high_col, pd.DataFrame): high_col = high_col.iloc[:, 0]
            if isinstance(close_col, pd.DataFrame): close_col = close_col.iloc[:, 0]

            highs, closes = high_col.dropna(), close_col.dropna()
            if highs.empty or closes.empty: raise ValueError("No valid High/Close data")

            adj_ath, adj_close = float(highs.max()), float(closes.iloc[-1])
            if not math.isfinite(adj_ath) or not math.isfinite(adj_close) or adj_ath <= 0 or adj_close <= 0:
                raise ValueError(f"Invalid price values")

            drawdown = adj_close / adj_ath - 1.0
            extreme = drawdown <= -0.75

            result[sym] = {
                "ath": adj_ath, "close": adj_close, "drawdown": drawdown,
                "source": "yfinance_download", "extreme": extreme, "valid": True,
            }
            print(f"{sym:<6} | ATH={adj_ath:>10.2f} | Close={adj_close:>10.2f} | DD={drawdown:>8.2%} | PASS")
        except Exception as e:
            result[sym] = {"valid": False, "error": str(e)}
            print(f"{sym:<6} | Validation=FAILED | Error={e}")
        time.sleep(1.0)
    print("======== [ATH CHECK END] ========\n")
    return result

# ================= 4. 期权 BS 定价与数据抓取 =================
def norm_cdf(x): return (1.0 + math.erf(x / math.sqrt(2.0))) / 2.0
def norm_pdf(x): return math.exp(-0.5 * x**2) / math.sqrt(2.0 * math.pi)

def calc_option_greeks(S, K, T, r, sigma, opt_type="Call"):
    """手搓纯 Python 版 Black-Scholes 期权希腊字母引擎"""
    if T <= 0 or sigma <= 0 or S <= 0:
        return {"theo_price": 0.0, "delta": 0.0, "gamma": 0.0}
    d1 = (math.log(S / K) + (r + 0.5 * sigma**2) * T) / (sigma * math.sqrt(T))
    d2 = d1 - sigma * math.sqrt(T)
    gamma = norm_pdf(d1) / (S * sigma * math.sqrt(T))
    if opt_type.lower() == "call":
        delta = norm_cdf(d1)
        theo_price = S * norm_cdf(d1) - K * math.exp(-r * T) * norm_cdf(d2)
    else:
        delta = norm_cdf(d1) - 1.0
        theo_price = K * math.exp(-r * T) * norm_cdf(-d2) - S * norm_cdf(-d1)
    return {"theo_price": theo_price, "delta": delta, "gamma": gamma}

def build_yahoo_option_ticker(sym, expiry_str, opt_type, strike):
    dt = datetime.datetime.strptime(expiry_str, '%Y-%m-%d')
    strike_str = f"{int(round(strike * 1000)):08d}"
    return f"{sym}{dt.strftime('%y%m%d')}{'C' if opt_type.lower() == 'call' else 'P'}{strike_str}"

def fetch_yahoo_option_quote(opt_ticker):
    """利用无需鉴权的 v8 chart 接口强穿透抓取期权现价"""
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{opt_ticker}?interval=1d&range=5d"
    try:
        req = urllib.request.Request(url, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=12) as resp:
            payload = json.loads(resp.read().decode('utf-8'))
        result = payload["chart"]["result"][0]
        meta = result.get("meta", {})
        last_price = meta.get("regularMarketPrice")
        if last_price is None:
            closes = [c for c in result["indicators"]["quote"][0]["close"] if c is not None]
            if closes: last_price = float(closes[-1])
        return {"lastPrice": float(last_price) if last_price else 0.0, "impliedVolatility": 0.35} # IV暂用0.35基准
    except Exception as e:
        print(f"⚠️ 期权 {opt_ticker} 抓取失败: {e}")
        return None

def fetch_supabase_options():
    url, key = os.environ.get("SUPABASE_URL"), os.environ.get("SUPABASE_KEY")
    if not url or not key: return []
    try:
        endpoint = f"{url.rstrip('/')}/rest/v1/options_positions"
        req = urllib.request.Request(endpoint, headers={"apikey": key, "Authorization": f"Bearer {key}"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except: return []

# ================= 5. 基础行情抓取引擎 =================
def http_get_json(url):
    with urllib.request.urlopen(url, timeout=20) as resp: return json.loads(resp.read().decode("utf-8"))

def fetch_yahoo_index(y_symbol, range_="1y"):
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{y_symbol}?interval=1d&range={range_}"
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=15) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    q = payload["chart"]["result"][0]["indicators"]["quote"][0]
    ts = payload["chart"]["result"][0]["timestamp"]
    rows = []
    for i in range(len(ts)):
        if q["close"][i] is None: continue
        d = datetime.datetime.utcfromtimestamp(ts[i]).date().isoformat()
        rows.append({"datetime": d, "close": str(q["close"][i]), "high": str(q["high"][i] if q["high"][i] is not None else q["close"][i]), "low": str(q["low"][i] if q["low"][i] is not None else q["close"][i]), "open": str(q["open"][i] if q["open"][i] is not None else q["close"][i])})
    rows.reverse() 
    if not rows: raise RuntimeError("Yahoo returned no rows")
    return rows

def fetch_real_index_or_proxy(y_symbol, proxy_symbol, today, proxy_rows_cache=None):
    try:
        return analyze(y_symbol, fetch_yahoo_index(y_symbol), today), "yahoo_real", None
    except Exception as e:
        try:
            return analyze(proxy_symbol, proxy_rows_cache or fetch_time_series(proxy_symbol), today), "etf_proxy", str(e)
        except Exception as e2:
            return {"error": str(e2)}, "failed", str(e)

def fetch_time_series(symbol, outputsize=260, retries=3):
    params = urllib.parse.urlencode({"symbol": symbol, "interval": "1day", "outputsize": outputsize, "apikey": API_KEY})
    url = f"{BASE}/time_series?{params}"
    for attempt in range(retries):
        throttle()
        try:
            payload = http_get_json(url)
            if payload.get("status") == "error":
                if payload.get("code") == 429:
                    time.sleep(15)
                    continue
                raise RuntimeError(payload.get("message", "error"))
            return payload["values"]
        except Exception as e:
            if attempt == retries - 1: raise e
            time.sleep(10)

def fetch_tencent_quotes(symbols):
    req = urllib.request.Request(TENCENT_URL.format(symbols=",".join(symbols)), headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=10) as resp: raw = resp.read().decode("gbk", errors="ignore")
    except Exception as e: return {sym: {"error": str(e)} for sym in symbols}
    out = {}
    for line in raw.strip().split(";"):
        if not line or "=" not in line: continue
        sym = line.split("=", 1)[0].replace("v_", "").strip()
        fields = line.split("=", 1)[1].strip().strip('"').split("~")
        if len(fields) >= 5:
            try:
                name, price, prev_close = fields[1], float(fields[3]), float(fields[4])
                out[sym] = {"name": name, "price": price, "prev_close": prev_close, "day_chg": (price - prev_close)/prev_close if prev_close else None}
            except Exception as e: out[sym] = {"error": str(e)}
    return out

def calculate_daily_breadth(old_breadth=None, today_str=None):
    """霸道缓存兜底版：防封锁"""
    is_cache_valid = False
    if old_breadth and old_breadth.get("status") == "ok":
        try:
            if (datetime.datetime.strptime(today_str, "%Y-%m-%d").date() - datetime.datetime.strptime(old_breadth.get("date", "2000-01-01"), "%Y-%m-%d").date()).days <= 3:
                is_cache_valid = True
        except: pass

    if datetime.datetime.utcnow().hour < 12:
        if is_cache_valid or (old_breadth and old_breadth.get("status") == "ok"): return old_breadth
        return {"status": "skip", "message": "亚洲盘中且无缓存"}

    try:
        with open(os.path.join(os.path.dirname(__file__), 'sp500_constituents.json'), 'r') as f:
            tickers = json.load(f)
        data = yf.download(tickers, period="300d", interval="1d", threads=True, progress=False)['Close']
        ma20, ma50, ma200 = data.rolling(20).mean(), data.rolling(50).mean(), data.rolling(200).mean()
        valid = data.notna().sum(axis=1)
        b20 = ((data > ma20).sum(axis=1) / valid).dropna()
        if len(b20) < 11: raise ValueError("YF返回有效数据不足")
        b50, b200 = ((data > ma50).sum(axis=1) / valid).dropna(), ((data > ma200).sum(axis=1) / valid).dropna()
        return {"status": "ok", "date": today_str, "b20": float(b20.iloc[-1]), "b50": float(b50.iloc[-1]), "b200": float(b200.iloc[-1]), "slope_10d": float(b20.iloc[-1] - b20.iloc[-11])}
    except Exception as e:
        if old_breadth and old_breadth.get("status") == "ok": return old_breadth
        return {"status": "error", "message": str(e)}

# ================= 6. 指标推演算法 =================
def pct_change(latest, prior): return (latest - prior) / prior if prior else None
def tier_reached(drawdown, tiers):
    if drawdown is None or not tiers: return 0, None
    loss = -drawdown 
    if loss >= tiers["t3"]: return 3, "三级"
    if loss >= tiers["t2"]: return 2, "二级"
    if loss >= tiers["t1"]: return 1, "一级"
    return 0, None

def calc_rsi(closes, period=14):
    if len(closes) < period + 1: return None
    closes_asc = closes[::-1]
    gains = [max(0, closes_asc[i] - closes_asc[i-1]) for i in range(1, len(closes_asc))]
    losses = [max(0, closes_asc[i-1] - closes_asc[i]) for i in range(1, len(closes_asc))]
    ag, al = sum(gains[:period])/period, sum(losses[:period])/period
    for i in range(period, len(closes_asc)-1):
        ag, al = (ag*(period-1) + gains[i])/period, (al*(period-1) + losses[i])/period
    if al == 0: return 100.0
    return 100.0 - (100.0 / (1.0 + ag/al))

def analyze(symbol, rows, today, tiers=None, is_stock=False, ath_metric=None):
    closes = [float(r["close"]) for r in rows]
    latest_close = closes[0]
    
    ytd_rows = [r for r in rows if r["datetime"].startswith(str(today.year))]
    ytd_high = max([float(r["high"]) for r in ytd_rows]) if ytd_rows else latest_close
    
    ath_is_true, strategy_drawdown, ath_validation = False, None, "UNAVAILABLE"
    if ath_metric and ath_metric.get("valid"):
        strategy_drawdown = ath_metric.get("drawdown")
        ath_is_true = True
        ath_validation = "CHECK" if ath_metric.get("extreme") else "PASS"

    window_high = max([float(r["high"]) for r in rows if r.get("high") is not None]) if rows else None
    window_drawdown = (latest_close / window_high - 1.0) if window_high and latest_close else None

    level, level_label = 0, None
    if not is_stock and ath_is_true and strategy_drawdown is not None and tiers and ath_validation != "CHECK":
        level, level_label = tier_reached(strategy_drawdown, tiers)

    out = {
        "date": rows[0]["datetime"][:10], "close": latest_close, "prev_close": closes[1] if len(closes)>1 else latest_close,
        "day_chg": pct_change(latest_close, closes[1] if len(closes)>1 else latest_close), "ytd_high": ytd_high,
        "rsi": calc_rsi(closes, 14), "dist_200ma": pct_change(latest_close, sum(closes[:200])/200 if len(closes)>=200 else None),
        "ath_is_true": ath_is_true, "ath_validation": ath_validation, "strategy_drawdown": strategy_drawdown, "window_drawdown": window_drawdown,
    }
    if is_stock: out.update({"open": float(rows[0]["open"]), "high": float(rows[0]["high"]), "low": float(rows[0]["low"])})
    else: out.update({"drawdown": strategy_drawdown if ath_is_true else window_drawdown, "tiers": tiers, "level": level, "level_label": level_label})
    return out

# ================= 7. 构建调度中心 =================
def process_options_data(opt_positions, stocks, index, core, today):
    """期权风控：融合持仓数据、正股行情与BS引擎推演"""
    options_data = []
    for opt in opt_positions:
        sym, opt_type, side, strike, expiry, cost, qty = opt['symbol'], opt['opt_type'], opt.get('side','Long'), float(opt['strike']), str(opt['expiry']), float(opt['cost']), int(opt['qty'])

        curr_price = None
        for pool in (stocks, index, core):
            if sym in pool and "error" not in pool[sym]: curr_price = pool[sym]["close"]
            
        opt_ticker = build_yahoo_option_ticker(sym, expiry, opt_type, strike)
        q = fetch_yahoo_option_quote(opt_ticker)
        
        last_price, iv = (q["lastPrice"], q["impliedVolatility"]) if q else (0.0, 0.35)
        dte_days = (datetime.datetime.strptime(expiry, '%Y-%m-%d').date() - today).days
        
        greeks = calc_option_greeks(curr_price or strike, strike, max(dte_days, 0)/365.0, 0.042, iv, opt_type)
        delta = -greeks["delta"] if side.lower() == "short" else greeks["delta"]

        break_even = strike + cost if opt_type.lower() == 'call' else strike - cost
        unrealized_pnl = ((last_price - cost) if side.lower() == 'long' else (cost - last_price)) * 100 * qty if last_price > 0 else 0.0

        options_data.append({"symbol": sym, "opt_type": opt_type, "side": side, "strike": strike, "expiry": expiry, "cost": cost, "qty": qty, "last_price": last_price, "iv": iv, "delta": delta, "dte": dte_days, "curr_price": curr_price or 0.0, "unrealized_pnl": unrealized_pnl, "break_even": break_even})
        time.sleep(0.5)
    return options_data

def build():
    today = datetime.date.today()
    core, index, stocks, overview_charts, data_status = {}, {}, {}, {}, {}
    try:
        with open(os.path.join(os.path.dirname(__file__), '..', 'docs', 'data.json'), 'r', encoding='utf-8') as f: old_breadth = json.load(f).get("raw_breadth")
    except: old_breadth = None

    sb_targets = fetch_supabase_targets()
    data_status["Supabase"] = "🟢 已连接" if sb_targets else "🔴 Fallback"
    if sb_targets:
        for sym, tgt in sb_targets.items():
            if sym in STOCK_META: STOCK_META[sym]["target"] = tgt

    core_ath_metrics = get_core_ath_metrics(list(CORE_TIERS.keys()))

    for name, tiers in CORE_TIERS.items():
        try: core[name] = analyze(name, fetch_time_series(name), today, tiers, ath_metric=core_ath_metrics.get(name, {"valid": False}))
        except Exception as e: core[name] = {"error": str(e)}

    spy_rows_for_regime = None
    for name in INDEX:
        try:
            # 智能免费路由
            rows = fetch_yahoo_index("GC=F", range_="2y") if name == "GCMAIN" else (fetch_yahoo_index("BTC-USD", range_="2y") if name == "BTC/USD" else fetch_time_series(name))
            index[name] = analyze(name, rows, today, tiers=CORE_TIERS.get(name), ath_metric=core_ath_metrics.get(name, {"valid": False}))
            if name in ("QQQ", "SPY"): overview_charts[name] = [{"d": r["datetime"][:10], "c": float(r["close"])} for r in rows[:30][::-1]]
            if name == "SPY": spy_rows_for_regime = rows 
        except Exception as e: index[name] = {"error": str(e)}

    spx_data, spx_src, _ = fetch_real_index_or_proxy("%5EGSPC", "SPY", today)
    ixic_data, ixic_src, _ = fetch_real_index_or_proxy("%5EIXIC", "QQQ", today)
    vix_data, vix_src, _ = fetch_real_index_or_proxy("%5EVIX", VOL_PROXY_SYM, today)
    data_status["US Market"] = "🟢 Yahoo Real" if spx_src == "yahoo_real" else "🟡 ETF Proxy"
    data_status["VIX"] = "🟢 Yahoo Real" if vix_src == "yahoo_real" else "🟡 ETF Proxy"

    try: gspc_long_rows = fetch_yahoo_index("%5EGSPC", range_="max")
    except: gspc_long_rows = None
        
    breadth_data = calculate_daily_breadth(old_breadth, today.isoformat())
    if breadth_data.get("status") == "ok":
        data_status["Breadth"] = f"🟡 缓存 ({breadth_data.get('date', '未知')})" if old_breadth and breadth_data == old_breadth else "🟢 实时"
    elif breadth_data.get("status") == "skip": data_status["Breadth"] = "🟡 跳过拉取"
    else: data_status["Breadth"] = f"🔴 异常 ({breadth_data.get('message', '获取失败')[:8]}..)"

    market_regime = calc_market_regime(gspc_long_rows, spy_rows_for_regime, vix_data.get("close") if "error" not in vix_data else None, today, breadth_data)

    for name in STOCKS:
        try: stocks[name] = analyze(name, fetch_time_series(name), today, is_stock=True)
        except Exception as e: stocks[name] = {"error": str(e)}
        
    cn_hk_data = {}
    try:
        cn_hk_data.update(fetch_tencent_quotes(list(CN_HK_SYMBOLS.keys())))
        data_status["CN_HK"] = "🟢 Tencent" if cn_hk_data else "🔴 Error"
    except: data_status["CN_HK"] = "🔴 Error"

    for code, yf_sym in {"sh000001": "000001.SS", "sh000300": "000300.SS", "sz159307": "159307.SZ", "hk03086": "3086.HK", "hk03416": "3416.HK"}.items():
        try: overview_charts[code] = [{"d": r["datetime"][:10], "c": float(r["close"])} for r in fetch_yahoo_index(yf_sym, range_="1mo")[::-1]]
        except Exception as e: print(f"⚠️ {code} 历史趋势抓取失败: {e}")
        time.sleep(0.5)

    try:
        json_path = os.path.join(os.path.dirname(__file__), 'historical_signals.json')
        with open(json_path, 'r', encoding='utf-8') as f:
            historical_signals = json.load(f)
            for r in historical_signals: r["source"] = "资产自身三档线" if r.get("rating", "").startswith("★") else "全市场宽度恐慌"
            historical_signals.sort(key=lambda r: r.get("date", ""), reverse=True)
    except: historical_signals = []

    return {"updated": today.isoformat(), "gen_time": (datetime.datetime.utcnow() + datetime.timedelta(hours=8)).strftime("%Y-%m-%d %H:%M:%S"),
            "spy_date": index.get("SPY", {}).get("date", "-"), "core": core, "index": index, "stocks": stocks,
            "overview_charts": overview_charts, "options": process_options_data(fetch_supabase_options(), stocks, index, core, today),
            "cn_hk": cn_hk_data, "market_regime": market_regime, "historical_signals": historical_signals, "data_status": data_status,
            "raw_breadth": breadth_data, "market_indicators": {"spx": spx_data, "spx_source": spx_src, "ixic": ixic_data, "ixic_source": ixic_src, "vix": vix_data, "vix_source": vix_src}}

# ================= 8. 前端 HTML 组件渲染 =================
def fmt_pct(x, digits=2): return f"{x*100:.{digits}f}%" if isinstance(x, (int, float)) and not math.isnan(x) else "-"
def fmt_num(x, digits=2): return f"{x:.{digits}f}" if isinstance(x, (int, float)) and not math.isnan(x) else "-"
def get_dist_text(dd, tiers):
    if dd is None or not tiers: return ""
    try:
        loss, t1, t2, t3 = -float(dd), tiers.get("t1"), tiers.get("t2"), tiers.get("t3")
        if not t1: return ""
        if loss < t1: return f"(差 {fmt_pct(t1 - loss)} 到一级)"
        elif loss < t2: return f"(差 {fmt_pct(t2 - loss)} 到二级)"
        elif loss < t3: return f"(差 {fmt_pct(t3 - loss)} 到三级)"
        else: return "(已达最高档)"
    except: return ""

def engine_item(name, r):
    if "error" in r: return f'<div class="engine-item"><div class="k">{name}</div><div class="v">-</div><div class="pt">数据获取失败</div></div>'
    level, hit_cls = r.get("level", 0), "hit" if r.get("level", 0) > 0 else ""
    tiers_str = f'一级{fmt_pct((r.get("tiers") or {}).get("t1"),0)} / 二级{fmt_pct((r.get("tiers") or {}).get("t2"),0)} / 三级{fmt_pct((r.get("tiers") or {}).get("t3"),0)}'

    if r.get("ath_is_true"):
        dd, label, dist_text = r.get("strategy_drawdown"), "回撤 (ATH)", get_dist_text(r.get("strategy_drawdown"), r.get("tiers"))
        if r.get("ath_validation") == "CHECK": status_text, hit_cls = "⚠ 极端回撤 · 请验证数据", "warn"
        else: status_text = f'{r.get("level_label") if level > 0 else "未触发"} <span style="opacity:0.85">{dist_text}</span>'
    else:
        dd, label, status_text = r.get("window_drawdown"), "窗口回撤", "ATH 暂不可用 · 仅供参考"
    return f'''<div class="engine-item {hit_cls}"><div class="k">{name} {label}</div><div class="v">{fmt_pct(dd)}</div><div class="pt">{status_text} · 阈值 {tiers_str}</div></div>'''

def card_etf(name, r):
    disp_name = {"GCMAIN": "黄金连续期货 (GC=F)", "BTC/USD": "比特币 (BTC-USD)", "QQQ": "纳斯达克100 (QQQ)", "VOO": "标普500 (VOO)", "SMH": "半导体ETF (SMH)", "TQQQ": "纳指3倍做多 (TQQQ)"}.get(name, name)
    if "error" in r: return f'<div class="card err"><div class="sym">{disp_name}</div><div class="errmsg">获取失败: {r["error"]}</div></div>'
    dist_text = get_dist_text(r.get("drawdown"), r.get("tiers"))
    dist_row = f'<div class="row"><span>下一档距离</span><span style="color:var(--brass);font-weight:700;">{dist_text.replace("(","").replace(")","")}</span></div>' if dist_text else ""
    return f'''<div class="card"><div class="card-header"><span class="sym">{disp_name}</span><span class="price">${r["close"]:.2f}</span></div><div class="divider"></div><div class="row"><span>当年(YTD)最高</span><span class="fw-bold">${fmt_num(r["ytd_high"])}</span></div><div class="row"><span>策略回撤基准</span><span class="{'neg-text fw-bold' if r['drawdown'] and r['drawdown']<0 else 'fw-bold'}">{fmt_pct(r["drawdown"])}</span></div>{dist_row}<div class="row"><span>RSI (14)</span><span class="fw-bold">{fmt_num(r["rsi"])}</span></div><div class="row"><span>距 200MA</span><span class="fw-bold">{fmt_pct(r["dist_200ma"])}</span></div></div>'''

def render_options_html(options_data):
    if not options_data: return '<tr><td colspan="10" style="text-align:center; color:var(--muted)">当前没有记录的期权持仓</td></tr>'
    html = ""
    for opt in options_data:
        sym, opt_type, side, strike, expiry, cost, last_price, iv, delta, dte, curr_price, pnl, break_even = opt['symbol'], opt['opt_type'], opt['side'], opt['strike'], opt['expiry'], opt['cost'], opt['last_price'], opt['iv'], opt['delta'], opt['dte'], opt['curr_price'], opt['unrealized_pnl'], opt['break_even']
        dist_pct = ((curr_price - break_even) if opt_type.lower()=="call" else (break_even - curr_price)) / break_even * 100 if curr_price and break_even else 0
        pnl_cls, pnl_str = "pos-text" if pnl >= 0 else "neg-text", f"${pnl:+.2f}"
        status_html = '<span class="opt-status danger">极高风险 (DTE<14)</span>' if dte < 14 else ('<span class="opt-status warn">注意损耗</span>' if dte < 45 else '<span class="opt-status safe">周期健康</span>')
        side_color, side_bg = ("var(--green)", "var(--green-soft)") if side.lower() == "long" else ("var(--amber)", "var(--amber-soft)")
        html += f'''<tr><td style="text-align:left; font-weight:600; color:var(--ink)">{sym} <span style="font-size:10px; color:{side_color}; font-weight:600; background:{side_bg}; padding:2px 6px; border-radius:4px; margin-left:4px;">{side} {opt_type}</span></td><td class="fw-bold">${strike:.2f}</td><td>{expiry} <span style="font-size:10px;color:var(--muted)">({dte}d)</span></td><td>${cost:.2f}</td><td class="fw-bold">${last_price:.2f}</td><td class="{pnl_cls} fw-bold">{pnl_str}</td><td style="color:var(--navy); font-weight:600">${break_even:.2f}</td><td class="fw-bold">${curr_price:.2f}</td><td class="{pnl_cls}">{f"{dist_pct:+.2f}%" if curr_price else "-"}</td><td style="font-size:11.5px;color:var(--muted)">{iv:.1%} / {f"{delta:+.3f}" if delta else "-"}</td></tr>'''
    return html

def render_html(data):
    engine_html = "".join(engine_item(k, v) for k, v in data["core"].items())
    max_level = max([v.get("level", 0) for v in data["core"].values() if "error" not in v] or [0])
    index_html = "".join(card_etf(k, data["index"][k]) for k in DISPLAYED_INDEX if k in data["index"])
    stock_html = "".join(f'''<tr><td><div style="font-weight:600; font-size:13.5px; color:var(--ink); line-height:1.2;">{STOCK_META.get(sym, {{}}).get("name", sym)}</div><div style="font-size:11px; color:var(--muted); margin-top:3px; font-weight:500;">{sym}</div></td><td class="fw-bold" id="close-{sym}">${v["close"]:.2f}</td><td class="{'pos-text' if (v.get('day_chg') or 0)>=0 else 'neg-text'}" id="chg-{sym}">{(v.get('day_chg') or 0)*100:+.2f}%</td><td>${v["open"]:.2f}</td><td>${v["high"]:.2f}</td><td>${v["low"]:.2f}</td><td>${fmt_num(v["ytd_high"])}</td><td>{fmt_num(v["rsi"])}</td><td>{fmt_pct(v["dist_200ma"])}</td><td><b id="target-{sym}">${STOCK_META.get(sym, {{}}).get("target") or "-"}</b> <span id="action-{sym}">{ '<span class="alert-text fw-bold ml">(信号触发!)</span>' if STOCK_META.get(sym, {}).get("target") and v["close"] <= STOCK_META.get(sym, {}).get("target") else ""}</span></td></tr>''' for sym, v in data["stocks"].items() if "error" not in v)
    
    signals_html = ""
    for s in data.get("historical_signals", []):
        badge_cls = "warn" if "一级" in s['rating'] else ("bad" if "重点" in s['rating'] or "极限" in s['rating'] else "neutral")
        signals_html += f'''<tr><td style="text-align:left; font-weight:600;">{s['symbol']}</td><td>{s['date']}</td><td class="fw-bold">${s['price']:.4f}</td><td class="neg-text">{fmt_pct(s['drawdown'])}</td><td><span class="badge {badge_cls}">{s['rating']}</span></td><td><span class="badge {'neutral' if s.get("source") == "资产自身三档线" else 'good'}">{s.get('source','-')}</span></td></tr>'''

    mr = data.get("market_regime", {"error": "无数据"})
    market_regime_html = f'<div class="card err"><div class="sym">市场状态引擎</div><div class="errmsg">{mr["error"]}</div></div>' if "error" in mr else f'''<div class="panel"><div class="panel-head"><strong>市场状态引擎</strong><span>有效评分 {mr["score"]}/{mr["max_available_score"]} 分（满分体系 {mr["max_score"]} 分）</span></div><div class="pulse-list"><div class="pulse"><div><div class="pulse-label">当前风控评级</div><div class="pulse-main">{mr["tier_label"]}{'<span class="badge neutral" style="margin-left:6px">数据不完整</span>' if mr["max_available_score"]<mr["max_score"] else ''}</div></div><div class="pulse-right"><span class="badge {{"normal": "good", "tier1": "warn", "major": "warn", "extreme": "bad"}.get(mr["tier"], "neutral")}">{mr["score"]}/{mr["max_available_score"]} 可用分</span></div></div><div class="row"><span>指数历史高点回撤（阈值 {fmt_pct(mr["drawdown"]["threshold"])}）</span><span class="fw-bold">{fmt_pct(mr["drawdown"]["value"])} {'<span class="badge bad">命中 2分</span>' if mr["drawdown"]["hit"] else '<span class="badge neutral">未触发</span>'}</span></div>{"".join([f'<div class="row"><span>{c["key"]}（阈值 {c["threshold_note"]}）</span><span class="fw-bold">{fmt_pct(c["val"])} {'<span class="badge bad">命中 ' + str(c["points"]) + '分</span>' if c["hit"] else '<span class="badge neutral">未触发</span>'}</span></div>' for c in mr.get("conditions", [])])}</div>{f'<div class="errmsg" style="padding:0 19px 16px;color:var(--{"muted" if mr.get("breadth_status") == "skip" else "red"});font-size:11px">{"ℹ️" if mr.get("breadth_status") == "skip" else "⚠️"} {mr.get("breadth_message","")}，当前{"暂未触发" if mr.get("breadth_status") == "skip" else "以指数回撤独立打分"}。</div>' if not mr.get("conditions") else ""}</div>'''

    def metric_card(label, value, change=None, note="", tone="neutral", live_code=None):
        return f'''<div class="metric-card"><div class="metric-top">{label}<span class="metric-dot {tone}"></span></div><div class="metric-value"{f' data-live-price="{live_code}"' if live_code else ""}>{value}</div>{f'<div class="metric-change {"positive" if change>=0 else "negative"}" data-live-chg="{live_code or ""}">{"+" if change>=0 else ""}{fmt_pct(change)}</div>' if isinstance(change, (int, float)) else ""}<div class="metric-note">{note}</div></div>'''

    return f'''<!DOCTYPE html><html lang="zh-CN"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"><title>myAlphaView · Market Intelligence</title>
<meta name="author" content="Simon"><link href="https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,380;9..144,520;9..144,620&family=Inter:wght@400;500;600;700;800&display=swap" rel="stylesheet"><script src="https://cdn.jsdelivr.net/npm/chart.js@4"></script><script src="https://cdn.jsdelivr.net/npm/@supabase/supabase-js@2"></script>
<style>
:root{{--bg:#f4f2ec;--surface:#ffffff;--surface2:#ebe8df;--ink:#14161c;--muted:#696d76;--line:#e1ddd0;--nav:#11162a;--nav2:#0a0d1a;--navmuted:#8d93ab;--navline:rgba(255,255,255,.08);--brass:#b8863a;--brass-soft:#e8d3ab;--navy:#1f2b52;--green:#1c7a4c;--green-soft:#e5f1e9;--red:#b23b2e;--red-soft:#f6e6e2;--amber:#c07f2e;--amber-soft:#f6ecd8;--shadow:0 12px 32px rgba(15,15,10,.07);--serif:'Fraunces',ui-serif,Georgia,serif;--sans:'Inter',-apple-system,"PingFang SC","Microsoft YaHei",sans-serif;}}
*{{box-sizing:border-box;margin:0;padding:0}} body{{font-family:var(--sans);background:var(--bg);color:var(--ink);min-height:100vh;-webkit-font-smoothing:antialiased}} .app{{display:flex;min-height:100vh}}
.sidebar{{width:252px;background:linear-gradient(190deg,var(--nav),var(--nav2));color:#fff;padding:24px 16px;position:fixed;inset:0 auto 0 0;z-index:20;display:flex;flex-direction:column}} .brand{{display:flex;align-items:center;gap:12px;padding:6px 8px 24px;border-bottom:1px solid var(--navline)}} .mav-brand-mark{{width:38px;height:38px;border-radius:12px;flex:0 0 auto;background:linear-gradient(135deg,#d8a75c,var(--brass));display:grid;place-items:center;box-shadow:0 8px 18px rgba(184,134,58,.35)}} .brand strong{{display:block;font-family:var(--serif);font-size:17px;font-weight:600;letter-spacing:.2px}} .brand small{{display:block;color:var(--navmuted);margin-top:2px;font-size:11px}}
.nav-group{{margin-top:22px}} .nav-title{{color:#5c6178;font-size:10.5px;font-weight:600;letter-spacing:.5px;margin:0 10px 8px}} .nav-menu{{list-style:none;display:grid;gap:3px}} .nav-menu li{{display:flex;align-items:center;gap:11px;padding:10px 12px;border-radius:9px;color:var(--navmuted);cursor:pointer;font-size:13.5px;font-weight:500;transition:.16s}} .nav-menu li:hover{{background:rgba(255,255,255,.06);color:#fff}} .nav-menu li.active{{color:#fff;background:rgba(184,134,58,.16);box-shadow:inset 2.5px 0 0 var(--brass)}} .nav-icon{{width:18px;text-align:center;font-size:14px}} .sidebar-footer{{margin-top:auto;color:#565b71;font-size:10.5px;line-height:1.7;padding-top:16px;border-top:1px solid var(--navline)}}
.auth-btn-top {{ background: var(--brass); color: #fff; border: none; padding: 6px 14px; border-radius: 6px; cursor: pointer; font-size: 11.5px; font-weight: 600; transition: 0.2s; box-shadow: 0 4px 10px rgba(184,134,58,.3); margin-left: 12px; }} .auth-btn-top:hover {{ background: #a67732; transform: translateY(-1px); }}
.main{{margin-left:252px;width:calc(100% - 252px)}} .topbar{{height:64px;background:rgba(244,242,236,.9);backdrop-filter:blur(14px);border-bottom:1px solid var(--line);display:flex;align-items:center;justify-content:space-between;padding:0 32px;position:sticky;top:0;z-index:10}} .breadcrumb{{font-size:13px;color:var(--muted)}} .breadcrumb strong{{color:var(--ink);font-weight:600}} .top-meta{{display:flex;gap:18px;color:var(--muted);font-size:11.5px;align-items:center}} .live-dot{{width:7px;height:7px;border-radius:50%;background:var(--green);display:inline-block;margin-right:6px}} .content{{max-width:1440px;margin:0 auto;padding:36px 32px 40px}}
.hero{{display:flex;justify-content:space-between;gap:28px;align-items:flex-end;margin-bottom:28px}} .hero h1{{font-family:var(--serif);font-size:34px;font-weight:560;line-height:1.18;letter-spacing:-.2px;max-width:640px}} .hero p{{color:var(--muted);margin-top:12px;font-size:13.5px;line-height:1.75;max-width:600px}} .public-note{{flex:0 0 260px;background:var(--surface);border:1px solid var(--line);border-left:3px solid var(--brass);border-radius:4px;padding:14px 16px;font-size:11.5px;color:#555;line-height:1.65}} .public-note b{{color:var(--ink);display:block;margin-bottom:4px;font-size:12px}}
.section{{margin-top:32px}} .section-head{{display:flex;justify-content:space-between;align-items:baseline;margin-bottom:14px}} .section-head h2{{font-family:var(--serif);font-size:19px;font-weight:560}} .section-head p{{color:var(--muted);font-size:11.5px}}
.metrics{{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:14px}} .metric-card{{background:var(--surface);border:1px solid var(--line);border-radius:12px;padding:18px 19px;box-shadow:var(--shadow)}} .metric-top{{display:flex;justify-content:space-between;color:var(--muted);font-size:11.5px;font-weight:600}} .metric-dot{{width:7px;height:7px;border-radius:50%;background:#c9c2ac}} .metric-dot.good{{background:var(--green)}} .metric-dot.warn{{background:var(--amber)}} .metric-dot.bad{{background:var(--red)}} .metric-value{{font-family:var(--serif);font-size:27px;font-weight:560;margin-top:13px;font-variant-numeric:tabular-nums}} .metric-change{{font-size:12px;font-weight:600;margin-top:5px}} .positive{{color:var(--green)}} .negative{{color:var(--red)}} .metric-note{{color:var(--muted);font-size:10.5px;margin-top:9px}}
.engine{{margin-top:20px;background:var(--nav);border-radius:16px;padding:26px 28px;color:#fff;position:relative;overflow:hidden;box-shadow:0 20px 40px rgba(10,12,25,.25)}} .engine::after{{content:"";position:absolute;right:-60px;top:-60px;width:260px;height:260px;border-radius:50%;background:radial-gradient(circle,rgba(184,134,58,.25),transparent 70%)}} .engine-top{{display:flex;justify-content:space-between;align-items:flex-start;gap:20px;position:relative}} .engine-label{{font-size:11px;color:var(--navmuted);letter-spacing:.3px}} .engine-title{{font-family:var(--serif);font-size:24px;margin-top:6px;font-weight:560}} .engine-badge{{font-size:12px;font-weight:700;padding:8px 16px;border-radius:99px;white-space:nowrap}} .engine-badge.normal{{background:rgba(255,255,255,.1);color:#cfd3e0}} .engine-badge.t2{{background:rgba(184,134,58,.35);color:#ffdca0}} .engine-grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px, 1fr));gap:10px;margin-top:22px;position:relative}} .engine-item{{background:rgba(255,255,255,.045);border:1px solid rgba(255,255,255,.08);border-radius:10px;padding:12px 13px}} .engine-item .k{{font-size:10.5px;color:var(--navmuted)}} .engine-item .v{{font-family:var(--serif);font-size:17px;margin-top:5px}} .engine-item.hit{{border-color:rgba(184,134,58,.5);background:rgba(184,134,58,.1)}} .engine-item.warn{{border-color:rgba(192,127,46,.5);background:rgba(192,127,46,.1)}} .engine-item .pt{{font-size:10px;color:var(--brass-soft);margin-top:3px}} .engine-foot{{margin-top:16px;font-size:11px;color:var(--navmuted);position:relative}}
.dashboard-grid{{display:grid;grid-template-columns:minmax(0,1.6fr) minmax(280px,.8fr);gap:16px}} .panel{{background:var(--surface);border:1px solid var(--line);border-radius:14px;box-shadow:var(--shadow)}} .panel-head{{display:flex;justify-content:space-between;align-items:center;padding:16px 19px;border-bottom:1px solid var(--line)}} .panel-head strong{{font-size:13px;font-weight:600}} .panel-head span{{color:var(--muted);font-size:10.5px}} .chart-wrap{{height:300px;padding:14px 18px 18px}} .pulse-list{{padding:6px 19px 14px}} .pulse{{display:flex;align-items:center;justify-content:space-between;padding:14px 0;border-bottom:1px solid var(--line)}} .pulse:last-child{{border-bottom:0}} .pulse-label{{color:var(--muted);font-size:11px}} .pulse-main{{margin-top:4px;font-size:15px;font-weight:700}} .pulse-right{{text-align:right;font-size:11px;font-weight:600}}
.badge{{display:inline-flex;border-radius:99px;padding:4px 9px;font-size:10px;font-weight:700}} .badge.good{{background:var(--green-soft);color:var(--green)}} .badge.warn{{background:var(--amber-soft);color:var(--amber)}} .badge.bad{{background:var(--red-soft);color:var(--red)}} .badge.neutral{{background:var(--surface2);color:var(--muted)}}
.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:14px}} .card{{background:var(--surface);border:1px solid var(--line);border-radius:12px;padding:18px;box-shadow:var(--shadow)}} .card-header{{display:flex;justify-content:space-between;align-items:center}} .sym{{font-weight:700;font-size:16px}} .price{{font-size:20px;font-weight:700;font-family:var(--serif)}} .divider{{height:1px;background:var(--line);margin:14px 0}} .row{{display:flex;justify-content:space-between;font-size:12px;color:var(--muted);margin-bottom:10px}} .fw-bold{{color:var(--ink);font-weight:600}} .pos-text{{color:var(--green)}} .neg-text{{color:var(--red)}} .alert-text{{color:var(--red)}} .errmsg{{color:var(--muted);font-size:12px;margin-top:8px}} 
.table-container{{overflow-x:auto;background:var(--surface);border:1px solid var(--line);border-radius:12px;box-shadow:var(--shadow)}} table{{width:100%;border-collapse:collapse;text-align:right;white-space:nowrap;font-variant-numeric:tabular-nums}} th,td{{padding:14px;border-bottom:1px solid var(--line);font-size:13px}} th{{background:var(--surface2);color:var(--muted);font-weight:600;font-size:11.5px}} th:nth-child(1),td:nth-child(1){{text-align:left}} tr:hover td{{background:#fbfbfb}}
.mkt-card{{background:var(--surface);border:1px solid var(--line);border-radius:13px;padding:17px 18px;box-shadow:var(--shadow); align-self:start; transition: transform 0.2s, box-shadow 0.2s;}} .mkt-card.hover-card {{cursor: pointer;}} .mkt-card.hover-card:hover {{transform: translateY(-2px); box-shadow: 0 16px 40px rgba(15,15,10,.08);}} .chart-hint {{font-size: 10px; color: var(--brass); opacity: 0.8; font-weight: normal; margin-left: 6px;}} .mkt-chart-wrap {{display: none; margin-top: 15px; padding-top: 15px; border-top: 1px dashed var(--line);}} .mkt-chart-wrap.open {{display: block; animation: fadeDown 0.3s ease;}} @keyframes fadeDown {{from {{opacity: 0; transform: translateY(-5px);}} to {{opacity: 1; transform: none;}}}} .mkt-card .name{{font-size:12.5px;color:var(--muted);display:flex;justify-content:space-between; align-items:center;}} .mkt-card .val{{font-family:var(--serif);font-size:21px;margin-top:8px}} .mkt-card .chg{{font-size:11.5px;font-weight:600;margin-top:4px}} .opt-grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(250px,1fr));gap:14px; align-items:start;}}
.footer{{color:#9a9484;font-size:10.5px;line-height:1.7;text-align:center;padding:34px 0 10px}} .tab-pane{{display:none;animation:fade .3s ease}} .tab-pane.active{{display:block}} @keyframes fade{{from{{opacity:0;transform:translateY(5px)}}to{{opacity:1;transform:none}}}}
.opt-status {{ display:inline-flex; align-items:center; gap:5px; font-weight:600; font-size:11px; }} .opt-status.safe {{ color: var(--green); }} .opt-status.warn {{ color: var(--amber); }} .opt-status.danger {{ color: var(--red); }} .opt-status::before {{ content:""; display:block; width:6px; height:6px; border-radius:50%; }} .opt-status.safe::before {{ background: var(--green); }} .opt-status.warn::before {{ background: var(--amber); }} .opt-status.danger::before {{ background: var(--red); }}
@media (max-width: 1024px) {{ .dashboard-grid {{ grid-template-columns: 1fr; }} .metrics {{ grid-template-columns: repeat(2, 1fr); }} }}
@media (max-width: 768px) {{ .app {{ flex-direction: column; }} .sidebar {{ position: static; width: 100%; padding: 16px 20px; border-bottom: 1px solid var(--navline); }} .nav-group {{ margin-top: 16px; }} .nav-menu {{ display: flex; flex-wrap: wrap; gap: 8px; }} .nav-menu li {{ font-size: 12px; padding: 8px 12px; }} .main {{ margin-left: 0; width: 100%; }} .topbar {{ padding: 12px 20px; height: auto; flex-direction: column; align-items: flex-start; gap: 12px; }} .top-meta {{ flex-wrap: wrap; width: 100%; justify-content: space-between; }} .content {{ padding: 20px; }} .hero {{ flex-direction: column; align-items: flex-start; gap: 16px; }} .public-note {{ width: 100%; flex: auto; }} .metrics {{ grid-template-columns: 1fr; }} .engine::after {{ display: none; }} .engine-top {{ flex-direction: column; gap: 12px; }} .table-container {{ overflow-x: auto; -webkit-overflow-scrolling: touch; border-radius: 8px; }} th, td {{ padding: 10px; font-size: 12px; }} }}
</style></head><body><div class="app">

<aside class="sidebar"><div class="brand"><div class="mav-brand-mark"><svg width="20" height="20" viewBox="0 0 24 24" fill="none"><path d="M4 17 L9 9 L13 14 L20 5" stroke="#181109" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"/><circle cx="20" cy="5" r="2.1" fill="#181109"/></svg></div><div><strong>myAlphaView</strong><small>myAlphaView · myalphaview.com</small></div></div>
<div class="nav-group"><div class="nav-title">美股 · 宏观</div><ul class="nav-menu">
  <li class="active" onclick="switchTab('tab-overview',this)"><span class="nav-icon">◆</span>市场总览</li>
  <li onclick="switchTab('tab-engine',this)"><span class="nav-icon">◒</span>策略引擎</li>
  <li onclick="switchTab('tab-index',this)"><span class="nav-icon">◫</span>指数 & ETF</li>
</ul></div>
<div class="nav-group"><div class="nav-title">A股 · 港股 · 红利</div><ul class="nav-menu">
  <li onclick="switchTab('tab-cn-hk',this)"><span class="nav-icon">◇</span>大盘 & 红利低波</li>
</ul></div>
<div class="nav-group"><div class="nav-title">观察 & 持仓</div><ul class="nav-menu">
  <li onclick="switchTab('tab-stocks',this)"><span class="nav-icon">⌁</span>个股观察池</li>
  <li onclick="switchTab('tab-options',this)"><span class="nav-icon">⚑</span>期权持仓监控</li>
  <li onclick="switchTab('tab-archive',this)"><span class="nav-icon">📜</span>历史买点归档</li>
</ul></div>
<div class="sidebar-footer">公开研究版 · 不展示个人真实资产<br>数据仅供研究演示</div></aside>

<main class="main"><header class="topbar"><div class="breadcrumb">myAlphaView / <strong id="bc-title">市场总览</strong></div>
<div class="top-meta">
  <span id="liveStatus" style="display:none;"><i class="live-dot"></i><span id="liveStatusText">数据抓取成功</span></span>
  <div style="text-align:right; line-height:1.4;">
    <div style="font-weight:600; font-size:12px; color:var(--ink);">生成时间: {data.get('gen_time', '-')}</div>
    <div style="color:var(--muted); font-size:10.5px;">美股截至: {data.get('spy_date', '-')} | A/港股盘中动态刷新</div>
  </div>
  <button id="authBtn" class="auth-btn-top" onclick="handleAuth()">🔐 登录私有看板</button>
</div></header><div class="content">

<div id="tab-overview" class="tab-pane active">
<section class="hero"><div><h1>看清市场在说什么，而不是账户在做什么。</h1><p>公开版投资研究面板：聚焦市场趋势、回撤、波动率与策略触发条件。</p></div><div class="public-note"><b id="modeTitle">公开展示模式</b><span id="modeDesc">这里展示的是研究指标与策略信号，不代表任何个人账户的实际仓位或收益。</span></div></section>
<section class="section"><div class="section-head"><h2>市场核心指标</h2><p>自动更新</p></div><div class="metrics">{metric_card('纳斯达克综合指数',f'{data["market_indicators"]["ixic"]["close"]:,.2f}' if "error" not in data["market_indicators"]["ixic"] else "—",data["market_indicators"]["ixic"].get("day_chg"),f"成长/科技风格温度 · {'真实指数(Yahoo)' if data['market_indicators']['ixic_source']=='yahoo_real' else 'ETF代理'}",'good' if isinstance(data["market_indicators"]["ixic"].get("day_chg"),(int,float)) and data["market_indicators"]["ixic"].get("day_chg")>=0 else 'warn')}{metric_card('标普500指数',f'{data["market_indicators"]["spx"]["close"]:,.2f}' if "error" not in data["market_indicators"]["spx"] else "—",data["market_indicators"]["spx"].get("day_chg"),f"大盘风险偏好 · {'真实指数(Yahoo)' if data['market_indicators']['spx_source']=='yahoo_real' else 'ETF代理'}",'good' if isinstance(data["market_indicators"]["spx"].get("day_chg"),(int,float)) and data["market_indicators"]["spx"].get("day_chg")>=0 else 'warn')}{metric_card('VIX恐慌指数',fmt_num(data["market_indicators"]["vix"].get("close")) if "error" not in data["market_indicators"]["vix"] else "—",None,f"{'真实指数(Yahoo)' if data['market_indicators']['vix_source']=='yahoo_real' else 'ETF代理'}",'neutral')}{metric_card('红利低波100 (159307)',f'{data["cn_hk"].get("sz159307", {{}}).get("price", 0):,.3f}' if "price" in data["cn_hk"].get("sz159307", {{}}) else "—",data["cn_hk"].get("sz159307", {{}}).get("day_chg"),'A股红利代理 · 腾讯行情','good',live_code='sz159307')}</div></section>
<section class="section">{market_regime_html}</section>
<section class="section"><div class="section-head"><h2>QQQ & SPY · 近 30 个交易日</h2><p>历史走势</p></div><div class="dashboard-grid"><div class="panel"><div class="panel-head"><strong>趋势对比</strong><span>收盘价</span></div><div class="chart-wrap"><canvas id="trendChart"></canvas></div></div><div class="panel"><div class="panel-head"><strong>Data Status Center</strong><span>数据状态监控</span></div><div class="pulse-list"><div class="pulse"><div><div class="pulse-label">恐慌指数源</div><div class="pulse-main">{data['data_status'].get('VIX')}</div></div></div><div class="pulse"><div><div class="pulse-label">美股宽基指数</div><div class="pulse-main">{data['data_status'].get('US Market')}</div></div></div><div class="pulse"><div><div class="pulse-label">全市场宽度扫描</div><div class="pulse-main">{data['data_status'].get('Breadth')}</div></div></div><div class="pulse"><div><div class="pulse-label">亚太股指代理</div><div class="pulse-main">{data['data_status'].get('CN_HK')}</div></div></div><div class="pulse"><div><div class="pulse-label">场外基金接口</div><div class="pulse-main">{data['data_status'].get('OTC')}</div></div></div><div class="pulse"><div><div class="pulse-label">云端策略参数集</div><div class="pulse-main">{data['data_status'].get('Supabase')}</div></div></div></div></div></div></section>
</div>

<div id="tab-engine" class="tab-pane">
<section class="hero"><div><h1>核心策略信号</h1><p>用回撤、RSI 与长期均线观察核心 ETF 的风险与潜在策略触发点。</p></div></section>
<section class="section"><div class="engine"><div class="engine-top"><div><div class="engine-label">STRATEGY ENGINE · 核心ETF三档加仓线</div><div class="engine-title">当前状态：实时监测</div></div><div class="engine-badge {engine_badge_cls}">{level_names[max_level]}</div></div><div class="engine-grid">{engine_html}</div><div class="engine-foot">分级规则：策略触发严格使用经复权验证的历史全期最高点（ATH）作为基准；ATH 暂不可用或触发异常保险丝时仅展示窗口回撤参考值，不触发正式策略信号。此处展示规则与信号，不展示实盘资金规模。</div></div></section>
</div>

<div id="tab-index" class="tab-pane"><section class="hero"><div><h1>指数与行业 ETF</h1><p>从宽基指数到行业 ETF，快速观察价格、当年最高点回撤、RSI 与 200 日均线距离。</p></div></section><section class="section"><div class="grid">{index_html}</div></section></div>

<div id="tab-cn-hk" class="tab-pane">
<section class="hero"><div><h1>A股港股 & 红利低波</h1><p>自动同步腾讯行情。中证红利低波100指数(930955)本身不在免费行情源覆盖范围内，用紧密跟踪该指数的场内ETF(159307)代理展示走势。</p></div></section>
<section class="section"><div class="section-head"><h2>大盘与红利核心池</h2><p>点击卡片展开近 30 日历史趋势</p></div><div class="opt-grid">{mkt_card_a("上证指数", data["cn_hk"].get("sh000001"), "sh000001")}{mkt_card_a("沪深300", data["cn_hk"].get("sh000300"), "sh000300")}{mkt_card_a("红利低波100 ETF (159307)", data["cn_hk"].get("sz159307"), "sz159307")}</div></section>
<section class="section"><div class="section-head"><h2>港股跨境池</h2><p>点击卡片展开近 30 日历史趋势</p></div><div class="opt-grid">{mkt_card_a("华夏纳指 (港股)", data["cn_hk"].get("hk03086"), "hk03086")}{mkt_card_a("国指备兑 (港股)", data["cn_hk"].get("hk03416"), "hk03416")}</div></section>
</div>

<div id="tab-stocks" class="tab-pane"><section class="hero"><div><h1>个股观察池</h1><p>包含中英文名称对照及核心技术指标监控。</p></div></section><section class="section"><div class="table-container"><table><thead><tr><th>名称代码</th><th>最新价</th><th>涨跌幅</th><th>开盘</th><th>最高</th><th>最低</th><th>当年(YTD)最高</th><th>RSI(14)</th><th>距200MA</th><th>策略参考价</th></tr></thead><tbody id="stocksTableBody">{stock_html}</tbody></table></div></section></div>

<div id="tab-options" class="tab-pane">
<section class="hero"><div><h1>期权持仓监控 V1.5</h1><p>全自动动态云端账本追踪：实时捕获 Yahoo 隐波 (IV) 并内置自研 Black-Scholes 引擎推演理论 Delta 与对冲收益，真实盈亏一目了然。</p></div></section>
<section class="section"><div class="table-container"><table><thead><tr><th style="text-align:left;">合约 / 策略</th><th>行权价</th><th>到期日(DTE)</th><th>建仓成本</th><th>最新价</th><th>浮动盈亏</th><th>盈亏平衡点</th><th>正股现价</th><th>距盈亏平衡</th><th>IV / Delta</th></tr></thead><tbody id="optionsTableBody">{options_html}</tbody></table></div></section>
<section class="section"><p style="font-size:11.5px;color:var(--muted);line-height:1.7">💡 主理人说明：浮盈/浮亏自动结合 Long/Short 策略方向推演计算。Delta 指标可用于评估对冲正股所需的仓位，以及辅助预判合约归零/行权的最终概率。</p></section>
</div>

<div id="tab-archive" class="tab-pane">
<section class="hero"><div><h1>历史买点归档数据库</h1><p>完整回溯 2005 年以来各大核心资产触发一级、重点及极限加仓信号的黄金历史买点，验证策略透明度。</p></div></section>
<section class="section"><div class="table-container"><table><thead><tr><th style="text-align:left;">资产代号</th><th>触发日期</th><th>触发收盘价</th><th>当时全期回撤幅度</th><th>触发加仓评级</th><th>规则体系</th></tr></thead><tbody id="archiveTableBody">{signals_html}</tbody></table></div></section>
<section class="section"><p style="font-size:11.5px;color:var(--muted);line-height:1.7">同一资产同一天可能出现两条记录——"资产自身三档线"是该ETF自己相对真实全期最高点的回撤触发的加仓线；"全市场宽度恐慌"是标普500全市场宽度指标触发的分级信号。两套规则相互独立，同一天都触发是正常情况，不是数据重复。</p></section></div>

<div class="footer">© 2026 myAlphaView · Built by Simon · Public Research Dashboard<br>市场数据与策略指标仅供研究、学习与信息参考，不构成投资建议。</div>
</div></main></div>

<script>
const DATA = {chart_json};
const MKT_CHARTS = {{}}; 

function switchTab(id,el){{
  document.querySelectorAll('.tab-pane').forEach(t=>t.classList.remove('active'));
  document.querySelectorAll('.nav-menu li').forEach(l=>l.classList.remove('active'));
  document.getElementById(id).classList.add('active');
  el.classList.add('active');
  document.getElementById('bc-title').innerText = el.innerText.replace('NEW', '').replace(/^[◆◒◫◇⌁⚑📜]/u, '').trim();
  window.scrollTo({{top:0,behavior:'smooth'}});
}}

function toggleMktChart(code, title) {{
    const wrap = document.getElementById(`wrap-${{code}}`);
    const canvas = document.getElementById(`canvas-${{code}}`);
    if (wrap.classList.contains('open')) {{ wrap.classList.remove('open'); return; }}
    wrap.classList.add('open');
    if (!MKT_CHARTS[code] && DATA[code]) {{
        const chartData = DATA[code];
        const labels = chartData.map(x => x.d), values = chartData.map(x => x.c);
        const isPositive = values[values.length - 1] >= values[0];
        const color = isPositive ? '#1c7a4c' : '#b23b2e', bgColor = isPositive ? 'rgba(28,122,76,.05)' : 'rgba(178,59,46,.05)';
        MKT_CHARTS[code] = new Chart(canvas, {{ type: 'line', data: {{ labels: labels, datasets: [{{ label: title, data: values, borderColor: color, backgroundColor: bgColor, borderWidth: 2, pointRadius: 0, fill: true, tension: 0.35 }}] }}, options: {{ responsive: true, maintainAspectRatio: false, interaction: {{ mode: 'index', intersect: false }}, plugins: {{ legend: {{ display: false }} }}, scales: {{ x: {{ display: false }}, y: {{ position: 'right', grid: {{ color: '#eee9dc' }}, ticks: {{ font: {{size: 9}} }} }} }} }} }});
    }} else if (!DATA[code]) {{ wrap.innerHTML = '<div style="font-size:11px;color:var(--muted);text-align:center;padding-top:20px;">暂无历史趋势数据</div>'; }}
}}

window.addEventListener('load',function(){{
  const c=document.getElementById('trendChart');
  const qq=DATA.QQQ||[], sp=DATA.SPY||[];
  if(qq.length && sp.length) {{
      const labels=qq.map(x=>x.d), qv=qq.map(x=>x.c), sv=sp.map(x=>x.c);
      new Chart(c,{{type:'line',data:{{labels,datasets:[{{label:'QQQ',data:qv,borderColor:'#b8863a',backgroundColor:'rgba(184,134,58,.08)',fill:true,borderWidth:2,pointRadius:0,tension:.35,yAxisID:'y'}},{{label:'SPY',data:sv,borderColor:'#1c7a4c',backgroundColor:'transparent',borderWidth:2,pointRadius:0,tension:.35,yAxisID:'y1'}}]}},options:{{responsive:true,maintainAspectRatio:false,interaction:{{mode:'index',intersect:false}},plugins:{{legend:{{position:'top',align:'end'}}}},scales:{{x:{{grid:{{display:false}},ticks:{{maxTicksLimit:6}}}},y:{{position:'left',grid:{{color:'#eee9dc'}}}},y1:{{position:'right',grid:{{drawOnChartArea:false}}}}}}}}}});
  }}
}});

const SUPABASE_URL = 'https://rhielbkvhgqbthcgztci.supabase.co';
const SUPABASE_ANON_KEY = 'sb_publishable_7_S0qA1oh31fHiihhx07PA_1LPAighW';
const ADMIN_EMAIL = 'xxj8166@gmail.com';
let isAdmin = false;
const supabaseClient = supabase.createClient(SUPABASE_URL, SUPABASE_ANON_KEY);
const authBtn = document.getElementById('authBtn');

async function fetchAndRenderTargets() {{
  const {{ data, error }} = await supabaseClient.from('stock_targets').select('*');
  if (data) {{
      data.forEach(row => {{
          const targetEl = document.getElementById(`target-${{row.symbol}}`), closeEl = document.getElementById(`close-${{row.symbol}}`), actionEl = document.getElementById(`action-${{row.symbol}}`);
          if (targetEl && closeEl) {{
              targetEl.innerHTML = `$${{row.target_price.toFixed(2)}}`;
              if (isAdmin) targetEl.innerHTML += ` <span style="cursor:pointer;font-size:12px;margin-left:6px;filter:grayscale(1) opacity(0.5);transition:0.2s;" onmouseover="this.style.filter='none'" onmouseout="this.style.filter='grayscale(1) opacity(0.5)'" onclick="editTarget('${{row.symbol}}', ${{row.target_price}})" title="修改策略价">✏️</span>`;
              actionEl.innerHTML = (parseFloat(closeEl.innerText.replace('$', '')) <= row.target_price) ? '<span class="alert-text fw-bold ml" style="margin-left:4px;">(信号触发!)</span>' : '';
          }}
      }});
  }}
}}

async function editTarget(symbol, currentPrice) {{
  const newPrice = prompt(`主理人后台：\\n请输入 [${{symbol}}] 的新策略加仓价：\\n当前点位：$${{currentPrice}}`, currentPrice);
  if (newPrice !== null && newPrice.trim() !== '') {{
      const num = parseFloat(newPrice);
      if (!isNaN(num)) {{
          const {{ error }} = await supabaseClient.from('stock_targets').upsert({{ symbol: symbol, target_price: num }});
          if (error) alert('更新失败：' + error.message);
          else fetchAndRenderTargets();
      }} else alert('输入无效，请输入纯数字。');
  }}
}}

async function checkSession() {{
  const {{ data: {{ session }} }} = await supabaseClient.auth.getSession();
  if (session) {{
      if (session.user.email === ADMIN_EMAIL) {{
          isAdmin = true;
          document.getElementById('modeTitle').innerText = "👑 主理人控制台已激活"; document.getElementById('modeDesc').innerText = "您现在可以在下方个股面板中，直接点击✏️修改全局策略触发价。";
      }} else {{
          isAdmin = false;
          document.getElementById('modeTitle').innerText = "🔥 资金与策略模型已解锁"; document.getElementById('modeDesc').innerText = "您已安全登录，当前正在展示最新的高级量化策略信号。";
      }}
      authBtn.innerHTML = "🔓 退出账号"; document.getElementById('modeTitle').style.color = "var(--red)"; document.getElementById('liveStatusText').innerText = "连接云端数据库";
  }} else {{ isAdmin = false; authBtn.innerHTML = "🔐 登录私有看板"; }}
  fetchAndRenderTargets();
}}

async function handleAuth() {{
  const {{ data: {{ session }} }} = await supabaseClient.auth.getSession();
  if (session) {{ await supabaseClient.auth.signOut(); alert('已退出登录，恢复为公开展示模式。'); window.location.reload(); }} 
  else {{
      const email = prompt("请输入您的邮箱地址，获取免密登录链接：");
      if (!email) return;
      authBtn.innerHTML = "⏳ 正在发送...";
      const {{ error }} = await supabaseClient.auth.signInWithOtp({{ email: email, options: {{ emailRedirectTo: window.location.origin + window.location.pathname }} }});
      if (error) {{ alert("发送失败: " + error.message); authBtn.innerHTML = "🔐 登录私有看板"; }} 
      else {{ alert("✅ 魔法验证链接已发送，请查收邮件！"); authBtn.innerHTML = "✉️ 请查收邮件"; }}
  }}
}}

window.addEventListener('load', checkSession);
supabaseClient.auth.onAuthStateChange((event, session) => {{ if (event === 'SIGNED_IN') checkSession(); }});

const CNHK_SYMBOLS = ['sh000001', 'sh000300', 'sz159307', 'hk03086', 'hk03416'];
function fetchLiveCNHK() {{
  const script = document.createElement('script');
  script.src = `https://qt.gtimg.cn/q=${{CNHK_SYMBOLS.join(',')}}&r=${{Math.random()}}`;
  script.onload = () => {{
      CNHK_SYMBOLS.forEach(sym => {{
          const rawData = window['v_' + sym];
          if (rawData) {{
              const fields = rawData.split('~');
              if (fields.length > 5) {{
                  const currentPrice = parseFloat(fields[3]), prevClose = parseFloat(fields[4]), pctChange = (currentPrice - prevClose) / prevClose;
                  document.querySelectorAll(`[data-live-price="${{sym}}"]`).forEach(el => el.innerText = currentPrice.toFixed(3));
                  document.querySelectorAll(`[data-live-chg="${{sym}}"]`).forEach(el => {{
                      el.innerText = (pctChange >= 0 ? "+" : "") + (pctChange * 100).toFixed(2) + "%";
                      el.classList.remove("positive", "negative"); el.classList.add(pctChange >= 0 ? "positive" : "negative");
                  }});
              }}
          }}
      }});
      document.head.removeChild(script);
  }};
  document.head.appendChild(script);
}}
window.addEventListener('load', () => {{ setInterval(fetchLiveCNHK, 5000); }});
</script></body></html>'''

def push_to_supabase(data):
    supabase_url, supabase_key = os.environ.get("SUPABASE_URL"), os.environ.get("SUPABASE_KEY")
    if not supabase_url or not supabase_key: return
    req = urllib.request.Request(f"{supabase_url.rstrip('/')}/rest/v1/market_data", data=json.dumps({"payload": data}).encode("utf-8"), headers={"apikey": supabase_key, "Authorization": f"Bearer {supabase_key}", "Content-Type": "application/json", "Prefer": "return=minimal"}, method="POST")
    try: urllib.request.urlopen(req, timeout=15); print("✅ 成功将最新数据推送到 Supabase")
    except Exception as e: print(f"❌ 推送 Supabase 失败: {e}")

if __name__ == '__main__':
    data = build()
    out = os.path.join(os.path.dirname(__file__), '..', 'docs', 'data.json')
    with open(out, 'w', encoding='utf-8') as f: json.dump(data, f, ensure_ascii=False, indent=2)
    html_out = os.path.join(os.path.dirname(__file__), '..', 'docs', 'index.html')
    with open(html_out, 'w', encoding='utf-8') as f: f.write(render_html(data))
    print(f'Generated {html_out}')
    push_to_supabase(data)
