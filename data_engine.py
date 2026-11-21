"""
ETF Momentum Dashboard — Data Engine
=====================================
Downloads 10 years of daily close prices for 100 ETFs via Yahoo Finance,
calculates multi-timeframe returns, momentum scores, relative strength vs SPY,
and writes a single dashboard.json consumed by the web dashboard.

Run:  python data_engine.py
Output: dashboard.json  (refreshed every run)
"""

import json, os, math, time, sys
from datetime import datetime, date
import yfinance as yf
import pandas as pd

# ── Configuration ─────────────────────────────────────────────────────────────
BASE_DIR   = os.path.dirname(os.path.abspath(__file__))
ETF_LIST   = os.path.join(BASE_DIR, "etf_list.json")
OUTPUT     = os.path.join(BASE_DIR, "dashboard.json")
HISTORY    = os.path.join(BASE_DIR, "history.json")
BENCHMARK  = "SPY"
# Parquet cache (replaced the old *.pkl.gz pickles — pickle serialized numpy
# internals and broke across numpy versions, e.g. a numpy-2.x CI run writing a
# cache a numpy-1.x machine couldn't read. Parquet is a stable, portable,
# columnar format with no such version coupling.)
CACHE_RAW  = os.path.join(BASE_DIR, "nav_core_raw.parquet")
CACHE_ADJ  = os.path.join(BASE_DIR, "nav_core_adj.parquet")
# Legacy pickle paths — only read once, to migrate an existing cache to Parquet
# on the first run after this change (best-effort; ignored if unreadable).
LEGACY_CACHE_RAW = os.path.join(BASE_DIR, "cache_raw.pkl.gz")
LEGACY_CACHE_ADJ = os.path.join(BASE_DIR, "cache_adj.pkl.gz")

PERIODS = {            # label : calendar lookback — start = the same date one
                       # week/month/year earlier; if that was a weekend/holiday,
                       # that market's previous close (Yahoo/Google/NSE convention)
    "1W":  pd.DateOffset(weeks=1),
    "15D": pd.DateOffset(days=15),
    "1M":  pd.DateOffset(months=1),
    "2M":  pd.DateOffset(months=2),
    "3M":  pd.DateOffset(months=3),
    "6M":  pd.DateOffset(months=6),
    "9M":  pd.DateOffset(months=9),
    "12M": pd.DateOffset(years=1),
    "2Y":  pd.DateOffset(years=2),
    "3Y":  pd.DateOffset(years=3),
    "5Y":  pd.DateOffset(years=5),
    "7Y":  pd.DateOffset(years=7),
    "10Y": pd.DateOffset(years=10),
}
CAGR_YEARS = {"12M": 1, "2Y": 2, "3Y": 3, "5Y": 5, "7Y": 7, "10Y": 10}   # shown annualised

MOMENTUM_WEIGHTS = {"1M": 0.20, "3M": 0.30, "6M": 0.30, "12M": 0.20}

# Corporate-action repair: a one-day close-to-close move outside these bounds
# (-30% / +30%) is treated as a suspected split / reverse split / bad stitch,
# and that ticker's full history is re-downloaded.
JUMP_DOWN      = 0.70
JUMP_UP        = 1.30
NO_JUMP_CHECK  = {"^VIX"}    # genuinely moves this much

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
# etfdb-derived fundamentals published by the monthly etf_details_engine run.
# Holdings count and Top-10 % live here because yfinance returns null for both
# on most ETFs — without this they fall back to a static April snapshot.
DERIVED_FILE = os.path.join(BASE_DIR, "etf_derived.json")
# Pull the latest profiles cache from Supabase before reading (no-op without creds)
try:
    import supabase_store as _sb
    if _sb.enabled():
        _sb.download_file("nav/yf_profiles.json", YF_FILE)
        _sb.download_file("nav/etf_derived.json", DERIVED_FILE)
except Exception:
    pass
try:
    with open(DERIVED_FILE, encoding="utf-8") as _f:
        ETF_DERIVED = json.load(_f) or {}
    print(f"  etf_derived.json loaded ({len(ETF_DERIVED)} symbols).")
