"""
ETF Momentum Dashboard — Data Engine
=====================================
Downloads 10 years of daily close prices for 100 ETFs via Yahoo Finance,
calculates multi-timeframe returns, momentum scores, relative strength vs SPY,
and writes a single dashboard.json consumed by the web dashboard.

Run:  python data_engine.py
Output: dashboard.json  (refreshed every run)
"""

import json, os, math, time
from datetime import datetime, date
import yfinance as yf
import pandas as pd

# ── Configuration ─────────────────────────────────────────────────────────────
BASE_DIR   = os.path.dirname(os.path.abspath(__file__))
ETF_LIST   = os.path.join(BASE_DIR, "etf_list.json")
OUTPUT     = os.path.join(BASE_DIR, "dashboard.json")
HISTORY    = os.path.join(BASE_DIR, "history.json")
BENCHMARK  = "SPY"
CACHE_RAW  = os.path.join(BASE_DIR, "cache_raw.pkl.gz")
CACHE_ADJ  = os.path.join(BASE_DIR, "cache_adj.pkl.gz")

PERIODS = {            # label : trading-day lookback
    "1W":  5,
    "15D": 15,
    "1M":  21,
    "2M":  42,
    "3M":  63,
    "6M":  126,
    "9M":  189,
    "12M": 252,
    "2Y":  504,
    "3Y":  756,
    "5Y":  1260,
    "7Y":  1764,
    "10Y": 2520,
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
    "^CRSLDX": "Nifty 500",
    "^VIX": "VIX",
    "^BSESN": "Sensex"
}

# ── Load Metadata & Profiles ────────────────────────────────────────────────
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

# Ensure SPY is in the list (needed as benchmark)
if BENCHMARK not in tickers:
    tickers.insert(0, BENCHMARK)

print(f"[{datetime.now():%H:%M:%S}] Fetching price data for {len(tickers)} ETFs...")
print("This may take 1-3 minutes on first run.\n")

# ── Load or Create Cache ──────────────────────────────────────────────────────
close_raw = pd.DataFrame()
close_adj = pd.DataFrame()

cache_loaded = False
if os.path.exists(CACHE_RAW) and os.path.exists(CACHE_ADJ):
    try:
        close_raw = pd.read_pickle(CACHE_RAW, compression='gzip')
        close_adj = pd.read_pickle(CACHE_ADJ, compression='gzip')
        if not close_raw.empty and not close_adj.empty:
            cache_loaded = True
            print(f"[{datetime.now():%H:%M:%S}] Cache loaded successfully. Last date in cache: {close_raw.index[-1].date()}")
    except Exception as e:
        print(f"[{datetime.now():%H:%M:%S}] Cache read error, starting fresh: {e}")

# ── Self-healing: Fetch full history for newly added tickers ──────────────────
if cache_loaded:
    missing = [t for t in tickers if t not in close_raw.columns or t not in close_adj.columns]
    if missing:
        print(f"[{datetime.now():%H:%M:%S}] Found {len(missing)} missing tickers in cache. Fetching 11-year history...")
        try:
            raw_missing = yf.download(
                missing,
                period="11y",
                interval="1d",
                auto_adjust=False,
                progress=False,
                threads=True
            )
            if isinstance(raw_missing.columns, pd.MultiIndex):
                close_raw_missing = raw_missing["Close"]
                close_adj_missing = raw_missing.get("Adj Close", raw_missing["Close"])
            else:
                close_raw_missing = raw_missing[["Close"]]
                close_raw_missing.columns = missing
                close_adj_missing = raw_missing.get("Adj Close", close_raw_missing)

            close_raw_missing = close_raw_missing.dropna(how="all")
            close_raw_missing.index = pd.to_datetime(close_raw_missing.index)
            close_adj_missing = close_adj_missing.dropna(how="all")
            close_adj_missing.index = pd.to_datetime(close_adj_missing.index)

            # Concat columns
            close_raw = pd.concat([close_raw, close_raw_missing], axis=1)
            close_adj = pd.concat([close_adj, close_adj_missing], axis=1)
            print(f"[{datetime.now():%H:%M:%S}] Missing tickers merged successfully.")
        except Exception as e:
            print(f"[{datetime.now():%H:%M:%S}] Error fetching missing tickers: {e}")

