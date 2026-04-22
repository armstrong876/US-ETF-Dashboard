"""
ETF Momentum Dashboard — ALL ETFs Data Engine
=============================================
Downloads 10 years of daily close prices for ~4500 ETFs via Yahoo Finance.
Writes dashboard_all.json.

Run:  python data_engine_all.py
Output: dashboard_all.json
"""

import json, os, time
from datetime import datetime
import yfinance as yf
import pandas as pd

BASE_DIR   = os.path.dirname(os.path.abspath(__file__))
ETF_LIST   = os.path.join(BASE_DIR, "etf_list_all.json")
OUTPUT     = os.path.join(BASE_DIR, "dashboard_all.json")
BENCHMARK  = "SPY"

PERIODS = {
    "1W":  5, "15D": 15, "1M":  21, "2M":  42, "3M":  63,
    "6M":  126, "9M":  189, "12M": 252, "2Y":  504,
    "3Y":  756, "5Y":  1260, "7Y":  1764, "10Y": 2520,
}

MOMENTUM_WEIGHTS = {"1M": 0.20, "3M": 0.30, "6M": 0.30, "12M": 0.20}

MARKET_INDICES = {
    "^GSPC": "S&P 500 Index",
    "^NDX": "Nasdaq-100 Index",
    "^DJI": "Dow Jones Indu Avg",
    "^FTSE": "FTSE 100 Index",
    "^RUT": "Russell 2000 Index",
    "000001.SS": "SSE Composite",
    "^NSEI": "Nifty 50",
    "^CNX500": "Nifty 500"
}

with open(ETF_LIST) as f:
    etf_meta = json.load(f)

# Load cached YF Profiles
YF_PROFILES = {}
YF_FILE = os.path.join(BASE_DIR, "yf_profiles.json")
if os.path.exists(YF_FILE):
    try:
        with open(YF_FILE) as f:
            YF_PROFILES = json.load(f)
    except:
        pass

tickers_meta = {e["symbol"]: e for e in etf_meta}
tickers      = [e["symbol"] for e in etf_meta]

# Ensure Market Indices are in tickers
for sym in MARKET_INDICES:
    if sym not in tickers:
        tickers.append(sym)

if BENCHMARK not in tickers:
    tickers.insert(0, BENCHMARK)

print(f"[{datetime.now():%H:%M:%S}] Fetching price data for {len(tickers)} ETFs in batches...")
print("This may take 5-15 minutes for 4500+ ETFs. Please wait...\n")

# Batch download ~4500 ETFs safely
batch_size = 250
all_closes = []

for i in range(0, len(tickers), batch_size):
    batch = tickers[i:i+batch_size]
    print(f"[{datetime.now():%H:%M:%S}]   Fetching batch {i//batch_size + 1}/{(len(tickers)-1)//batch_size + 1} ({len(batch)} symbols)...")
    
    try:
        raw = yf.download(
            batch,
            period="max",
            interval="1d",
            auto_adjust=True,
            progress=False,
            threads=True,
            ignore_tz=True
        )
        if isinstance(raw.columns, pd.MultiIndex):
            close = raw["Close"]
        else:
            close = raw[["Close"]]
            close.columns = batch
            
        all_closes.append(close)
    except Exception as e:
        print(f"  Error on batch {i}: {e}")
    time.sleep(1) # slight pause between batches

close = pd.concat(all_closes, axis=1) if all_closes else pd.DataFrame()
# Remove duplicated columns if benchmark was accidentally repeated in batches
close = close.loc[:, ~close.columns.duplicated()]

close = close.dropna(how="all")
close.index = pd.to_datetime(close.index)

print(f"\n[{datetime.now():%H:%M:%S}] Price data loaded. Rows: {len(close)}, Cols: {len(close.columns)}")

def pct_return(series, n_days):
    if len(series) <= n_days:
        return None
    current = series.iloc[-1]
    past    = series.iloc[-(n_days + 1)]
    if pd.isna(current) or pd.isna(past) or past == 0:
        return None
    
    if n_days >= 252:
        return round(((current / past) ** (252.0 / n_days) - 1) * 100, 2)
    else:
        return round((current / past - 1) * 100, 2)

spy_returns = {}
if BENCHMARK in close.columns:
    spy_series = close[BENCHMARK].dropna()
    for label, days in PERIODS.items():
        spy_returns[label] = pct_return(spy_series, days)

print(f"[{datetime.now():%H:%M:%S}] Calculating returns...")
results = []