except Exception as _e:
    ETF_DERIVED = {}
    print(f"  etf_derived.json unavailable ({_e}) — Holdings / Top-10 % keep their etf_list.json values.")

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

# ── Pull the latest Parquet cache from Supabase (source of truth) ─────────────
# If Supabase creds are present, the freshest cache lives there — download it so
# the load below reads it. Falls back silently to the local file if unavailable,
# so a plain local run without .env behaves exactly as before.
try:
    import supabase_store as _sb
    if _sb.enabled():
        _r = _sb.download_file("nav/nav_core_raw.parquet", CACHE_RAW)
        _a = _sb.download_file("nav/nav_core_adj.parquet", CACHE_ADJ)
        print(f"[{datetime.now():%H:%M:%S}] Supabase: pulled Parquet cache." if (_r and _a)
              else f"[{datetime.now():%H:%M:%S}] Supabase: no remote cache yet; using local if present.")
except Exception as _e:
    print(f"[{datetime.now():%H:%M:%S}] Supabase pull skipped ({_e}); using local cache.")

# ── Load or Create Cache ──────────────────────────────────────────────────────
close_raw = pd.DataFrame()
close_adj = pd.DataFrame()

cache_loaded = False
if os.path.exists(CACHE_RAW) and os.path.exists(CACHE_ADJ):
    try:
        close_raw = pd.read_parquet(CACHE_RAW)
        close_adj = pd.read_parquet(CACHE_ADJ)
        if not close_raw.empty and not close_adj.empty:
            cache_loaded = True
            print(f"[{datetime.now():%H:%M:%S}] Parquet cache loaded. Last date in cache: {close_raw.index[-1].date()}")
    except Exception as e:
        print(f"[{datetime.now():%H:%M:%S}] Parquet cache read error, starting fresh: {e}")

# One-time migration: if no Parquet cache yet but an old pickle cache exists and
# is readable in this environment, convert it so we skip a heavy cold re-download.
if not cache_loaded and os.path.exists(LEGACY_CACHE_RAW) and os.path.exists(LEGACY_CACHE_ADJ):
    try:
        close_raw = pd.read_pickle(LEGACY_CACHE_RAW, compression='gzip')
        close_adj = pd.read_pickle(LEGACY_CACHE_ADJ, compression='gzip')
        if not close_raw.empty and not close_adj.empty:
            cache_loaded = True
            print(f"[{datetime.now():%H:%M:%S}] Migrated legacy pickle cache -> Parquet (last date: {close_raw.index[-1].date()}).")
    except Exception as e:
        print(f"[{datetime.now():%H:%M:%S}] Legacy pickle unreadable ({e}); will cold-start fresh.")

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

# ── Corporate-action helpers ──────────────────────────────────────────────────
# The cache only appends the last few days, but Yahoo restates an ETF's WHOLE
# past series after a split (Close + Adj Close) or a distribution (Adj Close).
# Stitching fresh rows onto old cached rows then creates a fake cliff — e.g.
# SOXX's 3:1 split (Oct-2026) showed as a -69% one-day "crash" and -72% 1M.
def tickers_with_actions(raw, batch_tickers, fields=("Stock Splits", "Dividends", "Capital Gains")):
    """Tickers with a split or cash distribution inside a yf.download(actions=True) window."""
    hit = set()
    for field in fields:
        if isinstance(raw.columns, pd.MultiIndex):
            if field in raw.columns.get_level_values(0):
                f = raw[field].fillna(0)
                hit.update(f.columns[(f != 0).any()])
        elif field in raw.columns and (raw[field].fillna(0) != 0).any():
            hit.update(batch_tickers)
    return hit

def tickers_with_jumps(df, last_n=None):
    """Tickers whose close moves outside JUMP_DOWN/JUMP_UP in a single day."""
    d = df if last_n is None else df.iloc[-(last_n + 1):]
    d = d.ffill()
    ratio = d / d.shift(1)
    bad = ((ratio < JUMP_DOWN) | (ratio > JUMP_UP)).any()
    return sorted(t for t in bad[bad].index if t not in NO_JUMP_CHECK)