# ── Download fresh data ───────────────────────────────────────────────────────
if cache_loaded:
    # Warm start: Only download increment since the last cached date
    last_date = close_raw.index[-1]
    start_date = last_date.strftime("%Y-%m-%d")
    print(f"[{datetime.now():%H:%M:%S}] Fetching incremental update since {start_date}...")
    
    raw_new = yf.download(
        tickers,
        start=start_date,
        interval="1d",
        auto_adjust=False,
        progress=False,
        threads=True,
    )
    
    if isinstance(raw_new.columns, pd.MultiIndex):
        close_raw_new = raw_new["Close"]
        close_adj_new = raw_new.get("Adj Close", raw_new["Close"])
    else:
        close_raw_new = raw_new[["Close"]]
        close_raw_new.columns = tickers
        close_adj_new = raw_new.get("Adj Close", close_raw_new)

      # Concat rows
    close_raw = pd.concat([close_raw, close_raw_new])
    close_adj = pd.concat([close_adj, close_adj_new])
    
    # Clean up index duplicates (keeping the latest downloaded data)
    close_raw = close_raw.loc[~close_raw.index.duplicated(keep='last')].sort_index()
    close_adj = close_adj.loc[~close_adj.index.duplicated(keep='last')].sort_index()
else:
    # Cold start: Full 11-year download
    print(f"[{datetime.now():%H:%M:%S}] Fetching full 11-year history from Yahoo Finance...")
    raw = yf.download(
        tickers,
        period="11y",
        interval="1d",
        auto_adjust=False,
        progress=True,
        threads=True,
    )
    
    if isinstance(raw.columns, pd.MultiIndex):
        close_raw = raw["Close"]
        close_adj = raw.get("Adj Close", raw["Close"])
    else:
        close_raw = raw[["Close"]]
        close_raw.columns = tickers
        close_adj = raw.get("Adj Close", close_raw)

    close_raw = close_raw.dropna(how="all")
    close_raw.index = pd.to_datetime(close_raw.index)

    close_adj = close_adj.dropna(how="all")
    close_adj.index = pd.to_datetime(close_adj.index)

# ── Bound Cache & Save ────────────────────────────────────────────────────────
# Limit history to the last 11 years to prevent memory leaks/unbounded growth
eleven_years_ago = datetime.now() - pd.DateOffset(years=11)
close_raw = close_raw.loc[close_raw.index >= eleven_years_ago]
close_adj = close_adj.loc[close_adj.index >= eleven_years_ago]

try:
    close_raw.to_pickle(CACHE_RAW, compression='gzip')
    close_adj.to_pickle(CACHE_ADJ, compression='gzip')
    print(f"[{datetime.now():%H:%M:%S}] Caches updated and saved to disk.")
except Exception as e:
    print(f"[{datetime.now():%H:%M:%S}] Cache write error: {e}")

print(f"\n[{datetime.now():%H:%M:%S}] Price data loaded. Rows: {len(close_raw)}, Cols: {len(close_raw.columns)}")

# ─────────────────────────────────────────────────────────────────────────────
# Helper: safe percentage return
# ─────────────────────────────────────────────────────────────────────────────
def pct_return(series, n_days, calendar_index):
    """Return absolute % for <1Y, and Annualized (CAGR) % for >=1Y using date-based lookup."""
    if len(series) < 5 or len(calendar_index) <= n_days:
        return None
    current = series.iloc[-1]
    target_date = calendar_index[-(n_days + 1)]
    
    # Find the price at or before target_date (fallback: target_date-1, target_date-2, etc.)
    past = series.asof(target_date)
    
    if pd.isna(current) or pd.isna(past) or past == 0:
        return None
    
    if n_days >= 252:
        return round(((current / past) ** (252.0 / n_days) - 1) * 100, 2)
    else:
        return round((current / past - 1) * 100, 2)

# ─────────────────────────────────────────────────────────────────────────────
# Calculate SPY returns (benchmark)
# ─────────────────────────────────────────────────────────────────────────────
spy_returns = {}
if BENCHMARK in close_adj.columns:
    spy_series = close_adj[BENCHMARK].dropna()
    for label, days in PERIODS.items():
        spy_returns[label] = pct_return(spy_series, days, close_adj.index)

# ─────────────────────────────────────────────────────────────────────────────
# Calculate returns for every ETF
# ─────────────────────────────────────────────────────────────────────────────
print(f"[{datetime.now():%H:%M:%S}] Calculating returns...")
results = []

