"""
A股 / 港股 行情抓取模块
------------------------------------------------
用于并入 quant-dashboard 的 fetch_and_build.py。
只用标准库 urllib，不引入额外依赖，风格与现有脚本保持一致。

⚠️ 重要提醒（请在真正接入前务必做一次验证）：
腾讯行情接口没有官方文档，字段顺序是社区长期观察总结出来的约定，
不同证券类型（指数/股票/ETF/港股）字段个数可能有细微差异，
且腾讯可能在不通知的情况下调整格式。
建议第一次接入时，先跑一次 debug_print_raw() 把原始返回打印出来，
人工核对一遍字段位置（尤其是"当前价"和"昨收"两个位置容易混淆），
确认无误后再接入每日自动构建流程。
"""

import json
import urllib.request

# ---------- 标的清单 ----------
# 腾讯行情格式：sh=上海 sz=深圳 hk=港股
# 930955（中证红利低波100指数）实测在腾讯/新浪免费行情库里查不到——
# 它属于中证指数公司2016年后推出的"930xxx"定制策略指数系列，不经沪深交易所
# 实时行情系统分发，免费接口普遍没有这类指数的数据。已从抓取清单里去掉，
# 页面上改用159307（紧密跟踪该指数的场内ETF）的价格代理展示指数走势。
CN_HK_SYMBOLS = {
    "sz159307": {"name": "红利低波100ETF(场内，代理展示930955指数走势)", "kind": "etf"},
    "sh000001": {"name": "上证指数", "kind": "index"},
    "sh000300": {"name": "沪深300", "kind": "index"},
    "hk03086": {"name": "华夏纳指(港股)", "kind": "hk_etf"},
    "hk03416": {"name": "Global X 国指备兑(港股)", "kind": "hk_etf"},
}

# 场外联接基金：没有"实时行情"，只有盘中估值 + 收盘后的正式净值
OTC_FUNDS = {
    "021550": "红利低波100ETF联接(场外)",
}

TENCENT_URL = "http://qt.gtimg.cn/q={symbols}"
FUND_EST_URL = "http://fundgz.1234567.com.cn/js/{code}.js"

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}


def _http_get_text(url, timeout=10):
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        # 腾讯接口返回 GBK 编码
        return resp.read().decode("gbk", errors="ignore")


def debug_print_raw():
    """接入前先跑这个，人工核对字段顺序，别直接信下面的下标。"""
    symbols = ",".join(CN_HK_SYMBOLS.keys())
    raw = _http_get_text(TENCENT_URL.format(symbols=symbols))
    print(raw)


def fetch_tencent_quotes(symbols):
    """
    一次请求拿多个标的的行情。
    返回 {symbol: {"name":..., "price":..., "prev_close":..., "pct_change":...}}
    """
    joined = ",".join(symbols)
    raw = _http_get_text(TENCENT_URL.format(symbols=joined))
    out = {}
    for line in raw.strip().split(";"):
        line = line.strip()
        if not line or "=" not in line:
            continue
        var_part, val_part = line.split("=", 1)
        sym = var_part.replace("v_", "").strip()
        val = val_part.strip().strip('"')
        fields = val.split("~")
        if len(fields) < 5:
            out[sym] = {"error": "字段数量异常，接口格式可能变了，先跑 debug_print_raw() 核对"}
            continue
        try:
            name = fields[1]
            price = float(fields[3])
            prev_close = float(fields[4])
            pct_change = round((price - prev_close) / prev_close * 100, 2) if prev_close else None
            out[sym] = {"name": name, "price": price, "prev_close": prev_close, "pct_change": pct_change}
        except (ValueError, IndexError) as e:
            out[sym] = {"error": f"解析失败: {e}"}
    return out


FUND_HEADERS = {
    "User-Agent": HEADERS["User-Agent"],
    # 天天基金对没有 Referer 的请求（尤其是云服务器IP）有时会拦截，
    # 加上这个头模拟"从基金页面发起请求"，能明显提高成功率。
    "Referer": "http://fund.eastmoney.com/",
}


def fetch_fund_estimate(fund_code):
    """
    场外联接基金的盘中估值 / 昨日正式净值。
    这是天天基金公开使用的估值接口，返回 JSONP，需要手动剥掉外层函数名。
    收盘后 gsz(估算净值) 会等于 dwjz(正式净值)。
    """
    req = urllib.request.Request(FUND_EST_URL.format(code=fund_code), headers=FUND_HEADERS)
    with urllib.request.urlopen(req, timeout=10) as resp:
        raw = resp.read().decode("utf-8", errors="ignore")

    json_str = raw[raw.find("{"):raw.rfind("}") + 1]
    try:
        data = json.loads(json_str)
    except json.JSONDecodeError:
        # 失败时把原始返回打出来，而不是直接吞掉——
        # 如果这里打印出来是一段HTML或者空字符串，基本就能确认是IP被拦截，
        # 不是接口格式变了。截断到200字符避免刷屏。
        return {"error": "解析失败", "raw_response_preview": raw[:200]}
    return {
        "name": data.get("name"),
        "nav_date": data.get("jzrq"),       # 上一交易日正式净值日期
        "nav": data.get("dwjz"),            # 上一交易日正式净值
        "est_nav": data.get("gsz"),         # 当前估算净值
        "est_pct_change": data.get("gszzl"),# 当前估算涨跌幅(%)
        "est_time": data.get("gztime"),     # 估值时间
    }


def build_cn_hk_section():
    """整合成一个可以直接塞进 data.json 的结构。"""
    result = {"indices_and_etf": {}, "otc_funds": {}}

    quotes = fetch_tencent_quotes(list(CN_HK_SYMBOLS.keys()))
    for sym, meta in CN_HK_SYMBOLS.items():
        q = quotes.get(sym, {"error": "未取到数据"})
        result["indices_and_etf"][sym] = {**meta, **q}

    for code, name in OTC_FUNDS.items():
        est = fetch_fund_estimate(code)
        result["otc_funds"][code] = {"name": name, **est}

    return result


if __name__ == "__main__":
    # 第一次跑：先看原始返回，人工核对字段顺序
    print("=== 原始返回（用于核对字段顺序） ===")
    debug_print_raw()
    print("\n=== 解析后的结构 ===")
    print(json.dumps(build_cn_hk_section(), ensure_ascii=False, indent=2))