def with_newer_cache(fresh, cached):
    """Full-history download, plus any cached prices dated after a ticker's last
    downloaded price — a long Yahoo download that comes back a day short must
    not erase the latest close we already have."""
    out = fresh
    for t in fresh.columns:
        last = fresh[t].last_valid_index()
        if last is not None and t in cached.columns:
            tail = cached[t].loc[cached.index > last].dropna()
            if not tail.empty:
                out = out.combine_first(tail.to_frame(t))
    return out

# ── Download fresh data — Priority Batched ────────────────────────────────────
# Priority order (ensures most important symbols always get freshest data):
#   Batch 1 — Market Indices  (index cards on dashboard)
#   Batch 2 — Core 80 ETFs   (main universe — returns, momentum, signals)
#   Batch 3 — Any remaining   (extra tickers added via data_engine_all)
if cache_loaded:
    last_date  = close_raw.index[-1]
    # Go back 5 calendar days to safely cover weekends + public holidays gaps
    # so we never miss a trading day due to cache being slightly stale.
    fetch_from = last_date - pd.DateOffset(days=5)
    start_date = fetch_from.strftime("%Y-%m-%d")
    # end=TODAY is EXCLUSIVE in yfinance — so data is always capped at YESTERDAY.
    # This guarantees previous-day data regardless of what time the script runs.
    YESTERDAY  = date.today().strftime("%Y-%m-%d")
    print(f"[{datetime.now():%H:%M:%S}] Fetching incremental update {start_date} → {YESTERDAY} (prev day cap, priority batched)...")

    core_etf_symbols = [e["symbol"] for e in etf_meta]
    index_symbols    = list(MARKET_INDICES.keys())
    batch1 = index_symbols
    batch2 = [t for t in core_etf_symbols if t not in batch1]
    batch3 = [t for t in tickers if t not in batch1 and t not in batch2]

    def fetch_batch(batch_tickers, label, start, end):
        """Returns (close, adj_close, tickers with a split/distribution in the window)."""
        if not batch_tickers:
            return pd.DataFrame(), pd.DataFrame(), set()
        try:
            raw = yf.download(batch_tickers, start=start, end=end, interval="1d",
                              auto_adjust=False, actions=True, progress=False, threads=True)
            if raw.empty:
                return pd.DataFrame(), pd.DataFrame(), set()
            if isinstance(raw.columns, pd.MultiIndex):
                r = raw["Close"]
                a = raw.get("Adj Close", raw["Close"])
            else:
                r = raw[["Close"]]; r.columns = batch_tickers
                a = raw.get("Adj Close", r)
            print(f"[{datetime.now():%H:%M:%S}]   {label}: {len(batch_tickers)} tickers done.")
            return r, a, tickers_with_actions(raw, batch_tickers)
        except Exception as e:
            print(f"[{datetime.now():%H:%M:%S}]   {label}: error — {e}")
            return pd.DataFrame(), pd.DataFrame(), set()

    def fetch_batch_retry(batch_tickers, label, start, end, rounds=2, wait=20):
        """fetch_batch, then re-request tickers that came back empty (Yahoo rate
        limit / transient yfinance 'database is locked'), backing off between rounds."""
        r, a, acted = fetch_batch(batch_tickers, label, start, end)
        for n in range(1, rounds + 1):
            empty = [t for t in batch_tickers if t not in r.columns or r[t].isna().all()]
            if not empty:
                break
            print(f"[{datetime.now():%H:%M:%S}]   {label}: {empty} came back empty — retry {n}/{rounds} in {wait * n}s")
            time.sleep(wait * n)
            r2, a2, acted2 = fetch_batch(empty, f"{label} (retry {n})", start, end)
            keep = [t for t in empty if t in r2.columns and t in a2.columns and r2[t].notna().any()]
            if keep:
                r = pd.concat([r.drop(columns=[c for c in keep if c in r.columns]), r2[keep]], axis=1)
                a = pd.concat([a.drop(columns=[c for c in keep if c in a.columns]), a2[keep]], axis=1)
            acted |= acted2
        return r, a, acted

    r1, a1, act1 = fetch_batch_retry(batch1, "Batch 1 — Indices",   start_date, YESTERDAY)
    r2, a2, act2 = fetch_batch_retry(batch2, "Batch 2 — Core ETFs", start_date, YESTERDAY)
    r3, a3, act3 = fetch_batch_retry(batch3, "Batch 3 — Remaining", start_date, YESTERDAY)

    new_raw = pd.concat([r1, r2, r3], axis=1)
    new_adj = pd.concat([a1, a2, a3], axis=1)
    new_raw = new_raw.loc[:, ~new_raw.columns.duplicated(keep='last')]
    new_adj = new_adj.loc[:, ~new_adj.columns.duplicated(keep='last')]

    # Fresh values win, but a ticker whose download failed (all-NaN in new_raw)
    # keeps its cached prices for the overlap days instead of being blanked —
    # a row-level replace here once rolled ^DJI back 4 days after one failed fetch.
    close_raw = new_raw.combine_first(close_raw).sort_index()
    close_adj = new_adj.combine_first(close_adj).sort_index()

    # ── Corporate-action repair: re-download full history where Yahoo restated it ──
    # Triggers: a split/distribution in today's window, or a suspicious one-day
    # jump anywhere in the cache (catches splits Yahoo dated outside the window).
    acted  = (act1 | act2 | act3) & set(close_raw.columns)
    jumped = set(tickers_with_jumps(close_raw))
    # Indices + core ETFs get their full history re-downloaded EVERY day (~90
    # tickers, a few seconds): a day Yahoo failed to send in some earlier run
    # can never stay missing (a missing day shifted ^DJI's 1Y return by 2.4 pts),
    # and any later Yahoo correction is picked up. Failed downloads keep cache.
    refresh = (set(batch1) | set(batch2)) & set(close_raw.columns)
    repair = sorted(acted | jumped | refresh)
    if repair:
        print(f"[{datetime.now():%H:%M:%S}] Full-history refresh for {len(repair)} tickers "
              f"(indices + core ETFs: {len(refresh)}; split/distribution: {sorted(acted) or '-'}; "
              f"suspicious jump: {sorted(jumped) or '-'})")
        full_start = (date.today() - pd.DateOffset(years=11)).strftime("%Y-%m-%d")
        fr, fa, _ = fetch_batch_retry(repair, "Full-history repair", full_start, YESTERDAY, rounds=3, wait=30)
        got = [t for t in repair if t in fr.columns and t in fa.columns and fr[t].notna().any()]
        # Yahoo's history now starting much later than ours = ticker reused by a
        # new/restructured fund; the old fund's prices are dropped, not stitched.
        restarted = [t for t in got if t in close_raw.columns and close_raw[t].first_valid_index() is not None
                     and fr[t].first_valid_index() > max(close_raw[t].first_valid_index(), pd.Timestamp(full_start))
                                                     + pd.Timedelta(days=30)]
        if restarted:
            print(f"[{datetime.now():%H:%M:%S}]   Yahoo restarted history (new/restructured fund?): {restarted}")
        if got:
            close_raw = pd.concat([close_raw.drop(columns=got), with_newer_cache(fr[got], close_raw)], axis=1).sort_index()
            close_adj = pd.concat([close_adj.drop(columns=got), with_newer_cache(fa[got], close_adj)], axis=1).sort_index()
        failed = sorted(set(repair) - set(got))
        if failed:
            print(f"[{datetime.now():%H:%M:%S}]   Repair download failed for {failed} — kept cached data.")
        genuine = [t for t in tickers_with_jumps(close_raw) if t in got]
        if genuine:
            print(f"[{datetime.now():%H:%M:%S}]   Still a big one-day move after repair (genuine per Yahoo): {genuine}")

