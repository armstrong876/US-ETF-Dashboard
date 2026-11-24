"""
ETF Momentum Dashboard — ALL ETFs Data Engine
=============================================
Downloads 10 years of daily close prices for ~4500 ETFs via Yahoo Finance.
Writes dashboard_all.json.

Run:  python data_engine_all.py
Output: dashboard_all.json
"""

import json, os, time, sys
from datetime import datetime
import yfinance as yf
import pandas as pd

BASE_DIR   = os.path.dirname(os.path.abspath(__file__))
ETF_LIST   = os.path.join(BASE_DIR, "etf_list_all.json")
OUTPUT     = os.path.join(BASE_DIR, "dashboard_all.json")
BENCHMARK  = "SPY"
# Parquet cache (replaced *.pkl.gz — see data_engine.py note on numpy/pickle fragility)
CACHE_RAW  = os.path.join(BASE_DIR, "nav_all_raw.parquet")
CACHE_ADJ  = os.path.join(BASE_DIR, "nav_all_adj.parquet")
LEGACY_CACHE_RAW = os.path.join(BASE_DIR, "cache_raw_all.pkl.gz")
LEGACY_CACHE_ADJ = os.path.join(BASE_DIR, "cache_adj_all.pkl.gz")

PERIODS = {            # calendar lookback — identical rule to data_engine.py
    "1W":  pd.DateOffset(weeks=1),   "15D": pd.DateOffset(days=15),
    "1M":  pd.DateOffset(months=1),  "2M":  pd.DateOffset(months=2),
    "3M":  pd.DateOffset(months=3),  "6M":  pd.DateOffset(months=6),
    "9M":  pd.DateOffset(months=9),  "12M": pd.DateOffset(years=1),
    "2Y":  pd.DateOffset(years=2),   "3Y":  pd.DateOffset(years=3),
    "5Y":  pd.DateOffset(years=5),   "7Y":  pd.DateOffset(years=7),
    "10Y": pd.DateOffset(years=10),
}
CAGR_YEARS = {"12M": 1, "2Y": 2, "3Y": 3, "5Y": 5, "7Y": 7, "10Y": 10}   # shown annualised
US_ANCHOR_TICKERS = ("SPY", "QQQ", "IVV", "VOO", "IWM", "DIA")         # define the US trading calendar
STALE_DAYS = 5   # an ETF whose last price is older than this many US trading days is treated as closed (left out)

MOMENTUM_WEIGHTS = {"1M": 0.20, "3M": 0.30, "6M": 0.30, "12M": 0.20}

# Corporate-action repair (see data_engine.py): a one-day move outside these
# bounds (-30% / +30%) marks a suspected split / reverse split / bad stitch.
# The whole cache is scanned; leveraged single-stock ETFs with genuine huge
# moves get re-downloaded each run too (~230 tickers, about one extra batch).
JUMP_DOWN      = 0.70
JUMP_UP        = 1.30
NO_JUMP_CHECK  = {"^VIX"}
ACTION_FIELDS  = ("Stock Splits", "Dividends", "Capital Gains")
action_tickers = set()    # filled by download_in_batches when actions=True

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
tickers      = list(dict.fromkeys(e["symbol"] for e in etf_meta))   # each ticker once (the list has a few repeats)

# Ensure Market Indices are in tickers
for sym in MARKET_INDICES:
    if sym not in tickers:
        tickers.append(sym)

if BENCHMARK not in tickers:
    tickers.insert(0, BENCHMARK)

print(f"[{datetime.now():%H:%M:%S}] Fetching price data for {len(tickers)} ETFs in batches...")
print("This may take 5-15 minutes for 4500+ ETFs. Please wait...\n")

