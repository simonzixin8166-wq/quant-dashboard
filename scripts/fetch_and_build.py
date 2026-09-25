import json, datetime, os, time, math, tempfile
import urllib.request, urllib.parse
import yfinance as yf
import pandas as pd
import warnings
try:
    from opportunity_strategy import build_tqqq_x2_strategy, build_leaps_radar, merge_alert_history
except ModuleNotFoundError:
    import sys
    sys.path.insert(0, os.path.dirname(__file__))
    from opportunity_strategy import build_tqqq_x2_strategy, build_leaps_radar, merge_alert_history

warnings.filterwarnings("ignore")

# 单一版本源：每日 Action 生成 HTML 时，页面标题和静态资源缓存版本都从这里读取。
APP_VERSION = "3.8.1"
OPTIONS_VERSION = "3.8.1"
ASSET_VERSION = "3.8.1"

API_KEY = os.environ.get("TWELVE_DATA_KEY", "demo")
BASE = "https://api.twelvedata.com"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

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
TENCENT_URL = "http://qt.gtimg.cn/q={symbols}"

# ================= 3. ATH 强复权校验 =================
def get_core_ath_metrics(symbols):
    result = {}
    print("\n========== [ATH CHECK (fetch_yahoo_index)] ==========")
    for sym in symbols:
        try:
            rows = fetch_yahoo_index(sym, range_="max")
            if not rows: raise ValueError("Empty rows")

            adj_ath = max(float(r["high"]) for r in rows)
            adj_close = float(rows[0]["close"])
            if not math.isfinite(adj_ath) or not math.isfinite(adj_close) or adj_ath <= 0 or adj_close <= 0:
                raise ValueError("Invalid price values")

            drawdown = adj_close / adj_ath - 1.0
            extreme = drawdown <= -0.75

            result[sym] = {
                "ath": adj_ath, "close": adj_close, "drawdown": drawdown,
                "source": "yahoo_chart_api", "extreme": extreme, "valid": True,
            }
            print(f"{sym:<6} | ATH={adj_ath:>10.2f} | Close={adj_close:>10.2f} | DD={drawdown:>8.2%} | PASS")
        except Exception as e:
            result[sym] = {"valid": False, "error": str(e)}
            print(f"{sym:<6} | Validation=FAILED | Error={e}")
        throttle()
    print("======== [ATH CHECK END] ========\n")
    return result

# ================= 4. 期权 BS 定价与数据抓取 =================
def norm_cdf(x): return (1.0 + math.erf(x / math.sqrt(2.0))) / 2.0
def norm_pdf(x): return math.exp(-0.5 * x**2) / math.sqrt(2.0 * math.pi)