else:
    # Cold start: Full 11-year download — end=TODAY (exclusive) caps at yesterday
    # Wrapped in retry/backoff: this single big call has no fallback batches like
    # the incremental path does, so a transient Yahoo rate-limit here used to crash
    # the whole run outright (this is what caused the multi-week failure streak).
    YESTERDAY = date.today().strftime("%Y-%m-%d")
    print(f"[{datetime.now():%H:%M:%S}] Fetching full 11-year history from Yahoo Finance (capped at {YESTERDAY})...")

    raw = pd.DataFrame()
    for attempt in range(3):
        try:
            raw = yf.download(
                tickers,
                start=(date.today() - pd.DateOffset(years=11)).strftime("%Y-%m-%d"),
                end=YESTERDAY,
                interval="1d",
                auto_adjust=False,
                progress=True,
                threads=True,
            )
            if not raw.empty:
                break
            print(f"[{datetime.now():%H:%M:%S}] Cold-start download returned empty (attempt {attempt+1}/3), retrying...")
        except Exception as e:
            print(f"[{datetime.now():%H:%M:%S}] Cold-start download failed (attempt {attempt+1}/3): {e}")
        time.sleep(15 * (attempt + 1))

    if isinstance(raw.columns, pd.MultiIndex):
        close_raw = raw["Close"]
        close_adj = raw.get("Adj Close", raw["Close"])
    elif not raw.empty:
        close_raw = raw[["Close"]]
        close_raw.columns = tickers
        close_adj = raw.get("Adj Close", close_raw)

    close_raw = close_raw.dropna(how="all")
    close_raw.index = pd.to_datetime(close_raw.index)

    close_adj = close_adj.dropna(how="all")
    close_adj.index = pd.to_datetime(close_adj.index)