# ── Batch Download Helper Function ──────────────────────────────────────────
def download_in_batches(tickers_to_download, download_kwargs, batch_size=250, pause=1):
    all_raw_list = []
    all_adj_list = []
    
    for i in range(0, len(tickers_to_download), batch_size):
        batch = tickers_to_download[i:i+batch_size]
        print(f"[{datetime.now():%H:%M:%S}]   Fetching batch {i//batch_size + 1}/{(len(tickers_to_download)-1)//batch_size + 1} ({len(batch)} symbols)...")
        
        try:
            raw = yf.download(
                batch,
                progress=False,
                threads=True,
                ignore_tz=True,
                **download_kwargs
            )
            if isinstance(raw.columns, pd.MultiIndex):
                cr = raw["Close"]
                ca = raw.get("Adj Close", raw["Close"])
                for field in ACTION_FIELDS:
                    if field in raw.columns.get_level_values(0):
                        f = raw[field].fillna(0)
                        action_tickers.update(f.columns[(f != 0).any()])
            else:
                cr = raw[["Close"]]
                cr.columns = batch
                ca = raw.get("Adj Close", cr)
                if any(field in raw.columns and (raw[field].fillna(0) != 0).any() for field in ACTION_FIELDS):
                    action_tickers.update(batch)

            all_raw_list.append(cr)
            all_adj_list.append(ca)
        except Exception as e:
            print(f"  Error on batch {i}: {e}")
        time.sleep(pause)

    df_raw = pd.concat(all_raw_list, axis=1) if all_raw_list else pd.DataFrame()
    df_raw = df_raw.loc[:, ~df_raw.columns.duplicated()]
    if not df_raw.empty:
        df_raw = df_raw.dropna(how="all")
        df_raw.index = pd.to_datetime(df_raw.index)
        
    df_adj = pd.concat(all_adj_list, axis=1) if all_adj_list else pd.DataFrame()
    df_adj = df_adj.loc[:, ~df_adj.columns.duplicated()]
    if not df_adj.empty:
        df_adj = df_adj.dropna(how="all")
        df_adj.index = pd.to_datetime(df_adj.index)
        
    return df_raw, df_adj

def download_with_retries(tickers_to_download, download_kwargs, label, rounds=2, wait=60, batch_size=250, pause=1):
    """download_in_batches, then re-request tickers that came back empty (Yahoo
    rate limits / transient yfinance 'database is locked'), backing off between
    rounds. Genuinely delisted tickers simply stay empty."""
    df_raw, df_adj = download_in_batches(tickers_to_download, download_kwargs, batch_size, pause)
    for n in range(1, rounds + 1):
        empty = [t for t in tickers_to_download if t not in df_raw.columns or df_raw[t].isna().all()]
        if not empty:
            break
        print(f"[{datetime.now():%H:%M:%S}]   {label}: {len(empty)} tickers came back empty — retry {n}/{rounds} in {wait * n}s")
        time.sleep(wait * n)
        r2, a2 = download_in_batches(empty, download_kwargs, batch_size, pause)
        keep = [t for t in empty if t in r2.columns and t in a2.columns and r2[t].notna().any()]
        if keep:
            df_raw = pd.concat([df_raw.drop(columns=[c for c in keep if c in df_raw.columns]), r2[keep]], axis=1)
            df_adj = pd.concat([df_adj.drop(columns=[c for c in keep if c in df_adj.columns]), a2[keep]], axis=1)
    return df_raw, df_adj

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

def tickers_with_gaps(df, skip=()):
    """US tickers with no price on a day the US market traded, between their
    first and last price — a download that failed in some earlier run."""
    anchors = [t for t in US_ANCHOR_TICKERS if t in df.columns]
    if not anchors:
        return []
    cols = [c for c in df.columns if c not in skip]
    have = df[cols].reindex(df[anchors].dropna(how="all").index).notna()
    inside = have.cummax() & have[::-1].cummax()[::-1]
    gaps = (inside & ~have).sum()
    return sorted(gaps[gaps > 0].index)

def tickers_behind(df, skip=(), recent=STALE_DAYS):
    """US tickers whose last price is a few US trading days old (missing the
    latest days, e.g. after a rate-limited download) — still trading, so worth
    re-downloading. Funds silent for longer are treated as closed (not retried)."""
    anchors = [t for t in US_ANCHOR_TICKERS if t in df.columns]
    cal = df[anchors].dropna(how="all").index if anchors else df.index
    if len(cal) <= recent:
        return []
    last = df[[c for c in df.columns if c not in skip and c not in MARKET_INDICES]].apply(lambda s: s.last_valid_index())
    return sorted(t for t, d in last.items() if d is not None and cal[-recent - 1] <= d < cal[-1])

# ── Load or Create Cache ──────────────────────────────────────────────────────
close_raw = pd.DataFrame()
close_adj = pd.DataFrame()

# Pull the full-universe Parquet cache from Supabase (no-op without creds)
try:
    import supabase_store as _sb
    if _sb.enabled():
        _sb.download_file("nav/nav_all_raw.parquet", CACHE_RAW)
        _sb.download_file("nav/nav_all_adj.parquet", CACHE_ADJ)
except Exception:
    pass

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

# One-time migration from a readable legacy pickle cache (best-effort).
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
            close_raw_missing, close_adj_missing = download_in_batches(
                missing, 
                {"period": "11y", "interval": "1d", "auto_adjust": False}
            )
            # Concat columns
            close_raw = pd.concat([close_raw, close_raw_missing], axis=1)
            close_adj = pd.concat([close_adj, close_adj_missing], axis=1)
            print(f"[{datetime.now():%H:%M:%S}] Missing tickers merged successfully.")
        except Exception as e:
            print(f"[{datetime.now():%H:%M:%S}] Error fetching missing tickers: {e}")

