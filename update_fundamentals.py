"""
ETF Fundamentals Monthly Updater
=================================
Refreshes the KEY FUNDAMENTALS for all ETFs from Yahoo Finance:
AUM, P/E, Expense Ratio, Dividend Yield, Inception.

SOURCE OF TRUTH — fixed, do not mix:
  * Key Fundamentals      -> yfinance   (this file)
  * Portfolio Composition -> etfdb      (etf_details_engine.py)
  * Risk ratios           -> CALCULATED FROM NAVs by etf_analytics_engine.py.
  * Beta                  -> still taken from yfinance here, because nothing
                             consumes the NAV beta yet. Wiring the dashboard and
                             the one-pager to risk_analysis.beta is the step that
                             lets this be dropped.
  * Holdings-count / Top-10% -> derived from the etfdb holdings we already collect.

Schedule : Runs automatically on the 12th of every month via GitHub Actions
           (the "Monthly ETF Refresh" workflow, alongside etf_details_engine.py).
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
        # longName FIRST: Yahoo caps shortName at 31 characters, which was
        # cutting 38 of the 80 fund names mid-word ("VanEck Fabless Semiconductor ET").
        "name":          info.get("longName") or info.get("shortName"),
        "category":      info.get("category"),
        "aum":           info.get("totalAssets") or info.get("netAssets"),
        "pe":            info.get("trailingPE"),
        # Beta is kept for now. The intent is to use the NAV-derived beta from
        # etf_analytics_engine.py, but nothing reads it yet: both the dashboard
        # table and the one-pager's Portfolio Beta card take etfObj.beta, which
        # data_engine fills from here. Dropping it would silently fall back to
        # the static April value in etf_list.json rather than switch to NAV.
        "beta":          info.get("beta3Year") or info.get("beta"),
        "expense_ratio": info.get("netExpenseRatio"),
        "yield":         info.get("yield") or info.get("dividendYield"),
        # NOTE: holdings-count and top-10% are NOT fetched here — yfinance returns
        # null for most ETFs, and both are derived from the etfdb holdings we already
        # collect (top-10% = sum of the top-10 weights on the ETF page; holdings count
        # comes from etf_list.json via data_engine's `or meta.get(...)` fallback).
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

def is_usable(profile):
    """A record is only allowed to REPLACE an existing one if it actually carries
    data. yfinance can return an empty info dict without raising, which would
    otherwise silently blank out a good record."""
    if not profile or "error" in profile:
        return False
    return any(profile.get(f) is not None
               for f in ("aum", "expense_ratio", "pe", "yield", "name"))


def fetch_profiles(symbols, batch_label, profiles, throttle=0.6):
    """Fetch YF .info for each symbol, update profiles dict in-place."""
    total  = len(symbols)
    done   = 0
    errors = 0
    print(f"\n[{datetime.now():%H:%M:%S}] {batch_label} — {total} symbols")

    kept = 0
    for sym in symbols:
        try:
            info = yf.Ticker(sym).info
            fresh = extract_profile(sym, info)
            if is_usable(fresh):
                profiles[sym] = fresh
            else:
                # Empty response — keep whatever we already had rather than
                # replacing a good record with nulls.
                errors += 1
                if sym not in profiles:
                    profiles[sym] = fresh
                else:
                    kept += 1
        except Exception:
            # Fetch failed. NEVER overwrite a previously-good record with an
            # error stub — the Portfolio Builder would read it as real data.
            errors += 1
            if sym not in profiles:
                profiles[sym] = {
                    "symbol":       sym,
                    "error":        "fetch failed",
                    "last_updated": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                }
            else:
                kept += 1

        done += 1
        if done % 10 == 0 or done == total:
            print(f"  [{datetime.now():%H:%M:%S}]  {done}/{total} done  (errors: {errors})")
            save_json(OUTPUT, profiles)   # checkpoint save every 10 records

        time.sleep(throttle)

    if kept:
        print(f"  ({kept} symbols failed this run — kept their previous good values)")
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

# ── Seed with LAST MONTH'S profiles ───────────────────────────────────────────
# Pull the previous yf_profiles.json from Supabase first. Without this the run
# starts empty on a fresh GitHub runner, and any symbol that fails this month
# would lose its good values instead of carrying them forward.
try:
    import supabase_store as _sb0
    if _sb0.enabled() and _sb0.download_file("nav/yf_profiles.json", OUTPUT):
        print("  Seeded from Supabase: previous yf_profiles.json downloaded.")
except Exception as _e:
    print(f"  (could not seed from Supabase: {_e})")

profiles = load_json(OUTPUT, {})
if not isinstance(profiles, dict):
    profiles = {}
print(f"  Starting from {len(profiles):,} existing records "
      f"(failed symbols will keep these values).")

# ── Fetch in priority order ───────────────────────────────────────────────────
profiles = fetch_profiles(batch1, "Priority 1 — Market Indices", profiles)
profiles = fetch_profiles(batch2, "Priority 2 — Core 80 ETFs",  profiles)
profiles = fetch_profiles(batch3, "Priority 3 — Remaining ETFs", profiles)

# ── Final save ────────────────────────────────────────────────────────────────
save_json(OUTPUT, profiles)
print(f"\n[{datetime.now():%H:%M:%S}] ✅ DONE — yf_profiles.json updated.")
print(f"   Total records : {len(profiles)}")
print(f"   Errors        : {sum(1 for v in profiles.values() if 'error' in v)}")

# ── Push profiles cache to Supabase (private bucket) so it persists across runs
#    without git. No-op without creds (local run unaffected). ──
try:
    import supabase_store as _sb
    if _sb.enabled():
        _ok = _sb.upload_file(OUTPUT, "nav/yf_profiles.json")
        print(f"[{datetime.now():%H:%M:%S}] Supabase: yf_profiles.json synced." if _ok
              else f"[{datetime.now():%H:%M:%S}] Supabase: yf_profiles.json sync FAILED.")
except Exception as _e:
    print(f"[{datetime.now():%H:%M:%S}] Supabase profiles sync skipped ({_e}).")
