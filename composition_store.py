"""
Per-ETF monthly snapshot store (Parquet)
========================================
ONE Parquet file per ETF, holding EVERY monthly detail for that ETF:

    ETF Data/composition/{SYMBOL}.parquet        <- main folder, one sub-file per ETF

Each run appends one month of rows. Nothing is ever overwritten, so the file
becomes the permanent month-by-month history that the Portfolio Builder reads.

SOURCE OF TRUTH (deliberate, do not mix):
    Portfolio Composition  -> etfdb      (holdings / sector / country / market cap)
    Key Fundamentals       -> yfinance   (aum / pe / expense_ratio / yield / inception)
    Beta + all risk ratios -> NOT STORED HERE. Calculated from NAVs by
                              etf_analytics_engine.py. Never fetched from a vendor.

Every row carries its own `source`, so a value can always be traced back and two
vendors' numbers can never be silently blended.

SCHEMA (long / tidy — one row per measurement, per month):
    as_of   date32   last completed month-end; the snapshot key
    kind    string   holding | sector | country | region | mcap | fundamental
    key     string   NVDA | Electronic Technology | United States | Large | aum
    value   float64  the number (weight % for composition, metric for fundamentals)
    text    string   company name / inception date / category  (null when numeric)
    source  string   etfdb | yfinance

Long format means etfdb adding a sector, or you adding a new fundamental, needs
NO schema change and cannot break older months.

SAFETY RULES (all enforced on every write):
    1. Idempotent   — writing a month REPLACES that month's rows wholesale (stale
                      holdings can't linger); re-running the same data is a no-op.
    2. Never shrink — refuses to write if it would drop an existing month, OR if a
                      re-write would collapse an existing month's row count (a
                      half-failed scrape must not degrade a good month). Pass
                      allow_shrink=True to override deliberately.
    3. Validated    — re-reads the file after writing and verifies months + row count
                      BEFORE it is allowed to replace the real file.
    4. Atomic       — writes to .tmp then os.replace(), so a crash can't truncate a file.
    5. Fixed dtypes — identical every month, so stacked reads never fail on type drift.
"""
import os
import pandas as pd

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LOCAL_DIR = os.path.join(BASE_DIR, "composition")      # local mirror
REMOTE_DIR = "composition"                             # folder inside the private bucket

COLUMNS = ["as_of", "kind", "key", "value", "text", "source"]
KINDS = ("holding", "sector", "country", "region", "mcap", "fundamental")

# Fundamentals we keep, and where each one legitimately comes from.
# beta is absent ON PURPOSE — it is derived from NAVs, not fetched.
FUNDAMENTAL_FIELDS = ("aum", "pe", "expense_ratio", "yield", "inception", "category", "name")


def _frame(rows):
    """Build the canonical frame: fixed column order, fixed dtypes, stable sort."""
    df = pd.DataFrame(list(rows), columns=COLUMNS)
    df["as_of"] = pd.to_datetime(df["as_of"]).dt.date
    df["value"] = pd.to_numeric(df["value"], errors="coerce").astype("float64")
    for c in ("kind", "key", "text", "source"):
        df[c] = df[c].astype("string")
    return (df.sort_values(["as_of", "kind", "key", "source"], kind="mergesort")
              .reset_index(drop=True))


# ── row builders ──────────────────────────────────────────────────────────
def composition_rows(rec):
    """etfdb composition record -> long rows. `rec` is etf_details_engine's dict."""
    as_of, src = rec["as_of"], "etfdb"
    rows = []
    for h in rec.get("holdings") or []:
        rows.append((as_of, "holding", h["sym"], h.get("wt"), h.get("name"), src))
    # region is kept HERE (cheap, dictionary-encoded) even though the website's
    # JSON drops it — the Portfolio Builder benefits from the complete record.
    # etfdb also states the FULL position count and (via the weights above) the
    # top-10 concentration. Stored as fundamentals tagged source=etfdb so they
    # never blend with the yfinance fundamentals, and so the Portfolio Builder
    # can track concentration drift month over month.
    if rec.get("holdings_count") is not None:
        rows.append((as_of, "fundamental", "holdings_count",
                     rec["holdings_count"], None, src))
    if rec.get("top10_pct") is not None:
        rows.append((as_of, "fundamental", "top10_pct",
                     rec["top10_pct"], None, src))

    for kind, field in (("sector", "sector"), ("country", "country"),
                        ("region", "region"), ("mcap", "market_cap")):
        for k, v in (rec.get(field) or {}).items():
            # Drop 0.0 buckets — etfdb pads unused market-cap bands with zeros and
            # they carry no information, only bytes.
            if v:
                rows.append((as_of, kind, k, v, None, src))
    return rows


def fundamental_rows(as_of, profile):
    """yfinance profile dict -> long rows. Numbers go in `value`, text in `text`."""
    src = "yfinance"
    rows = []
    for f in FUNDAMENTAL_FIELDS:
        v = profile.get(f)
        if v is None or v == "":
            continue
        if f in ("inception", "category", "name"):
            rows.append((as_of, "fundamental", f, None, str(v), src))
        else:
            rows.append((as_of, "fundamental", f, v, None, src))
    return rows


