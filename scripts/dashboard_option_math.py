"""Pure option math helpers extracted from fetch_and_build.py."""
from __future__ import annotations
import datetime, math

def norm_cdf(x):
    return (1.0 + math.erf(x / math.sqrt(2.0))) / 2.0

def norm_pdf(x):
    return math.exp(-0.5 * x**2) / math.sqrt(2.0 * math.pi)

def calc_option_greeks(S, K, T, r, sigma, opt_type="Call"):
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
    dt = datetime.datetime.strptime(expiry_str, "%Y-%m-%d")
    strike_str = f"{int(round(strike * 1000)):08d}"
    return f"{sym}{dt.strftime('%y%m%d')}{'C' if opt_type.lower() == 'call' else 'P'}{strike_str}"