# ── Sanity check BEFORE touching disk or generating anything ──────────────────
# If Yahoo rate-limited/failed and we ended up with empty or badly incomplete
# data, stop here — never overwrite a good cache (or dashboard.json/history.json)
# with a broken one. This is what silently corrupted the cache previously and
# caused a multi-day cascade of failed runs (every subsequent run re-read the
# now-empty cache and fell back into this same fragile cold-start path).
MIN_ROWS = 100          # ~5 months of trading days — far below any real scenario
MIN_TICKER_COVERAGE = 0.5  # at least half the expected tickers must have data

if close_raw.empty or close_adj.empty:
    print(f"[{datetime.now():%H:%M:%S}] FATAL: fetched price data is empty — "
          f"likely a Yahoo Finance rate-limit or outage. Leaving the existing "
          f"cache/dashboard files untouched and failing this run.")
    sys.exit(1)

if len(close_raw) < MIN_ROWS or len(close_adj) < MIN_ROWS:
    print(f"[{datetime.now():%H:%M:%S}] FATAL: fetched price data has only "
          f"{len(close_raw)} rows (expected >= {MIN_ROWS}). Leaving the existing "
          f"cache/dashboard files untouched and failing this run.")
    sys.exit(1)

coverage = len(set(close_raw.columns) & set(tickers)) / max(len(tickers), 1)
if coverage < MIN_TICKER_COVERAGE:
    print(f"[{datetime.now():%H:%M:%S}] FATAL: only {coverage:.0%} of expected "
          f"tickers have data (expected >= {MIN_TICKER_COVERAGE:.0%}). Leaving "
          f"the existing cache/dashboard files untouched and failing this run.")
    sys.exit(1)

# ── Bound Cache & Save ────────────────────────────────────────────────────────
# Limit history to the last 11 years to prevent memory leaks/unbounded growth
eleven_years_ago = datetime.now() - pd.DateOffset(years=11)
close_raw = close_raw.loc[close_raw.index >= eleven_years_ago]
close_adj = close_adj.loc[close_adj.index >= eleven_years_ago]

try:
    close_raw.to_parquet(CACHE_RAW, compression='zstd')
    close_adj.to_parquet(CACHE_ADJ, compression='zstd')
    print(f"[{datetime.now():%H:%M:%S}] Parquet caches updated and saved to disk.")
except Exception as e:
    print(f"[{datetime.now():%H:%M:%S}] Cache write error: {e}")

# ── Push the updated Parquet cache back to Supabase ───────────────────────────
try:
    import supabase_store as _sb
    if _sb.enabled():
        _u1 = _sb.upload_file(CACHE_RAW, "nav/nav_core_raw.parquet")
        _u2 = _sb.upload_file(CACHE_ADJ, "nav/nav_core_adj.parquet")
        print(f"[{datetime.now():%H:%M:%S}] Supabase: Parquet cache pushed." if (_u1 and _u2)
              else f"[{datetime.now():%H:%M:%S}] Supabase: parquet push FAILED (check creds/bucket).")
except Exception as e:
    print(f"[{datetime.now():%H:%M:%S}] Supabase push skipped ({e}).")