# ── the guarded write ─────────────────────────────────────────────────────
def path_for(symbol):
    return os.path.join(LOCAL_DIR, f"{symbol.upper()}.parquet")


def read_history(symbol):
    fp = path_for(symbol)
    if not os.path.exists(fp):
        return None
    return pd.read_parquet(fp)


def upsert_month(symbol, rows, allow_shrink=False):
    """Merge one month of `rows` into {SYMBOL}.parquet under all five safety rules.
    Returns (n_rows, sorted_months). Raises on any integrity violation."""
    if not rows:
        raise ValueError(f"{symbol}: refusing to write an empty month")

    new = _frame(rows)
    months_new = set(new["as_of"].unique())
    if len(months_new) != 1:
        raise ValueError(f"{symbol}: a write must cover exactly one month, got {months_new}")
    month = months_new.pop()

    bad = set(new["kind"].dropna().unique()) - set(KINDS)
    if bad:
        raise ValueError(f"{symbol}: unknown kind(s) {bad}")

    os.makedirs(LOCAL_DIR, exist_ok=True)
    fp = path_for(symbol)

    old = read_history(symbol)
    if old is not None and not old.empty:
        months_before = set(old["as_of"].unique())
        # RULE 2b: re-writing a month must not gut it. A partially-failed scrape
        # would otherwise silently replace a good month with a fraction of its rows.
        if month in months_before and not allow_shrink:
            had = int((old["as_of"] == month).sum())
            if len(new) < had * 0.5:
                raise RuntimeError(
                    f"{symbol}: refusing to rewrite {month} with {len(new)} rows "
                    f"(existing month has {had}). Looks like a partial scrape — "
                    f"pass allow_shrink=True only if this really is intended.")
        # RULE 1: a month is REPLACED, not merged — drop every existing row for this
        # month before inserting the new ones. A merge would leave a holding that
        # etfdb has since dropped sitting in the snapshot forever.
        kept = _frame(old.itertuples(index=False, name=None))
        kept = kept[kept["as_of"] != month]
        merged = pd.concat([kept, new], ignore_index=True)
    else:
        months_before = set()
        merged = new

    merged = merged.drop_duplicates(subset=["as_of", "kind", "key", "source"], keep="last")
    merged = (merged.sort_values(["as_of", "kind", "key", "source"], kind="mergesort")
                    .reset_index(drop=True))

    months_after = set(merged["as_of"].unique())
    # RULE 2: never shrink
    lost = months_before - months_after
    if lost:
        raise RuntimeError(f"{symbol}: write would LOSE month(s) {sorted(map(str, lost))} — aborted")
    if month not in months_after:
        raise RuntimeError(f"{symbol}: new month {month} missing after merge — aborted")

    # RULE 4: atomic — temp file first
    tmp = fp + ".tmp"
    merged.to_parquet(tmp, compression="zstd", index=False)

    # RULE 3: validate by re-reading before we let it replace the real file
    try:
        chk = pd.read_parquet(tmp)
        if len(chk) != len(merged):
            raise RuntimeError(f"row count {len(chk)} != {len(merged)}")
        if set(chk["as_of"].unique()) != months_after:
            raise RuntimeError("month set changed on re-read")
        if chk["value"].dtype != "float64":
            raise RuntimeError(f"value dtype drifted to {chk['value'].dtype}")
    except Exception:
        os.remove(tmp)
        raise

    os.replace(tmp, fp)
    return len(merged), sorted(str(m) for m in months_after)


# ── Supabase sync (private bucket, alongside the nav/*.parquet caches) ─────
try:
    import supabase_store as _sb
except Exception:
    _sb = None


def _remote(symbol):
    return f"{REMOTE_DIR}/{symbol.upper()}.parquet"


def pull(symbol):
    """Download {SYMBOL}.parquet from Supabase so this run appends to the real
    history rather than starting a fresh file. True if a file came down.

    CRITICAL: if the object exists remotely but the download fails, we must NOT
    continue — writing would create a new file and silently orphan the history.
    That case raises."""
    if not (_sb and _sb.enabled()):
        return False
    os.makedirs(LOCAL_DIR, exist_ok=True)
    fp = path_for(symbol)
    if _sb.download_file(_remote(symbol), fp):
        try:
            pd.read_parquet(fp)          # must be readable, not a truncated body
            return True
        except Exception as e:
            os.remove(fp)
            raise RuntimeError(f"{symbol}: downloaded parquet is unreadable ({e}) — aborting "
                               f"rather than risk overwriting good history")
    # Nothing remote (first ever run for this ETF) -> start clean locally.
    if os.path.exists(fp):
        os.remove(fp)
    return False


def push(symbol):
    """Upload {SYMBOL}.parquet to the private bucket. True on success."""
    if not (_sb and _sb.enabled()):
        return False
    return _sb.upload_file(path_for(symbol), _remote(symbol),
                           bucket=_sb.BUCKET,
                           content_type="application/octet-stream")
