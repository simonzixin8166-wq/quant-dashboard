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

# ================= 美股配置 =================
CORE_TIERS = {
    "QQQM": {"t1": 0.12, "t2": 0.18, "t3": 0.25},
    "QQQ":  {"t1": 0.12, "t2": 0.18, "t3": 0.25},
    "VGT":  {"t1": 0.15, "t2": 0.20, "t3": 0.30},
    "QLD":  {"t1": 0.25, "t2": 0.35, "t3": 0.50},
    "TQQQ": {"t1": 0.40, "t2": 0.50, "t3": 0.70},
    "VOO":  {"t1": 0.075, "t2": 0.10, "t3": 0.15},
}
# INDEX是内部实际抓取的清单——SPY虽然不在展示列表里，但首页QQQ&SPY走势图和
# 市场状态引擎的ATH兜底都依赖它，所以还是要抓，只是不在"指数&ETF"这个tab里单独展示。
INDEX = ["QQQ", "SPY", "VOO", "SMH", "TQQQ", "GCMAIN", "BTC/USD"]
# DISPLAYED_INDEX才是"指数&ETF"tab真正渲染出来的卡片列表。
# GCMAIN是Twelve Data的COMEX黄金期货连续合约代码，BTC/USD是Twelve Data的比特币兑美元代码，
# 如果这两个代码在你的Twelve Data账号权限下不可用，卡片会显示"获取失败"，不会影响其他资产。
DISPLAYED_INDEX = ["QQQ", "VOO", "SMH", "TQQQ", "GCMAIN", "BTC/USD"]
VOL_PROXY_SYM = "VIXY"

