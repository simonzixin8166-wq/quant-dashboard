"""Static dashboard universe configuration extracted from fetch_and_build.py."""
INDEX = ["QQQ", "SPY", "VOO", "SMH", "TQQQ", "GCMAIN", "BTC/USD"]
DISPLAYED_INDEX = ["QQQ", "VOO", "SMH", "TQQQ", "GCMAIN", "BTC/USD"]
VOL_PROXY_SYM = "VIXY"
BREADTH_EQUAL_WEIGHT_PROXIES = ["RSP", "QQQE"]

STOCK_META = {
    "SOFI": {"name": "SoFi Technologies"}, "IREN": {"name": "Iris Energy"}, "ORCL": {"name": "甲骨文"},
    "TSLA": {"name": "特斯拉"}, "NVDA": {"name": "英伟达"}, "TSM": {"name": "台积电"},
    "LITE": {"name": "Lumentum"}, "AVGO": {"name": "博通"}, "MRVL": {"name": "美满电子"},
    "NBIS": {"name": "Nebius"}, "GOOG": {"name": "谷歌"}, "AMD": {"name": "超威半导体"},
    "HOOD": {"name": "Robinhood"}, "DRAM": {"name": "Roundhill内存芯片"}, "SPCX": {"name": "SpaceX代币化"},
    "QQQM": {"name": "纳指100(QQQM)"}, "QLD": {"name": "纳指2倍做多(QLD)"}, "VGT": {"name": "信息技术ETF(VGT)"},
    "QQQ": {"name": "纳指100(QQQ)"}, "VOO": {"name": "标普500(VOO)"},
}
STOCKS = list(STOCK_META.keys())

CN_HK_SYMBOLS = {
    "sh000001": "上证指数", "sh000300": "沪深300", "sz159307": "红利低波100 ETF",
    "hk03086": "华夏纳指 (港股)", "hk03416": "国指备兑 (港股)",
}
TENCENT_URL = "http://qt.gtimg.cn/q={symbols}"