# ── Download fresh data — Priority Batched ────────────────────────────────────
# Priority order (ensures most important symbols always get freshest data):
#   Batch 1 — Market Indices  (index cards on dashboard — fetch first)
#   Batch 2 — Core 80 ETFs   (main universe — returns, momentum, signals)
#   Batch 3 — Remaining ETFs  (extended universe — lower priority)
if cache_loaded:
    last_date  = close_raw.index[-1]
    # Go back 5 calendar days to safely cover weekends + public holidays gaps
    # so we never miss a trading day due to cache being slightly stale.
    fetch_from = last_date - pd.DateOffset(days=5)
    start_date = fetch_from.strftime("%Y-%m-%d")
    # end=TODAY is EXCLUSIVE in yfinance — so data is always capped at YESTERDAY.
    # This guarantees previous-day data regardless of what time the script runs.
    from datetime import date as _date_cls
    YESTERDAY  = _date_cls.today().strftime("%Y-%m-%d")
    print(f"[{datetime.now():%H:%M:%S}] Fetching incremental update {start_date} → {YESTERDAY} (prev day cap, priority batched)...")

    core_etf_symbols = []
    core_list_path   = os.path.join(BASE_DIR, "etf_list.json")
    if os.path.exists(core_list_path):
        with open(core_list_path) as _f:
            core_etf_symbols = [e["symbol"] for e in json.load(_f)]

    index_symbols = list(MARKET_INDICES.keys())
    batch1 = index_symbols                                                  # Priority 1
    batch2 = [t for t in core_etf_symbols if t not in batch1]              # Priority 2
    batch3 = [t for t in tickers if t not in batch1 and t not in batch2]   # Priority 3

    inc_kwargs = {"start": start_date, "end": YESTERDAY, "interval": "1d", "auto_adjust": False, "actions": True}

    print(f"[{datetime.now():%H:%M:%S}]   Priority 1 — Indices ({len(batch1)} symbols)...")
    r1, a1 = download_with_retries(batch1, inc_kwargs, "Indices", wait=20)
    print(f"[{datetime.now():%H:%M:%S}]   Priority 2 — Core ETFs ({len(batch2)} symbols)...")
    r2, a2 = download_with_retries(batch2, inc_kwargs, "Core ETFs", wait=20)
    print(f"[{datetime.now():%H:%M:%S}]   Priority 3 — Remaining ({len(batch3)} symbols)...")
    r3, a3 = download_with_retries(batch3, inc_kwargs, "Remaining")

    new_raw = pd.concat([r1, r2, r3], axis=1)
    new_adj = pd.concat([a1, a2, a3], axis=1)
    new_raw = new_raw.loc[:, ~new_raw.columns.duplicated(keep='last')]
    new_adj = new_adj.loc[:, ~new_adj.columns.duplicated(keep='last')]

    # Fresh values win, but a ticker whose download failed (all-NaN in new_raw)
    # keeps its cached prices for the overlap days instead of being blanked.
    close_raw = new_raw.combine_first(close_raw).sort_index()
    close_adj = new_adj.combine_first(close_adj).sort_index()

    # ── Corporate-action repair: re-download full history where Yahoo restated it ──
    # Triggers: a split/distribution in this run's window, or a suspicious one-day
    # jump anywhere in the cache (catches splits Yahoo dated outside the window).
    acted  = action_tickers & set(close_raw.columns)
    jumped = set(tickers_with_jumps(close_raw))
    # Indices + core ETFs: full history refreshed every run (as in the daily
    # engine). Other ETFs: refreshed when a US trading day is missing from their
    # history, so a gap left by an old failed download gets filled.
    refresh = (set(batch1) | set(batch2)) & set(close_raw.columns)
    gapped  = set(tickers_with_gaps(close_raw, skip=refresh))
    behind  = set(tickers_behind(close_raw, skip=refresh))   # missing the latest few days
    repair = sorted(acted | jumped | refresh | gapped | behind)
    if repair:
        print(f"[{datetime.now():%H:%M:%S}] Full-history repair for {len(repair)} tickers "
              f"(indices + core ETFs: {len(refresh)}, split/distribution: {len(acted)}, "
              f"suspicious jump: {len(jumped)}, missing days: {len(gapped)}, "
              f"missing latest days: {len(behind)})")
        full_start = (pd.Timestamp.today() - pd.DateOffset(years=11)).strftime("%Y-%m-%d")
        # Smaller, slower batches + 3 backed-off retry rounds: a burst of 11-year
        # downloads right after the incremental pass gets Yahoo-rate-limited
        # (first live run: 351 of 410 repairs refused with "Too Many Requests").
        time.sleep(30)
        fr, fa = download_with_retries(
            repair,
            {"start": full_start, "end": YESTERDAY, "interval": "1d", "auto_adjust": False},
            "Full-history repair", rounds=3, wait=60, batch_size=100, pause=5
        )
        got = [t for t in repair if t in fr.columns and t in fa.columns and fr[t].notna().any()]
        # Yahoo's history now starting much later than ours = ticker reused by a
        # new/restructured fund; the old fund's prices are dropped, not stitched.
        restarted = [t for t in got if t in close_raw.columns and close_raw[t].first_valid_index() is not None
                     and fr[t].first_valid_index() > max(close_raw[t].first_valid_index(), pd.Timestamp(full_start))
                                                     + pd.Timedelta(days=30)]
        if restarted:
            print(f"[{datetime.now():%H:%M:%S}]   Yahoo restarted history for {len(restarted)} tickers (new/restructured fund?): {restarted[:40]}")
        if got:
            close_raw = pd.concat([close_raw.drop(columns=got), with_newer_cache(fr[got], close_raw)], axis=1).sort_index()
            close_adj = pd.concat([close_adj.drop(columns=got), with_newer_cache(fa[got], close_adj)], axis=1).sort_index()
        failed = sorted(set(repair) - set(got))
        if failed:
            print(f"[{datetime.now():%H:%M:%S}]   Repair download failed for {len(failed)} tickers — kept cached data: {failed[:20]}")
        genuine = [t for t in tickers_with_jumps(close_raw) if t in got]
        if genuine:
            print(f"[{datetime.now():%H:%M:%S}]   Still a big one-day move after repair (genuine per Yahoo): {genuine[:40]}")
        still_gapped = [t for t in tickers_with_gaps(close_raw, skip=refresh) if t in got]
        if still_gapped:
            print(f"[{datetime.now():%H:%M:%S}]   Days Yahoo itself has no price for ({len(still_gapped)} tickers, "
                  f"previous close is used): {still_gapped[:20]}")

