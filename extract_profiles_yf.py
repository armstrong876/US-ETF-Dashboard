import json
import os
import time
from datetime import datetime
import yfinance as yf

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ETF_LIST = os.path.join(BASE_DIR, "etf_list_all.json")
OUTPUT = os.path.join(BASE_DIR, "yf_profiles.json")

def load_json(path, default):
    if os.path.exists(path):
        try:
            with open(path) as f:
                return json.load(f)
        except:
            return default
    return default

def save_json(path, data):
    with open(path, "w") as f:
        json.dump(data, f, indent=2)

print(f"[{datetime.now():%H:%M:%S}] Loading ETF list...")
etfs = load_json(ETF_LIST, [])
tickers = [e["symbol"] for e in etfs]

profiles = load_json(OUTPUT, {})

count = 0
total = len(tickers)

print(f"[{datetime.now():%H:%M:%S}] Fetching Yahoo Finance profiles. Resuming from {len(profiles)} records...")

for sym in tickers:
    if sym in profiles and profiles[sym].get("last_updated"):
        # optionally check date if you want to expire cache
        continue
    
    try:
        ticker_obj = yf.Ticker(sym)
        info = ticker_obj.info
        
        # We extract available fields
        profile = {
            "symbol": sym,
            "name": info.get("shortName", info.get("longName")),
            "category": info.get("category"),
            "aum": info.get("totalAssets", info.get("netAssets")),
            "pe": info.get("trailingPE"),
            "beta": info.get("beta3Year"),
            "expense_ratio": info.get("netExpenseRatio"),
            "yield": info.get("yield", info.get("dividendYield")),
            "inception": None,
            "last_updated": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        
        # Handle Inception date timestamp
        idate = info.get("fundInceptionDate") or info.get("firstTradeDateMilliseconds")
        if idate:
            try:
                if idate > 10**11: # milliseconds
                    dt = datetime.fromtimestamp(idate / 1000)
                else: # seconds
                    dt = datetime.fromtimestamp(idate)
                profile["inception"] = dt.strftime("%Y-%m-%d")
            except:
                pass
        
        profiles[sym] = profile
        
    except Exception as e:
        print(f"Error on {sym}: {e}")
        profiles[sym] = {"symbol": sym, "error": str(e), "last_updated": datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
        
    count += 1
    
    if count % 10 == 0:
        print(f"[{datetime.now():%H:%M:%S}] Processed {len(profiles)}/{total}...")
        save_json(OUTPUT, profiles)
        
    time.sleep(0.5) # throttle to avoid YF ban

# Final save
save_json(OUTPUT, profiles)
print(f"[{datetime.now():%H:%M:%S}] Finished downloading YF profiles!")