for ticker in etf_meta:
    ticker_sym = ticker["symbol"]
    if ticker_sym not in close_raw.columns or ticker_sym not in close_adj.columns:
        print(f"  Skipping {ticker_sym} — no data")
        continue

    series_raw = close_raw[ticker_sym].dropna()
    series_adj = close_adj[ticker_sym].dropna()
    if len(series_raw) < 10 or len(series_adj) < 10:
        print(f"  Skipping {ticker_sym} — insufficient data ({len(series_raw)} rows)")
        continue

    meta = tickers_meta.get(ticker_sym, {})
    yf_p = YF_PROFILES.get(ticker_sym, {})
    
    # Merge strategy: Priority YF -> Fallback Excel
    row  = {
        "symbol":      ticker_sym,
        "name":        yf_p.get("name") or meta.get("name", ticker_sym),
        "asset_class": meta.get("asset_class", ""),
        "category":    yf_p.get("category") or meta.get("category", ""),
        "aum":         yf_p.get("aum") or meta.get("aum", 0),
        "er":          yf_p.get("expense_ratio") or meta.get("er", 0),
        "price":       round(float(series_raw.iloc[-1]), 2), # Use unadjusted Close for the displayed quote price
        
        # New Overview Fields
        "inception":   yf_p.get("inception") or meta.get("inception"),
        "pe":          yf_p.get("pe") or meta.get("pe"),
        "beta":        yf_p.get("beta") or meta.get("beta"),
        "alpha":       yf_p.get("alpha") or meta.get("alpha"), # Excel might have it or default null
        "holdings":    yf_p.get("holdings") or meta.get("holdings"),
        "top10_pct":   yf_p.get("top10_pct") or meta.get("top10_pct"),
        "yield":       yf_p.get("yield"),
        
        "returns":     {},
        "vs_spy":      {},
    }

    # ── Multi-timeframe returns ────────────────────────────────────────────
    for label, days in PERIODS.items():
        val = pct_return(series_adj, days, close_adj.index) # Use Adj Close for performance/return metrics
        row["returns"][label] = val

    # ── Momentum score ─────────────────────────────────────────────────────
    score = 0.0
    score_valid = True
    for period, weight in MOMENTUM_WEIGHTS.items():
        v = row["returns"].get(period)
        if v is None:
            score_valid = False
            break
        score += v * weight
    row["momentum_score"] = round(score, 4) if score_valid else None

    # ── Relative strength vs SPY ───────────────────────────────────────────
    for label in PERIODS:
        etf_ret = row["returns"].get(label)
        spy_ret = spy_returns.get(label)
        if etf_ret is not None and spy_ret is not None:
            row["vs_spy"][label] = round(etf_ret - spy_ret, 2)
        else:
            row["vs_spy"][label] = None

    # ── Signal ────────────────────────────────────────────────────────────
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

# ─────────────────────────────────────────────────────────────────────────────
# Build summary stats
# ─────────────────────────────────────────────────────────────────────────────
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

# ─────────────────────────────────────────────────────────────────────────────
# Write dashboard.json
# ─────────────────────────────────────────────────────────────────────────────
# ── Calculate Market Indices Stats ────────────────────────────────────
index_stats = []
for sym, name in MARKET_INDICES.items():
    if sym in close_raw.columns:
        s = close_raw[sym].dropna()
        if len(s) >= 2:
            price = round(float(s.iloc[-1]), 2)
            chg_1d = round((s.iloc[-1] / s.iloc[-2] - 1) * 100, 2)
            # Trading Day Lookbacks: 3M=63, 6M=126, 1Y=252
            # Since global index calendars differ, we map lookbacks to calendar index dates (US benchmark index)
            def get_ret(n):
                if len(close_adj.index) > n:
                    target_date = close_adj.index[-(n + 1)]
                    past = s.asof(target_date)
                    if pd.isna(past) or past == 0:
                        return 0
                    return round((s.iloc[-1] / past - 1) * 100, 2)
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

# ── Write dashboard.json ─────────────────────────────────────────────
output = {
    "last_updated":  datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    "as_of_date":    str(close_raw.index[-1].date()),
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

print(f"\n[{datetime.now():%H:%M:%S}] DONE! dashboard.json written.")
print(f"   ETFs processed : {len(results)}")
print(f"   As-of date     : {output['as_of_date']}")
print(f"\n   Top 5 Momentum:")
for r in top10[:5]:
    print(f"   {r['rank']:2}. {r['symbol']:6}  Score: {r['score']:7.2f}  {r['signal']}")

# ── Write history.json (last 1Y normalised prices for comparison chart) ──────
try:
    HISTORY_DAYS = 252  # ~1 trading year
    hist_tickers = list(close_adj.columns)
    hist_df = close_adj[hist_tickers].iloc[-HISTORY_DAYS:].copy()
    # Normalise each series to 100 on first available day
    hist_norm = (hist_df / hist_df.iloc[0] * 100).round(4)
    dates = [str(d.date()) for d in hist_norm.index]
    history_data = {
        "dates": dates,
        "series": {ticker: hist_norm[ticker].ffill().tolist()
                   for ticker in hist_tickers if ticker in hist_norm.columns}
    }
    with open(HISTORY, "w") as f:
        json.dump(history_data, f, separators=(',', ':'))
    print(f"[{datetime.now():%H:%M:%S}] history.json written ({len(hist_tickers)} tickers, {len(dates)} days).")
except Exception as e:
    print(f"[{datetime.now():%H:%M:%S}] Warning: history.json write failed: {e}")