else:
    # Cold start: Full 11-year download — end=TODAY (exclusive) caps at yesterday
    from datetime import date as _date_cls
    YESTERDAY = _date_cls.today().strftime("%Y-%m-%d")
    print(f"[{datetime.now():%H:%M:%S}] Fetching full 11-year history from Yahoo Finance in batches (capped at {YESTERDAY})...")
    close_raw, close_adj = download_in_batches(
        tickers,
        {"start": (pd.Timestamp.today() - pd.DateOffset(years=11)).strftime("%Y-%m-%d"),
         "end": YESTERDAY, "interval": "1d", "auto_adjust": False}
    )

# ── Sanity check BEFORE touching disk or generating anything ──────────────────
# If Yahoo rate-limited/failed and we ended up with empty or badly incomplete
# data, stop here — never overwrite a good Parquet cache (or dashboard_all.json)
# with a broken one.
MIN_ROWS = 100
MIN_TICKER_COVERAGE = 0.5

if close_raw.empty or close_adj.empty:
    print(f"[{datetime.now():%H:%M:%S}] FATAL: fetched price data is empty — "
          f"likely a Yahoo Finance rate-limit or outage. Leaving existing cache/"
          f"dashboard files untouched and failing this run.")
    sys.exit(1)

if len(close_raw) < MIN_ROWS or len(close_adj) < MIN_ROWS:
    print(f"[{datetime.now():%H:%M:%S}] FATAL: fetched price data has only "
          f"{len(close_raw)} rows (expected >= {MIN_ROWS}). Leaving existing "
          f"cache/dashboard files untouched and failing this run.")
    sys.exit(1)

coverage = len(set(close_raw.columns) & set(tickers)) / max(len(tickers), 1)
if coverage < MIN_TICKER_COVERAGE:
    print(f"[{datetime.now():%H:%M:%S}] FATAL: only {coverage:.0%} of expected "
          f"tickers have data (expected >= {MIN_TICKER_COVERAGE:.0%}). Leaving "
          f"existing cache/dashboard files untouched and failing this run.")
    sys.exit(1)

# ── Bound Cache & Save ────────────────────────────────────────────────────────
# Limit history to the last 11 years to prevent memory leaks/unbounded growth
eleven_years_ago = datetime.now() - pd.DateOffset(years=11)
if not close_raw.empty:
    close_raw = close_raw.loc[close_raw.index >= eleven_years_ago]