def calc_option_greeks(S, K, T, r, sigma, opt_type="Call"):
    if T <= 0 or sigma <= 0 or S <= 0: return {"theo_price": 0.0, "delta": 0.0, "gamma": 0.0}
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
    url_v7 = f"https://query1.finance.yahoo.com/v7/finance/quote?symbols={opt_ticker}"
    try:
        req = urllib.request.Request(url_v7, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            res = data.get('quoteResponse', {}).get('result', [])
            if res:
                q_data = res[0]
                last_price = q_data.get("regularMarketPrice", 0.0)
                iv = q_data.get("impliedVolatility", 0.0)
                if iv and iv > 0: return {"lastPrice": float(last_price) if last_price else 0.0, "impliedVolatility": float(iv)}
    except Exception: pass

    url_v8 = f"https://query1.finance.yahoo.com/v8/finance/chart/{opt_ticker}?interval=1d&range=5d"
    try:
        req = urllib.request.Request(url_v8, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=12) as resp:
            payload = json.loads(resp.read().decode('utf-8'))
        result = payload["chart"]["result"][0]
        meta = result.get("meta", {})
        last_price = meta.get("regularMarketPrice")
        if last_price is None:
            closes = [c for c in result["indicators"]["quote"][0]["close"] if c is not None]
            if closes: last_price = float(closes[-1])
        # Chart 备用接口不提供可靠 IV。宁可明确缺失，也不能用固定值冒充实时隐波。
        return {"lastPrice": float(last_price) if last_price else 0.0, "impliedVolatility": None}
    except Exception as e: return None

def fetch_supabase_options():
    url, key = os.environ.get("SUPABASE_URL"), os.environ.get("SUPABASE_KEY")
    if not url or not key: return []
    try:
        endpoint = f"{url.rstrip('/')}/rest/v1/options_positions"
        req = urllib.request.Request(endpoint, headers={"apikey": key, "Authorization": f"Bearer {key}"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except: return []

def fetch_supabase_targets():
    supabase_url = os.environ.get("SUPABASE_URL")
    supabase_key = os.environ.get("SUPABASE_KEY")
    if not supabase_url or not supabase_key: return None
    try:
        endpoint = f"{supabase_url.rstrip('/')}/rest/v1/stock_targets?select=symbol,target_price"
        req = urllib.request.Request(endpoint, headers={"apikey": supabase_key, "Authorization": f"Bearer {supabase_key}"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return {item["symbol"]: float(item["target_price"]) for item in data}
    except: return None

def fetch_supabase_watchlist():
    """返回数据库观察池；None 表示接口不可用，空列表表示用户主动清空。"""
    supabase_url = os.environ.get("SUPABASE_URL")
    supabase_key = os.environ.get("SUPABASE_KEY")
    if not supabase_url or not supabase_key: return None
    try:
        endpoint = f"{supabase_url.rstrip('/')}/rest/v1/stock_watchlist?select=symbol,display_name,sort_order&order=sort_order.asc,symbol.asc"
        req = urllib.request.Request(endpoint, headers={"apikey": supabase_key, "Authorization": f"Bearer {supabase_key}"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        print(f"WARNING: stock_watchlist unavailable, using code defaults: {e}")
        return None

# ================= 5. 基础行情抓取引擎 =================
def http_get_json(url):
    with urllib.request.urlopen(url, timeout=20) as resp: return json.loads(resp.read().decode("utf-8"))

def fetch_yahoo_index(y_symbol, range_="1y"):
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{y_symbol}?interval=1d&range={range_}&events=splits"
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=15) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    result = payload["chart"]["result"][0]
    q = result["indicators"]["quote"][0]
    ts = result["timestamp"]

    split_events = []
    for v in (result.get("events", {}).get("splits", {}) or {}).values():
        try:
            ratio = float(v["numerator"]) / float(v["denominator"])
            if ratio > 0: split_events.append((int(v["date"]), ratio))
        except Exception: continue
    split_events.sort()

    rows = []
    for i in range(len(ts)):
        if q["close"][i] is None: continue
        t = ts[i]
        factor = 1.0
        for split_ts, ratio in split_events:
            if split_ts > t: factor /= ratio
        d = datetime.datetime.utcfromtimestamp(t).date().isoformat()
        close = float(q["close"][i]) * factor
        high = float(q["high"][i] if q["high"][i] is not None else q["close"][i]) * factor
        low = float(q["low"][i] if q["low"][i] is not None else q["close"][i]) * factor
        open_ = float(q["open"][i] if q["open"][i] is not None else q["close"][i]) * factor
        rows.append({"datetime": d, "close": str(close), "high": str(high), "low": str(low), "open": str(open_)})
    rows.reverse()
    if not rows: raise RuntimeError("Yahoo returned no rows")
    return rows

def fetch_real_index_or_proxy(y_symbol, proxy_symbol, today, proxy_rows_cache=None):
    try: return analyze(y_symbol, fetch_yahoo_index(y_symbol), today), "yahoo_real", None
    except Exception as e:
        try: return analyze(proxy_symbol, proxy_rows_cache or fetch_time_series(proxy_symbol), today), "etf_proxy", str(e)
        except Exception as e2: return {"error": str(e2)}, "failed", str(e)

def fetch_time_series(symbol, outputsize=260, retries=3):
    params = urllib.parse.urlencode({"symbol": symbol, "interval": "1day", "outputsize": outputsize, "apikey": API_KEY})
    url = f"{BASE}/time_series?{params}"
    for attempt in range(retries):
        throttle()
        try:
            payload = http_get_json(url)
            if payload.get("status") == "error":
                if payload.get("code") == 429: time.sleep(15); continue
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

def _extract_yf_close(raw, batch):
    """兼容 yfinance 单代码/多代码及不同 MultiIndex 排列。"""
    if raw is None or raw.empty: return pd.DataFrame()
    if isinstance(raw.columns, pd.MultiIndex):
        if "Close" in raw.columns.get_level_values(0): close = raw["Close"]
        elif "Close" in raw.columns.get_level_values(1): close = raw.xs("Close", axis=1, level=1)
        else: return pd.DataFrame()
    elif "Close" in raw.columns:
        close = raw[["Close"]].rename(columns={"Close": batch[0]})
    else: return pd.DataFrame()
    if isinstance(close, pd.Series): close = close.to_frame(name=batch[0])
    return close.apply(pd.to_numeric, errors="coerce")

def _compute_breadth_from_closes(data):
    if data is None or data.empty: raise ValueError("YF未返回收盘价")
    data = data.sort_index().loc[:, ~data.columns.duplicated()]
    expected_symbols = 503
    # 至少205个有效日线数据才有资格进入200日均线宽度分母。
    eligible = data.columns[data.notna().sum() >= 205]
    data = data[eligible]
    symbol_coverage = data.shape[1] / expected_symbols
    if data.shape[1] < 450 or symbol_coverage < 0.90:
        raise ValueError(f"有效成分股覆盖不足: {data.shape[1]}/{expected_symbols} ({symbol_coverage:.1%})")
    coverage = data.notna().sum(axis=1)
    min_daily_coverage = max(450, math.ceil(data.shape[1] * 0.90))
    data = data.loc[coverage >= min_daily_coverage]
    if len(data) < 211: raise ValueError(f"有效交易日不足: {len(data)}")

    # 美股开盘期间不把尚未收盘的日K纳入日线市场宽度。
    latest_idx = data.index[-1]
    latest_date = latest_idx.date() if hasattr(latest_idx, "date") else None
    if latest_date == datetime.datetime.utcnow().date() and datetime.datetime.utcnow().hour < 21:
        data = data.iloc[:-1]
    if len(data) < 211: raise ValueError("剔除盘中未完成日K后数据不足")

    ma20, ma50, ma200 = data.rolling(20, min_periods=20).mean(), data.rolling(50, min_periods=50).mean(), data.rolling(200, min_periods=200).mean()
    b20 = ((data > ma20).sum(axis=1) / data.notna().sum(axis=1)).iloc[199:]
    b50 = ((data > ma50).sum(axis=1) / data.notna().sum(axis=1)).iloc[199:]
    b200 = ((data > ma200).sum(axis=1) / data.notna().sum(axis=1)).iloc[199:]
    if len(b20) < 11: raise ValueError(f"宽度序列不足: {len(b20)}")
    market_date = data.index[-1].date().isoformat() if hasattr(data.index[-1], "date") else str(data.index[-1])[:10]
    latest_coverage = int(data.iloc[-1].notna().sum())
    return {"status":"ok", "date":market_date, "b20":float(b20.iloc[-1]), "b50":float(b50.iloc[-1]), "b200":float(b200.iloc[-1]), "slope_10d":float(b20.iloc[-1]-b20.iloc[-11]), "symbols":int(data.shape[1]), "universe":expected_symbols, "coverage":latest_coverage, "coverage_pct":latest_coverage/expected_symbols, "quality_gate":"pass"}

def _cached_breadth(old_breadth, reason):
    if not old_breadth or old_breadth.get("status") != "ok": return None
    out = dict(old_breadth)
    out.update({"is_cached": True, "message": reason})
    return out

def _previous_completed_us_session(now=None):
    """近似计算最近一个已经完成的美股交易日；节假日由缓存降级说明兜底。"""
    now = now or datetime.datetime.utcnow()
    candidate = now.date() if now.hour >= 21 else now.date() - datetime.timedelta(days=1)
    while candidate.weekday() >= 5:
        candidate -= datetime.timedelta(days=1)
    return candidate

def _weekday_gap(start, end):
    """统计 start 之后至 end（含）的工作日数量，不引入额外交易日历依赖。"""
    if not start or not end or start >= end: return 0
    cursor, count = start + datetime.timedelta(days=1), 0
    while cursor <= end:
        if cursor.weekday() < 5: count += 1
        cursor += datetime.timedelta(days=1)
    return count

def breadth_freshness(breadth, now=None):
    if not breadth or breadth.get("status") != "ok":
        return {"tone":"bad", "label":"不可用", "meta":(breadth or {}).get("message", "等待首次完整收盘数据")}
    try: market_date = datetime.date.fromisoformat(str(breadth.get("date")))
    except (TypeError, ValueError):
        return {"tone":"bad", "label":"日期异常", "meta":"宽度快照缺少有效交易日期"}
    expected = _previous_completed_us_session(now)
    gap = _weekday_gap(market_date, expected)
    cached = bool(breadth.get("is_cached"))
    if gap == 0:
        return {"tone":"good", "label":f"已更新至 {market_date.isoformat()}", "meta":"503只成分股完整收盘扫描"}
    if gap == 1:
        return {"tone":"warn", "label":f"最近有效收盘 {market_date.isoformat()}", "meta":breadth.get("message") or "等待下一次完整收盘扫描"}
    return {"tone":"bad", "label":f"数据陈旧 · {market_date.isoformat()}", "meta":breadth.get("message") or f"落后约 {gap} 个交易日，请检查每日任务"}

def calculate_daily_breadth(old_breadth=None, today_str=None):
    # 亚洲白天没有必要重复下载503只美股；优先展示上一完整交易日。
    if datetime.datetime.utcnow().hour < 12:
        cached = _cached_breadth(old_breadth, "美股未收盘，使用上一完整交易日")
        return cached or {"status":"skip", "message":"等待首次美股收盘宽度数据"}

    try:
        with open(os.path.join(os.path.dirname(__file__), 'sp500_constituents.json'), 'r') as f: tickers = json.load(f)
        tickers = [str(x).replace('.', '-') for x in tickers]
        frames, failures, batch_size = [], [], 50
        for start in range(0, len(tickers), batch_size):
            batch = tickers[start:start+batch_size]
            close = pd.DataFrame()
            last_error = None
            for attempt in range(3):
                try:
                    raw = yf.download(batch, period="18mo", interval="1d", auto_adjust=True, threads=False, progress=False, timeout=35)
                    close = _extract_yf_close(raw, batch)
                    if not close.empty: break
                    last_error = "空数据"
                except Exception as e: last_error = str(e)
                time.sleep(3 * (attempt + 1))
            if close.empty: failures.append(f"{start//batch_size+1}:{last_error}")
            else: frames.append(close)
            time.sleep(1.2)
        if not frames: raise ValueError("所有YF分批请求均失败: " + "; ".join(failures[:3]))
        result = _compute_breadth_from_closes(pd.concat(frames, axis=1))
        result["failed_batches"] = len(failures)
        print(f"✅ Breadth {result['date']}: {result['symbols']} symbols, failed_batches={len(failures)}")
        return result
    except Exception as e:
        cached = _cached_breadth(old_breadth, f"本次刷新失败，沿用缓存：{e}")
        if cached: return cached
        return {"status":"error", "message":str(e)}

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
    options_data = []
    for opt in opt_positions:
        opt_id = opt.get('id', 0)
        sym, opt_type, side, strike, expiry, cost, qty = opt['symbol'], opt['opt_type'], opt.get('side','Long'), float(opt['strike']), str(opt['expiry']), float(opt['cost']), int(opt['qty'])

        curr_price = None
        for pool in (stocks, index, core):
            if sym in pool and "error" not in pool[sym]: curr_price = pool[sym]["close"]
            
        opt_ticker = build_yahoo_option_ticker(sym, expiry, opt_type, strike)
        q = fetch_yahoo_option_quote(opt_ticker)
        
        last_price, iv = (q["lastPrice"], q.get("impliedVolatility")) if q else (0.0, None)
        dte_days = (datetime.datetime.strptime(expiry, '%Y-%m-%d').date() - today).days
        
        greeks = calc_option_greeks(curr_price or strike, strike, max(dte_days, 0)/365.0, 0.042, iv, opt_type) if iv else None
        delta = (-greeks["delta"] if side.lower() == "short" else greeks["delta"]) if greeks else None

        break_even = strike + cost if opt_type.lower() == 'call' else strike - cost
        unrealized_pnl = ((last_price - cost) if side.lower() == 'long' else (cost - last_price)) * 100 * qty if last_price > 0 else 0.0

        options_data.append({"id": opt_id, "symbol": sym, "opt_type": opt_type, "side": side, "strike": strike, "expiry": expiry, "cost": cost, "qty": qty, "last_price": last_price, "iv": iv, "delta": delta, "dte": dte_days, "curr_price": curr_price or 0.0, "unrealized_pnl": unrealized_pnl, "break_even": break_even})
        time.sleep(0.5)
    return options_data

def build():
    today = datetime.date.today()
    core, index, stocks, overview_charts, data_status = {}, {}, {}, {}, {}
    old_data = {}
    try:
        with open(os.path.join(os.path.dirname(__file__), '..', 'docs', 'data.json'), 'r', encoding='utf-8') as f: old_data = json.load(f)
    except: old_data = {}
    old_breadth = old_data.get("raw_breadth")

    sb_targets = fetch_supabase_targets()
    sb_watchlist = fetch_supabase_watchlist()
    active_stocks = list(STOCKS)
    if sb_watchlist is not None:
        active_stocks = []
        for item in sb_watchlist:
            sym = str(item.get("symbol", "")).strip().upper()
            if not sym: continue
            active_stocks.append(sym)
            STOCK_META[sym] = {**STOCK_META.get(sym, {}), "name": item.get("display_name") or sym}
    data_status["Supabase"] = "🟢 已连接" if sb_targets else "🔴 Fallback"
    if sb_targets:
        for sym, tgt in sb_targets.items():
            if sym in STOCK_META: STOCK_META[sym]["target"] = tgt

    core_ath_metrics = get_core_ath_metrics(list(CORE_TIERS.keys()))

    strategy_rows = {}
    for name, tiers in CORE_TIERS.items():
        try:
            rows = fetch_time_series(name)
            core[name] = analyze(name, rows, today, tiers, ath_metric=core_ath_metrics.get(name, {"valid": False}))
            if name in ("VGT",): strategy_rows[name] = rows
        except Exception as e: core[name] = {"error": str(e)}

    spy_rows_for_regime = None
    for name in INDEX:
        try:
            rows = fetch_yahoo_index("GC=F", range_="2y") if name == "GCMAIN" else (fetch_yahoo_index("BTC-USD", range_="2y") if name == "BTC/USD" else fetch_time_series(name))
            index[name] = analyze(name, rows, today, tiers=CORE_TIERS.get(name), ath_metric=core_ath_metrics.get(name, {"valid": False}))
            if name in ("QQQ", "SMH", "TQQQ"): strategy_rows[name] = rows
            if name in ("QQQ", "SPY"): overview_charts[name] = [{"d": r["datetime"][:10], "c": float(r["close"])} for r in rows[:30][::-1]]
            if name == "SPY": spy_rows_for_regime = rows 
        except Exception as e: index[name] = {"error": str(e)}

    spx_data, spx_src, _ = fetch_real_index_or_proxy("%5EGSPC", "SPY", today)
    ixic_data, ixic_src, _ = fetch_real_index_or_proxy("%5EIXIC", "QQQ", today)
    vix_data, vix_src, _ = fetch_real_index_or_proxy("%5EVIX", VOL_PROXY_SYM, today)
    data_status["US Market"] = "🟢 Yahoo指数日线" if spx_src == "yahoo_real" else "🟡 ETF日线代理"
    data_status["VIX"] = "🟢 Yahoo指数日线" if vix_src == "yahoo_real" else "🟡 ETF日线代理"

    # 机会雷达使用约5年的完整日线形成闭合状态；抓取失败时退回现有日线。
    try: qqq_strategy_rows = fetch_yahoo_index("QQQ", range_="5y")
    except Exception: qqq_strategy_rows = strategy_rows.get("QQQ", [])
    try: vix_strategy_rows = fetch_yahoo_index("%5EVIX", range_="5y")
    except Exception: vix_strategy_rows = []
    tqqq_x2 = build_tqqq_x2_strategy(qqq_strategy_rows, vix_strategy_rows, recorded_position=0)
    leaps_radar = build_leaps_radar(strategy_rows, vix_data.get("close") if "error" not in vix_data else None)
    opportunity_history = merge_alert_history(old_data.get("opportunity_history"), tqqq_x2, leaps_radar)

    try: gspc_long_rows = fetch_yahoo_index("%5EGSPC", range_="max")
    except: gspc_long_rows = None
        
    breadth_data = calculate_daily_breadth(old_breadth, today.isoformat())
    breadth_state = breadth_freshness(breadth_data)
    if breadth_data.get("status") == "ok":
        icon = {"good":"🟢", "warn":"🟡", "bad":"🔴"}.get(breadth_state["tone"], "🟡")
        data_status["Breadth"] = f"{icon} {breadth_state['label']}"
    elif breadth_data.get("status") == "skip": data_status["Breadth"] = "🟡 跳过拉取"
    else: data_status["Breadth"] = f"🔴 异常 ({breadth_data.get('message', '获取失败')[:8]}..)"

    market_regime = {"error": "指数历史数据不足，无法计算回撤"}
    if gspc_long_rows or spy_rows_for_regime:
        m_rows = gspc_long_rows if gspc_long_rows else spy_rows_for_regime
        m_score, m_max, m_cond = 0, 9, []
        m_drawdown = pct_change(float(m_rows[0]["close"]), max([float(r["high"]) for r in m_rows]))
        recent_rows = m_rows[:252] if len(m_rows) >= 252 else m_rows
        high_52w = max([float(r["high"]) for r in recent_rows])
        dist_52w_high = pct_change(float(m_rows[0]["close"]), high_52w)
        drawdown_hit = isinstance(m_drawdown, (int, float)) and not math.isnan(m_drawdown) and m_drawdown <= -0.08
        if drawdown_hit: m_score += 2
        
        if breadth_data and breadth_data.get("status") == "ok":
            b20, b50, b200, slope = breadth_data["b20"], breadth_data["b50"], breadth_data["b200"], breadth_data["slope_10d"]
            m_score += 2 if b20 <= 0.20 else 0; m_cond.append({"key":"20天宽度", "threshold_note":"≤20%", "points":2, "hit":b20<=0.20, "val":b20})
            m_score += 2 if b50 <= 0.15 else 0; m_cond.append({"key":"50天宽度", "threshold_note":"≤15%", "points":2, "hit":b50<=0.15, "val":b50})
            m_score += 2 if slope <= -0.30 else 0; m_cond.append({"key":"斜率冻点", "threshold_note":"≤-30%", "points":2, "hit":slope<=-0.30, "val":slope})
            m_score += 1 if b200 <= 0.50 else 0; m_cond.append({"key":"200天宽度", "threshold_note":"≤50%", "points":1, "hit":b200<=0.50, "val":b200})
        else: m_max = 2
            
        divergence_level, divergence_label = "l1", "未触发宽度顶背离"
        near_high = isinstance(dist_52w_high, (int, float)) and dist_52w_high >= -0.01
        if near_high and breadth_data.get("status") == "ok":
            if breadth_data["b50"] < 0.35 or breadth_data["b200"] < 0.45:
                divergence_level, divergence_label = "l3", "指数近高位，市场宽度严重背离"
            elif breadth_data["b50"] < 0.50:
                divergence_level, divergence_label = "l2", "指数近高位，市场宽度开始背离"

        m_tier = "extreme" if m_score >= 7 else ("major" if m_score >= 5 else ("tier1" if m_score >= 3 else "normal"))
        market_regime = {"score": m_score, "max_score": 9, "max_available_score": m_max, "tier": m_tier, "tier_label": {"extreme":"极限恐慌", "major":"重点恐慌", "tier1":"一级恐慌"}.get(m_tier, "盘中临时状态" if m_max<9 else "正常"), "drawdown": {"value": m_drawdown, "threshold": -0.08, "hit": drawdown_hit, "points": 2}, "conditions": m_cond, "vix": vix_data.get("close") if "error" not in vix_data else None, "breadth_status": (breadth_data or {}).get("status", "error"), "breadth_message": (breadth_data or {}).get("message", "宽度数据缺失"), "dist_52w_high": dist_52w_high, "divergence": {"level":divergence_level, "label":divergence_label, "near_high":near_high}}

    for name in active_stocks:
        try: stocks[name] = analyze(name, fetch_time_series(name), today, is_stock=True)
        except Exception as e: stocks[name] = {"error": str(e)}
        
    cn_hk_data = {}
    try:
        cn_hk_data.update(fetch_tencent_quotes(list(CN_HK_SYMBOLS.keys())))
        data_status["CN_HK"] = "🟢 腾讯行情" if cn_hk_data else "🔴 暂不可用"
    except: data_status["CN_HK"] = "🔴 暂不可用"

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
            # 真实期权持仓不得写入公开的 docs/data.json / index.html。
            # 登录用户改由浏览器在 Supabase RLS 保护下按需读取。
            "overview_charts": overview_charts, "options": [],
            "cn_hk": cn_hk_data, "market_regime": market_regime, "historical_signals": historical_signals, "data_status": data_status,
            "raw_breadth": breadth_data, "market_indicators": {"spx": spx_data, "spx_source": spx_src, "ixic": ixic_data, "ixic_source": ixic_src, "vix": vix_data, "vix_source": vix_src},
            "tqqq_x2": tqqq_x2, "leaps_radar": leaps_radar, "opportunity_history": opportunity_history}

# ================= 8. 前端 HTML 组件独立渲染函数 =================
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
    tiers = r.get("tiers") or CORE_TIERS.get(name) or {}
    if r.get("ath_is_true"):
        dd, label, dist_text = r.get("strategy_drawdown"), "回撤 (ATH)", get_dist_text(r.get("strategy_drawdown"), tiers)
        if r.get("ath_validation") == "CHECK": status_text, hit_cls = "⚠ 极端回撤 · 请验证数据", "warn"
        else: status_text = f'{r.get("level_label") if level > 0 else "未触发"} <span style="opacity:0.85">{dist_text}</span>'
    else:
        dd, label, status_text = r.get("window_drawdown"), "窗口回撤", "ATH 暂不可用 · 仅供参考"
    close = r.get("close")
    formal_signal = bool(r.get("ath_is_true") and r.get("ath_validation") != "CHECK")
    ath = close / (1 + dd) if formal_signal and isinstance(close, (int, float)) and isinstance(dd, (int, float)) and dd > -1 else None
    tier_values = [tiers.get("t1"), tiers.get("t2"), tiers.get("t3")]
    next_index = min(level, 2)
    next_tier = tier_values[next_index] if tier_values else None
    trigger = ath * (1 - next_tier) if ath and isinstance(next_tier, (int, float)) else None
    price_gap = trigger / close - 1 if trigger and close else None
    trigger_label = "最高档状态" if level >= 3 else f"下一档 · {next_index + 1}级"
    reference = '<span class="engine-reference">同指数参考</span>' if name == "QQQ" else ''
    action_text = "仅观察：ATH尚未通过校验" if not formal_signal else ({0:"等待触发 · 不提前加仓",1:"一级已触发 · 进入第一档加仓区",2:"二级已触发 · 进入第二档加仓区",3:"三级已触发 · 极端回撤加仓区"}.get(level,"等待触发"))
    tier_cards = []
    for index, value in enumerate(tier_values, start=1):
        tier_price = ath * (1 - value) if ath and isinstance(value, (int, float)) else None
        tier_class = "reached" if level >= index else ("next" if formal_signal and level + 1 == index else "")
        tier_cards.append(f'<span class="strategy-tier {tier_class}"><small>{index}级回撤</small><b>{fmt_pct(value,1)}</b><em>{"$"+format(tier_price,".2f") if tier_price else "待校验"}</em></span>')
    if level >= 3 and formal_signal:
        trigger_value, trigger_note = "三级已触发", "已进入策略最高档加仓区"
    else:
        trigger_value = '$'+format(trigger,'.2f') if trigger else '待校验'
        trigger_note = '距当前 '+fmt_pct(price_gap) if isinstance(price_gap,(int,float)) else '仅供参考'
    return f'''<article class="engine-item {hit_cls}" data-signal-symbol="{name}" data-drawdown="{dd if isinstance(dd,(int,float)) else ''}" data-t1="{tiers.get('t1','')}" data-t2="{tiers.get('t2','')}" data-t3="{tiers.get('t3','')}"><div class="engine-item-head"><div class="k">{name} {label} {reference}</div><div class="engine-state">{status_text}</div></div><div class="engine-value-row"><div><small>当前回撤</small><div class="v">{fmt_pct(dd)}</div></div><span class="engine-action">{action_text}</span></div><div class="engine-trigger"><span>{trigger_label}</span><b>{trigger_value}</b><small>{trigger_note}</small></div><div class="strategy-tier-grid">{"".join(tier_cards)}</div></article>'''

def card_etf(name, r):
    disp_name = {"GCMAIN": "黄金连续期货 (GC=F)", "BTC/USD": "比特币 (BTC-USD)", "QQQ": "纳斯达克100 (QQQ)", "VOO": "标普500 (VOO)", "SMH": "半导体ETF (SMH)", "TQQQ": "纳指3倍做多 (TQQQ)"}.get(name, name)
    if "error" in r: return f'<div class="card err"><div class="sym">{disp_name}</div><div class="errmsg">获取失败: {r["error"]}</div></div>'
    drawdown, close, tiers = r.get("drawdown"), r.get("close"), r.get("tiers") or {}
    basis = "策略基准：历史ATH" if r.get("ath_is_true") else "参考基准：近2年窗口高点"
    high_label = "ATH" if r.get("ath_is_true") else "窗口高点"
    high = close / (1 + drawdown) if isinstance(close,(int,float)) and isinstance(drawdown,(int,float)) and drawdown > -1 else None
    formal_signal = bool(r.get("ath_is_true") and r.get("ath_validation") != "CHECK")
    level = r.get("level",0) or 0
    tier_values = [tiers.get("t1"),tiers.get("t2"),tiers.get("t3")]
    next_tier = tier_values[min(level,2)] if tiers else None
    trigger = high * (1-next_tier) if formal_signal and high and isinstance(next_tier,(int,float)) else None
    gap = trigger/close-1 if trigger and close else None
    if trigger:
        trigger_row = f'<div class="row trigger-row"><span>{"三级" if level>=3 else str(level+1)+"级"}触发价</span><span><b>${trigger:.2f}</b><small>距触发 {fmt_pct(gap)}</small></span></div>'
    elif tiers:
        trigger_row = '<div class="row"><span>策略信号</span><span class="muted-value">ATH未校验，不触发正式信号</span></div>'
    else:
        trigger_row = '<div class="row"><span>策略信号</span><span class="muted-value">不参与核心ETF加仓信号</span></div>'
    return f'''<div class="card asset-card"><div class="card-header"><span class="sym">{disp_name}</span><span class="price">${r["close"]:.2f}</span></div><div class="asset-basis">{basis}</div><div class="divider"></div><div class="row"><span>{high_label}</span><span class="fw-bold">${fmt_num(high)}</span></div><div class="row"><span>当前回撤</span><span class="{'neg-text fw-bold' if drawdown and drawdown<0 else 'fw-bold'}">{fmt_pct(drawdown)}</span></div>{trigger_row}<div class="row"><span>RSI / 距200MA</span><span class="fw-bold">{fmt_num(r["rsi"])} / {fmt_pct(r["dist_200ma"])}</span></div><div class="asset-date">收盘日线截至：{r.get("date","-")}</div></div>'''

def render_options_html(options_data):
    if not options_data: return '<tr><td colspan="9" style="text-align:center; color:var(--muted)">当前没有记录的期权持仓</td></tr>'
    html = ""
    for opt in options_data:
        opt_id, sym, opt_type, side, strike, expiry, cost, last_price, iv, delta, dte, curr_price, pnl, break_even = opt['id'], opt['symbol'], opt['opt_type'], opt['side'], opt['strike'], opt['expiry'], opt['cost'], opt['last_price'], opt['iv'], opt['delta'], opt['dte'], opt['curr_price'], opt['unrealized_pnl'], opt['break_even']
        
        total_cost_basis = cost * 100 * opt['qty']
        pnl_pct = (pnl / total_cost_basis) if total_cost_basis > 0 else 0.0
        dist_pct = ((curr_price - break_even) if opt_type.lower()=="call" else (break_even - curr_price)) / break_even * 100 if curr_price and break_even else 0
        
        pnl_cls = "pos-text" if pnl >= 0 else "neg-text"
        pnl_str = f"${pnl:+.2f}"
        pnl_pct_str = f"{pnl_pct:+.2%}"

        action_tip = ""
        if side.lower() == "short":
            if pnl_pct >= 0.80:
                action_tip = ' <span style="font-size:9.5px; background:var(--green); color:#fff; padding:1px 4px; border-radius:3px; font-weight:600;">达成80%止盈，可平仓</span>'
            elif pnl_pct >= 0.50:
                action_tip = ' <span style="font-size:9.5px; background:var(--green-soft); color:var(--green); padding:1px 4px; border-radius:3px; font-weight:600;">建议止盈</span>'

        side_color, side_bg = ("var(--green)", "var(--green-soft)") if side.lower() == "long" else ("var(--amber)", "var(--amber-soft)")

        html += f'''<tr id="opt-row-{opt_id}">
            <td style="text-align:left; font-weight:600; color:var(--ink)">
                {sym} <span style="font-size:10px; color:{side_color}; font-weight:600; background:{side_bg}; padding:2px 6px; border-radius:4px; margin-left:4px;">{side} {opt_type}</span>
            </td>
            <td class="fw-bold">${strike:.2f}</td>
            <td>{expiry} <span style="font-size:10px;color:var(--muted)">({dte}d)</span></td>
            <td>${cost:.2f}</td>
            <td class="fw-bold">${last_price:.2f}</td>
            <td class="{pnl_cls} fw-bold">{pnl_str}</td>
            <td class="{pnl_cls} fw-bold">{pnl_pct_str}{action_tip}</td>
            <td style="color:var(--navy); font-weight:600">${break_even:.2f}</td>
            <td class="fw-bold">${curr_price:.2f}</td>
            <td class="{pnl_cls}">{f"{dist_pct:+.2f}%" if curr_price else "-"}</td>
            <td style="font-size:11.5px;color:var(--muted)">{iv:.1%} / {f"{delta:+.3f}" if delta else "-"}</td>
            <td style="text-align:center;"><button class="manage-option-btn" onclick="OptionV2.openLifecycle('{opt_id}')" title="平仓或结算">管理</button></td>
        </tr>'''
    return html

def classify_stock_status(close, target=None, rsi=None, dist_200ma=None):
    """Return the single highest-priority decision state for a watchlist row."""
    if isinstance(target, (int, float)) and target > 0 and isinstance(close, (int, float)):
        if close <= target:
            return "triggered", "已触发"
        if close / target - 1 <= .05:
            return "near", "接近策略价"
    if isinstance(rsi, (int, float)) and rsi < 35:
        return "oversold", "超卖观察"
    if isinstance(dist_200ma, (int, float)) and dist_200ma < -.10:
        return "weak", "趋势偏弱"
    if (isinstance(rsi, (int, float)) and rsi > 70) or (isinstance(dist_200ma, (int, float)) and dist_200ma > .25):
        return "hot", "过热"
    return "normal", "正常观察"

def render_tqqq_x2(strategy):
    if not strategy.get("available"):
        return f'''<section class="opportunity-block" id="tqqqX2Module"><div class="opportunity-head"><div><span class="opportunity-kicker">TQQQ DAILY SCAN</span><h2>TQQQ X2 风险敞口</h2></div><span class="opportunity-badge unavailable">数据不足</span></div><div class="opportunity-empty">{strategy.get("error","等待完整收盘数据")}</div></section>'''
    s = strategy["snapshot"]
    target = strategy["target_position"]
    risk_level = "l3" if target == 0 else ("l2" if target == 33 else "l1")
    risk_attr = f' data-risk-todo="TQQQ X2：{strategy["action"]}" data-risk-level="{risk_level}"' if target < 67 else ""
    rule_labels = {
        "hard_exit": "硬退出", "tier2": "二级降险", "tier1": "一级降险",
        "full_restore": "完整恢复", "partial_restore": "部分恢复", "hold": "状态延续",
    }
    rows = "".join(f'''<tr><td>{row["date"]}</td><td>{row["target_position"]}%</td><td>{row["target_daily_exposure"]:.2f}x</td><td>{rule_labels.get(row["rule"],row["rule"])}</td><td>{row["vix"]:.2f}</td><td>{fmt_pct(row.get("vix_3d_change"))}</td></tr>''' for row in strategy.get("history", [])[-20:][::-1])
    checks = [
        ("一级降险", s.get("tier1"), "VIX三日涨幅>20%、VIX≥18、QQQ低于MA20"),
        ("二级降险", s.get("tier2"), "VIX三日涨幅>20%、VIX≥20、QQQ确认跌破MA50"),
        ("硬退出", s.get("hard_exit"), "VIX>26且低于MA50，或低于MA200且VIX>24"),
        ("超卖恢复", s.get("oversold_restore"), "RSI≤30、硬退出已解除且VIX≤26"),
        ("趋势恢复", s.get("trend_restore"), "连续两日站上上升MA20且VIX三日涨幅≤20%"),
    ]
    check_html = "".join(f'''<div class="strategy-check {'hit' if hit else ''}"><span>{'●' if hit else '○'}</span><div><b>{name}</b><small>{desc}</small></div></div>''' for name,hit,desc in checks)
    return f'''<section class="opportunity-block" id="tqqqX2Module"{risk_attr}>
      <div class="opportunity-head"><div><span class="opportunity-kicker">TQQQ DAILY SCAN · 收盘确认</span><h2>TQQQ X2 风险敞口</h2><p>目标X2表示约2倍日内敞口；当前记录为空仓。仅作次日行动提示，不纳入核心配置。</p></div><span class="opportunity-badge state-{target}">{strategy["status_label"]}</span></div>
      <div class="tqqq-decision-grid"><div class="tqqq-action"><span>建议目标</span><strong>{target}% TQQQ</strong><em>约 {strategy["target_daily_exposure"]:.2f}x 日内敞口</em></div><div class="tqqq-action secondary"><span>当前记录</span><strong>{strategy["recorded_position"]}% · 空仓</strong><em>不推导差额、金额或交易数量</em></div><div class="tqqq-action emphasis"><span>收盘动作</span><strong>{strategy["action"]}</strong><em>规则：{rule_labels.get(strategy["rule"],strategy["rule"])}</em></div></div>
      <div class="strategy-metrics"><div><span>QQQ</span><b>${s["qqq"]:.2f}</b></div><div><span>MA20 / MA50</span><b>{s["ma20"]:.2f} / {s["ma50"]:.2f}</b></div><div><span>MA200</span><b>{s["ma200"]:.2f}</b></div><div><span>RSI(14)</span><b>{s["rsi14"]:.1f}</b></div><div><span>VIX</span><b>{s["vix"]:.2f}</b></div><div><span>VIX三日变化</span><b>{fmt_pct(s.get("vix_3d_change"))}</b></div></div>
      <div class="strategy-checks">{check_html}</div>
      <div class="opportunity-foot"><span>市场日线：{strategy["date"]}</span><span>{strategy["note"]}</span></div>
      <details class="opportunity-history"><summary>查看最近20个交易日状态记录</summary><div class="table-container"><table><thead><tr><th>日期</th><th>TQQQ目标</th><th>日内敞口</th><th>生效规则</th><th>VIX</th><th>VIX三日</th></tr></thead><tbody>{rows}</tbody></table></div></details>
    </section>'''

def render_leaps_radar(radar):
    cards = []
    for row in radar.get("assets", []):
        if not row.get("available"):
            cards.append(f'''<article class="leaps-card unavailable"><div class="leaps-title"><b>{row.get("symbol","-")}</b><span>数据不足</span></div><p>{row.get("error","等待日线")}</p></article>''')
            continue
        risk_attr = f' data-risk-todo="{row["symbol"]} LEAPS：{row["status_label"]}" data-risk-level="{row["risk_level"]}"' if row["status"] in ("candidate","strong") else ""
        trend = "200MA上升" if row.get("ma200_rising") else "200MA未上升"
        caution = "趋势/波动门槛需谨慎" if row.get("trend_risk") or row.get("vix_risk") else "未触发额外风险拦截"
        cards.append(f'''<article class="leaps-card status-{row["status"]}"{risk_attr}><div class="leaps-title"><div><b>{row["symbol"]}</b><small>收盘日线 {row["date"]}</small></div><span>{row["status_label"]}</span></div><div class="leaps-price">${row["close"]:.2f}</div><div class="leaps-grid"><div><span>RSI(14)</span><b>{row["rsi14"]:.1f}</b></div><div><span>63日高点回撤</span><b>{fmt_pct(row["drawdown63"])}</b></div><div><span>距200MA</span><b>{fmt_pct(row["dist_200ma"])}</b></div><div><span>趋势状态</span><b>{trend}</b></div></div><p class="leaps-caution">{caution}</p><button type="button" class="leaps-load" data-leaps-symbol="{row["symbol"]}">查看候选合约</button></article>''')
    return f'''<section class="opportunity-block" id="leapsRadarModule">
      <div class="opportunity-head"><div><span class="opportunity-kicker">LEAPS CALL OPPORTUNITY</span><h2>LEAPS Call 机会雷达</h2><p>QQQ、SMH、VGT 按完整收盘日线筛选；提醒机会，不代表立即买入。</p></div><div class="leaps-risk-cap"><b>单次≤1%</b><span>全部LEAPS合计≤3%</span><small>仅显示风险上限，不计算金额</small></div></div>
      <div class="leaps-cards">{"".join(cards)}</div>
      <div class="leaps-rule-note"><span>观察：RSI≤40 或 63日回撤≥5%</span><span>候选：RSI≤35 且回撤≥8%</span><span>强候选：RSI连续两日≤30 且回撤≥10%</span></div>
      <div id="leapsContractPanel" class="leaps-contract-panel" hidden><div class="leaps-contract-head"><div><span class="opportunity-kicker">INDICATIVE OPTION CHAIN</span><h3 id="leapsContractTitle">候选合约</h3></div><div class="leaps-contract-controls"><label>筛选方式<select id="leapsMode"><option value="growth">成长型：Delta 0.50–0.60</option><option value="replacement">替代正股：Delta 0.70–0.85</option></select></label><label>到期日<select id="leapsExpiry"></select></label><button type="button" id="leapsReload">刷新</button></div></div><div id="leapsContractStatus" class="leaps-contract-status">请选择上方资产。</div><div class="table-container"><table><thead><tr><th>到期日 / DTE</th><th>行权价</th><th>Bid / Ask</th><th>中间价</th><th>Delta</th><th>IV</th><th>价差质量</th></tr></thead><tbody id="leapsContractBody"><tr><td colspan="7">等待选择</td></tr></tbody></table></div><p class="leaps-disclaimer">Alpaca Indicative 仅作免费参考；下单前必须以 IBKR Bid/Ask、合约乘数及流动性为准。本模块不生成投入金额、合约数量或下单指令。</p></div>
      <details class="leaps-method"><summary>查看合约筛选与风险纪律</summary><div><p><b>成长型：</b>DTE 365–900天，Delta 0.50–0.60。</p><p><b>替代正股：</b>DTE 540–900天，Delta 0.70–0.85。</p><p>优先有效Bid/Ask且相对价差≤10%；超过15%不进入候选。低于下降中的200MA、VIX≥30或报价陈旧时保留“高风险”提示。</p></div></details>
    </section>'''

def render_opportunity_history(history):
    labels = {"TQQQ_X2": "TQQQ X2", "LEAPS": "LEAPS机会"}
    rows = "".join(f'''<tr><td>{item.get("date","-")}</td><td>{labels.get(item.get("kind"),item.get("kind","-"))}</td><td>{item.get("symbol","-")}</td><td><span class="opportunity-history-level {item.get("level","l1")}">{item.get("level","l1").upper()}</span></td><td>{item.get("label","-")}</td></tr>''' for item in (history or [])[:40])
    if not rows:
        rows = '<tr><td colspan="5">尚无达到记录条件的收盘信号</td></tr>'
    return f'''<section class="opportunity-block opportunity-ledger"><details><summary>策略机会历史（最近40条）</summary><div class="table-container"><table><thead><tr><th>日期</th><th>模块</th><th>标的</th><th>级别</th><th>收盘结论</th></tr></thead><tbody>{rows}</tbody></table></div></details></section>'''

def render_html(data):
    engine_order = ["QQQM", "VGT", "QLD", "VOO", "TQQQ", "QQQ"]
    engine_html = "".join(engine_item(k, data["core"].get(k, {"error":"无数据"})) for k in engine_order)
    max_level = max([v.get("level", 0) for v in data["core"].values() if "error" not in v] or [0])
    level_names = {0: "正常 · 未触发", 1: "一级加仓线", 2: "二级加仓线", 3: "三级加仓线"}
    engine_badge_cls = "normal" if max_level == 0 else "t2"
    tqqq_x2_html = render_tqqq_x2(data.get("tqqq_x2") or {})
    leaps_radar_html = render_leaps_radar(data.get("leaps_radar") or {})
    opportunity_history_html = render_opportunity_history(data.get("opportunity_history") or [])
    
    def asset_group(title, subtitle, symbols):
        cards = "".join(card_etf(k, data["index"][k]) for k in symbols if k in data["index"])
        return f'<div class="asset-group"><div class="section-head compact"><h2>{title}</h2><p>{subtitle}</p></div><div class="grid">{cards}</div></div>'
    index_html = "".join([
        asset_group("核心指数", "长期趋势与正式策略触发", ["QQQ","VOO"]),
        asset_group("卫星及杠杆", "行业卫星仓与高波动工具", ["SMH","TQQQ"]),
        asset_group("另类资产", "黄金与比特币使用近2年窗口回撤，仅供参考", ["GCMAIN","BTC/USD"]),
    ])
    
    stock_html = ""
    for sym, v in data["stocks"].items():
        if "error" not in v:
            name = STOCK_META.get(sym, {}).get("name", sym)
            target = STOCK_META.get(sym, {}).get("target")
            chg, close, ytd_high, rsi, dist = v.get("day_chg") or 0, v["close"], v.get("ytd_high"), v.get("rsi"), v.get("dist_200ma")
            ytd_dd = close/ytd_high-1 if ytd_high else None
            target_distance = target/close-1 if target and close else None
            status, status_label = classify_stock_status(close, target, rsi, dist)
            if target:
                target_gap_text = f'低于策略价 {fmt_pct(close/target-1)}' if close <= target else f'还需下跌 {fmt_pct(abs(target_distance))}'
            else: target_gap_text = "等待策略数据"
            target_display = f"${target:.2f}" if isinstance(target,(int,float)) else "—"
            stock_html += f'''<tr data-stock-row data-status="{status}" data-target-distance="{abs(target_distance) if isinstance(target_distance,(int,float)) else 999}" data-drawdown="{abs(ytd_dd) if isinstance(ytd_dd,(int,float)) else 0}" data-rsi="{rsi if isinstance(rsi,(int,float)) else 999}" data-dist200="{dist if isinstance(dist,(int,float)) else 0}"><td class="stock-identity"><div class="stock-name">{name}</div><div class="stock-symbol">{sym}</div><details class="stock-details"><summary>行情详情</summary><div>开 ${v.get("open",0):.2f} · 高 ${v.get("high",0):.2f} · 低 ${v.get("low",0):.2f}<br>YTD高点 ${fmt_num(ytd_high)} · 日线截至 {v.get("date","-")}</div></details></td><td data-label="最新价 / 涨跌"><b id="close-{sym}">${close:.2f}</b><small id="chg-{sym}" class="{'pos-text' if chg>=0 else 'neg-text'}">{chg*100:+.2f}%</small></td><td data-label="YTD回撤" class="neg-text fw-bold">{fmt_pct(ytd_dd)}</td><td data-label="RSI">{fmt_num(rsi)}</td><td data-label="距200MA" class="{'neg-text' if isinstance(dist,(int,float)) and dist<0 else ''}">{fmt_pct(dist)}</td><td data-label="策略价 / 距离" id="target-cell-{sym}"><b id="target-{sym}">{target_display}</b><small id="target-gap-{sym}">{target_gap_text}</small></td><td data-label="状态"><span id="stock-status-{sym}" class="stock-status {status}">{status_label}</span><span id="action-{sym}"></span></td></tr>'''
            
    options_html = '<tr><td colspan="9" style="text-align:center; color:var(--muted)">请登录后查看私有期权持仓</td></tr>'

    signals_html = ""
    for s in data.get("historical_signals", []):
        badge_cls = "warn" if "一级" in s.get('rating', '') else ("bad" if "重点" in s.get('rating', '') or "极限" in s.get('rating', '') else "neutral")
        signals_html += f'''<tr><td style="text-align:left; font-weight:600;">{s.get('symbol', '')}</td><td>{s.get('date', '')}</td><td class="fw-bold">${s.get('price', 0):.4f}</td><td class="neg-text">{fmt_pct(s.get('drawdown'))}</td><td><span class="badge {badge_cls}">{s.get('rating', '')}</span></td><td><span class="badge {'neutral' if s.get("source") == "资产自身三档线" else 'good'}">{s.get('source','-')}</span></td></tr>'''

    mr = data.get("market_regime", {"error": "无数据"})
    if "error" in mr:
        market_regime_html = f'<div class="card err"><div class="sym">市场状态引擎</div><div class="errmsg">{mr["error"]}</div></div>'
    else:
        incomplete_badge = '<span class="badge neutral" style="margin-left:6px">数据不完整</span>' if mr["max_available_score"] < mr["max_score"] else ""
        tier_badge_cls = {"normal": "good", "tier1": "warn", "major": "warn", "extreme": "bad"}.get(mr["tier"], "neutral")
        dd_hit_badge = '<span class="badge bad">命中 2分</span>' if mr["drawdown"]["hit"] else '<span class="badge neutral">未触发</span>'
        condition_rows = []
        for c in mr.get("conditions", []):
            cond_badge = f'<span class="badge bad">命中 {c["points"]}分</span>' if c["hit"] else '<span class="badge neutral">未触发</span>'
            condition_rows.append(f'<div class="row"><span>{c["key"]}（阈值 {c["threshold_note"]}）</span><span class="fw-bold">{fmt_pct(c["val"])} {cond_badge}</span></div>')
        condition_rows_html = "".join(condition_rows)
        breadth_notice = ""
        if not mr.get("conditions"):
            breadth_is_skip = mr.get("breadth_status") == "skip"
            breadth_color = "muted" if breadth_is_skip else "red"
            breadth_icon = "ℹ️" if breadth_is_skip else "⚠️"
            breadth_action = "暂未触发" if breadth_is_skip else "以指数回撤独立打分"
            breadth_notice = f'<div class="errmsg" style="padding:0 19px 16px;color:var(--{breadth_color});font-size:11px">{breadth_icon} {mr.get("breadth_message", "")}，当前{breadth_action}。</div>'
        market_regime_html = f'''<div class="panel"><div class="panel-head"><strong>市场状态引擎</strong><span>有效评分 {mr["score"]}/{mr["max_available_score"]} 分（满分体系 {mr["max_score"]} 分）</span></div><div class="pulse-list"><div class="pulse"><div><div class="pulse-label">当前风控评级</div><div class="pulse-main">{mr["tier_label"]}{incomplete_badge}</div></div><div class="pulse-right"><span class="badge {tier_badge_cls}">{mr["score"]}/{mr["max_available_score"]} 可用分</span></div></div><div class="row"><span>指数历史高点回撤（阈值 {fmt_pct(mr["drawdown"]["threshold"])}）</span><span class="fw-bold">{fmt_pct(mr["drawdown"]["value"])} {dd_hit_badge}</span></div>{condition_rows_html}</div>{breadth_notice}</div>''' 

    breadth = data.get("raw_breadth") or {}
    if breadth.get("status") == "ok":
        divergence = mr.get("divergence", {"level":"l1", "label":"未触发宽度顶背离"}) if "error" not in mr else {"level":"unknown", "label":"等待指数数据"}
        breadth_summary_html = f'''<section class="section protected-section"><div class="section-head"><h2>标普500市场宽度</h2><p>完整收盘日线 · {breadth.get('date','—')} · 覆盖 {breadth.get('coverage',breadth.get('symbols','—'))}/{breadth.get('universe',503)} ({fmt_pct(breadth.get('coverage_pct'))})</p></div><div class="breadth-grid"><div class="breadth-card"><span>站上20日线</span><strong>{fmt_pct(breadth.get('b20'))}</strong></div><div class="breadth-card"><span>站上50日线</span><strong>{fmt_pct(breadth.get('b50'))}</strong></div><div class="breadth-card"><span>站上200日线</span><strong>{fmt_pct(breadth.get('b200'))}</strong></div><div class="breadth-card"><span>20日宽度10日斜率</span><strong>{fmt_pct(breadth.get('slope_10d'))}</strong></div></div><div class="risk-alert {divergence.get('level','unknown')}"><span class="risk-level">{divergence.get('level','unknown').upper()}</span><div><strong>{divergence.get('label','等待判断')}</strong><p>此背离提示与恐慌加仓评分相互独立；L2/L3 时优先检查 QLD/TQQQ、新增杠杆和裸卖期权风险。</p></div></div></section>'''
    else:
        breadth_summary_html = f'''<section class="section protected-section"><div class="risk-alert unknown"><span class="risk-level">—</span><div><strong>市场宽度暂不可用于决策</strong><p>{breadth.get('message','等待首次满足质量门槛的完整收盘数据')}。系统不会用残缺样本参与9分制评分。</p></div></div></section>'''

    def clean_status(value):
        text = str(value or "等待数据")
        return text.removeprefix("🟢 ").removeprefix("🟡 ").removeprefix("🔴 ")

    def status_tone(value):
        text = str(value or "")
        return "bad" if text.startswith("🔴") else ("warn" if text.startswith("🟡") else "good")

    def status_item(label, value, meta, element_id="", tone=None):
        item_tone = tone or status_tone(value)
        id_attr = f' id="{element_id}"' if element_id else ""
        return f'''<div class="status-item" data-tone="{item_tone}"><span class="status-dot" aria-hidden="true"></span><div class="status-copy"><div class="status-label">{label}</div><div class="status-value"{id_attr}>{clean_status(value)}</div><div class="status-meta">{meta}</div></div></div>'''

    breadth_state = breadth_freshness(breadth)
    status_center_html = "".join([
        status_item("VIX 恐慌指数", data["data_status"].get("VIX"), "盘中5分钟 · 盘前盘后30分钟 · 周末停止轮询", "usLiveVixStatus"),
        status_item("美股宽基指数", data["data_status"].get("US Market"), "盘中5分钟 · 节假日2小时 · 涨跌基于昨收", "usLiveIndexStatus"),
        status_item("标普500市场宽度", breadth_state["label"], breadth_state["meta"], tone=breadth_state["tone"]),
        status_item("亚太市场行情", data["data_status"].get("CN_HK"), "A股与港股交易时段动态刷新"),
        status_item("云端策略配置", data["data_status"].get("Supabase"), "策略价、观察池与账户配置"),
    ])

    mi = data.get("market_indicators", {})
    cn = data.get("cn_hk", {})
    spy, qqq, vol = mi.get("spx", {}), mi.get("ixic", {}), mi.get("vix", {})
    src_label = lambda s: "真实指数(Yahoo)" if s == "yahoo_real" else "ETF代理"

    vol_value = vol.get("close") if "error" not in vol else None
    vol_tone = "neutral"
    if isinstance(vol_value, (int, float)):
        if vol_value < 15: vol_tone = "good"
        elif vol_value < 25: vol_tone = "good"
        elif vol_value < 35: vol_tone = "warn"
        else: vol_tone = "bad"
        
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

    def metric_card(label, value, change=None, note="", tone="neutral", live_code=None, us_live_code=None):
        price_attr = f' data-us-live-price="{us_live_code}"' if us_live_code else (f' data-live-price="{live_code}"' if live_code else "")
        change_attr = f' data-us-live-chg="{us_live_code}"' if us_live_code else f' data-live-chg="{live_code or ""}"'
        change_html = f'<div class="metric-change {"positive" if change>=0 else "negative"}"{change_attr}>{"+" if change>=0 else ""}{fmt_pct(change)}</div>' if isinstance(change, (int, float)) else (f'<div class="metric-change"{change_attr}>—</div>' if us_live_code else "")
        note_attr = f' data-us-live-note="{us_live_code}"' if us_live_code else ""
        return f'''<div class="metric-card"><div class="metric-top">{label}<span class="metric-dot {tone}"></span></div><div class="metric-value"{price_attr}>{value}</div>{change_html}<div class="metric-note"{note_attr}>{note}</div></div>'''

    def vix_gauge_card(value, change=None, note=""):
        numeric = float(value) if isinstance(value, (int, float)) else None
        angle = -90 + min(max(numeric or 0, 0), 40) / 40 * 180
        if numeric is None: zone, zone_color = "等待数据", "#8d93a1"
        elif numeric < 15: zone, zone_color = "平静区", "#1f9d63"
        elif numeric < 20: zone, zone_color = "温和波动", "#91b63c"
        elif numeric < 25: zone, zone_color = "警戒区", "#e2a62b"
        elif numeric < 30: zone, zone_color = "高风险", "#db7131"
        else: zone, zone_color = "极端恐慌", "#bd3f35"
        change_html = f'<span class="vix-change {"positive" if change>=0 else "negative"}" data-us-live-chg="vix">{"+" if change>=0 else ""}{fmt_pct(change)}</span>' if isinstance(change, (int, float)) else '<span class="vix-change" data-us-live-chg="vix">—</span>'
        return f'''<div class="metric-card vix-metric-card" data-vix-card><div class="metric-top">VIX恐慌指数<span class="metric-dot" data-vix-dot style="background:{zone_color}"></span></div><div class="vix-gauge" data-vix-gauge style="--vix-angle:{angle:.2f}deg"><svg viewBox="0 0 200 108" role="img" aria-label="VIX风险分区半圆仪表盘"><path class="vix-arc calm" d="M18 100 A82 82 0 0 1 68.6 24.2"/><path class="vix-arc mild" d="M68.6 24.2 A82 82 0 0 1 100 18"/><path class="vix-arc caution" d="M100 18 A82 82 0 0 1 131.4 24.2"/><path class="vix-arc high" d="M131.4 24.2 A82 82 0 0 1 158 42"/><path class="vix-arc extreme" d="M158 42 A82 82 0 0 1 182 100"/></svg><span class="vix-needle"></span><span class="vix-hub"></span></div><div class="vix-reading"><strong data-us-live-price="vix">{fmt_num(numeric) if numeric is not None else "—"}</strong>{change_html}<span class="vix-zone" data-vix-zone style="color:{zone_color}">{zone}</span></div><div class="vix-band-legend" aria-label="VIX风险区间"><span class="calm">&lt;15</span><span class="mild">15–20</span><span class="caution">20–25</span><span class="high">25–30</span><span class="extreme">≥30</span></div><div class="metric-note" data-us-live-note="vix">{note}</div></div>'''

    def mkt_card_a(title, mdata, code="", proxy=False, buy_below=None):
        if not mdata or "error" in mdata: return f'<div class="mkt-card"><div class="name">{title}</div><div class="val" style="font-size:14px;color:var(--muted);margin-top:12px">接口拦截/闭市</div></div>'
        decimals = 2 if code.startswith('sh') else 3
        proxy_badge = '<span class="proxy-badge">指数代理</span>' if proxy else ''
        price = float(mdata.get("price", 0) or 0)
        buy_html = ''
        if isinstance(buy_below, (int,float)):
            triggered = price <= buy_below
            buy_html = f'<div class="buy-zone {"triggered" if triggered else ""}" data-buy-zone="{code}" data-threshold="{buy_below:.3f}"><span>加仓区 ≤ {buy_below:.3f}（含）</span><strong>{"已进入加仓区" if triggered else f"距加仓区 {price-buy_below:.3f}"}</strong></div>'
        return f'''<div class="mkt-card hover-card" onclick="toggleMktChart('{code}', '{title}')"><div class="name"><span>{title} {proxy_badge}</span><span class="chart-hint">30日趋势</span></div><div class="mkt-quote"><div class="val" data-live-price="{code}">{price:,.{decimals}f}</div><div class="chg {"positive" if mdata.get("day_chg",0)>=0 else "negative"}" data-live-chg="{code}">{"+" if mdata.get("day_chg",0)>=0 else ""}{fmt_pct(mdata.get("day_chg",0))}</div></div>{buy_html}<div class="mkt-meta"><span data-market-state="{code}">腾讯行情 · 状态检查中</span><span data-live-time="{code}">页面生成 {data.get("gen_time","-")}</span></div><div class="mkt-chart-wrap" id="wrap-{code}"><div style="height:140px; position:relative; width:100%;"><canvas id="canvas-{code}"></canvas></div></div></div>'''

    chart_json = json.dumps(data.get("overview_charts", {}), ensure_ascii=False)

    return f'''<!DOCTYPE html><html lang="zh-CN"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"><title>myAlphaView · Market Intelligence</title>
<meta name="author" content="Simon"><meta name="application-version" content="{APP_VERSION}"><meta name="robots" content="noindex,nofollow,noarchive,nosnippet"><meta name="referrer" content="no-referrer"><link href="https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,380;9..144,520;9..144,620&family=Inter:wght@400;500;600;700;800&display=swap" rel="stylesheet"><link href="assets/options-v2.css?v={ASSET_VERSION}" rel="stylesheet"><link href="assets/roll-manager.css?v={ASSET_VERSION}" rel="stylesheet"><link href="assets/finance-tools.css?v={ASSET_VERSION}" rel="stylesheet"><link href="assets/opportunity-radar.css?v={ASSET_VERSION}" rel="stylesheet"><script src="https://cdn.jsdelivr.net/npm/chart.js@4"></script><script src="https://cdn.jsdelivr.net/npm/@supabase/supabase-js@2"></script>
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
.compact-hero{{margin-bottom:18px;align-items:center}}.compact-hero h1{{font-size:30px}}.compact-hero p{{margin-top:7px}}.overview-hero{{align-items:center;margin-bottom:18px;padding:14px 16px;background:var(--surface);border:1px solid var(--line);border-radius:12px;box-shadow:var(--shadow)}}.overview-hero h1{{font-size:25px}}.overview-hero p{{margin-top:5px;font-size:11.5px}}.overview-hero .public-note{{padding:9px 12px;flex-basis:240px;box-shadow:none}}.data-legend{{display:flex;flex-wrap:wrap;gap:6px;margin-top:8px}}.data-legend span{{padding:3px 7px;border-radius:99px;background:var(--surface2);color:var(--muted);font-size:9px}}.data-legend .live{{color:var(--green);background:var(--green-soft)}}.data-legend .close{{color:var(--navy)}}.data-legend .missing{{color:var(--red);background:var(--red-soft)}}.engine-asof{{font-size:10.5px;color:var(--navmuted);margin-top:6px}}.engine-grid{{grid-template-columns:repeat(3,minmax(0,1fr))}}.engine-item{{padding:15px;min-width:0}}.engine-item-head{{display:flex;justify-content:space-between;gap:8px;align-items:flex-start}}.engine-state{{font-size:9.5px;color:var(--brass-soft);text-align:right}}.engine-reference{{display:inline-block;padding:2px 5px;border-radius:99px;background:rgba(255,255,255,.08);font-size:8px}}.engine-trigger{{display:grid;grid-template-columns:1fr auto;gap:2px 8px;margin-top:9px;padding:8px;border-radius:8px;background:rgba(255,255,255,.05);font-size:10px;color:var(--navmuted)}}.engine-trigger b{{color:#fff;font-size:12px}}.engine-trigger small{{grid-column:1/-1;color:var(--brass-soft)}}.engine-budget-label{{display:block;font-size:9.5px;color:var(--navmuted);margin-top:10px}}.engine .budget-input{{background:rgba(255,255,255,.08);border-color:rgba(255,255,255,.13);color:#fff;padding:7px 8px}}.engine .budget-allocation{{margin-top:7px}}.engine .budget-allocation span{{background:rgba(255,255,255,.05);color:var(--navmuted);padding:6px}}.engine .budget-allocation b{{color:#fff}}.engine .budget-next{{color:var(--brass-soft);border-color:rgba(255,255,255,.1);margin-top:7px;padding-top:7px}}.asset-groups{{display:grid;gap:24px}}.asset-group .grid{{grid-template-columns:repeat(2,minmax(0,1fr))}}.section-head.compact{{margin-bottom:10px}}.asset-basis{{font-size:10px;color:var(--brass);margin-top:6px}}.asset-date{{font-size:9px;color:var(--muted);border-top:1px solid var(--line);padding-top:8px;margin-top:10px}}.trigger-row>span:last-child{{display:grid;justify-items:end}}.trigger-row small{{font-size:9px;color:var(--brass)}}.muted-value{{color:var(--muted);font-size:10px;white-space:normal;text-align:right;max-width:190px}}.mkt-card{{padding:14px 16px}}.mkt-quote{{display:flex;justify-content:space-between;align-items:flex-end;margin-top:7px}}.mkt-card .val{{margin-top:0;font-size:20px}}.mkt-card .chg{{margin:0}}.mkt-meta{{display:flex;justify-content:space-between;gap:10px;margin-top:9px;padding-top:8px;border-top:1px solid var(--line);font-size:9px;color:var(--muted)}}.proxy-badge{{display:inline-block;margin-left:5px;padding:2px 5px;border-radius:99px;background:var(--amber-soft);color:var(--amber);font-size:8px;font-weight:700}}.stock-toolbar{{display:flex;justify-content:space-between;gap:12px;align-items:center;margin-bottom:10px}}.stock-filters{{display:flex;flex-wrap:wrap;gap:6px}}.stock-toolbar button,.stock-toolbar select{{border:1px solid var(--line);background:var(--surface);color:var(--muted);padding:7px 10px;border-radius:99px;font-size:10.5px;cursor:pointer}}.stock-toolbar button.active{{background:var(--navy);border-color:var(--navy);color:#fff}}.stock-toolbar select{{border-radius:7px}}.stock-name{{font-weight:700;font-size:12.5px}}.stock-symbol{{font-size:10px;color:var(--muted);margin-top:2px}}.stock-table thead th{{position:sticky;top:0;z-index:2}}.stock-table td small{{display:block;font-size:9.5px;margin-top:3px}}.stock-status{{display:inline-block;padding:4px 7px;border-radius:99px;font-size:9.5px;font-weight:700;background:var(--surface2);color:var(--muted)}}.stock-status.triggered{{background:var(--red-soft);color:var(--red)}}.stock-status.near,.stock-status.oversold{{background:var(--amber-soft);color:var(--amber)}}.stock-status.hot{{background:var(--red-soft);color:var(--red)}}.stock-status.weak{{background:rgba(70,90,130,.12);color:#52678f}}.stock-details{{margin-top:5px}}.stock-details summary{{cursor:pointer;color:var(--brass);font-size:9px;list-style:none}}.stock-details summary::-webkit-details-marker{{display:none}}.stock-details div{{margin-top:6px;text-align:left;font-size:9.5px;line-height:1.7;color:var(--muted)}}
.engine-action{{margin-top:7px;font-size:10px;font-weight:700;color:#fff}}
.footer{{color:#9a9484;font-size:10.5px;line-height:1.7;text-align:center;padding:34px 0 10px}} .tab-pane{{display:none;animation:fade .3s ease}} .tab-pane.active{{display:block}} @keyframes fade{{from{{opacity:0;transform:translateY(5px)}}to{{opacity:1;transform:none}}}}
.opt-status {{ display:inline-flex; align-items:center; gap:5px; font-weight:600; font-size:11px; }} .opt-status.safe {{ color: var(--green); }} .opt-status.warn {{ color: var(--amber); }} .opt-status.danger {{ color: var(--red); }} .opt-status::before {{ content:""; display:block; width:6px; height:6px; border-radius:50%; }} .opt-status.safe::before {{ background: var(--green); }} .opt-status.warn::before {{ background: var(--amber); }} .opt-status.danger::before {{ background: var(--red); }}
@media (max-width: 1024px) {{ .dashboard-grid {{ grid-template-columns: 1fr; }} .metrics {{ grid-template-columns: repeat(2, 1fr); }} }}
@media (max-width: 1000px) {{.engine-grid{{grid-template-columns:repeat(2,minmax(0,1fr))}}}} @media (max-width: 768px) {{ .app {{ flex-direction: column; }} .sidebar {{ position: static; width: 100%; padding: 16px 20px; border-bottom: 1px solid var(--navline); }} .nav-group {{ margin-top: 16px; }} .nav-menu {{ display: flex; flex-wrap: wrap; gap: 8px; }} .nav-menu li {{ font-size: 12px; padding: 8px 12px; }} .main {{ margin-left: 0; width: 100%; }} .topbar {{ padding: 12px 20px; height: auto; flex-direction: column; align-items: flex-start; gap: 12px; }} .top-meta {{ flex-wrap: wrap; width: 100%; justify-content: space-between; }} .content {{ padding: 20px; }} .hero {{ flex-direction: column; align-items:flex-start;gap:10px}} .compact-hero h1{{font-size:26px}}.public-note {{ width: 100%; flex: auto; }} .metrics {{ grid-template-columns: 1fr; }} .engine{{padding:20px}}.engine::after {{ display: none; }} .engine-top {{ flex-direction: column; gap: 12px; }}.engine-grid,.asset-group .grid{{grid-template-columns:1fr}}.stock-toolbar{{align-items:flex-start;flex-direction:column}}.mkt-meta{{flex-direction:column;gap:3px}} .table-container {{ overflow-x: auto; -webkit-overflow-scrolling: touch; border-radius: 8px; }} th, td {{ padding: 10px; font-size: 12px; }} }}
@media (max-width: 680px) {{.stock-table{{overflow:visible;background:transparent;border:0;box-shadow:none}}.stock-table table,.stock-table tbody{{display:block}}.stock-table thead{{display:none}}.stock-table tr[data-stock-row]{{display:grid;grid-template-columns:1fr 1fr;background:var(--surface);border:1px solid var(--line);border-radius:12px;margin-bottom:10px;padding:12px;box-shadow:var(--shadow)}}.stock-table td{{display:flex;justify-content:space-between;gap:10px;align-items:center;border:0;padding:7px 5px;text-align:right!important;white-space:normal}}.stock-table td::before{{content:attr(data-label);font-size:9.5px;color:var(--muted);font-weight:500}}.stock-table td.stock-identity{{grid-column:1/-1;display:block;text-align:left!important;border-bottom:1px solid var(--line);padding-bottom:9px;margin-bottom:2px}}.stock-table td.stock-identity::before{{display:none}}.stock-table td[data-label="策略价 / 距离"],.stock-table td[data-label="状态"]{{grid-column:1/-1}}.stock-table td small{{margin-top:0}}}}
/* 沙盒特有样式 */
.sandbox-grid {{ display: grid; grid-template-columns: 300px 1fr; gap: 24px; }}
.sandbox-controls {{ background: var(--surface); padding: 20px; border-radius: 12px; border: 1px solid var(--line); box-shadow: var(--shadow); }}
.sandbox-controls label {{ display: block; font-size: 11.5px; color: var(--muted); margin-bottom: 6px; }}
.sandbox-controls input, .sandbox-controls select {{ width: 100%; padding: 10px; margin-bottom: 16px; border: 1px solid var(--line); border-radius: 6px; font-family: var(--sans); }}
.sandbox-btn {{ width: 100%; background: var(--navy); color: #fff; border: none; padding: 12px; border-radius: 6px; font-weight: 600; cursor: pointer; transition: 0.2s; }}
.sandbox-btn:hover {{ background: #121a36; }}
.sandbox-results {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; margin-bottom: 20px; }}
.s-res-card {{ background: var(--surface); border: 1px solid var(--line); border-radius: 8px; padding: 16px; text-align: center; }}
.s-res-label {{ font-size: 11px; color: var(--muted); }}
.s-res-val {{ font-family: var(--serif); font-size: 20px; font-weight: 600; margin-top: 6px; }}
@media (max-width: 800px) {{ .sandbox-grid {{ grid-template-columns: 1fr; }} }}
</style><link href="assets/dashboard-v2.2.css?v={ASSET_VERSION}" rel="stylesheet"></head><body class="auth-pending" data-app-version="{APP_VERSION}"><div class="app">

<aside class="sidebar"><div class="brand"><div class="mav-brand-mark"><svg width="20" height="20" viewBox="0 0 24 24" fill="none"><path d="M4 17 L9 9 L13 14 L20 5" stroke="#181109" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"/><circle cx="20" cy="5" r="2.1" fill="#181109"/></svg></div><div><strong>myAlphaView</strong><small>myAlphaView · myalphaview.com</small></div></div>
<div class="nav-group"><div class="nav-title">美股 · 宏观</div><ul class="nav-menu"><li class="active" onclick="switchTab('tab-overview',this)"><span class="nav-icon">◆</span>市场总览</li><li data-auth-required onclick="switchTab('tab-engine',this)"><span class="nav-icon">◒</span>策略引擎</li><li data-auth-required onclick="switchTab('tab-index',this)"><span class="nav-icon">◫</span>指数 & ETF</li></ul></div>
<div class="nav-group"><div class="nav-title">A股 · 港股 · 红利</div><ul class="nav-menu"><li data-auth-required onclick="switchTab('tab-cn-hk',this)"><span class="nav-icon">◇</span>大盘 & 红利低波</li></ul></div>
<div class="nav-group"><div class="nav-title">观察 & 持仓</div><ul class="nav-menu"><li data-auth-required onclick="switchTab('tab-stocks',this)"><span class="nav-icon">⌁</span>个股观察池</li><li data-auth-required onclick="switchTab('tab-options',this)"><span class="nav-icon">⚑</span>期权持仓监控</li><li data-auth-required onclick="switchTab('tab-archive',this)"><span class="nav-icon">📜</span>历史买点归档</li></ul></div>
<div class="nav-group"><div class="nav-title">规划 & 工具</div><ul class="nav-menu"><li data-auth-required onclick="switchTab('tab-finance-tools',this)"><span class="nav-icon">◎</span>理财工具</li><li data-auth-required onclick="switchTab('tab-sandbox',this)"><span class="nav-icon">🧮</span>策略推演沙盒</li></ul></div>
<div class="sidebar-footer">主理人私有看板 · 敏感持仓由 Supabase RLS 保护<br>未登录仅提供市场概览预览</div></aside>

<main class="main"><header class="topbar"><div class="breadcrumb">myAlphaView / <strong id="bc-title">市场总览</strong></div>
<div class="top-meta"><span id="liveStatus" style="display:none;"><i class="live-dot"></i><span id="liveStatusText">数据抓取成功</span></span><div style="text-align:right; line-height:1.4;"><div style="font-weight:600; font-size:12px; color:var(--ink);">生成时间: {data.get('gen_time', '-')}</div><div id="usLiveAsOf" style="color:var(--muted); font-size:10.5px;">美股收盘日线截至: {data.get('spy_date', '-')} | A/港股盘中动态刷新</div></div><button id="themeToggle" class="theme-toggle" title="切换深浅主题">🌙 深色</button><button id="authBtn" class="auth-btn-top" onclick="handleAuth()">🔐 登录私有看板</button></div></header><div class="content">

<div id="tab-overview" class="tab-pane active">
<section class="hero overview-hero"><div><h1>市场与风险驾驶舱</h1><p>先看市场状态、策略距离和必须处理的风险，再决定是否行动。</p><div class="data-legend" aria-label="数据状态说明"><span class="live">盘中延迟行情</span><span class="close">最近有效收盘</span><span class="missing">不可用不计分</span></div></div><div class="public-note" id="modePanel"><b id="modeTitle">访客预览模式</b><span id="modeDesc">未登录仅显示市场概览；策略、观察池与持仓模块需要主理人登录。</span></div><button id="privateModeShield" class="private-mode-shield" type="button" title="私有控制台已连接，真实持仓受 Supabase RLS 保护">🛡️ 私有模式</button></section>
<section class="section"><div class="section-head"><h2>市场核心指标</h2><p>美股盘中5分钟刷新；宽度每日收盘更新</p></div><div class="metrics">{metric_card('纳斯达克综合指数',qqq_value,qqq_chg,qqq_note,'good' if isinstance(qqq_chg,(int,float)) and qqq_chg>=0 else 'warn',us_live_code='ixic')}{metric_card('标普500指数',spy_value,spy_chg,spy_note,'good' if isinstance(spy_chg,(int,float)) and spy_chg>=0 else 'warn',us_live_code='spx')}{vix_gauge_card(vol_value,None,vix_note)}{metric_card('红利低波100 (159307)',sz_val,sz_chg,'A股红利代理 · ≤0.995（含）进入加仓区','good',live_code='sz159307')}</div></section>
<section class="public-access-gate"><div><span class="access-lock">🔐</span><strong>其余模块仅限主理人登录后浏览</strong><p>包括策略信号、市场宽度、个股观察、期权持仓、推演与历史记录。</p></div><button type="button" onclick="handleAuth()">登录解锁</button></section>
<section class="section private-console"><div class="panel risk-todo"><div class="panel-head"><strong>今日风险待办</strong><span>只列需要人工确认的事项</span></div><div id="riskTodoList" class="risk-todo-list"><div class="risk-todo-empty">正在检查临期期权、缺失报价、宏观事件与宽度背离…</div></div></div></section>
<section class="section protected-section">{market_regime_html}</section>
{breadth_summary_html}
<section class="section protected-section"><div class="section-head"><h2>QQQ & SPY · 近 30 个交易日</h2><p>收盘趋势与数据健康状态</p></div><div class="dashboard-grid"><div class="panel"><div class="panel-head"><strong>趋势对比</strong><span>最近30个交易日收盘价</span></div><div class="chart-wrap"><canvas id="trendChart"></canvas></div></div><div class="panel status-panel"><div class="panel-head"><strong>数据健康状态</strong><span>自动更新与降级说明</span></div><div class="status-list">{status_center_html}</div></div></div></section>
<section class="section private-console"><div class="panel"><div class="panel-head"><strong>匿名访问统计</strong><span>不记录姓名、邮箱或IP地址</span></div><div id="siteAnalyticsRoot" class="site-analytics"><div class="site-analytics-empty">正在读取访问统计…</div></div></div></section>
</div>

<div id="tab-engine" class="tab-pane">
<section class="hero compact-hero"><div><h1>核心策略信号</h1><p>正式信号按经复权ATH与完整收盘价确认；只判断是否进入加仓区，不记录或分配资金。</p></div></section>
<section class="section"><div class="engine"><div class="engine-top"><div><div class="engine-label">STRATEGY ENGINE · 核心ETF三档加仓线</div><div class="engine-title">当前状态：{level_names[max_level]}</div><div class="engine-asof">策略数据截至 {data.get('spy_date','-')} 美股收盘 · 盘中价格仅供距离参考</div></div><div class="engine-badge {engine_badge_cls}">{level_names[max_level]}</div></div><div id="strategySignalGrid" class="engine-grid">{engine_html}</div><div class="engine-foot">规则：严格使用经复权验证的历史全期最高点（ATH）和各资产独立阈值；到达点位只提示进入对应加仓区，不自动下单。QQQ与QQQM属于同一指数敞口。</div></div></section>
<section class="section">{tqqq_x2_html}</section>
<section class="section">{leaps_radar_html}</section>
<section class="section">{opportunity_history_html}</section>
</div>

<div id="tab-index" class="tab-pane"><section class="hero compact-hero"><div><h1>指数、行业与另类资产</h1><p>区分历史ATH与窗口高点，直接显示下一档触发价格和真实价格距离。</p></div></section><section class="section asset-groups">{index_html}</section></div>

<div id="tab-cn-hk" class="tab-pane">
<section class="hero compact-hero"><div><h1>A股港股 & 红利低波</h1><p>自动同步腾讯行情；159307明确作为中证红利低波100指数的场内代理标的。</p></div></section>
<section class="section"><div class="section-head"><h2>大盘与红利核心池</h2><p>点击卡片展开近 30 日历史趋势</p></div><div class="opt-grid">{mkt_card_a("上证指数", data["cn_hk"].get("sh000001"), "sh000001")}{mkt_card_a("沪深300", data["cn_hk"].get("sh000300"), "sh000300")}{mkt_card_a("红利低波100 ETF (159307)", data["cn_hk"].get("sz159307"), "sz159307", True, 0.995)}</div></section>
<section class="section"><div class="section-head"><h2>港股跨境池</h2><p>点击卡片展开近 30 日历史趋势</p></div><div class="opt-grid">{mkt_card_a("华夏纳指 (港股)", data["cn_hk"].get("hk03086"), "hk03086")}{mkt_card_a("国指备兑 (港股)", data["cn_hk"].get("hk03416"), "hk03416")}</div></section>
</div>

<div id="tab-stocks" class="tab-pane"><section class="hero compact-hero"><div><h1>个股观察池</h1><p>按策略距离和风险状态自动排出关注顺序；登录后由Alpaca参考行情盘中更新，技术指标以最近完整收盘日线计算。</p></div><div class="stock-watch-actions"><span id="stockWatchStatus" class="stock-watch-status">公开版显示最近构建数据</span><button type="button" onclick="StockWatchlist.refresh()">↻ 刷新行情</button><button class="primary" type="button" onclick="StockWatchlist.openAdd()">＋ 新增个股</button></div></section><section class="section"><div class="stock-toolbar"><div class="stock-filters"><button class="active" data-stock-filter="all" onclick="StockDecision.filter(this,'all')">全部</button><button data-stock-filter="triggered" onclick="StockDecision.filter(this,'triggered')">已触发</button><button data-stock-filter="near" onclick="StockDecision.filter(this,'near')">接近策略价</button><button data-stock-filter="oversold" onclick="StockDecision.filter(this,'oversold')">超卖</button><button data-stock-filter="weak" onclick="StockDecision.filter(this,'weak')">趋势偏弱</button><button data-stock-filter="hot" onclick="StockDecision.filter(this,'hot')">过热</button></div><select id="stockSort" onchange="StockDecision.sort(this.value)"><option value="priority">关注优先</option><option value="target">距策略价最近</option><option value="drawdown">YTD回撤最大</option><option value="rsi">RSI最低</option><option value="default">默认顺序</option></select></div><div class="table-container stock-table"><table><thead><tr><th>名称</th><th>最新价 / 涨跌</th><th>YTD回撤</th><th>RSI</th><th>距200MA</th><th>策略价 / 距离</th><th>状态</th></tr></thead><tbody id="stocksTableBody">{stock_html}</tbody></table></div></section></div>

<div id="tab-options" class="tab-pane">
<section class="hero"><div><h1>期权持仓与风险监控 V{OPTIONS_VERSION}</h1><p>优先呈现真实建仓成本、现金担保年化ROC、临期风险和官方宏观事件。自动行情来自 Alpaca Indicative 免费参考源；下单前仍以 IBKR Bid/Ask 为准。</p></div></section>
<section class="section">
    <div id="macroEventStrip" class="event-strip"><div class="event-item skeleton">正在读取FOMC/CPI官方日历</div></div>
    <div id="optionRiskSummary" class="risk-grid"><div class="risk-card skeleton">正在计算持仓风险</div></div>
    <div class="option-position-toolbar">
        <span id="optionAutoStatus" class="option-auto-status">登录后检查持仓报价；美股常规时段每15分钟自动刷新</span>
        <button id="refreshAllOptions" class="option-secondary" type="button">↻ 刷新全部持仓</button>
        <button id="toggleOptionHistory" class="option-secondary" type="button" onclick="OptionV2.toggleHistory()">查看历史（0）</button>
        <button onclick="openAddOptionModal()" style="background:var(--brass); color:#fff; border:none; padding:8px 16px; border-radius:6px; cursor:pointer; font-weight:600; font-size:12.5px; box-shadow:0 4px 10px rgba(184,134,58,.3);">➕ 录入期权成交</button>
    </div>
    <div class="option-pnl-head"><strong>开放期权盈亏汇总</strong><span>Short按Ask、Long按Bid估值；休市为最近参考报价，无报价仓位不计入金额</span></div><div id="optionPnlSummary" class="option-pnl-summary"><div class="option-pnl-empty">登录后统计分账户期权盈亏</div></div>
    <div class="table-container">
        <table>
            <thead>
                <tr>
                    <th style="text-align:left;">账户 / 合约</th><th>策略 / DTE</th><th>建仓价</th><th>当前估值</th><th>浮动盈亏</th><th>Delta</th><th>资金 / 有效价</th><th>风险状态</th><th>操作</th>
                </tr>
            </thead>
            <tbody id="optionsTableBody">{options_html}</tbody>
        </table>
    </div>
    <div id="optionHistorySection" class="option-history" hidden>
      <div class="option-history-head"><div><strong>期权交易历史</strong><span>关闭后保留完整账本，不再从数据库删除</span></div><span id="optionHistoryCount">0 笔</span></div>
      <div class="table-container"><table><thead><tr><th>合约 / 策略</th><th>建仓 → 结束</th><th>处理结果</th><th>平仓价</th><th>总费用</th><th>已实现盈亏</th><th>行权有效价</th><th>备注</th><th>操作</th></tr></thead><tbody id="optionHistoryBody"><tr><td colspan="9" style="text-align:center;color:var(--muted)">登录后读取历史记录</td></tr></tbody></table></div>
    </div>
</section>
<section class="section">
  <div id="rollManagerRoot" class="roll-manager">
    <div class="roll-manager-head"><div><h2>分账户期权与展期管理</h2><p>同一股票按券商账户隔离；Covered Call占用该账户正股，Sell Put独立统计资金。收盘Delta触发纪律，盘中Delta仅供参考。</p></div><div class="roll-manager-actions"><button type="button" onclick="RollManager.load()">↻ 刷新</button><button type="button" onclick="RollManager.openAccounts()">账户管理</button><button type="button" onclick="RollManager.prefillSellPut()">＋ Sell Put</button><button class="primary" type="button" onclick="RollManager.openUnderlying()">＋ 正股持仓</button></div></div>
    <div id="rollManagerSummary" class="roll-summary"><div class="roll-empty">登录后读取展期计划</div></div>
    <div class="roll-section-title"><h3>分账户正股覆盖与分层减仓</h3><span>不同券商账户不得互相覆盖</span></div>
    <div id="rollUnderlyingGrid" class="roll-underlyings"></div>
    <div class="roll-section-title"><h3>展期纪律清单</h3><span>Call使用Roll Up；Put使用Roll Down & Out</span></div>
    <div id="rollPositionList" class="roll-position-list"></div>
    <div class="roll-history"><details><summary>查看展期历史（平旧仓＋开新仓＋净收付）</summary><div class="table-container"><table><thead><tr><th>标的 / 策略</th><th>旧合约</th><th>新合约</th><th>本次净额</th><th>累计权利金</th><th>成交时间</th><th>操作</th></tr></thead><tbody id="rollHistoryBody"><tr><td colspan="7" class="roll-empty">登录后读取</td></tr></tbody></table></div></details></div>
    <p class="option-note">纪律提示：Delta不是指派概率保证。美股个股期权卖方可能在到期前被指派；临近除息、深度实值、流动性差或重大事件前，请额外核对时间价值、Bid/Ask与券商保证金。</p>
  </div>
</section>
<section class="section"><p style="font-size:11.5px;color:var(--muted);line-height:1.7">💡 主理人说明：浮盈/浮亏自动结合 Long/Short 策略方向推演计算。Delta 指标可用于评估对冲正股所需的仓位，以及辅助预判合约归零/行权的最终概率。</p></section>
</div>

<!-- 理财工具 -->
<div id="tab-finance-tools" class="tab-pane">
<section class="hero compact-hero finance-hero"><div><h1>理财工具</h1><p>用同一组现金流假设计算期末资产，或反推每期投入、所需收益率、起始本金与投资年限。所有字段与结果均使用中文。</p></div><div class="finance-privacy-note"><b>仅在本机计算</b><span>方案保存在当前浏览器，不上传账户、资产或目标金额。</span></div></section>
<div id="financeToolsRoot" class="finance-tools-shell">
  <section class="finance-mode-panel" aria-label="计算目标">
    <div class="finance-section-kicker">选择要解决的问题</div>
    <div class="finance-mode-tabs" role="tablist">
      <button type="button" class="active" data-finance-mode="end">期末能有多少</button>
      <button type="button" data-finance-mode="contribution">每期需要投入多少</button>
      <button type="button" data-finance-mode="return">需要多少年化收益</button>
      <button type="button" data-finance-mode="start">起始需要多少本金</button>
      <button type="button" data-finance-mode="length">需要投资多少年</button>
    </div>
  </section>
  <div class="finance-layout">
    <section class="finance-card finance-input-card">
      <div class="finance-card-head"><div><span class="finance-section-kicker">规划参数</span><h2 id="financeModeTitle">计算期末资产</h2></div><button type="button" class="finance-ghost" id="financeReset">重置</button></div>
      <div class="finance-form-grid">
        <label data-finance-field="target"><span>目标金额</span><input id="financeTarget" type="number" min="0" step="1000" value="1000000"><small>用于反推目标</small></label>
        <label data-finance-field="start"><span>起始本金</span><input id="financeStart" type="number" min="0" step="1000" value="100000"><small>当前已经投入的本金</small></label>
        <label data-finance-field="years"><span>投资期限（年）</span><input id="financeYears" type="number" min="0.1" max="100" step="0.1" value="20"><small>允许小数年</small></label>
        <label data-finance-field="rate"><span>预期年化复合收益率</span><div class="finance-input-suffix"><input id="financeRate" type="number" min="-99" max="200" step="0.1" value="8"><b>%</b></div><small>按年化复合收益率折算到每个投入周期</small></label>
        <label data-finance-field="contribution"><span>定期投入金额</span><input id="financeContribution" type="number" min="0" step="100" value="4000"><small>不包含起始本金</small></label>
        <label><span>投入频率</span><select id="financeFrequency"><option value="12">每月</option><option value="52">每周</option><option value="252">每个交易日</option><option value="1">每年</option></select><small>交易日按每年252次估算</small></label>
        <label><span>投入时间</span><select id="financeTiming"><option value="end">每期期末</option><option value="begin">每期期初</option></select><small>期初投入会多获得一期收益</small></label>
        <label><span>显示币种</span><select id="financeCurrency"><option value="CNY">人民币（¥）</option><option value="USD">美元（$）</option></select><small>只改变金额格式，不做汇率换算</small></label>
      </div>
      <div class="finance-quick-row"><span>收益情景</span><button type="button" data-rate-preset="5">保守 5%</button><button type="button" data-rate-preset="8" class="active">基准 8%</button><button type="button" data-rate-preset="12">积极 12%</button></div>
      <div id="financeValidation" class="finance-validation" aria-live="polite"></div>
      <div class="finance-actions"><button type="button" class="finance-primary" id="financeCalculate">开始计算</button><button type="button" class="finance-secondary" id="financeSave">保存当前方案</button><button type="button" class="finance-secondary" id="financeExport">导出明细 CSV</button></div>
      <p class="finance-disclaimer">本工具为现金流规划模型，不预测市场收益，也未计入税费、通胀、汇率和基金费率。交易日定投按每年252次均匀估算。</p>
    </section>
    <section class="finance-card finance-result-card">
      <div class="finance-card-head"><div><span class="finance-section-kicker">计算结果</span><h2 id="financeAnswerLabel">预计期末资产</h2></div><span id="financeAnswerMeta" class="finance-answer-meta">20年 · 年化8%</span></div>
      <div id="financeAnswer" class="finance-answer">—</div>
      <div id="financeAnswerHint" class="finance-answer-hint">输入参数后自动计算</div>
      <div class="finance-result-grid">
        <div><span>累计投入本金</span><strong id="financePrincipal">—</strong></div>
        <div><span>累计投资收益</span><strong id="financeInterest">—</strong></div>
        <div><span>收益占期末资产</span><strong id="financeInterestShare">—</strong></div>
        <div><span>目标完成度</span><strong id="financeTargetProgress">—</strong></div>
      </div>
      <div class="finance-composition"><div class="finance-chart-wrap"><canvas id="financeCompositionChart"></canvas></div><div id="financeCompositionLegend" class="finance-chart-legend"></div></div>
    </section>
  </div>
  <section class="finance-card finance-growth-card">
    <div class="finance-card-head"><div><span class="finance-section-kicker">资产积累路径</span><h2>本金、定投与收益如何变化</h2></div><div class="finance-view-tabs"><button type="button" class="active" data-finance-view="chart">增长图</button><button type="button" data-finance-view="table">逐年明细</button></div></div>
    <div id="financeChartView" class="finance-growth-chart"><canvas id="financeGrowthChart"></canvas></div>
    <div id="financeTableView" class="finance-schedule-wrap" hidden><table><thead><tr><th>年份</th><th>年初余额</th><th>本年投入</th><th>本年收益</th><th>年末余额</th></tr></thead><tbody id="financeScheduleBody"></tbody></table></div>
  </section>
  <section class="finance-lower-grid">
    <div class="finance-card"><div class="finance-card-head"><div><span class="finance-section-kicker">收益率敏感度</span><h2>不同收益情景</h2></div></div><div id="financeScenarios" class="finance-scenarios"></div></div>
    <div class="finance-card"><div class="finance-card-head"><div><span class="finance-section-kicker">本机方案</span><h2>已保存的规划</h2></div><span class="finance-local-tag">仅此浏览器</span></div><div id="financeSavedPlans" class="finance-saved-plans"><p>尚未保存方案</p></div></div>
  </section>
</div>
</div>

<!-- 期权决策台 -->
<div id="tab-sandbox" class="tab-pane">
<section class="hero"><div><h1>期权决策台 V{OPTIONS_VERSION}</h1><p>既可按 Alpaca 参考报价模拟新开仓，也可从持仓监控带入真实成本，推演“目标日期股价为 X 时，这个仓位值多少钱”。金额统一按合约乘数（默认100）和实际张数计算。</p></div></section>
<div id="optionV2Root" class="option-v2-shell" data-endpoint="https://rhielbkvhgqbthcgztci.supabase.co/functions/v1/options-market">
  <div class="option-v2-toolbar"><span id="optV2Status" class="option-v2-status warn">登录后可读取 Alpaca Indicative 参考行情；接口异常时可使用手动报价</span><button id="manualToggle" class="option-secondary">手动报价</button><button id="advancedToggle" class="option-secondary">高级参数</button></div>
  <details class="option-v2-card" style="margin-bottom:14px;padding:14px 18px"><summary style="cursor:pointer;font-weight:700">如何使用：现有持仓与新开仓的区别</summary><p class="option-note" style="margin-top:10px;line-height:1.8">现有持仓请从“期权持仓监控”点击“推演”，系统会保留数据库中的真实建仓成本；不要重新点击期权链，否则会切换成按当前报价模拟新开仓。目标日期必须早于到期日；目标股价 X 是你假设该日正股可能达到的价格；IV 变化用于测试波动率收缩或上升。Short 仓位当前平仓成本优先采用 Ask，Long 仓位当前卖出价值优先采用 Bid。</p></details>
  <div class="option-v2-grid">
    <div class="option-v2-card">
      <h3>1. 选择合约与仓位</h3>
      <div class="option-field"><label>股票代码</label><div style="display:grid;grid-template-columns:1fr auto;gap:7px"><input id="optionSymbol" list="optionSymbols" value="IREN" placeholder="IREN"><button id="loadExpirations" class="option-primary">读取到期日</button></div><datalist id="optionSymbols"><option value="IREN"><option value="LITE"><option value="NVDA"><option value="ORCL"><option value="TSLA"><option value="QQQ"><option value="SPY"></datalist></div>
      <div class="option-field"><label>策略</label><div class="option-pills"><button class="option-pill active" data-strategy="SELL_PUT">Sell Put</button><button class="option-pill" data-strategy="BUY_CALL">Buy Call</button><button class="option-pill" data-strategy="BUY_PUT">Buy Put</button><button class="option-pill" data-strategy="COVERED_CALL">Covered Call</button><button class="option-pill" data-strategy="NAKED_CALL">Naked Call</button></div></div>
      <div class="option-two"><div class="option-field"><label>到期日</label><select id="optExpiryV2"><option value="">选择到期日</option></select></div><div class="option-field"><label>期权方向</label><select id="chainSide"><option value="put">Put</option><option value="call">Call</option></select></div></div>
      <div class="option-chain-wrap"><table class="option-chain"><thead><tr><th>Strike</th><th>Bid</th><th>Ask</th><th>Mid</th><th>IV</th><th>Delta</th><th>Vol</th><th>OI</th></tr></thead><tbody id="optionChainBody"></tbody></table></div>
      <div id="selectedContract" class="option-selected" style="margin-top:10px">尚未选择真实合约</div>
      <div class="option-two"><div class="option-field"><label>开仓价格采用</label><select id="quoteBasis"><option value="mid">Mid 中间价</option><option value="bid">Bid</option><option value="ask">Ask</option><option value="last">Last</option></select></div><div class="option-field"><label>合约张数</label><div class="qty-control"><button id="qtyMinus">−</button><input id="optionQty" type="number" min="1" value="1"><button id="qtyPlus">＋</button></div></div></div>
      <div id="manualPanel" class="manual-panel active"><h4>手动报价 / 接口回退</h4><div class="option-two"><div class="option-field"><label>正股现价</label><input id="manualSpot" type="number" step="0.01" value="42.62"></div><div class="option-field"><label>行权价</label><input id="manualStrike" type="number" step="0.01" value="40"></div></div><div class="option-two"><div class="option-field"><label>权利金报价（每股）</label><input id="manualPremium" type="number" step="0.01" value="3.50"></div><div class="option-field"><label>当前IV（%）</label><input id="manualIv" type="number" step="0.01" value="60"></div></div><div class="option-field"><label>到期日</label><input id="manualExpiry" type="date" value="2026-10-30"></div></div>
      <div id="advancedPanel" class="advanced-panel"><h4>高级参数</h4><div class="option-two"><div class="option-field"><label>每张单边手续费</label><input id="feePerContract" type="number" step="0.01" value="0.65"></div><div class="option-field"><label>合约乘数</label><input id="contractMultiplier" type="number" value="100"></div></div><div class="option-two"><div class="option-field"><label>无风险利率（%）</label><input id="riskFreeRate" type="number" step="0.01" value="4.20"></div><div class="option-field"><label>股息率（%）</label><input id="dividendYield" type="number" step="0.01" value="0"></div></div><div id="stockCostWrap" class="option-field" style="display:none"><label>备兑正股成本</label><input id="stockCost" type="number" step="0.01"></div></div>
    </div>
    <div class="option-v2-card">
      <h3>2. 设置下周情景</h3>
      <div class="option-field"><label>目标日期</label><div class="option-pills"><button class="option-pill" data-date-preset="1">明天</button><button class="option-pill active" data-date-preset="friday">下周五</button><button class="option-pill" data-date-preset="7">7天后</button><button class="option-pill" data-date-preset="14">14天后</button></div><input id="targetDate" type="date" style="margin-top:7px"></div>
      <div class="option-field"><label>目标股价 X</label><div class="option-pills"><button class="option-pill" data-spot-preset="-.20">-20%</button><button class="option-pill" data-spot-preset="-.10">-10%</button><button class="option-pill" data-spot-preset="-.05">-5%</button><button class="option-pill" data-spot-preset="0">现价</button><button class="option-pill" data-spot-preset="strike">行权价</button><button class="option-pill" data-spot-preset="breakeven">盈亏平衡</button><button class="option-pill" data-spot-preset=".10">+10%</button></div><input id="targetSpot" type="number" step="0.01" value="36.50" style="margin-top:7px"></div>
      <div class="option-field"><label>IV相对变化</label><div class="option-pills"><button class="option-pill" data-iv="-.2">-20%</button><button class="option-pill" data-iv="-.1">-10%</button><button class="option-pill active" data-iv="0">维持</button><button class="option-pill" data-iv=".1">+10%</button><button class="option-pill" data-iv=".2">+20%</button></div></div>
      <button id="runScenario" class="option-primary" style="width:100%;margin:4px 0 14px">计算目标日仓位价值</button>
      <div id="scenarioAnswer" class="scenario-answer">选择或输入合约参数后开始推演。</div>
      <div id="optionStats" class="option-summary"></div>
      <h4>股价 × IV 情景矩阵（净盈亏）</h4><div id="optionHeatmap" class="option-heatmap"></div>
      <p class="option-note" style="margin-top:12px">目标日期估值为模型推演，不是成交保证。Short仓位实际平仓重点参考Ask，Long仓位重点参考Bid。美式期权提前行权、财报跳空和流动性会造成偏差。</p>
    </div>
  </div>
</div>
</div>

<div id="tab-archive" class="tab-pane">
<section class="hero"><div><h1>历史买点归档数据库</h1><p>完整回溯 2005 年以来各大核心资产触发一级、重点及极限加仓信号的黄金历史买点，验证策略透明度。</p></div></section>
<section class="section"><div class="table-container"><table><thead><tr><th style="text-align:left;">资产代号</th><th>触发日期</th><th>触发收盘价</th><th>当时全期回撤幅度</th><th>触发加仓评级</th><th>规则体系</th></tr></thead><tbody id="archiveTableBody">{signals_html}</tbody></table></div></section>
<section class="section"><p style="font-size:11.5px;color:var(--muted);line-height:1.7">同一资产同一天可能出现两条记录——"资产自身三档线"是该ETF自己相对真实全期最高点的回撤触发的加仓线；"全市场宽度恐慌"是标普500全市场宽度指标触发的分级信号。两套规则相互独立，同一天都触发是正常情况，不是数据重复。</p></section></div>

<div class="footer">© 2026 myAlphaView · Private Research Dashboard<br>市场数据与策略指标仅供研究参考，不构成投资建议；本站仅记录匿名访问次数，不采集姓名、邮箱或IP地址。</div>
</div></main></div>

<div id="underlyingModal" class="option-modal-backdrop" style="display:none">
  <div class="option-modal-card"><div class="option-modal-head"><div><h3>正股覆盖计划</h3><p>跨设备保存到私有Supabase；分层目标只做纪律记录。</p></div><button type="button" onclick="RollManager.closeUnderlying()">×</button></div>
    <div class="roll-form-grid"><div class="option-field wide"><label>券商账户（账户之间不能互相覆盖）</label><select id="underlyingAccount"></select></div><div class="option-field"><label>股票代码</label><input id="underlyingSymbol" placeholder="IREN"></div><div class="option-field"><label>该账户持股数</label><input id="underlyingShares" type="number" min="0" step="1"></div><div class="option-field"><label>正股成本 / 股</label><input id="underlyingCost" type="number" min="0" step="0.01"></div><div class="option-field"><label>当前价（可手工更新）</label><input id="underlyingPrice" type="number" min="0" step="0.01"></div><div class="option-field"><label>Covered Call观察Delta</label><input id="underlyingWatch" type="number" min="0.01" max="0.99" step="0.01" value="0.70"></div><div class="option-field"><label>Covered Call紧急Delta</label><input id="underlyingUrgent" type="number" min="0.01" max="1" step="0.01" value="0.80"></div><div class="option-field"><label>Sell Put观察 |Delta|</label><input id="putWatch" type="number" min="0.01" max="0.99" step="0.01" value="0.50"></div><div class="option-field"><label>Sell Put紧急 |Delta|</label><input id="putUrgent" type="number" min="0.01" max="1" step="0.01" value="0.70"></div><div class="option-field wide"><label>Sell Put到期偏好</label><select id="putAssignmentMode"><option value="accept">愿意按计划接货</option><option value="avoid">尽量避免被指派</option></select></div><div class="option-field wide"><label>分层减仓（每行：价格区间:比例）</label><textarea id="underlyingTargets" rows="3" placeholder="65-70:50%&#10;75-80:50%"></textarea></div></div>
    <div class="option-modal-actions"><button id="deleteUnderlyingBtn" class="option-danger-link" type="button" onclick="RollManager.deleteUnderlying()" hidden>删除计划</button><span></span><button class="option-secondary" type="button" onclick="RollManager.closeUnderlying()">取消</button><button class="option-primary" type="button" onclick="RollManager.saveUnderlying()">保存计划</button></div>
  </div>
</div>

<div id="accountModal" class="option-modal-backdrop" style="display:none">
  <div class="option-modal-card"><div class="option-modal-head"><div><h3>券商账户管理</h3><p>账户只是私有别名；不要填写账号、密码或完整账户号码。</p></div><button type="button" onclick="RollManager.closeAccounts()">×</button></div>
    <div id="accountList" class="account-list"></div>
    <input id="accountId" type="hidden">
    <div class="roll-form-grid"><div class="option-field"><label>账户名称</label><input id="accountName" placeholder="例如：IBKR主账户"></div><div class="option-field"><label>券商</label><input id="accountBroker" placeholder="IBKR / Tradier"></div><div class="option-field"><label>排序</label><input id="accountSort" type="number" value="0"></div></div>
    <div class="option-modal-actions"><button class="option-secondary" type="button" onclick="RollManager.resetAccountForm()">取消编辑</button><span></span><button class="option-secondary" type="button" onclick="RollManager.closeAccounts()">关闭</button><button class="option-primary" type="button" onclick="RollManager.saveAccount()">保存账户</button></div>
  </div>
</div>

<div id="rollModal" class="option-modal-backdrop" style="display:none">
  <div class="option-modal-card"><div class="option-modal-head"><div><h3 id="rollModalTitle">展期管理</h3><p id="rollModalSummary"></p></div><button type="button" onclick="RollManager.closeRoll()">×</button></div><input id="rollPositionId" type="hidden">
    <div class="roll-form-grid"><div class="option-field"><label>Delta（IBKR）</label><input id="rollDelta" type="number" min="-1" max="1" step="0.0001" oninput="RollManager.updateMonitorPreview()"></div><div class="option-field"><label>观察口径</label><select id="rollObservation" onchange="RollManager.updateMonitorPreview()"><option value="close">收盘Delta（触发纪律）</option><option value="intraday">盘中Delta（仅参考）</option></select></div><div class="option-field"><label>连续处于观察区的收盘数</label><input id="rollWatchCloses" type="number" min="0" step="1" value="0" oninput="RollManager.updateMonitorPreview()"></div><label class="roll-inline-check"><input id="rollCatalyst" type="checkbox" onchange="RollManager.updateMonitorPreview()">已有实锤消息 / 催化剂</label><div class="option-field wide"><label>观察与成交备注</label><textarea id="rollNotes" rows="2" maxlength="500" placeholder="例如：Horizon交付已官宣；IBKR组合单号"></textarea></div></div>
    <div id="monitorPreview" class="monitor-preview"></div><div class="roll-observation-actions"><button class="option-danger-link" type="button" onclick="RollManager.clearObservation()">清除手工Delta</button><button class="option-secondary" type="button" onclick="RollManager.saveObservation()">保存本次Delta观察</button></div>
    <div id="rollCalculator" class="roll-calculator"><h4>按券商实际成交价计算展期</h4><div class="roll-form-grid"><div class="option-field"><label>本次展期张数</label><input id="rollQty" type="number" min="1" step="1" oninput="RollManager.updateRollPreview()"></div><div class="option-field"><label>新行权价</label><input id="newRollStrike" type="number" min="0.01" step="0.01" oninput="RollManager.updateRollPreview()"></div><div class="option-field"><label>新到期日</label><input id="newRollExpiry" type="date" onchange="RollManager.updateRollPreview()"></div><div class="option-field"><label>买回旧仓 Debit / 股</label><input id="rollCloseDebit" type="number" min="0" step="0.01" oninput="RollManager.updateRollPreview()"></div><div class="option-field"><label>卖出新仓 Credit / 股</label><input id="rollOpenCredit" type="number" min="0" step="0.01" oninput="RollManager.updateRollPreview()"></div><div class="option-field"><label>旧仓平仓总手续费</label><input id="rollCloseFee" type="number" min="0" step="0.01" value="0" oninput="RollManager.updateRollPreview()"></div><div class="option-field"><label>新仓开仓总手续费</label><input id="rollOpenFee" type="number" min="0" step="0.01" value="0" oninput="RollManager.updateRollPreview()"></div></div><div id="rollPreview" class="roll-preview"></div></div>
    <div class="option-modal-actions"><span></span><span></span><button class="option-secondary" type="button" onclick="RollManager.closeRoll()">取消</button><button id="confirmRollBtn" class="option-primary" type="button" onclick="RollManager.confirmRoll()">确认IBKR已成交并记账</button></div>
  </div>
</div>

<div id="optionLifecycleModal" class="option-modal-backdrop" style="display:none">
  <div class="option-modal-card">
    <div class="option-modal-head"><div><h3 id="lifecycleTitle">管理期权持仓</h3><p id="lifecycleSummary"></p></div><button type="button" onclick="OptionV2.closeLifecycle()">×</button></div>
    <div class="option-field"><label>所属券商账户</label><select id="lifecycleAccount"></select><small class="option-note">可将升级前归入“待分配账户”的仓位调整到真实账户。</small></div>
    <div class="option-field"><label>处理方式</label><select id="lifecycleAction" onchange="OptionV2.updateLifecyclePreview()"><option value="closed">主动平仓</option><option value="expired_worthless">到期作废（价值归零）</option><option value="assigned">被行权</option></select></div>
    <div class="option-two"><div class="option-field"><label>处理日期</label><input id="lifecycleDate" type="date"></div><div id="lifecycleExitWrap" class="option-field"><label>平仓成交价（每股）</label><input id="lifecycleExitPrice" type="number" min="0" step="0.01" oninput="OptionV2.updateLifecyclePreview()"></div></div>
    <div class="option-two"><div class="option-field"><label>本次总手续费</label><input id="lifecycleCloseFee" type="number" min="0" step="0.01" value="0" oninput="OptionV2.updateLifecyclePreview()"></div><div id="lifecycleStockWrap" class="option-field" style="display:none"><label>行权时正股价（可选，仅留档）</label><input id="lifecycleStockPrice" type="number" min="0" step="0.01"></div></div>
    <div class="option-field"><label>备注（可选）</label><textarea id="lifecycleNotes" rows="2" maxlength="500" placeholder="例如：50%止盈、到期被指派、券商成交单号"></textarea></div>
    <div id="lifecyclePreview" class="lifecycle-preview"></div>
    <div class="option-modal-actions"><button class="option-danger-link" type="button" onclick="OptionV2.deleteLifecycleRecord()">仅纠错：永久删除</button><button class="option-secondary" type="button" onclick="OptionV2.savePositionAccount()">只更新账户</button><button class="option-secondary" type="button" onclick="OptionV2.closeLifecycle()">取消</button><button id="saveLifecycleBtn" class="option-primary" type="button" onclick="OptionV2.saveLifecycle()">确认并归档</button></div>
  </div>
</div>

<div id="stockWatchModal" class="option-modal-backdrop" style="display:none">
  <div class="option-modal-card"><div class="option-modal-head"><div><h3 id="stockWatchModalTitle">新增观察个股</h3><p>网站内直接新增或删除，无需进入Supabase；保存后立即读取报价与完整收盘日线指标。</p></div><button type="button" onclick="StockWatchlist.close()">×</button></div>
    <input id="watchOriginalSymbol" type="hidden"><div class="roll-form-grid"><div class="option-field"><label>美股代码</label><input id="watchSymbol" maxlength="12" placeholder="例如 AAPL"></div><div class="option-field"><label>显示名称</label><input id="watchName" maxlength="60" placeholder="例如 苹果"></div><div class="option-field wide"><label>策略参考价（可选）</label><input id="watchTarget" type="number" min="0" step="0.01" placeholder="留空则只观察行情"></div></div>
    <div class="option-modal-actions"><span></span><span></span><button class="option-secondary" type="button" onclick="StockWatchlist.close()">取消</button><button class="option-primary" type="button" onclick="StockWatchlist.save()">验证并保存</button></div>
  </div>
</div>

<!-- ➕ 添加期权持仓弹窗 HTML -->
<div id="addOptionModal" style="display:none; position:fixed; inset:0; background:rgba(0,0,0,0.5); z-index:100; place-items:center;">
  <div style="background:var(--surface); padding:24px; border-radius:14px; width:min(560px,calc(100vw - 28px)); max-height:90vh; overflow:auto; box-shadow:0 20px 40px rgba(0,0,0,0.2);">
    <input id="optEditId" type="hidden"><h3 id="optionEntryTitle" style="margin-bottom:5px; font-family:var(--serif);">录入期权实际成交</h3><p id="optionEntryDesc" style="font-size:10.5px;color:var(--muted);margin:0 0 16px">按券商成交单录入；权利金为每股价格，盈亏自动按张数×合约乘数计算。</p>
    <div style="display:grid; gap:12px;">
      <div style="display:grid;grid-template-columns:1fr auto;gap:8px;align-items:end"><div><label style="font-size:11.5px;color:var(--muted)">券商账户</label><select id="optBrokerAccount" style="width:100%;padding:8px;border:1px solid var(--line);border-radius:6px;margin-top:4px"><option value="">请先选择账户</option></select></div><button type="button" class="option-secondary" onclick="RollManager.openAccounts()">管理账户</button></div>
      <div>
        <label style="font-size:11.5px; color:var(--muted);">正股代码 (Symbol)</label>
        <input type="text" id="optSym" placeholder="例如 LITE" style="width:100%; padding:8px; border:1px solid var(--line); border-radius:6px; margin-top:4px;">
      </div>
      <div>
        <label style="font-size:11.5px; color:var(--muted);">交易策略 (Strategy)</label>
        <select id="optStrategy" onchange="updateOptionEntryFields()" style="width:100%; padding:8px; border:1px solid var(--line); border-radius:6px; margin-top:4px;">
            <option value="SELL PUT">SELL PUT (卖出看跌)</option>
            <option value="BUY PUT">BUY PUT (买入看跌)</option>
            <option value="SELL CALL">SELL CALL (卖出看涨)</option>
            <option value="BUY CALL">BUY CALL (买入看涨)</option>
        </select>
      </div>
      <div id="optAssignmentWrap">
        <label style="font-size:11.5px;color:var(--muted)">Sell Put到期偏好</label><select id="optAssignmentMode" style="width:100%;padding:8px;border:1px solid var(--line);border-radius:6px;margin-top:4px"><option value="accept">愿意按计划接货</option><option value="avoid">尽量避免被指派</option></select>
      </div>
      <div id="optEntryHint" class="option-note"></div>
      <div style="display:grid; grid-template-columns:1fr 1fr; gap:8px;">
        <div>
          <label style="font-size:11.5px; color:var(--muted);">行权价 (Strike)</label>
          <input type="number" step="0.01" id="optStrike" placeholder="例如 660" style="width:100%; padding:8px; border:1px solid var(--line); border-radius:6px; margin-top:4px;">
        </div>
        <div>
          <label style="font-size:11.5px; color:var(--muted);">到期日 (Expiry)</label>
          <input type="date" id="optExpiry" style="width:100%; padding:8px; border:1px solid var(--line); border-radius:6px; margin-top:4px;">
        </div>
      </div>
      <div style="display:grid; grid-template-columns:1fr 1fr; gap:8px;">
        <div>
          <label style="font-size:11.5px; color:var(--muted);">建仓日期</label>
          <input type="date" id="optEntryDate" style="width:100%; padding:8px; border:1px solid var(--line); border-radius:6px; margin-top:4px;">
        </div>
        <div>
          <label style="font-size:11.5px; color:var(--muted);">担保方式</label>
          <select id="optCollateralMode" style="width:100%; padding:8px; border:1px solid var(--line); border-radius:6px; margin-top:4px;"><option value="cash_secured">Cash-Secured</option><option value="covered">Covered</option><option value="naked">Naked</option><option value="debit">Debit</option></select>
        </div>
      </div>
      <div style="display:grid; grid-template-columns:1fr 1fr; gap:8px;">
        <div>
          <label style="font-size:11.5px; color:var(--muted);">合约乘数</label>
          <input type="number" id="optMultiplier" min="1" value="100" style="width:100%; padding:8px; border:1px solid var(--line); border-radius:6px; margin-top:4px;">
        </div>
        <div>
          <label style="font-size:11.5px; color:var(--muted);">开仓总手续费</label>
          <input type="number" id="optOpenFee" min="0" step="0.01" value="0" style="width:100%; padding:8px; border:1px solid var(--line); border-radius:6px; margin-top:4px;">
        </div>
      </div>
      <div style="display:grid; grid-template-columns:1fr 1fr; gap:8px;">
        <div>
          <label style="font-size:11.5px; color:var(--muted);">成交权利金（每股）</label>
          <input type="number" step="0.01" id="optCost" placeholder="例如 33.48" style="width:100%; padding:8px; border:1px solid var(--line); border-radius:6px; margin-top:4px;">
        </div>
        <div>
          <label style="font-size:11.5px; color:var(--muted);">持仓张数 (Qty)</label>
          <input type="number" id="optQty" value="1" style="width:100%; padding:8px; border:1px solid var(--line); border-radius:6px; margin-top:4px;">
        </div>
      </div>
    </div>
    <div style="display:flex; justify-content:flex-end; gap:8px; margin-top:20px;">
      <button onclick="closeAddOptionModal()" style="background:var(--surface2); border:none; padding:8px 14px; border-radius:6px; cursor:pointer; font-weight:600;">取消</button>
      <button id="saveOptionPositionBtn" onclick="saveNewOptionPosition()" style="background:var(--brass); color:#fff; border:none; padding:8px 14px; border-radius:6px; cursor:pointer; font-weight:600;">保存到云端</button>
    </div>
  </div>
</div>

<script>
const DATA = {chart_json};
const MKT_CHARTS = {{}}; 

function switchTab(id,el){{
  if(id !== 'tab-overview' && !document.body.classList.contains('private-mode')){{
    window.MAV?.toast('此模块仅限主理人登录后浏览。请点击右上角登录。','warn');
    document.getElementById('authBtn')?.focus();
    return;
  }}
  document.querySelectorAll('.tab-pane').forEach(t=>t.classList.remove('active'));
  document.querySelectorAll('.nav-menu li').forEach(l=>l.classList.remove('active'));
  document.getElementById(id).classList.add('active');
  el.classList.add('active');
  document.getElementById('bc-title').innerText = el.innerText.replace('NEW', '').replace(/^[◆◒◫◇⌁⚑◎🧮📜]/u, '').trim();
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
window.SUPABASE_ANON_KEY = SUPABASE_ANON_KEY;
const ADMIN_EMAIL = 'xxj8166@gmail.com';
let isAdmin = false;
const supabaseClient = supabase.createClient(SUPABASE_URL, SUPABASE_ANON_KEY);
window.mavSupabase = supabaseClient;
const authBtn = document.getElementById('authBtn');

async function openAddOptionModal(preset={{}}) {{
  if (!isAdmin) {{ alert('🔒 权限提示：请先点击右上角 [🔐 登录私有看板] 并通过主理人邮箱登录后，方可录入真实期权！'); return; }}
  const editId=preset.edit_id||'';
  document.getElementById('optEditId').value=editId;
  document.getElementById('optionEntryTitle').textContent=editId?'修改期权成交记录':'录入期权实际成交';
  document.getElementById('optionEntryDesc').textContent=editId?'仅用于修正手工录入内容；展期链仓位不能直接修改。':'按券商成交单录入；权利金为每股价格，盈亏自动按张数×合约乘数计算。';
  document.getElementById('saveOptionPositionBtn').textContent=editId?'保存修改':'保存到云端';
  ['optSym','optStrike','optExpiry','optCost'].forEach(id=>document.getElementById(id).value='');
  document.getElementById('optStrategy').value='SELL PUT';document.getElementById('optQty').value='1';document.getElementById('optMultiplier').value='100';document.getElementById('optOpenFee').value='0';document.getElementById('optEntryDate').value=new Date().toISOString().slice(0,10);document.getElementById('optCollateralMode').value='cash_secured';document.getElementById('optAssignmentMode').value='accept';
  if (window.OptionV2?.populateAccountSelect) await window.OptionV2.populateAccountSelect('optBrokerAccount', preset.broker_account_id || preset.accountId);
  if (preset.symbol) document.getElementById('optSym').value = preset.symbol;
  if (preset.strategy) document.getElementById('optStrategy').value = preset.strategy;
  if (preset.collateral_mode || preset.collateralMode) document.getElementById('optCollateralMode').value = preset.collateral_mode || preset.collateralMode;
  if (preset.strike!==undefined) document.getElementById('optStrike').value=preset.strike;
  if (preset.expiry) document.getElementById('optExpiry').value=preset.expiry;
  if (preset.cost!==undefined) document.getElementById('optCost').value=preset.cost;
  if (preset.qty) document.getElementById('optQty').value=preset.qty;
  if (preset.multiplier) document.getElementById('optMultiplier').value=preset.multiplier;
  if (preset.open_fee!==undefined) document.getElementById('optOpenFee').value=preset.open_fee;
  if (preset.entry_date) document.getElementById('optEntryDate').value=preset.entry_date;
  if (preset.assignment_mode) document.getElementById('optAssignmentMode').value=preset.assignment_mode;
  updateOptionEntryFields();
  document.getElementById('addOptionModal').style.display = 'grid';
}}
function closeAddOptionModal() {{ document.getElementById('addOptionModal').style.display = 'none'; document.getElementById('optEditId').value=''; }}
function updateOptionEntryFields() {{
  const strategy=document.getElementById('optStrategy').value,mode=document.getElementById('optCollateralMode'),assignment=document.getElementById('optAssignmentWrap'),hint=document.getElementById('optEntryHint');
  if(strategy==='SELL PUT'){{mode.value=mode.value==='naked'?'naked':'cash_secured';assignment.style.display='block';hint.textContent='Sell Put不占用正股；Cash-Secured理论资金 = 行权价 × 100 × 张数。';}}
  else if(strategy==='SELL CALL'){{mode.value=mode.value==='naked'?'naked':'covered';assignment.style.display='none';hint.textContent='Covered Call只能使用同一券商账户内尚未被占用的正股。';}}
  else{{mode.value='debit';assignment.style.display='none';hint.textContent='Long期权按支付权利金监控，不进入Short展期纪律。';}}
}}

// 保存后必须从数据库读回确认；不再插入会自动消失的“假成功”行。
async function saveNewOptionPosition() {{
  const editId=document.getElementById('optEditId').value;
  const symbol = document.getElementById('optSym').value.trim().toUpperCase();
  const strategy = document.getElementById('optStrategy').value;
  const strike = parseFloat(document.getElementById('optStrike').value);
  const expiry = document.getElementById('optExpiry').value;
  const cost = parseFloat(document.getElementById('optCost').value);
  const qty = parseInt(document.getElementById('optQty').value);
  const entry_date = document.getElementById('optEntryDate').value;
  const collateral_mode = document.getElementById('optCollateralMode').value;
  const multiplier = parseInt(document.getElementById('optMultiplier').value) || 100;
  const open_fee = parseFloat(document.getElementById('optOpenFee').value) || 0;
  const broker_account_id = parseInt(document.getElementById('optBrokerAccount').value);
  const assignment_mode = document.getElementById('optAssignmentMode').value;

  if (!broker_account_id) {{ alert('请先选择这笔成交所属的券商账户。'); return; }}
  if (!symbol || isNaN(strike) || !expiry || isNaN(cost) || isNaN(qty) || qty<=0 || !entry_date) {{ alert('请完整填写所有期权参数和真实建仓日期！'); return; }}
  if (entry_date > expiry) {{ alert('建仓日期不能晚于到期日。'); return; }}

  let opt_type = "Put", side = "Short";
  if (strategy === "SELL PUT") {{ opt_type = "Put"; side = "Short"; }}
  else if (strategy === "BUY PUT") {{ opt_type = "Put"; side = "Long"; }}
  else if (strategy === "SELL CALL") {{ opt_type = "Call"; side = "Short"; }}
  else if (strategy === "BUY CALL") {{ opt_type = "Call"; side = "Long"; }}

  const {{ data: {{ session }} }} = await supabaseClient.auth.getSession();
  if (!session) {{ alert('登录状态已失效，请重新登录后再保存。'); return; }}

  if(strategy==='SELL CALL'&&collateral_mode==='covered'&&window.RollManager?.availableCoveredShares){{
    const existing=editId?window.OptionV2?.getPosition(editId):null,currentUnits=existing&&String(existing.side).toLowerCase()==='short'&&String(existing.opt_type).toLowerCase()==='call'&&String(existing.collateral_mode).toLowerCase()==='covered'&&String(existing.broker_account_id)===String(broker_account_id)&&existing.symbol===symbol?(Number(existing.qty)||0)*(Number(existing.multiplier)||100):0;
    const available=window.RollManager.availableCoveredShares(broker_account_id,symbol)+currentUnits;
    if(qty*multiplier>available){{alert(`该账户可用覆盖股数仅 ${{available}} 股，本次需要 ${{qty*multiplier}} 股。请调整张数、账户或担保方式。`);return;}}
  }}
  const premium_chain_per_share = side==='Short' ? Math.max(0,cost-open_fee/(qty*multiplier)) : null;
  const payload = {{ broker_account_id, symbol, opt_type, side, strike, expiry, cost, qty, multiplier, open_fee, entry_date, collateral_mode, assignment_mode, premium_chain_per_share, user_id: session.user.id }};
  const query=editId?supabaseClient.from('options_positions').update(payload).eq('id',editId):supabaseClient.from('options_positions').insert([payload]);
  const {{ data: saved, error }} = await query.select().single();
  if (error) {{ 
      const migrationHint = /user_id|row-level security|policy/i.test(error.message)
        ? '\\n\\n请先在 Supabase SQL Editor 执行项目根目录 SUPABASE_FIX_OPTIONS.sql。'
        : '';
      alert('保存失败: ' + error.message + migrationHint); 
  }} else {{ 
      closeAddOptionModal();
      if (!saved || !saved.id) {{ alert('数据库未返回刚保存的记录，请检查RLS读取策略。'); return; }}
      await window.OptionV2.loadPrivatePositions();
      if (window.RollManager) await window.RollManager.load();
      alert(editId?'✅ 期权成交记录已修改。':'✅ 期权成交已按账户保存，并从数据库验证读回。');
  }}
}}

async function fetchAndRenderTargets() {{
  const {{ data, error }} = await supabaseClient.from('stock_targets').select('*');
  if (error) {{
      document.querySelectorAll('#stocksTableBody [id^="target-gap-"]').forEach(el => el.textContent = '策略数据不可用');
      window.MAV?.toast(`策略价读取失败：${{error.message}}`, 'warn');
      return;
  }}
  if (data) {{
      const loaded = new Set(data.map(row => row.symbol));
      document.querySelectorAll('.target-controls').forEach(el=>el.remove());
      data.forEach(row => {{
          const targetEl = document.getElementById(`target-${{row.symbol}}`), targetCell=document.getElementById(`target-cell-${{row.symbol}}`), closeEl = document.getElementById(`close-${{row.symbol}}`);
          if (targetEl && closeEl) {{
              window.StockDecision?.updateTarget(row.symbol, row.target_price);
              if (isAdmin&&targetCell) targetCell.insertAdjacentHTML('beforeend', `<span class="target-controls"><button onclick="editTarget('${{row.symbol}}', ${{row.target_price}})">修改</button><button class="danger" onclick="deleteTarget('${{row.symbol}}')">删除</button></span>`);
          }}
      }});
      document.querySelectorAll('#stocksTableBody tr[data-stock-row]').forEach(row => {{
          const symbol = row.querySelector('.stock-symbol')?.textContent?.trim();
          if (symbol && !loaded.has(symbol)) {{window.StockDecision?.updateTarget(symbol, null);const cell=document.getElementById(`target-cell-${{symbol}}`);if(isAdmin&&cell)cell.insertAdjacentHTML('beforeend',`<span class="target-controls"><button onclick="editTarget('${{symbol}}', null)">＋ 设置</button></span>`);}}
      }});
      window.StockDecision?.sort('priority');
  }}
}}

async function editTarget(symbol, currentPrice) {{
  const newPrice = prompt(`主理人后台：\\n请输入 [${{symbol}}] 的策略加仓价：\\n取消不会保存。`, currentPrice??'');
  if (newPrice !== null && newPrice.trim() !== '') {{
      const num = parseFloat(newPrice);
      if (!isNaN(num)) {{
          const {{ error }} = await supabaseClient.from('stock_targets').upsert({{ symbol: symbol, target_price: num }});
          if (error) alert('更新失败：' + error.message); else fetchAndRenderTargets();
      }} else alert('输入无效，请输入纯数字。');
  }}
}}

async function deleteTarget(symbol) {{
  if(!confirm(`删除 [${{symbol}}] 的手工策略价？\\n\\n删除后该标的继续显示行情，但不再判断是否触发策略价。`))return;
  const {{error}}=await supabaseClient.from('stock_targets').delete().eq('symbol',symbol);
  if(error)alert('删除失败：'+error.message);else fetchAndRenderTargets();
}}

async function checkSession() {{
  let session = null;
  try {{ const result = await supabaseClient.auth.getSession(); session = result.data.session; }}
  catch (_error) {{ document.body.classList.remove('auth-pending'); document.body.classList.remove('private-mode'); authBtn.innerHTML = "🔐 登录暂不可用"; return; }}
  const authorized = Boolean(session && String(session.user.email || '').toLowerCase() === ADMIN_EMAIL.toLowerCase());
  document.body.classList.toggle('private-mode', authorized);
  document.body.classList.remove('auth-pending');
  if (session && !authorized) {{
      await supabaseClient.auth.signOut();
      isAdmin = false;
      authBtn.innerHTML = "🔐 登录私有看板";
      window.MAV?.toast('该账户没有主理人访问权限，已安全退出。','bad');
      window.SiteAnalytics?.onAuth(null, false);
      return;
  }}
  if (authorized) {{
      isAdmin = true; document.getElementById('modeTitle').innerText = "👑 主理人控制台已激活"; document.getElementById('modeDesc').innerText = "策略、观察池、期权与历史模块已解锁；真实持仓继续受 Supabase RLS 保护。";
      authBtn.innerHTML = "🔓 退出账号"; document.getElementById('modeTitle').style.color = "var(--red)"; document.getElementById('liveStatusText').innerText = "连接云端数据库";
      if (window.OptionV2) window.OptionV2.loadPrivatePositions();
      if (window.RollManager) window.RollManager.load();
      if (window.StockWatchlist) window.StockWatchlist.load();
      fetchAndRenderTargets();
  }} else {{
      isAdmin = false; authBtn.innerHTML = "🔐 登录私有看板";
      document.getElementById('modeTitle').innerText = "访客预览模式";
      document.getElementById('modeDesc').innerText = "未登录仅显示市场概览；策略、观察池与持仓模块需要主理人登录。";
      if (window.OptionV2) window.OptionV2.loadPrivatePositions();
      if (window.RollManager) window.RollManager.load();
  }}
  window.SiteAnalytics?.onAuth(session, authorized);
}}

async function handleAuth() {{
  const {{ data: {{ session }} }} = await supabaseClient.auth.getSession();
  if (session) {{ await supabaseClient.auth.signOut(); alert('已退出登录，恢复为公开展示模式。'); window.location.reload(); }} 
  else {{
      const email = prompt("请输入您的邮箱地址，获取免密登录链接：");
      if (!email) return;
      if (email.trim().toLowerCase() !== ADMIN_EMAIL.toLowerCase()) {{ alert('该邮箱没有主理人访问权限。'); return; }}
      authBtn.innerHTML = "⏳ 正在发送...";
      const {{ error }} = await supabaseClient.auth.signInWithOtp({{ email: email, options: {{ emailRedirectTo: window.location.origin + window.location.pathname }} }});
      if (error) {{ alert("发送失败: " + error.message); authBtn.innerHTML = "🔐 登录私有看板"; }} 
      else {{ alert("✅ 魔法验证链接已发送，请查收邮件！"); authBtn.innerHTML = "✉️ 请查收邮件"; }}
  }}
}}

window.addEventListener('load', checkSession);
supabaseClient.auth.onAuthStateChange((event, session) => {{ if (event === 'SIGNED_IN') checkSession(); }});

const CNHK_SYMBOLS = ['sh000001', 'sh000300', 'sz159307', 'hk03086', 'hk03416'];
let cnhkTimer = null;
function isAsiaMarketWindow() {{
  const parts = new Intl.DateTimeFormat('en-US', {{ timeZone:'Asia/Shanghai', weekday:'short', hour:'2-digit', minute:'2-digit', hourCycle:'h23' }}).formatToParts(new Date());
  const values = Object.fromEntries(parts.map(part => [part.type, part.value]));
  const minute = Number(values.hour) * 60 + Number(values.minute);
  return !['Sat','Sun'].includes(values.weekday) && minute >= 555 && minute <= 975;
}}
function fetchLiveCNHK() {{
  if (document.visibilityState === 'hidden') return;
  const script = document.createElement('script');
  script.src = `https://qt.gtimg.cn/q=${{CNHK_SYMBOLS.join(',')}}&r=${{Math.random()}}`;
  script.onload = () => {{
      CNHK_SYMBOLS.forEach(sym => {{
          const rawData = window['v_' + sym];
          if (rawData) {{
              const fields = rawData.split('~');
              if (fields.length > 5) {{
                  const currentPrice = parseFloat(fields[3]), prevClose = parseFloat(fields[4]), pctChange = (currentPrice - prevClose) / prevClose;
                  const decimals = sym.startsWith('sh') ? 2 : 3;
                  document.querySelectorAll(`[data-live-price="${{sym}}"]`).forEach(el => el.innerText = currentPrice.toFixed(decimals));
                  document.querySelectorAll(`[data-buy-zone="${{sym}}"]`).forEach(el => {{
                      const threshold=parseFloat(el.dataset.threshold),triggered=currentPrice<=threshold;
                      el.classList.toggle('triggered',triggered);
                      const strong=el.querySelector('strong');if(strong)strong.textContent=triggered?'已进入加仓区':`距加仓区 ${{(currentPrice-threshold).toFixed(3)}}`;
                  }});
                  document.querySelectorAll(`[data-live-chg="${{sym}}"]`).forEach(el => {{
                      el.innerText = (pctChange >= 0 ? "+" : "") + (pctChange * 100).toFixed(2) + "%";
                      el.classList.remove("positive", "negative"); el.classList.add(pctChange >= 0 ? "positive" : "negative");
                  }});
                  const nowText = new Intl.DateTimeFormat('zh-CN',{{timeZone:'Asia/Shanghai',hour:'2-digit',minute:'2-digit',hourCycle:'h23'}}).format(new Date());
                  document.querySelectorAll(`[data-market-state="${{sym}}"]`).forEach(el => el.textContent = `腾讯行情 · ${{isAsiaMarketWindow()?'交易时段':'休市'}}`);
                  document.querySelectorAll(`[data-live-time="${{sym}}"]`).forEach(el => el.textContent = `更新 ${{nowText}}`);
              }}
          }}
      }});
      document.head.removeChild(script);
  }};
  script.onerror = () => {{
      CNHK_SYMBOLS.forEach(sym => document.querySelectorAll(`[data-market-state="${{sym}}"]`).forEach(el => el.textContent='腾讯行情暂不可用 · 保留页面快照'));
      document.head.removeChild(script);
  }};
  document.head.appendChild(script);
}}
function scheduleCNHK() {{
  clearTimeout(cnhkTimer);
  cnhkTimer = setTimeout(() => {{ fetchLiveCNHK(); scheduleCNHK(); }}, isAsiaMarketWindow() ? 120000 : 15 * 60 * 1000);
}}
window.addEventListener('load', () => {{ fetchLiveCNHK(); scheduleCNHK(); }});
document.addEventListener('visibilitychange', () => {{ if (document.visibilityState === 'visible') {{ fetchLiveCNHK(); scheduleCNHK(); }} else clearTimeout(cnhkTimer); }});
</script><script src="assets/market-live.js?v={ASSET_VERSION}"></script><script src="assets/dashboard-v2.2.js?v={ASSET_VERSION}"></script><script src="assets/options-v2.js?v={ASSET_VERSION}"></script><script src="assets/roll-manager.js?v={ASSET_VERSION}"></script><script src="assets/stock-watchlist.js?v={ASSET_VERSION}"></script><script src="assets/finance-tools.js?v={ASSET_VERSION}"></script><script src="assets/opportunity-radar.js?v={ASSET_VERSION}"></script><script src="assets/site-analytics.js?v={ASSET_VERSION}"></script></body></html>'''

def push_to_supabase(data):
    supabase_url, supabase_key = os.environ.get("SUPABASE_URL"), os.environ.get("SUPABASE_KEY")
    if not supabase_url or not supabase_key: return
    req = urllib.request.Request(f"{supabase_url.rstrip('/')}/rest/v1/market_data", data=json.dumps({"payload": data}).encode("utf-8"), headers={"apikey": supabase_key, "Authorization": f"Bearer {supabase_key}", "Content-Type": "application/json", "Prefer": "return=minimal"}, method="POST")
    try: urllib.request.urlopen(req, timeout=15); print("✅ 成功将最新数据推送到 Supabase")
    except Exception as e: print(f"❌ 推送 Supabase 失败: {e}")

def validate_build_data(data):
    """阻止严重缺数的构建覆盖上一份可用站点。缓存宽度仍属于有效数据。"""
    errors = []
    indicators = data.get("market_indicators") or {}
    for key in ("spx", "vix"):
        row = indicators.get(key) or {}
        if not isinstance(row.get("close"), (int, float)) or row.get("close", 0) <= 0:
            errors.append(f"{key.upper()} 缺少有效收盘值")
    for key, minimum in (("core", 4), ("index", 4)):
        valid = sum(1 for row in (data.get(key) or {}).values() if isinstance(row, dict) and "error" not in row)
        if valid < minimum: errors.append(f"{key} 有效资产仅 {valid} 个，最低要求 {minimum} 个")
    stocks = data.get("stocks") or {}
    valid_stocks = sum(1 for row in stocks.values() if isinstance(row, dict) and "error" not in row)
    if stocks and valid_stocks / len(stocks) < 0.5:
        errors.append(f"观察池有效率仅 {valid_stocks}/{len(stocks)}")
    if "error" in (data.get("market_regime") or {}): errors.append("市场状态引擎不可用")
    if (data.get("raw_breadth") or {}).get("status") != "ok": errors.append("市场宽度没有可用的本次或缓存结果")
    if errors: raise RuntimeError("构建质量门未通过：" + "；".join(errors))


def atomic_write(path, content):
    directory = os.path.dirname(os.path.abspath(path))
    os.makedirs(directory, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".mav-build-", dir=directory, text=True)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except Exception:
        try: os.unlink(temporary)
        except FileNotFoundError: pass
        raise


if __name__ == '__main__':
    data = build()
    validate_build_data(data)
    docs_dir = os.path.join(os.path.dirname(__file__), '..', 'docs')
    out = os.path.join(docs_dir, 'data.json')
    html_out = os.path.join(docs_dir, 'index.html')
    atomic_write(out, json.dumps(data, ensure_ascii=False, indent=2))
    atomic_write(html_out, render_html(data))
    print(f'Generated {html_out} (quality gate passed)')
    push_to_supabase(data)
