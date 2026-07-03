"""
ETF Fundamentals Monthly Updater
=================================
Refreshes AUM, P/E, Beta, Holdings, Top-10%, Expense Ratio and other
fundamental data for all ETFs from Yahoo Finance.

Schedule : Runs automatically on the 15th of every month via GitHub Actions.
Output   : yf_profiles.json  (loaded by data_engine.py at every daily run)
Priority : Batch 1 — Market Indices
           Batch 2 — Core 80 ETFs  (etf_list.json)
           Batch 3 — Remaining ETFs (etf_list_all.json)

Run manually: python update_fundamentals.py
"""

import json, os, time
from datetime import datetime
import yfinance as yf

# ── Paths ─────────────────────────────────────────────────────────────────────
BASE_DIR      = os.path.dirname(os.path.abspath(__file__))
CORE_LIST     = os.path.join(BASE_DIR, "etf_list.json")       # 80 core ETFs
ALL_LIST      = os.path.join(BASE_DIR, "etf_list_all.json")   # full universe
OUTPUT        = os.path.join(BASE_DIR, "yf_profiles.json")    # output file

MARKET_INDICES = {
    "^GSPC": "S&P 500 Index",
    "^NDX":  "Nasdaq-100 Index",
    "^DJI":  "Dow Jones Indu Avg",
    "^FTSE": "FTSE 100 Index",
    "^RUT":  "Russell 2000 Index",
    "000001.SS": "SSE Composite",
    "^NSEI": "Nifty 50",
    "^CRSLDX": "Nifty 500",
    "^VIX":  "VIX",
    "^BSESN": "Sensex",
}

# ── Helpers ───────────────────────────────────────────────────────────────────
def load_json(path, default):
    if os.path.exists(path):
        try:
            with open(path) as f:
                return json.load(f)
        except Exception:
            return default
    return default

def save_json(path, data):
    with open(path, "w") as f:
        json.dump(data, f, indent=2, default=str)

def extract_profile(sym, info):
    """Extract and normalise the relevant fundamental fields from yf.Ticker.info."""
    profile = {
        "symbol":        sym,
        "name":          info.get("shortName") or info.get("longName"),
        "category":      info.get("category"),
        "aum":           info.get("totalAssets") or info.get("netAssets"),
        "pe":            info.get("trailingPE"),
        "beta":          info.get("beta3Year") or info.get("beta"),
        "expense_ratio": info.get("netExpenseRatio"),
        "yield":         info.get("yield") or info.get("dividendYield"),
        "holdings":      info.get("numberOfHoldings"),
        "top10_pct":     info.get("tenHoldingsPercentage"),   # top-10 weight %
        "inception":     None,
        "last_updated":  datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }

    # Parse inception date (comes as unix timestamp in seconds or milliseconds)
    idate = info.get("fundInceptionDate") or info.get("firstTradeDateMilliseconds")
    if idate:
        try:
            ts = idate / 1000 if idate > 10**11 else idate
            profile["inception"] = datetime.fromtimestamp(ts).strftime("%Y-%m-%d")
        except Exception:
            pass

    return profile

def fetch_profiles(symbols, batch_label, profiles, throttle=0.6):
    """Fetch YF .info for each symbol, update profiles dict in-place."""
    total  = len(symbols)
    done   = 0
    errors = 0
    print(f"\n[{datetime.now():%H:%M:%S}] {batch_label} — {total} symbols")

    for sym in symbols:
        try:
            info = yf.Ticker(sym).info
            profiles[sym] = extract_profile(sym, info)
        except Exception as e:
            profiles[sym] = {
                "symbol":       sym,
                "error":        str(e),
                "last_updated": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            }
            errors += 1

        done += 1
        if done % 10 == 0 or done == total:
            print(f"  [{datetime.now():%H:%M:%S}]  {done}/{total} done  (errors: {errors})")
            save_json(OUTPUT, profiles)   # checkpoint save every 10 records

        time.sleep(throttle)

    return profiles

# ── Build priority-ordered symbol lists ───────────────────────────────────────
core_etfs = [e["symbol"] for e in load_json(CORE_LIST, [])]
all_etfs  = [e["symbol"] for e in load_json(ALL_LIST,  [])]

batch1 = list(MARKET_INDICES.keys())                          # Priority 1: Indices
batch2 = [t for t in core_etfs if t not in batch1]           # Priority 2: Core 80 ETFs
batch3 = [t for t in all_etfs  if t not in batch1            # Priority 3: Remaining
                                and t not in batch2]

print("=" * 60)
print("  ETF Fundamentals Monthly Updater")
print(f"  Run date  : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
print(f"  Batch 1   : {len(batch1)} market indices")
print(f"  Batch 2   : {len(batch2)} core ETFs")
print(f"  Batch 3   : {len(batch3)} remaining ETFs")
print(f"  Output    : {OUTPUT}")
print("=" * 60)

# Load existing profiles (we will OVERWRITE all records — full monthly refresh)
profiles = {}

# ── Fetch in priority order ───────────────────────────────────────────────────
profiles = fetch_profiles(batch1, "Priority 1 — Market Indices", profiles)
profiles = fetch_profiles(batch2, "Priority 2 — Core 80 ETFs",  profiles)
profiles = fetch_profiles(batch3, "Priority 3 — Remaining ETFs", profiles)

# ── Final save ────────────────────────────────────────────────────────────────
save_json(OUTPUT, profiles)
print(f"\n[{datetime.now():%H:%M:%S}] ✅ DONE — yf_profiles.json updated.")
print(f"   Total records : {len(profiles)}")
print(f"   Errors        : {sum(1 for v in profiles.values() if 'error' in v)}")