if not close_adj.empty:
    close_adj = close_adj.loc[close_adj.index >= eleven_years_ago]

try:
    close_raw.to_parquet(CACHE_RAW, compression='zstd')
    close_adj.to_parquet(CACHE_ADJ, compression='zstd')
    print(f"[{datetime.now():%H:%M:%S}] Parquet caches updated and saved to disk.")
except Exception as e:
    print(f"[{datetime.now():%H:%M:%S}] Cache write error: {e}")

# ── Push full-universe Parquet cache to Supabase (private) ────────────────────
try:
    import supabase_store as _sb
    if _sb.enabled():
        _u1 = _sb.upload_file(CACHE_RAW, "nav/nav_all_raw.parquet")
        _u2 = _sb.upload_file(CACHE_ADJ, "nav/nav_all_adj.parquet")
        print(f"[{datetime.now():%H:%M:%S}] Supabase: full-universe Parquet pushed." if (_u1 and _u2)
              else f"[{datetime.now():%H:%M:%S}] Supabase: all-parquet push FAILED.")
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

PRICE_IDX = last_complete_trading_day(close_raw.index)
# US ETFs are dated by the last day the US market traded (index rows from other
# markets can run past the last US close on US holidays).
US_ANCHORS  = [t for t in US_ANCHOR_TICKERS if t in close_raw.columns]
US_CALENDAR = close_raw[US_ANCHORS].dropna(how="all").index if US_ANCHORS else close_raw.index
NAV_DATE = US_CALENDAR[-1] if len(US_CALENDAR) else close_raw.index[PRICE_IDX]
print(f"[{datetime.now():%H:%M:%S}] NAV date: {NAV_DATE.date()}")

def pct_return(series, label, end_date=None):
    """% change in Yahoo's closing price over PERIODS[label], ending end_date
    (default NAV_DATE). Start = the close on the same date one week/month/year
    earlier; on a weekend/holiday (or a day with no price) the previous close is
    used. 1Y and longer are annualised (CAGR). None if no price that far back.
    Identical to data_engine.py's pct_return."""
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

spy_returns = {}
if BENCHMARK in close_raw.columns:
    spy_series = close_raw[BENCHMARK].dropna()
    for label in PERIODS:
        spy_returns[label] = pct_return(spy_series, label)

print(f"[{datetime.now():%H:%M:%S}] Calculating returns...")
results = []
# A fund with no price for more than STALE_DAYS US trading days has stopped
# trading (closed/delisted): its frozen last price would show as 0.00% returns,
# so it is left out. It reappears automatically if it trades again.
STALE_CUTOFF = US_CALENDAR[-STALE_DAYS - 1] if len(US_CALENDAR) > STALE_DAYS else None
closed = []

for ticker in tickers:
    if ticker not in close_raw.columns or ticker not in close_adj.columns:
        continue

    series_raw = close_raw[ticker].dropna()
    series_adj = close_adj[ticker].dropna()
    if len(series_raw) < 10 or len(series_adj) < 10:
        continue
    if STALE_CUTOFF is not None and ticker not in MARKET_INDICES and series_raw.index[-1] < STALE_CUTOFF:
        closed.append(ticker)
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
        "price":       round(float(series_raw.asof(NAV_DATE)), 2), # Last settled NAV (not intraday)
        
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

    for label in PERIODS:
        val = pct_return(series_raw, label)  # Use raw Close — matches finance website prices
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
# Each index uses its OWN last available date — not the global US NAV date.
# This ensures Nifty/Indian indices show their correct settlement date.
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

            # Same calendar rule as the ETFs, ending on this index's own last close.
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

print(f"\n[{datetime.now():%H:%M:%S}] DONE! dashboard_all.json written.")

# Push the All-ETFs dashboard to Supabase (public site bucket) so the live
# "All ETFs" tab updates WITHOUT a Netlify deploy. No-op without creds.
try:
    import supabase_store as _sb
    if _sb.enabled():
        print(f"[{datetime.now():%H:%M:%S}] Supabase: dashboard_all.json synced."
              if _sb.upload_site(OUTPUT)
              else f"[{datetime.now():%H:%M:%S}] Supabase: dashboard_all.json sync FAILED.")
except Exception as _e:
    print(f"[{datetime.now():%H:%M:%S}] Supabase all-sync skipped ({_e}).")
print(f"   ETFs processed : {len(results)}")
if closed:
    print(f"   Left out — no price for over {STALE_DAYS} US trading days (closed/delisted): "
          f"{len(closed)} {closed[:60]}")