print(f"\n[{datetime.now():%H:%M:%S}] Price data loaded. Rows: {len(close_raw)}, Cols: {len(close_raw.columns)}")

# ── Determine last COMPLETE trading day ──────────────────────────────────────────────────────────────
def last_complete_trading_day(df_index):
    """
    Since all downloads are capped at end=YESTERDAY (exclusive), the last row
    in the DataFrame is always the previous trading day's settled close.
    No time-based check needed — always use the last available row.
    """
    last_date = df_index[-1].date()
    print(f"[{datetime.now():%H:%M:%S}] Using last available settled date: {last_date}")
    return -1

PRICE_IDX = last_complete_trading_day(close_raw.index)  # -1 (today settled) or -2 (prev day)
# US ETFs are dated by the last day the US market traded: the cache also holds
# Nifty/Sensex/SSE/FTSE, whose rows can run past the last US close (US holidays).
US_ANCHORS  = [t for t in ("SPY", "QQQ", "IVV", "VOO", "IWM", "DIA") if t in close_raw.columns]
US_CALENDAR = close_raw[US_ANCHORS].dropna(how="all").index if US_ANCHORS else close_raw.index
NAV_DATE = US_CALENDAR[-1] if len(US_CALENDAR) else close_raw.index[PRICE_IDX]
print(f"[{datetime.now():%H:%M:%S}] NAV date: {NAV_DATE.date()}")

# ───────────────────────────────────────────────────────────────────────────────────
# Helper: percentage return over a calendar period — ONE rule for the whole site
# ───────────────────────────────────────────────────────────────────────────────────
def pct_return(series, label, end_date=None):
    """% change in Yahoo's closing price over PERIODS[label], ending end_date
    (default NAV_DATE). Start = the close on the same date one week/month/year
    earlier; on a weekend/holiday (or a day with no price) the previous close is
    used — the market's value on that date. 1Y and longer are annualised (CAGR).
    None when the fund/index has no price that far back."""
    end_date = NAV_DATE if end_date is None else end_date
    s = series.loc[:end_date].dropna()
    if len(s) < 5:
        return None
    start_date = end_date - PERIODS[label]
    if s.index[0] > start_date:
        return None
    current, past = float(s.iloc[-1]), float(s.asof(start_date))
    if past == 0:
        return None
    years = CAGR_YEARS.get(label)
    if years:
        return round(((current / past) ** (1.0 / years) - 1) * 100, 2)
    return round((current / past - 1) * 100, 2)

# ─────────────────────────────────────────────────────────────────────────────
# Calculate SPY returns (benchmark)
# ─────────────────────────────────────────────────────────────────────────────
spy_returns = {}
if BENCHMARK in close_raw.columns:
    spy_series = close_raw[BENCHMARK].dropna()
    for label in PERIODS:
        spy_returns[label] = pct_return(spy_series, label)

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
    _der = ETF_DERIVED.get(ticker_sym, {})
    
    # Merge strategy: Priority YF -> Fallback Excel
    row  = {
        "symbol":      ticker_sym,
        # Curated name first — etf_list.json holds the full legal name, while a
        # vendor display name can arrive truncated.
        "name":        meta.get("name") or yf_p.get("name") or ticker_sym,
        "asset_class": meta.get("asset_class", ""),
        "category":    yf_p.get("category") or meta.get("category", ""),
        "aum":         yf_p.get("aum") or meta.get("aum", 0),
        "er":          yf_p.get("expense_ratio") or meta.get("er", 0),
        "price":       round(float(series_raw.asof(NAV_DATE)), 2), # Last settled NAV (not intraday)
        
        # New Overview Fields
        "inception":   yf_p.get("inception") or meta.get("inception"),
        "pe":          yf_p.get("pe") or meta.get("pe"),
        "beta":        yf_p.get("beta") or meta.get("beta"),
        "alpha":       yf_p.get("alpha") or meta.get("alpha"), # Excel might have it or default null
        # etfdb (monthly, live) -> yfinance -> etf_list.json. yfinance returns
        # null for both of these on most ETFs, so without the etfdb figures
        # these columns never moved off their April values.
        "holdings":    _der.get("holdings") or yf_p.get("holdings") or meta.get("holdings"),
        "top10_pct":   _der.get("top10_pct") or yf_p.get("top10_pct") or meta.get("top10_pct"),
        "yield":       yf_p.get("yield"),
        
        "returns":     {},
        "vs_spy":      {},
    }

    # ── Multi-timeframe returns ────────────────────────────────────────────
    for label in PERIODS:
        val = pct_return(series_raw, label)  # Use raw Close — matches what users see on finance sites
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
# Each index uses its OWN last available date — not the global US NAV date.
# This ensures Nifty/Indian indices show their correct settlement date
# (they trade during IST hours and settle independently of US markets).
index_stats = []
for sym, name in MARKET_INDICES.items():
    if sym in close_raw.columns:
        s = close_raw[sym].dropna()
        if len(s) >= 2:
            # Downloads are capped at end=YESTERDAY so the last row is always
            # the previous trading day's settled close. No time check needed.
            sym_nav      = s.index[-1]
            sym_prev_nav = s.index[-2]

            price      = round(float(s.loc[sym_nav]), 2)
            prev_price = float(s.loc[sym_prev_nav]) if sym_prev_nav in s.index else None
            chg_1d     = round((price / prev_price - 1) * 100, 2) if prev_price else 0

            # Same calendar rule as the ETFs, ending on this index's own last
            # close (each market keeps its own holidays).
            def get_ret(label, _s=s, _end=sym_nav):
                return pct_return(_s, label, _end)

            index_stats.append({
                "symbol":       sym,
                "name":         name,
                "price":        price,
                "chg_1d":       chg_1d,
                "chg_3m":       get_ret("3M"),
                "chg_6m":       get_ret("6M"),
                "chg_1y":       get_ret("12M"),
                "as_of_date":   str(sym_nav.date()),   # Per-index actual settlement date
            })