STOCK_META = {
    "SOFI": {"name": "SoFi Technologies"},
    "IREN": {"name": "Iris Energy"},
    "ORCL": {"name": "甲骨文"},
    "TSLA": {"name": "特斯拉"},
    "NVDA": {"name": "英伟达"},
    "TSM":  {"name": "台积电"},
    "LITE": {"name": "Lumentum"},
    "AVGO": {"name": "博通"},
    "MRVL": {"name": "美满电子"},
    "NBIS": {"name": "Nebius"},
    "GOOG": {"name": "谷歌"},
    "AMD":  {"name": "超威半导体"},
    "HOOD": {"name": "Robinhood"},
    "DRAM": {"name": "Roundhill内存芯片"},
    "SPCX": {"name": "SpaceX代币化产品"},
    # 下面5个是ETF，不是个股，放进观察池是因为想单独给它们设一个简单的Supabase提醒价，
    # 跟"策略引擎"tab里那套三档加仓线是两回事、互不影响，两边都能看，用途不同
    "QQQM": {"name": "纳指100(QQQM)"},
    "QLD":  {"name": "纳指2倍做多(QLD)"},
    "VGT":  {"name": "信息技术ETF(VGT)"},
    "QQQ":  {"name": "纳指100(QQQ)"},
    "VOO":  {"name": "标普500(VOO)"},
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
OTC_FUNDS = {}
TENCENT_URL = "http://qt.gtimg.cn/q={symbols}"
FUND_EST_URL = "http://fundgz.1234567.com.cn/js/{code}.js"

# ================= 辅助/信源抓取 =================
def fetch_supabase_targets():
    supabase_url = os.environ.get("SUPABASE_URL")
    supabase_key = os.environ.get("SUPABASE_KEY")
    if not supabase_url or not supabase_key:
        return None
    try:
        endpoint = f"{supabase_url.rstrip('/')}/rest/v1/stock_targets?select=symbol,target_price"
        req = urllib.request.Request(endpoint, headers={"apikey": supabase_key, "Authorization": f"Bearer {supabase_key}"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return {item["symbol"]: float(item["target_price"]) for item in data}
    except Exception as e:
        print(f"⚠️ 无法从 Supabase 获取策略价: {e}")
        return None

def get_true_aths(symbols):
    """
    逐个资产单独抓取真实历史最高点，而不是把所有资产打包成一次yfinance批量请求。
    之前的批量写法有个问题：只要这一次批量请求本身失败（限流/网络抖动），
    6个资产会同时集体fallback——这正是生产环境里"全部ETF都显示窗口回撤"的原因。
    改成一个一个单独抓，复用 fetch_yahoo_index()（这个函数已经在市场状态引擎那边
    稳定跑了一段时间），一个资产失败不会连累其他资产。
    """
    result = {}
    for sym in symbols:
        try:
            rows = fetch_yahoo_index(sym, range_="max")
            result[sym] = max(float(r["high"]) for r in rows)
        except Exception as e:
            print(f"⚠️ {sym} 真实ATH获取失败（不影响其他资产）: {e}")
        throttle()
    return result

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

# ================= 加载历史买点数据库 =================
def load_historical_signals():
    try:
        json_path = os.path.join(os.path.dirname(__file__), 'historical_signals.json')
        if not os.path.exists(json_path):
            return []
        with open(json_path, 'r', encoding='utf-8') as f:
            records = json.load(f)
            
        for r in records:
            rating = r.get("rating", "")
            r["source"] = "资产自身三档线" if rating.startswith("★") else "全市场宽度恐慌"
            
        records.sort(key=lambda r: r.get("date", ""), reverse=True)
        return records
    except Exception as e:
        print(f"❌ 读取历史买点失败: {e}")
        return []

# ================= 全市场宽度动态计算 =================
def calculate_daily_breadth():
    # 智能分流：A股/港股收盘那次轻量运行(UTC<12点)跳过这个重型计算，
    # 只在美股收盘那次(UTC>=12点)全量跑。这个判断之前被某次改动悄悄删掉了，
    # 导致 daily.yml 里的注释("任务2跳过重计算")变成了假话——
    # 实际上两次定时任务都在跑500只股票的完整下载，重新加回来。
    utc_hour = datetime.datetime.utcnow().hour
    if utc_hour < 12:
        msg = "当前为A股/港股收盘轻量运行时段，按设计跳过美股全市场宽度重计算（非异常）"
        print(f"🕒 {msg}")
        return {"status": "skip", "message": msg}

    try:
        json_path = os.path.join(os.path.dirname(__file__), 'sp500_constituents.json')
        if not os.path.exists(json_path):
            return {"status": "error", "message": "名单丢失"}

        with open(json_path, 'r') as f:
            tickers = json.load(f)
            
        data = yf.download(tickers, period="300d", interval="1d", threads=True, progress=False)
        closes = data['Close']
        
        ma20 = closes.rolling(window=20).mean()
        ma50 = closes.rolling(window=50).mean()
        ma200 = closes.rolling(window=200).mean()
        
        valid_count = closes.notna().sum(axis=1)
        b20 = (closes > ma20).sum(axis=1) / valid_count
        b50 = (closes > ma50).sum(axis=1) / valid_count
        b200 = (closes > ma200).sum(axis=1) / valid_count
        
        b20 = b20.dropna()
        if len(b20) < 11:
            return {"status": "error", "message": "数据不足"}
            
        latest_b20 = float(b20.iloc[-1])
        latest_b50 = float(b50.dropna().iloc[-1])
        latest_b200 = float(b200.dropna().iloc[-1])
        slope_10d = float(latest_b20 - b20.iloc[-11])
        
        return {
            "status": "ok",
            "b20": latest_b20, "b50": latest_b50, "b200": latest_b200, "slope_10d": slope_10d
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}

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

def tier_reached(drawdown, tiers):
    if drawdown is None or tiers is None: return 0, None
    loss = -drawdown 
    if loss >= tiers["t3"]: return 3, "三级"
    if loss >= tiers["t2"]: return 2, "二级"
    if loss >= tiers["t1"]: return 1, "一级"
    return 0, None

def analyze(symbol, rows, today, tiers=None, is_stock=False, true_ath=None):
    closes = [float(r["close"]) for r in rows]
    latest_close = closes[0]
    prev_close = closes[1] if len(closes) > 1 else latest_close
    
    # 提取当年(YTD)最高点用于卡片展示
    current_year = str(today.year)
    ytd_rows = [r for r in rows if r["datetime"].startswith(current_year)]
    ytd_high = max([float(r["high"]) for r in ytd_rows]) if ytd_rows else latest_close
    
    # 【核心安全机制】：策略触发线坚守 ATH，严防跨年重置 Bug！
    # 加入 math.isnan 判断防线，过滤崩溃数据
    if true_ath is not None and isinstance(true_ath, (int, float)) and not math.isnan(true_ath):
        all_time_high = true_ath
        ath_is_true = True
    else:
        # 如果 ATH 获取失败或为 NaN，退回使用抓取窗口(如260天)内的最高点
        all_time_high = max([float(r["high"]) for r in rows]) if rows else None
        ath_is_true = False
        
    out = {
        "date": rows[0]["datetime"][:10], "close": latest_close, "prev_close": prev_close,
        "day_chg": pct_change(latest_close, prev_close), "ytd_high": ytd_high,
        "rsi": calc_rsi(closes, 14), "dist_200ma": pct_change(latest_close, calc_sma(closes, 200)),
        "ath_is_true": ath_is_true
    }
    
    if is_stock:
        out.update({"open": float(rows[0]["open"]), "high": float(rows[0]["high"]), "low": float(rows[0]["low"])})
    else:
        # 触发器严格基于全期最高点(ATH)计算回撤
        drawdown = pct_change(latest_close, all_time_high)
        if ath_is_true:
            level, level_label = tier_reached(drawdown, tiers)
        else:
            # 窗口内最高点不是真实ATH，只能展示回撤数值供参考，不允许正式触发一/二/三级信号，
            # 避免"基准错误但系统看起来正常运行"这种最危险的静默错误
            level, level_label = 0, None
        out.update({
            "drawdown": drawdown, "tiers": tiers,
            "level": level, "level_label": level_label,
            "triggered": level > 0,
        })
    return out

# ================= 市场状态引擎 =================
def calc_market_regime(gspc_long_rows, spy_fallback_rows, vix_value, today, breadth_data):
    TIER_1, TIER_2, TIER_3 = 3, 5, 7
    TH_DRAWDOWN = -0.08
    TH_B20, TH_B50, TH_B200, TH_SLOPE = 0.20, 0.15, 0.50, -0.30

    rows_for_ath = gspc_long_rows if gspc_long_rows else spy_fallback_rows
    if not rows_for_ath:
        return {"error": "指数历史数据不足，无法计算回撤"}

    # 引擎同样使用历史全期数据计算回撤，不使用 YTD
    closes = [float(r["close"]) for r in rows_for_ath]
    latest = closes[0]
    ath = max([float(r["high"]) for r in rows_for_ath])
    drawdown = pct_change(latest, ath)

    drawdown_hit = isinstance(drawdown, (int, float)) and drawdown <= TH_DRAWDOWN and not math.isnan(drawdown)
    score = 2 if drawdown_hit else 0
    max_available_score = 9 

    conditions = []
    breadth_ok = breadth_data and breadth_data.get("status") == "ok"
    if breadth_ok:
        b20_hit = breadth_data["b20"] <= TH_B20
        if b20_hit: score += 2
        conditions.append({"key": "20天宽度", "threshold_note": f"≤{TH_B20:.0%}", "points": 2, "hit": b20_hit, "val": breadth_data["b20"]})
        
        b50_hit = breadth_data["b50"] <= TH_B50
        if b50_hit: score += 2
        conditions.append({"key": "50天宽度", "threshold_note": f"≤{TH_B50:.0%}", "points": 2, "hit": b50_hit, "val": breadth_data["b50"]})
        
        slope_hit = breadth_data["slope_10d"] <= TH_SLOPE
        if slope_hit: score += 2
        conditions.append({"key": "斜率冻点(20天宽10日骤降)", "threshold_note": f"≤{TH_SLOPE:.0%}", "points": 2, "hit": slope_hit, "val": breadth_data["slope_10d"]})
        
        b200_hit = breadth_data["b200"] <= TH_B200
        if b200_hit: score += 1
        conditions.append({"key": "200天宽度(绝对水平)", "threshold_note": f"≤{TH_B200:.0%}", "points": 1, "hit": b200_hit, "val": breadth_data["b200"]})
    else:
        max_available_score = 2

    if score >= TIER_3: tier, tier_label = "extreme", "极限恐慌"
    elif score >= TIER_2: tier, tier_label = "major", "重点恐慌"
    elif score >= TIER_1: tier, tier_label = "tier1", "一级恐慌"
    else: tier, tier_label = "normal", "正常"

    return {
        "score": score, "max_score": 9, "max_available_score": max_available_score,
        "tier": tier, "tier_label": tier_label,
        "drawdown": {"value": drawdown, "threshold": TH_DRAWDOWN, "hit": drawdown_hit, "points": 2},
        "conditions": conditions, "vix": vix_value,
        "breadth_status": (breadth_data or {}).get("status", "error"),
        "breadth_message": (breadth_data or {}).get("message", "宽度数据缺失"),
    }

def render_market_regime(mr):
    if "error" in mr:
        return f'<div class="card err"><div class="sym">市场状态引擎</div><div class="errmsg">{mr["error"]}</div></div>'
    tier_tone = {"normal": "good", "tier1": "warn", "major": "warn", "extreme": "bad"}.get(mr["tier"], "neutral")
    dd = mr["drawdown"]
    hit_badge = f'<span class="badge bad">命中 {dd["points"]}分</span>' if dd["hit"] else '<span class="badge neutral">未触发</span>'
    val_str = fmt_pct(dd["value"])
    
    active_row = f'<div class="row"><span>指数历史高点回撤（阈值 {fmt_pct(dd["threshold"])}）</span><span class="fw-bold">{val_str} {hit_badge}</span></div>'
    
    cond_rows = ""
    if mr.get("conditions"):
        for c in mr["conditions"]:
            c_val = fmt_pct(c["val"])
            c_badge = f'<span class="badge bad">命中 {c["points"]}分</span>' if c["hit"] else '<span class="badge neutral">未触发</span>'
            cond_rows += f'<div class="row"><span>{c["key"]}（阈值 {c["threshold_note"]}）</span><span class="fw-bold">{c_val} {c_badge}</span></div>'
            
    data_incomplete_note = ""
    if mr["max_available_score"] < mr["max_score"]:
        data_incomplete_note = '<span class="badge neutral" style="margin-left:6px">数据不完整</span>'

    errmsg = ""
    if not mr.get("conditions"):
        if mr.get("breadth_status") == "skip":
            errmsg = f'<div class="errmsg" style="padding:0 19px 16px;color:var(--muted);font-size:11px">ℹ️ {mr.get("breadth_message","")}，当前"正常"结论仅基于指数回撤这一项，不代表全市场宽度已确认正常。</div>'
        else:
            errmsg = f'<div class="errmsg" style="padding:0 19px 16px;color:var(--red);font-size:11px">⚠️ 宽度数据抓取异常：{mr.get("breadth_message","")}，已自动降级为只用"指数回撤"打分，"正常"结论不代表全市场宽度已确认正常，建议查日志排查。</div>'
        
    return f'''<div class="panel">
      <div class="panel-head"><strong>市场状态引擎</strong><span>有效评分 {mr["score"]}/{mr["max_available_score"]} 分（满分体系 {mr["max_score"]} 分）</span></div>
      <div class="pulse-list">
        <div class="pulse"><div><div class="pulse-label">当前风控评级</div><div class="pulse-main">{mr["tier_label"]}{data_incomplete_note}</div></div>
          <div class="pulse-right"><span class="badge {tier_tone}">{mr["score"]}/{mr["max_available_score"]} 可用分</span></div></div>
        {active_row}
        {cond_rows}
      </div>
      {errmsg}
    </div>'''

# ================= 核心构建 =================
def build():
    today = datetime.date.today()
    core, index, stocks, overview_charts = {}, {}, {}, {}
    data_status = {}

    sb_targets = fetch_supabase_targets()
    if sb_targets:
        for sym, tgt in sb_targets.items():
            if sym in STOCK_META:
                STOCK_META[sym]["target"] = tgt
        data_status["Supabase"] = "Connected"
    else:
        data_status["Supabase"] = "Fallback/Failed"

    core_aths = get_true_aths(list(CORE_TIERS.keys()))

    for name, tiers in CORE_TIERS.items():
        try:
            t_ath = core_aths.get(name)
            core[name] = analyze(name, fetch_time_series(name), today, tiers, true_ath=t_ath)
        except Exception as e:
            core[name] = {"error": str(e)}
        throttle()

    spy_rows_for_regime = None
    for name in INDEX:
        try:
            rows = fetch_time_series(name)
            index[name] = analyze(name, rows, today)
            if name in ("QQQ", "SPY"): 
                overview_charts[name] = [{"d": r["datetime"][:10], "c": float(r["close"])} for r in rows[:30][::-1]]
            if name == "SPY":
                spy_rows_for_regime = rows 
        except Exception as e:
            index[name] = {"error": str(e)}
        throttle()

    spx_data, spx_src, _ = fetch_real_index_or_proxy("%5EGSPC", "SPY", today)
    throttle()
    ixic_data, ixic_src, _ = fetch_real_index_or_proxy("%5EIXIC", "QQQ", today)
    throttle()
    vix_data, vix_src, _ = fetch_real_index_or_proxy("%5EVIX", VOL_PROXY_SYM, today)
    throttle()

    data_status["US Market"] = "Yahoo Real" if spx_src == "yahoo_real" else "ETF Proxy"
    data_status["VIX"] = "Yahoo Real" if vix_src == "yahoo_real" else "ETF Proxy"

    try:
        gspc_long_rows = fetch_yahoo_index("%5EGSPC", range_="max")
    except Exception:
        gspc_long_rows = None
        
    throttle()
    
    breadth_data = calculate_daily_breadth()
    data_status["Breadth"] = breadth_data.get("status", "error")
    
    vix_value = vix_data.get("close") if "error" not in vix_data else None
    market_regime = calc_market_regime(gspc_long_rows, spy_rows_for_regime, vix_value, today, breadth_data)

    for name in STOCKS:
        try:
            stocks[name] = analyze(name, fetch_time_series(name), today, is_stock=True)
        except Exception as e:
            stocks[name] = {"error": str(e)}
        throttle()
        
    cn_hk_data = {}
    try:
        res = fetch_tencent_quotes(list(CN_HK_SYMBOLS.keys()))
        cn_hk_data.update(res)
        data_status["CN_HK"] = "Tencent (Delayed)" if res else "Error"
    except: 
        data_status["CN_HK"] = "Error"
        
    try:
        if OTC_FUNDS:
            for code in OTC_FUNDS.keys():
                cn_hk_data[code] = fetch_fund_estimate(code)
            data_status["OTC"] = "EastMoney (Updated)"
        else:
            data_status["OTC"] = "None"
    except: 
        data_status["OTC"] = "Error"

    historical_signals = load_historical_signals()

    return {"updated": today.isoformat(), "core": core, "index": index,
            "stocks": stocks, "overview_charts": overview_charts,
            "cn_hk": cn_hk_data, "market_regime": market_regime,
            "historical_signals": historical_signals,
            "data_status": data_status,
            "market_indicators": {
                "spx": spx_data, "spx_source": spx_src,
                "ixic": ixic_data, "ixic_source": ixic_src,
                "vix": vix_data, "vix_source": vix_src,
            }}

# ================= HTML 组件与渲染 =================
# NaN 防护机制
def fmt_pct(x, digits=2): return f"{x*100:.{digits}f}%" if isinstance(x, (int, float)) and not math.isnan(x) else "-"
def fmt_num(x, digits=2): return f"{x:.{digits}f}" if isinstance(x, (int, float)) and not math.isnan(x) else "-"

def engine_item(name, r):
    if "error" in r: return f'<div class="engine-item"><div class="k">{name}</div><div class="v">-</div><div class="pt">数据获取失败</div></div>'
    level = r.get("level", 0)
    hit_cls = "hit" if level > 0 else ""
    drawdown_str = fmt_pct(r.get("drawdown"))
    tiers = r.get("tiers") or {}
    tiers_str = f'一级{fmt_pct(tiers.get("t1"),0)} / 二级{fmt_pct(tiers.get("t2"),0)} / 三级{fmt_pct(tiers.get("t3"),0)}'
    note = f'已达 {r.get("level_label")} 加仓线' if level > 0 else '未触发'
    ath_mark = " (ATH)" if r.get("ath_is_true") else " (窗口回撤)"
    return f'''<div class="engine-item {hit_cls}"><div class="k">{name} 回撤{ath_mark}</div><div class="v">{drawdown_str}</div><div class="pt">{note} · 阈值 {tiers_str}</div></div>'''

def card_etf(name, r):
    if "error" in r: return f'<div class="card err"><div class="sym">{name}</div><div class="errmsg">获取失败</div></div>'
    drawdown_cls = "neg-text fw-bold" if r["drawdown"] and r["drawdown"] < 0 else "fw-bold"
    return f'''<div class="card">
      <div class="card-header"><span class="sym">{name}</span><span class="price">${r["close"]:.2f}</span></div>
      <div class="divider"></div>
      <div class="row"><span>当年(YTD)最高</span><span class="fw-bold">${fmt_num(r["ytd_high"])}</span></div>
      <div class="row"><span>最高点回撤</span><span class="{drawdown_cls}">{fmt_pct(r["drawdown"])}</span></div>
      <div class="row"><span>RSI (14)</span><span class="fw-bold">{fmt_num(r["rsi"])}</span></div>
      <div class="row"><span>距 200MA</span><span class="fw-bold">{fmt_pct(r["dist_200ma"])}</span></div>
    </div>'''

def row_stock(sym, r):
    name = STOCK_META.get(sym, {}).get("name", sym)
    if "error" in r: 
        return f'<tr class="err"><td><div style="font-weight:600;color:var(--ink);">{name}</div><div style="font-size:11px;color:var(--muted);margin-top:2px;">{sym}</div></td><td colspan="9">获取数据失败</td></tr>'
    
    target = STOCK_META.get(sym, {}).get("target")
    target_str = f"${target:.2f}" if target else "-"
    action_html = '<span class="alert-text fw-bold ml">(信号触发!)</span>' if target and r["close"] <= target else ""
    chg_cls = "pos-text" if (r["day_chg"] or 0) >= 0 else "neg-text"
    chg_sign = "+" if (r["day_chg"] or 0) >= 0 else ""
    
    return f'''<tr>
        <td>
            <div style="font-weight:600; font-size:13.5px; color:var(--ink); line-height:1.2;">{name}</div>
            <div style="font-size:11px; color:var(--muted); margin-top:3px; font-weight:500;">{sym}</div>
        </td>
        <td class="fw-bold" id="close-{sym}">${r["close"]:.2f}</td><td class="{chg_cls}" id="chg-{sym}">{chg_sign}{fmt_pct(r["day_chg"])}</td>
        <td>${r["open"]:.2f}</td><td>${r["high"]:.2f}</td><td>${r["low"]:.2f}</td>
        <td>${fmt_num(r["ytd_high"])}</td><td>{fmt_num(r["rsi"])}</td><td>{fmt_pct(r["dist_200ma"])}</td>
        <td><b id="target-{sym}">{target_str}</b> <span id="action-{sym}">{action_html}</span></td>
    </tr>'''

def mkt_card_a(title, data, code=""):
    if not data or "error" in data:
        return f'<div class="mkt-card"><div class="name">{title}</div><div class="val" style="font-size:14px;color:var(--muted);margin-top:12px">接口拦截/闭市</div></div>'
    price = data.get("price", 0)
    chg = data.get("day_chg", 0)
    chg_str = f"+{fmt_pct(chg)}" if chg >= 0 else fmt_pct(chg)
    color_cls = "positive" if chg >= 0 else "negative"
    return f'<div class="mkt-card"><div class="name">{title}</div><div class="val" id="price-{code}">{price:,.3f}</div><div class="chg {color_cls}" id="chg-{code}">{chg_str}</div></div>'

def render_html(data):
    engine_html = "".join(engine_item(k, v) for k, v in data["core"].items())
    core_levels = [v.get("level", 0) for v in data["core"].values() if "error" not in v]
    max_level = max(core_levels) if core_levels else 0
    level_names = {0: "正常 · 未触发", 1: "一级加仓线", 2: "二级加仓线", 3: "三级加仓线"}
    engine_badge_cls = "normal" if max_level == 0 else "t2"
    index_html = "".join(card_etf(k, data["index"][k]) for k in DISPLAYED_INDEX if k in data["index"])
    stock_html = "".join(row_stock(k, v) for k, v in data["stocks"].items())

    signals_html = ""
    for s in data.get("historical_signals", []):
        badge_cls = "warn" if "一级" in s['rating'] else ("bad" if "重点" in s['rating'] or "极限" in s['rating'] else "neutral")
        source_cls = "neutral" if s.get("source") == "资产自身三档线" else "good"
        signals_html += f'''<tr>
            <td style="text-align:left; font-weight:600;">{s['symbol']}</td>
            <td>{s['date']}</td>
            <td class="fw-bold">${s['price']:.4f}</td>
            <td class="neg-text">{fmt_pct(s['drawdown'])}</td>
            <td><span class="badge {badge_cls}">{s['rating']}</span></td>
            <td><span class="badge {source_cls}">{s.get('source','-')}</span></td>
        </tr>'''

    mi = data.get("market_indicators", {})
    cn = data.get("cn_hk", {})
    ds = data.get("data_status", {})
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
    
    # 将股票现价传给前端期权监控雷达
    prices_map = {}
    for k, v in data.get("stocks", {}).items():
        if "error" not in v: prices_map[k] = v.get("close", 0)
    for k, v in data.get("core", {}).items():
        if "error" not in v: prices_map[k] = v.get("close", 0)
    prices_json = json.dumps(prices_map, ensure_ascii=False)

    market_regime_html = render_market_regime(data.get("market_regime", {"error": "无数据"}))

    return f'''<!DOCTYPE html><html lang="zh-CN"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"><title>myAlphaView · Market Intelligence</title>
<meta name="author" content="Simon">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,380;9..144,520;9..144,620&family=Inter:wght@400;500;600;700;800&display=swap" rel="stylesheet">
<script src="https://cdn.jsdelivr.net/npm/chart.js@4"></script>
<script src="https://cdn.jsdelivr.net/npm/@supabase/supabase-js@2"></script>
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
}}
*{{box-sizing:border-box;margin:0;padding:0}} body{{font-family:var(--sans);background:var(--bg);color:var(--ink);min-height:100vh;-webkit-font-smoothing:antialiased}} .app{{display:flex;min-height:100vh}}
.sidebar{{width:252px;background:linear-gradient(190deg,var(--nav),var(--nav2));color:#fff;padding:24px 16px;position:fixed;inset:0 auto 0 0;z-index:20;display:flex;flex-direction:column}}
.brand{{display:flex;align-items:center;gap:12px;padding:6px 8px 24px;border-bottom:1px solid var(--navline)}}
.mav-brand-mark{{width:38px;height:38px;border-radius:12px;flex:0 0 auto;background:linear-gradient(135deg,#d8a75c,var(--brass));display:grid;place-items:center;box-shadow:0 8px 18px rgba(184,134,58,.35)}}
.brand strong{{display:block;font-family:var(--serif);font-size:17px;font-weight:600;letter-spacing:.2px}} .brand small{{display:block;color:var(--navmuted);margin-top:2px;font-size:11px}}
.nav-group{{margin-top:22px}} .nav-title{{color:#5c6178;font-size:10.5px;font-weight:600;letter-spacing:.5px;margin:0 10px 8px}}
.nav-menu{{list-style:none;display:grid;gap:3px}} .nav-menu li{{display:flex;align-items:center;gap:11px;padding:10px 12px;border-radius:9px;color:var(--navmuted);cursor:pointer;font-size:13.5px;font-weight:500;transition:.16s}}
.nav-menu li:hover{{background:rgba(255,255,255,.06);color:#fff}} .nav-menu li.active{{color:#fff;background:rgba(184,134,58,.16);box-shadow:inset 2.5px 0 0 var(--brass)}} .nav-icon{{width:18px;text-align:center;font-size:14px}}
.nav-menu li .tag{{margin-left:auto;font-size:9px;background:rgba(255,255,255,.1);color:var(--navmuted);padding:2px 6px;border-radius:99px;font-weight:600}}
.sidebar-footer{{margin-top:auto;color:#565b71;font-size:10.5px;line-height:1.7;padding-top:16px;border-top:1px solid var(--navline)}}

.auth-btn-top {{ background: var(--brass); color: #fff; border: none; padding: 6px 14px; border-radius: 6px; cursor: pointer; font-size: 11.5px; font-weight: 600; transition: 0.2s; box-shadow: 0 4px 10px rgba(184,134,58,.3); margin-left: 12px; }}
.auth-btn-top:hover {{ background: #a67732; transform: translateY(-1px); }}

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

.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:14px}} .card{{background:var(--surface);border:1px solid var(--line);border-radius:12px;padding:18px;box-shadow:var(--shadow)}} .card-header{{display:flex;justify-content:space-between;align-items:center}} .sym{{font-weight:700;font-size:16px}} .price{{font-size:20px;font-weight:700;font-family:var(--serif)}} .divider{{height:1px;background:var(--line);margin:14px 0}} .row{{display:flex;justify-content:space-between;font-size:12px;color:var(--muted);margin-bottom:10px}} .fw-bold{{color:var(--ink);font-weight:600}} .pos-text{{color:var(--green)}} .neg-text{{color:var(--red)}} .alert-text{{color:var(--red)}} .errmsg{{color:var(--muted);font-size:12px;margin-top:8px}} 
.table-container{{overflow-x:auto;background:var(--surface);border:1px solid var(--line);border-radius:12px;box-shadow:var(--shadow)}} table{{width:100%;border-collapse:collapse;text-align:right;white-space:nowrap;font-variant-numeric:tabular-nums}} th,td{{padding:14px;border-bottom:1px solid var(--line);font-size:13px}} th{{background:var(--surface2);color:var(--muted);font-weight:600;font-size:11.5px}} th:nth-child(1),td:nth-child(1){{text-align:left}} tr:hover td{{background:#fbfbfb}}

.opt-grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(250px,1fr));gap:14px}} .mkt-card{{background:var(--surface);border:1px solid var(--line);border-radius:13px;padding:17px 18px;box-shadow:var(--shadow)}} .mkt-card .name{{font-size:12.5px;color:var(--muted);display:flex;justify-content:space-between}} .mkt-card .val{{font-family:var(--serif);font-size:21px;margin-top:8px}} .mkt-card .chg{{font-size:11.5px;font-weight:600;margin-top:4px}} .soon{{font-size:9.5px;background:var(--surface2);color:var(--muted);padding:2px 7px;border-radius:99px;font-weight:600}}
.footer{{color:#9a9484;font-size:10.5px;line-height:1.7;text-align:center;padding:34px 0 10px}}
.tab-pane{{display:none;animation:fade .3s ease}} .tab-pane.active{{display:block}} @keyframes fade{{from{{opacity:0;transform:translateY(5px)}}to{{opacity:1;transform:none}}}}

/* 期权持仓面板特别样式 */
.opt-status {{ display:inline-flex; align-items:center; gap:5px; font-weight:600; font-size:11px; }}
.opt-status.safe {{ color: var(--green); }}
.opt-status.warn {{ color: var(--amber); }}
.opt-status.danger {{ color: var(--red); }}
.opt-status::before {{ content:""; display:block; width:6px; height:6px; border-radius:50%; }}
.opt-status.safe::before {{ background: var(--green); }}
.opt-status.warn::before {{ background: var(--amber); }}
.opt-status.danger::before {{ background: var(--red); }}

/* ================= 苹果 iPad & iPhone 响应式适配 ================= */
@media (max-width: 1024px) {{
  .dashboard-grid {{ grid-template-columns: 1fr; }} 
  .metrics {{ grid-template-columns: repeat(2, 1fr); }} 
}}

@media (max-width: 768px) {{
  .app {{ flex-direction: column; }}
  .sidebar {{ position: static; width: 100%; padding: 16px 20px; border-bottom: 1px solid var(--navline); }}
  .nav-group {{ margin-top: 16px; }}
  .nav-menu {{ display: flex; flex-wrap: wrap; gap: 8px; }}
  .nav-menu li {{ font-size: 12px; padding: 8px 12px; }}
  .main {{ margin-left: 0; width: 100%; }}
  .topbar {{ padding: 12px 20px; height: auto; flex-direction: column; align-items: flex-start; gap: 12px; }}
  .top-meta {{ flex-wrap: wrap; width: 100%; justify-content: space-between; }}
  .content {{ padding: 20px; }}
  .hero {{ flex-direction: column; align-items: flex-start; gap: 16px; }}
  .public-note {{ width: 100%; flex: auto; }}
  .metrics {{ grid-template-columns: 1fr; }} 
  .engine::after {{ display: none; }}
  .engine-top {{ flex-direction: column; gap: 12px; }}
  .table-container {{ overflow-x: auto; -webkit-overflow-scrolling: touch; border-radius: 8px; }}
  th, td {{ padding: 10px; font-size: 12px; }}
}}
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
<div class="sidebar-footer">
  公开研究版 · 不展示个人真实资产<br>数据仅供研究演示
</div>
</aside>

<main class="main"><header class="topbar"><div class="breadcrumb">myAlphaView / <strong id="bc-title">市场总览</strong></div><div class="top-meta">
  <span id="liveStatus"><i class="live-dot"></i><span id="liveStatusText">数据抓取成功</span></span>
  <span id="updateTime">更新: {data['updated']}</span>
  <button id="authBtn" class="auth-btn-top" onclick="handleAuth()">🔐 登录私有看板</button>
</div></header><div class="content">

<!-- TAB 1: 市场总览 -->
<div id="tab-overview" class="tab-pane active">
<section class="hero"><div><h1>看清市场在说什么，而不是账户在做什么。</h1><p>公开版投资研究面板：聚焦市场趋势、回撤、波动率与策略触发条件。</p></div><div class="public-note"><b id="modeTitle">公开展示模式</b><span id="modeDesc">这里展示的是研究指标与策略信号，不代表任何个人账户的实际仓位或收益。</span></div></section>
<section class="section"><div class="section-head"><h2>市场核心指标</h2><p>自动更新</p></div><div class="metrics">{metric_card('纳斯达克综合指数',qqq_value,qqq_chg,qqq_note,'good' if isinstance(qqq_chg,(int,float)) and qqq_chg>=0 else 'warn')}{metric_card('标普500指数',spy_value,spy_chg,spy_note,'good' if isinstance(spy_chg,(int,float)) and spy_chg>=0 else 'warn')}{metric_card('VIX恐慌指数',vol_display,None,vix_note,vol_tone)}{metric_card('红利低波100 (159307)',sz_val,sz_chg,'A股红利代理 · 腾讯行情','good')}</div></section>

<section class="section">{market_regime_html}</section>

<section class="section"><div class="section-head"><h2>QQQ & SPY · 近 30 个交易日</h2><p>历史走势</p></div><div class="dashboard-grid"><div class="panel"><div class="panel-head"><strong>趋势对比</strong><span>收盘价</span></div><div class="chart-wrap"><canvas id="trendChart"></canvas></div></div><div class="panel"><div class="panel-head"><strong>Data Status Center</strong><span>数据状态监控</span></div><div class="pulse-list">
<div class="pulse"><div><div class="pulse-label">美股宽基指数</div><div class="pulse-main">{ds.get('US Market')}</div></div></div>
<div class="pulse"><div><div class="pulse-label">全市场宽度扫描</div><div class="pulse-main">{ds.get('Breadth')}</div></div></div>
<div class="pulse"><div><div class="pulse-label">亚太股指代理</div><div class="pulse-main">{ds.get('CN_HK')}</div></div></div>
<div class="pulse"><div><div class="pulse-label">场外基金接口</div><div class="pulse-main">{ds.get('OTC')}</div></div></div>
<div class="pulse"><div><div class="pulse-label">云端策略参数集</div><div class="pulse-main">{ds.get('Supabase')}</div></div></div>
</div></div></div></section>
</div>

<!-- TAB 2: 策略引擎 -->
<div id="tab-engine" class="tab-pane">
<section class="hero"><div><h1>核心策略信号</h1><p>用回撤、RSI 与长期均线观察核心 ETF 的风险与潜在策略触发点。</p></div></section>
<section class="section"><div class="engine"><div class="engine-top"><div><div class="engine-label">STRATEGY ENGINE · 核心ETF三档加仓线</div><div class="engine-title">当前状态：实时监测</div></div><div class="engine-badge {engine_badge_cls}">{level_names[max_level]}</div></div>
<div class="engine-grid">{engine_html}</div><div class="engine-foot">分级规则：每个核心ETF各自设有一级/二级/三级三档加仓线。回撤判定严格使用历史全期最高点(ATH)或跨年窗口作为打分基准，严防短视。此处展示规则与信号，不展示实盘资金规模。</div></div></section>
</div>

<!-- TAB 3: 指数与 ETF -->
<div id="tab-index" class="tab-pane"><section class="hero"><div><h1>指数与行业 ETF</h1><p>从宽基指数到行业 ETF，快速观察价格、当年最高点回撤、RSI 与 200 日均线距离。</p></div></section><section class="section"><div class="grid">{index_html}</div></section></div>

<!-- TAB 4: A股 & 港股 & 红利 -->
<div id="tab-cn-hk" class="tab-pane">
<section class="hero"><div><h1>A股港股 & 红利低波</h1><p>自动同步腾讯行情。中证红利低波100指数(930955)本身不在免费行情源覆盖范围内，用紧密跟踪该指数的场内ETF(159307)代理展示走势。</p></div></section>
<section class="section"><div class="section-head"><h2>大盘与红利核心池</h2><p>盘中自动实时跳动刷新</p></div><div class="opt-grid">
{mkt_card_a("上证指数", cn.get("sh000001"), "sh000001")}
{mkt_card_a("沪深300", cn.get("sh000300"), "sh000300")}
{mkt_card_a("红利低波100 ETF (159307)", cn.get("sz159307"), "sz159307")}
</div></section>
<section class="section"><div class="section-head"><h2>港股跨境池</h2><p>盘中自动实时跳动刷新</p></div><div class="opt-grid">
{mkt_card_a("华夏纳指 (港股)", cn.get("hk03086"), "hk03086")}
{mkt_card_a("国指备兑 (港股)", cn.get("hk03416"), "hk03416")}
</div></section>
</div>

<!-- TAB 5: 个股观察池 -->
<div id="tab-stocks" class="tab-pane"><section class="hero"><div><h1>个股观察池</h1><p>包含中英文名称对照及核心技术指标监控。</p></div></section><section class="section"><div class="table-container"><table><thead><tr><th>名称代码</th><th>最新价</th><th>涨跌幅</th><th>开盘</th><th>最高</th><th>最低</th><th>当年(YTD)最高</th><th>RSI(14)</th><th>距200MA</th><th>策略参考价</th></tr></thead><tbody id="stocksTableBody">{stock_html}</tbody></table></div></section></div>

<!-- TAB 6: 期权自查 (V1动态监控) -->
<div id="tab-options" class="tab-pane">
<section class="hero"><div><h1>期权持仓监控 V1</h1><p>下表数据为<b style="color:var(--brass)">示例占位数据</b>，用于演示 DTE 时间衰减、盈亏平衡距离与风控预警状态的计算方式，不是任何真实持仓。不展示真实资金规模与实盘仓位。</p></div></section>
<section class="section">
    <div class="table-container">
        <table>
            <thead>
                <tr>
                    <th style="text-align:left;">合约代码</th>
                    <th>方向</th>
                    <th>行权价</th>
                    <th>到期日</th>
                    <th>建仓成本</th>
                    <th>盈亏平衡点</th>
                    <th>正股现价</th>
                    <th>距盈亏平衡</th>
                    <th>风控状态</th>
                </tr>
            </thead>
            <tbody id="optionsTableBody">
                <!-- 由 JavaScript 渲染 -->
            </tbody>
        </table>
    </div>
</section>
<section class="section"><p style="font-size:11.5px;color:var(--muted);line-height:1.7">💡 V1 使用说明：此面板采用盲盒脱敏架构，不显示你持有的真实张数和美金数额。仅展示该合约“单张”相对于当前正股价的风控健康度（基于云端每日最新的正股抓取价格测算）。</p></section>
</div>

<!-- TAB 7: 历史买点归档 -->
<div id="tab-archive" class="tab-pane">
<section class="hero"><div><h1>历史买点归档数据库</h1><p>完整回溯 2005 年以来各大核心资产触发一级、重点及极限加仓信号的黄金历史买点，验证策略透明度。</p></div></section>
<section class="section"><div class="table-container"><table><thead><tr><th style="text-align:left;">资产代号</th><th>触发日期</th><th>触发收盘价</th><th>当时全期回撤幅度</th><th>触发加仓评级</th><th>规则体系</th></tr></thead><tbody id="archiveTableBody">{signals_html}</tbody></table></div></section>
<section class="section"><p style="font-size:11.5px;color:var(--muted);line-height:1.7">同一资产同一天可能出现两条记录——"资产自身三档线"是该ETF自己相对真实全期最高点的回撤触发的加仓线；"全市场宽度恐慌"是标普500全市场宽度指标触发的分级信号。两套规则相互独立，同一天都触发是正常情况，不是数据重复。</p></section></div>

<div class="footer">© 2026 myAlphaView · Built by Simon · Public Research Dashboard<br>市场数据与策略指标仅供研究、学习与信息参考，不构成投资建议。</div>
</div></main></div>

<script>
const DATA = {chart_json};
const STOCK_PRICES = {prices_json};

function switchTab(id,el){{
  document.querySelectorAll('.tab-pane').forEach(t=>t.classList.remove('active'));
  document.querySelectorAll('.nav-menu li').forEach(l=>l.classList.remove('active'));
  document.getElementById(id).classList.add('active');
  el.classList.add('active');
  document.getElementById('bc-title').innerText = el.innerText.replace('NEW', '').replace(/^[◆◒◫◇⌁⚑📜]/u, '').trim();
  window.scrollTo({{top:0,behavior:'smooth'}});
}}

window.addEventListener('load',function(){{
  const c=document.getElementById('trendChart');
  const qq=DATA.QQQ||[], sp=DATA.SPY||[];
  if(qq.length && sp.length) {{
      const labels=qq.map(x=>x.d), qv=qq.map(x=>x.c), sv=sp.map(x=>x.c);
      new Chart(c,{{type:'line',data:{{labels,datasets:[
          {{label:'QQQ',data:qv,borderColor:'#b8863a',backgroundColor:'rgba(184,134,58,.08)',fill:true,borderWidth:2,pointRadius:0,tension:.35,yAxisID:'y'}},
          {{label:'SPY',data:sv,borderColor:'#1c7a4c',backgroundColor:'transparent',borderWidth:2,pointRadius:0,tension:.35,yAxisID:'y1'}}
      ]}},options:{{responsive:true,maintainAspectRatio:false,interaction:{{mode:'index',intersect:false}},plugins:{{legend:{{position:'top',align:'end'}}}},scales:{{x:{{grid:{{display:false}},ticks:{{maxTicksLimit:6}}}},y:{{position:'left',grid:{{color:'#eee9dc'}}}},y1:{{position:'right',grid:{{drawOnChartArea:false}}}}}}}}}});
  }}

  // ================= 渲染期权监控面板 =================
  // ⚠️ 以下是示例占位数据，不是真实持仓，仅用于演示这个面板的计算逻辑。
  // 确认过：2026-09 core确认这是占位数据。以后如果要接入真实持仓，
  // 记得改掉这个数组名和上面hero区的文字说明。
  const EXAMPLE_OPTION_POSITIONS = [
      {{ symbol: "NVDA", type: "Call", strike: 155, expiry: "2026-05-22", cost: 2.13 }},
      {{ symbol: "TSLA", type: "Put", strike: 220, expiry: "2026-10-16", cost: 8.50 }}
  ];
  const OPTION_POSITIONS = EXAMPLE_OPTION_POSITIONS;

  const tbody = document.getElementById("optionsTableBody");
  const today = new Date();

  if(OPTION_POSITIONS.length === 0) {{
      tbody.innerHTML = `<tr><td colspan="9" style="text-align:center; color:var(--muted)">当前没有记录的期权持仓</td></tr>`;
  }} else {{
      let html = "";
      OPTION_POSITIONS.forEach(opt => {{
          const expDate = new Date(opt.expiry);
          const dte = Math.ceil((expDate - today) / (1000 * 60 * 60 * 24));
          const currentPrice = STOCK_PRICES[opt.symbol] || 0;
          
          let breakEven = 0;
          if (opt.type === "Call") {{ breakEven = opt.strike + opt.cost; }} 
          else {{ breakEven = opt.strike - opt.cost; }}
          
          // Put 的盈利方向和 Call 相反：Call 是现价越高于盈亏平衡价越好，
          // Put 是现价越低于盈亏平衡价越好，两者不能共用同一个方向的公式，
          // 否则 Put 的正负号和风险颜色会反过来。
          let distPct = 0;
          if (currentPrice) {{
              distPct = opt.type === "Call"
                  ? (currentPrice - breakEven) / breakEven * 100
                  : (breakEven - currentPrice) / breakEven * 100;
          }}
          const distStr = currentPrice ? (distPct >= 0 ? "+" : "") + distPct.toFixed(2) + "%" : "-";
          
          let statusHtml = "";
          if(dte < 14) {{
              statusHtml = '<span class="opt-status danger">极高风险 (DTE<14)</span>';
          }} else if(dte < 45) {{
              statusHtml = '<span class="opt-status warn">注意时间损耗</span>';
          }} else {{
              statusHtml = '<span class="opt-status safe">周期健康</span>';
          }}
          
          html += `<tr>
              <td style="text-align:left; font-weight:600; color:var(--ink)">${{opt.symbol}}</td>
              <td>${{opt.type}}</td>
              <td class="fw-bold">$${{opt.strike.toFixed(2)}}</td>
              <td>${{opt.expiry}}</td>
              <td>$${{opt.cost.toFixed(2)}}</td>
              <td style="color:var(--navy); font-weight:600">$${{breakEven.toFixed(2)}}</td>
              <td class="fw-bold">$${{currentPrice ? currentPrice.toFixed(2) : "-"}}</td>
              <td class="${{distPct >= 0 ? 'pos-text' : 'neg-text'}}">${{distStr}}</td>
              <td>${{statusHtml}}</td>
          </tr>`;
      }});
      tbody.innerHTML = html;
  }}
}});

// ================= Supabase 动态数据与身份验证 =================
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
          const targetEl = document.getElementById(`target-${{row.symbol}}`);
          const closeEl = document.getElementById(`close-${{row.symbol}}`);
          const actionEl = document.getElementById(`action-${{row.symbol}}`);
          
          if (targetEl && closeEl) {{
              targetEl.innerHTML = `$${{row.target_price.toFixed(2)}}`;
              if (isAdmin) {{
                  targetEl.innerHTML += ` <span style="cursor:pointer;font-size:12px;margin-left:6px;filter:grayscale(1) opacity(0.5);transition:0.2s;" onmouseover="this.style.filter='none'" onmouseout="this.style.filter='grayscale(1) opacity(0.5)'" onclick="editTarget('${{row.symbol}}', ${{row.target_price}})" title="修改策略价">✏️</span>`;
              }}
              const closePrice = parseFloat(closeEl.innerText.replace('$', ''));
              if (closePrice <= row.target_price) {{
                  actionEl.innerHTML = '<span class="alert-text fw-bold ml" style="margin-left:4px;">(信号触发!)</span>';
              }} else {{
                  actionEl.innerHTML = '';
              }}
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
          if (error) {{
              alert('更新失败，权限不足或网络异常：' + error.message);
          }} else {{
              fetchAndRenderTargets();
          }}
      }} else {{
          alert('输入无效，请输入纯数字。');
      }}
  }}
}}

async function checkSession() {{
  const {{ data: {{ session }} }} = await supabaseClient.auth.getSession();
  if (session) {{
      if (session.user.email === ADMIN_EMAIL) {{
          isAdmin = true;
          document.getElementById('modeTitle').innerText = "👑 主理人控制台已激活";
          document.getElementById('modeDesc').innerText = "您现在可以在下方个股面板中，直接点击✏️修改全局策略触发价。";
      }} else {{
          isAdmin = false;
          document.getElementById('modeTitle').innerText = "🔥 资金与策略模型已解锁";
          document.getElementById('modeDesc').innerText = "您已安全登录，当前正在展示最新的高级量化策略信号。";
      }}
      authBtn.innerHTML = "🔓 退出账号";
      document.getElementById('modeTitle').style.color = "var(--red)";
      document.getElementById('liveStatusText').innerText = "连接云端数据库";
  }} else {{
      isAdmin = false;
      authBtn.innerHTML = "🔐 登录私有看板";
  }}
  fetchAndRenderTargets();
}}

async function handleAuth() {{
  const {{ data: {{ session }} }} = await supabaseClient.auth.getSession();
  if (session) {{
      await supabaseClient.auth.signOut();
      alert('已退出登录，恢复为公开展示模式。');
      window.location.reload();
  }} else {{
      const email = prompt("欢迎探索 myAlphaView 私有量化模型。\\n请输入您的邮箱地址，我们将为您发送免密登录/免费注册链接：");
      if (!email) return;
      
      authBtn.innerHTML = "⏳ 正在发送...";
      const {{ error }} = await supabaseClient.auth.signInWithOtp({{
          email: email,
          options: {{ emailRedirectTo: window.location.origin + window.location.pathname }}
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

window.addEventListener('load', checkSession);
supabaseClient.auth.onAuthStateChange((event, session) => {{
  if (event === 'SIGNED_IN') checkSession();
}});

// ================= A股/港股 实时跳动引擎 =================
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
                  const currentPrice = parseFloat(fields[3]);
                  const prevClose = parseFloat(fields[4]);
                  const pctChange = (currentPrice - prevClose) / prevClose;
                  
                  const priceEl = document.getElementById(`price-${{sym}}`);
                  const chgEl = document.getElementById(`chg-${{sym}}`);
                  
                  if (priceEl && chgEl) {{
                      priceEl.innerText = currentPrice.toFixed(3);
                      const chgStr = (pctChange >= 0 ? "+" : "") + (pctChange * 100).toFixed(2) + "%";
                      chgEl.innerText = chgStr;
                      if (pctChange >= 0) {{
                          chgEl.className = "chg positive";
                      }} else {{
                          chgEl.className = "chg negative";
                      }}
                  }}
              }}
          }}
      }});
      document.head.removeChild(script);
  }};
  document.head.appendChild(script);
}}

window.addEventListener('load', () => {{
  setInterval(fetchLiveCNHK, 5000);
}});
</script></body></html>'''

# ================= 数据库推送逻辑 =================
def push_to_supabase(data):
    supabase_url = os.environ.get("SUPABASE_URL")
    supabase_key = os.environ.get("SUPABASE_KEY")
    
    if not supabase_url or not supabase_key:
        return
        
    endpoint = f"{supabase_url.rstrip('/')}/rest/v1/market_data"
    headers = {
        "apikey": supabase_key,
        "Authorization": f"Bearer {supabase_key}",
        "Content-Type": "application/json",
        "Prefer": "return=minimal"
    }
    body = json.dumps({"payload": data}).encode("utf-8")
    req = urllib.request.Request(endpoint, data=body, headers=headers, method="POST")
    
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            print(f"✅ 成功将最新数据推送到 Supabase 数据库！状态码: {resp.status}")
    except Exception as e:
        print(f"❌ 推送 Supabase 失败: {e}")

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
    
    push_to_supabase(data)