for ticker in tickers:
    if ticker not in close.columns:
        continue

    series = close[ticker].dropna()
    if len(series) < 10:
        continue

    meta = tickers_meta.get(ticker, {})
    yf_p = YF_PROFILES.get(ticker, {})

    row  = {
        "symbol":      ticker,
        "name":        yf_p.get("name") or meta.get("name", ticker),
        "asset_class": meta.get("asset_class", ""),
        "category":    yf_p.get("category") or meta.get("category", ""),
        "aum":         yf_p.get("aum") or meta.get("aum", 0),
        "er":          yf_p.get("expense_ratio") or meta.get("er", 0),
        "price":       round(float(series.iloc[-1]), 2),
        
        # New Overview Fields
        "inception":   yf_p.get("inception") or meta.get("inception"),
        "pe":          yf_p.get("pe") or meta.get("pe"),
        "beta":        yf_p.get("beta") or meta.get("beta"),
        "alpha":       yf_p.get("alpha") or meta.get("alpha"), 
        "holdings":    yf_p.get("holdings") or meta.get("holdings"),
        "top10_pct":   yf_p.get("top10_pct") or meta.get("top10_pct"),
        "yield":       yf_p.get("yield"),

        "returns":     {},
        "vs_spy":      {},
    }

    for label, days in PERIODS.items():
        val = pct_return(series, days)
        row["returns"][label] = val

    score = 0.0
    score_valid = True
    for period, weight in MOMENTUM_WEIGHTS.items():
        v = row["returns"].get(period)
        if v is None:
            score_valid = False
            break
        score += v * weight
    row["momentum_score"] = round(score, 4) if score_valid else None

    for label in PERIODS:
        etf_ret = row["returns"].get(label)
        spy_ret = spy_returns.get(label)
        if etf_ret is not None and spy_ret is not None:
            row["vs_spy"][label] = round(etf_ret - spy_ret, 2)
        else:
            row["vs_spy"][label] = None

    ms = row["momentum_score"]
    if ms is None:
        row["signal"] = "N/A"
    elif ms >= 15:
        row["signal"] = "Strong"
    elif ms >= 5:
        row["signal"] = "Neutral"
    else:
        row["signal"] = "Weak"

    results.append(row)

scored = [r for r in results if r["momentum_score"] is not None]
scored_sorted = sorted(scored, key=lambda x: x["momentum_score"], reverse=True)

top10 = [
    {"rank": i+1, "symbol": r["symbol"], "name": r["name"],
     "score": r["momentum_score"], "signal": r["signal"],
     "ret_1m": r["returns"].get("1M"), "ret_3m": r["returns"].get("3M"),
     "ret_6m": r["returns"].get("6M"), "ret_12m": r["returns"].get("12M")}
    for i, r in enumerate(scored_sorted[:10])
]
bottom10 = [
    {"rank": i+1, "symbol": r["symbol"], "name": r["name"],
     "score": r["momentum_score"], "signal": r["signal"],
     "ret_1m": r["returns"].get("1M"), "ret_3m": r["returns"].get("3M"),
     "ret_6m": r["returns"].get("6M"), "ret_12m": r["returns"].get("12M")}
    for i, r in enumerate(scored_sorted[-10:][::-1])
]

# ── Calculate Market Indices Stats ────────────────────────────────────
index_stats = []
for sym, name in MARKET_INDICES.items():
    if sym in close.columns:
        s = close[sym].dropna()
        if len(s) >= 2:
            price = round(float(s.iloc[-1]), 2)
            chg_1d = round((s.iloc[-1] / s.iloc[-2] - 1) * 100, 2)
            # Trading Day Lookbacks: 3M=63, 6M=126, 1Y=252
            def get_ret(n):
                if len(s) > n:
                    past = s.iloc[-(n+1)]
                    return round((s.iloc[-1] / past - 1) * 100, 2) if past != 0 else 0
                return 0

            index_stats.append({
                "symbol": sym,
                "name": name,
                "price": price,
                "chg_1d": chg_1d,
                "chg_3m": get_ret(63),
                "chg_6m": get_ret(126),
                "chg_1y": get_ret(252)
            })

output = {
    "last_updated":  datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    "as_of_date":    str(close.index[-1].date()),
    "total_etfs":    len(results),
    "benchmark":     BENCHMARK,
    "spy_returns":   spy_returns,
    "periods":       list(PERIODS.keys()),
    "etfs":          results,
    "top10":         top10,
    "bottom10":      bottom10,
    "market_indices": index_stats,
}

with open(OUTPUT, "w") as f:
    json.dump(output, f, indent=2, default=str)

print(f"\n[{datetime.now():%H:%M:%S}] DONE! dashboard_all.json written.")
print(f"   ETFs processed : {len(results)}")