# ── Write dashboard.json ─────────────────────────────────────────────
output = {
    "last_updated":  datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    "as_of_date":    str(NAV_DATE.date()),   # Always last fully settled trading day
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
    # Yahoo's closing price (same series as every return on the site), so the
    # charts' % lines agree with the tables. 5 calendar years + a margin so the
    # 5Y chart button always has its start date.
    hist_tickers = list(close_raw.columns)
    hist_start = NAV_DATE - pd.DateOffset(years=5) - pd.Timedelta(days=10)
    hist_df = close_raw[hist_tickers].loc[hist_start:].copy()
    
    # Normalise each series to 100 on its first valid date to support newer ETFs
    hist_norm = hist_df.copy()
    for ticker in hist_norm.columns:
        first_valid_idx = hist_norm[ticker].first_valid_index()
        if first_valid_idx is not None:
            first_val = hist_norm.loc[first_valid_idx, ticker]
            if first_val > 0:
                hist_norm[ticker] = (hist_norm[ticker] / first_val * 100).round(4)
                
    dates = [str(d.date()) for d in hist_norm.index]
    history_data = {
        "dates": dates,
        "series": {ticker: [None if pd.isna(val) else val for val in hist_norm[ticker].ffill().tolist()]
                   for ticker in hist_tickers if ticker in hist_norm.columns}
    }
    with open(HISTORY, "w") as f:
        json.dump(history_data, f, separators=(',', ':'))
    print(f"[{datetime.now():%H:%M:%S}] history.json written ({len(hist_tickers)} tickers, {len(dates)} days).")
except Exception as e:
    print(f"[{datetime.now():%H:%M:%S}] Warning: history.json write failed: {e}")

# ── Push website JSON to Supabase (public site bucket) so the live site sees the
#    update WITHOUT a Netlify deploy. No-op without creds (local run unaffected). ──
try:
    import supabase_store as _sb
    if _sb.enabled():
        _s1 = _sb.upload_site(OUTPUT)    # dashboard.json
        _s2 = _sb.upload_site(HISTORY)   # history.json
        print(f"[{datetime.now():%H:%M:%S}] Supabase: website JSON synced (dashboard.json, history.json)."
              if (_s1 and _s2) else f"[{datetime.now():%H:%M:%S}] Supabase: website JSON sync FAILED.")
except Exception as e:
    print(f"[{datetime.now():%H:%M:%S}] Supabase site sync skipped ({e}).")
