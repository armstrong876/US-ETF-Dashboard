"""
ETF Details Engine (etfdb.com) — monthly composition snapshots
==============================================================
One source, one clean pull per ETF: holdings + sector + country + region +
market-cap breakdown, all straight from etfdb.com/etf/{TICKER}/ (server-rendered
HTML, no login, no API key — verified 2026-07-22 for QQQ & SMH).

Design goals set by Ashwin:
  * Fetch once a MONTH for all 80 ETFs.
  * Stamp each snapshot with the END of the month it was fetched in
    (fetched 10 or 20 Jul -> as_of = 2026-07-31), so we get one clean dated
    point per month no matter which day the job runs.
  * Store COMPACT (name->pct maps, short holding keys) but WELL-STRUCTURED, so
    the same files can later feed the ETF one-pager AND a Portfolio Builder /
    historical analysis by stacking monthly snapshots.

Storage layout (one small file per ETF, ~2-3 KB each):
    site-data/details/{SYMBOL}.json   (public Supabase bucket, proxied by Netlify)

Politeness: etfdb sits behind Cloudflare. We fetch gently (a few seconds
between ETFs), keep a retry, and NEVER blow away a previously-good file if a
single fetch fails.

Run:
    python etf_details_engine.py QQQ            # one or more tickers
    python etf_details_engine.py --all          # every ticker in etf_list.json
    PUSH=1 python etf_details_engine.py QQQ      # also upload to Supabase
"""

import os
import re
import sys
import json
import time
from datetime import date, datetime, timedelta

import requests
from bs4 import BeautifulSoup

try:
    import supabase_store as _sb
except Exception:
    _sb = None

try:
    import composition_store as _cs
except Exception:
    _cs = None

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DETAILS_DIR = os.path.join(BASE_DIR, "details")
ETF_LIST = os.path.join(BASE_DIR, "etf_list.json")
YF_FILE = os.path.join(BASE_DIR, "yf_profiles.json")   # Key Fundamentals (yfinance)

ETFDB_URL = "https://etfdb.com/etf/{sym}/"
HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

MAX_HOLDINGS = 15          # etfdb shows ~top 15 free; the rest is Pro-only
CRAWL_DELAY = 4            # seconds between ETFs (respect etfdb's 3s crawl-delay)


# ── ETF metadata (name / asset_class / category) from etf_list.json ────────
def _load_meta():
    try:
        with open(ETF_LIST, encoding="utf-8") as f:
            data = json.load(f)
        items = data.values() if isinstance(data, dict) else data
        out = {}
        for x in items:
            if isinstance(x, dict) and x.get("symbol"):
                out[x["symbol"].upper()] = {
                    "name": x.get("name"),
                    "asset_class": x.get("asset_class"),
                    "category": x.get("category"),
                }
        return out
    except Exception:
        return {}


META = _load_meta()


# ── date helper ───────────────────────────────────────────────────────────
# ETF issuers publish month-end holdings with a lag, and etfdb does not state an
# "as of" date anywhere on the page — so the snapshot's period has to be inferred
# from the run date. Providers have reliably published the prior month by the 11th,
# which is why the job is scheduled for the 12th.
PUBLISH_DAY = 11


def month_end(d=None):
    """The month-end the holdings on the page actually represent.

    Run on/after the 11th -> the previous month is published:
        2026-09-12 -> 2026-08-31
        2026-07-22 -> 2026-06-30
    Run BEFORE the 11th -> the previous month is not out yet, so the page is
    still showing the month before that:
        2026-09-03 -> 2026-07-31
    Getting this wrong mislabels a snapshot by a full month, which would corrupt
    any month-over-month comparison in the Portfolio Builder."""
    d = d or date.today()
    prev_month_end = d.replace(day=1) - timedelta(days=1)
    if d.day >= PUBLISH_DAY:
        return prev_month_end.isoformat()
    return (prev_month_end.replace(day=1) - timedelta(days=1)).isoformat()


# ── parsing helpers ───────────────────────────────────────────────────────
def _pct(text):
    if text is None:
        return None
    try:
        return round(float(text.replace("%", "").replace(",", "").strip()), 2)
    except ValueError:
        return None


def _rows(table):
    out = []
    for tr in table.find_all("tr"):
        cells = [td.get_text(" ", strip=True) for td in tr.find_all(["td", "th"])]
        if cells:
            out.append(cells)
    return out


def _classify(header_cells):
    """Identify an etfdb data table from its header row text."""
    h = " ".join(header_cells).lower()
    if "% assets" in h:
        return "holdings"
    if h.startswith("sector"):
        return "sector"
    if h.startswith("country"):
        return "country"
    if h.startswith("region"):
        return "region"
    if h.startswith("market cap"):
        return "market_cap"
    return None


def _holdings_count(soup):
    """Total number of holdings, as etfdb states it on the page.

    This is the only place the FULL count is available — the holdings table
    itself is capped at the free-tier top 15 — and it is fresher than the
    static count in etf_list.json (QQQ read 103 here vs 102 there)."""
    for node in soup.find_all(string=re.compile(r"Number of Holdings", re.I)):
        parent = node.parent
        for _ in range(3):
            if parent is None:
                break
            m = re.search(r"Number of Holdings\s*:?\s*([\d,]+)",
                          parent.get_text(" ", strip=True), re.I)
            if m:
                try:
                    n = int(m.group(1).replace(",", ""))
                    # sanity-bound it: a real ETF holds 1..20000 positions
                    return n if 0 < n <= 20000 else None
                except ValueError:
                    return None
            parent = parent.parent
    return None


def _fund_name(soup, sym):
    # etfdb H1 is like "QQQ Invesco QQQ Trust Series I"; title is the clean name.
    h1 = soup.find("h1")
    if h1:
        txt = h1.get_text(" ", strip=True)
        txt = re.sub(rf"^\s*{re.escape(sym)}\s+", "", txt, flags=re.I).strip()
        if txt:
            return txt
    if soup.title:
        t = soup.title.get_text(strip=True)
        t = re.split(r"\s*\|\s*", t)[0].strip()
        if t and t.upper() != sym:
            return t
    return sym


def parse_etfdb(html, sym):
    soup = BeautifulSoup(html, "html.parser")
    result = {"holdings": [], "sector": {}, "country": {}, "region": {},
              "market_cap": {}, "holdings_count": None}

    for table in soup.find_all("table"):
        rows = _rows(table)
        if len(rows) < 2:
            continue
        kind = _classify(rows[0])
        if kind is None:
            continue
        body = rows[1:]

        if kind == "holdings" and not result["holdings"]:
            for r in body:
                if len(r) < 3:
                    continue                       # skips the "Export All ... Pro" row
                pct = _pct(r[-1])
                if pct is None:
                    continue
                result["holdings"].append({"sym": r[0], "name": r[1], "wt": pct})
                if len(result["holdings"]) >= MAX_HOLDINGS:
                    break

        elif kind in ("sector", "country", "region", "market_cap") and not result[kind]:
            for r in body:
                if len(r) < 2:
                    continue
                pct = _pct(r[-1])
                if pct is not None and r[0]:
                    result[kind][r[0]] = pct

    result["holdings_count"] = _holdings_count(soup)
    return result, _fund_name(soup, sym)


# ── fetch one ETF ─────────────────────────────────────────────────────────
def fetch_symbol(sym, tries=3):
    url = ETFDB_URL.format(sym=sym)
    last = None
    for i in range(tries):
        try:
            r = requests.get(url, headers=HEADERS, timeout=30)
            if r.status_code == 200 and "% Assets" in r.text:
                return r.text
            last = f"HTTP {r.status_code}"
        except Exception as e:
            last = str(e)
        print(f"    retry {i+1}/{tries} ({last})")
        time.sleep(CRAWL_DELAY * (i + 1))
    raise RuntimeError(f"{sym}: fetch failed ({last})")


def build_record(sym):
    html = fetch_symbol(sym)
    parsed, name = parse_etfdb(html, sym)
    meta = META.get(sym.upper(), {})
    has_breakdown = bool(parsed["sector"] or parsed["country"] or parsed["market_cap"])
    return {
        "symbol": sym,
        "name": name or meta.get("name") or sym,
        "asset_class": meta.get("asset_class"),     # from etf_list.json (authoritative)
        "category": meta.get("category"),
        "has_breakdown": has_breakdown,             # False for commodity funds -> hide those sections
        "as_of": month_end(),                       # month-END stamp (previous completed month)
        "fetched_on": date.today().isoformat(),
        "source": "etfdb.com",
        # full position count (the holdings list below is only the top 15)
        "holdings_count": parsed.get("holdings_count"),
        # top-10 weight, summed from the weights on this same page — the one
        # figure the dashboard used to take from a static April snapshot
        "top10_pct": (round(sum(h["wt"] for h in parsed["holdings"][:10]), 2)
                      if parsed["holdings"] else None),
        "holdings": parsed["holdings"],
        "sector": parsed["sector"],
        "country": parsed["country"],
        "region": parsed["region"],
        "market_cap": parsed["market_cap"],
    }


def is_complete(rec):
    """Worth saving if there is anything real to show — holdings OR a breakdown.
    Commodity funds (GLD = Gold 100%, etc.) have holdings but no breakdown; we
    still save them so all 80 ETFs get a file."""
    return bool(rec["holdings"]) or bool(rec["sector"] or rec["country"] or rec["market_cap"])


# ── save / upload ─────────────────────────────────────────────────────────
# Fields the website never reads. `region` is still kept in the Parquet history
# (see composition_store) — it is only dropped from the file the browser fetches.
JSON_DROP = ("region", "source")


def save_local(rec):
    """Write the compact JSON the website reads. No indentation and no unused
    fields: the browser gets ~890 B over the wire after Brotli."""
    os.makedirs(DETAILS_DIR, exist_ok=True)
    path = os.path.join(DETAILS_DIR, f"{rec['symbol']}.json")
    slim = {k: v for k, v in rec.items() if k not in JSON_DROP}
    with open(path, "w", encoding="utf-8") as f:
        json.dump(slim, f, ensure_ascii=False, separators=(",", ":"))
    return path


def load_fundamentals():
    """Key Fundamentals come from yfinance (yf_profiles.json). Pulled from
    Supabase when available so a GitHub run has the current month's values."""
    if _sb and _sb.enabled():
        _sb.download_file("nav/yf_profiles.json", YF_FILE)
    try:
        with open(YF_FILE, encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"  (no yf_profiles.json — fundamentals will be skipped: {e})")
        return {}


def store_month(rec, profile, do_push):
    """Append this month to the ETF's own Parquet file — the permanent history
    the Portfolio Builder reads. Composition from etfdb, fundamentals from
    yfinance, each row tagged with its source. Beta is NOT here: it is
    calculated from NAVs by etf_analytics_engine.py."""
    if _cs is None:
        print("    (composition_store unavailable — parquet step skipped)")
        return False
    sym = rec["symbol"]
    if do_push:
        _cs.pull(sym)                      # append to the real history, not a fresh file
    rows = _cs.composition_rows(rec)
    if profile:
        rows += _cs.fundamental_rows(rec["as_of"], profile)
    n, months = _cs.upsert_month(sym, rows)
    pushed = _cs.push(sym) if do_push else False
    print(f"    parquet: {n} rows across {len(months)} month(s)"
          f"{' -> Supabase OK' if pushed else (' -> Supabase FAILED' if do_push else ' (local only)')}")
    return True


def upload(rec):
    if not (_sb and _sb.enabled()):
        print(f"    (Supabase not enabled — skipped upload for {rec['symbol']})")
        return False
    path = os.path.join(DETAILS_DIR, f"{rec['symbol']}.json")
    ok = _sb.upload_file(path, f"details/{rec['symbol']}.json",
                         bucket=_sb.SITE_BUCKET,
                         content_type="application/json",
                         cache_control="max-age=300")
    print(f"    Supabase upload {'OK' if ok else 'FAILED'}: details/{rec['symbol']}.json")
    return ok


# ── derived fundamentals the daily dashboard needs ────────────────────────
DERIVED_FILE = os.path.join(BASE_DIR, "etf_derived.json")
DERIVED_REMOTE = "nav/etf_derived.json"


def publish_derived(records, do_push):
    """Write {SYMBOL: {holdings, top10_pct, as_of}} to one small file.

    data_engine.py reads this on the DAILY run to fill the Holdings and
    Top-10 % columns, which were otherwise stuck on a static April snapshot.
    One aggregate file rather than the 80 per-ETF files keeps the daily job to
    a single download.

    MERGES with whatever is already published, so a single-symbol run cannot
    wipe the other 79 entries."""
    if not records:
        return

    existing = {}
    if do_push and _sb and _sb.enabled():
        if _sb.download_file(DERIVED_REMOTE, DERIVED_FILE):
            try:
                with open(DERIVED_FILE, encoding="utf-8") as f:
                    existing = json.load(f) or {}
            except Exception:
                existing = {}
    elif os.path.exists(DERIVED_FILE):
        try:
            with open(DERIVED_FILE, encoding="utf-8") as f:
                existing = json.load(f) or {}
        except Exception:
            existing = {}

    for rec in records:
        existing[rec["symbol"]] = {
            "holdings": rec.get("holdings_count"),
            "top10_pct": rec.get("top10_pct"),
            "as_of": rec.get("as_of"),
        }

    with open(DERIVED_FILE, "w", encoding="utf-8") as f:
        json.dump(existing, f, ensure_ascii=False, separators=(",", ":"), sort_keys=True)

    if do_push and _sb and _sb.enabled():
        ok = _sb.upload_file(DERIVED_FILE, DERIVED_REMOTE)
        print(f"  etf_derived.json ({len(existing)} symbols) -> Supabase "
              f"{'OK' if ok else 'FAILED'}")
    else:
        print(f"  etf_derived.json written locally ({len(existing)} symbols)")


# ── driver ────────────────────────────────────────────────────────────────
def load_symbols(args):
    if "--all" in args:
        with open(ETF_LIST, encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            return list(data.keys())
        return [(x if isinstance(x, str) else x.get("symbol") or x.get("ticker")) for x in data]
    syms = [a.upper() for a in args if not a.startswith("--")]
    return syms or ["QQQ"]


def main():
    args = sys.argv[1:]
    symbols = load_symbols(args)
    do_push = os.environ.get("PUSH") == "1"
    profiles = load_fundamentals()

    print("=" * 60)
    print("  ETF Details Engine — etfdb.com (monthly composition)")
    print(f"  Run     : {datetime.now():%Y-%m-%d %H:%M:%S}")
    print(f"  as_of   : {month_end()}  (month-end stamp)")
    print(f"  Symbols : {', '.join(symbols)}")
    print(f"  Upload  : {'YES (PUSH=1)' if do_push else 'no (local only)'}")
    print(f"  Fundament: {len(profiles):,} yfinance profiles loaded")
    print(f"  Sources : composition=etfdb  fundamentals=yfinance  beta=NAV (not fetched)")
    print("=" * 60)

    ok, failed, store_failed = [], [], []
    good_records = []
    for i, sym in enumerate(symbols):
        print(f"\n[{datetime.now():%H:%M:%S}] {sym} — fetching etfdb.com ...")
        try:
            rec = build_record(sym)
            if not is_complete(rec):
                print(f"  {sym}: incomplete (holdings={len(rec['holdings'])}, "
                      f"sectors={len(rec['sector'])}) — not saved.")
                failed.append(sym)
                continue
            path = save_local(rec)
            print(f"  {sym}: saved {os.path.basename(path)} — "
                  f"{len(rec['holdings'])} holdings, {len(rec['sector'])} sectors, "
                  f"{len(rec['country'])} countries, {len(rec['market_cap'])} mkt-cap bands")
            if do_push:
                upload(rec)
            # Append this month to the ETF's Parquet history. A failure here must
            # not lose the JSON we just wrote, so it is reported and counted
            # separately rather than aborting the whole run.
            try:
                store_month(rec, profiles.get(sym), do_push)
            except Exception as e:
                print(f"    PARQUET FAILED for {sym}: {e}")
                store_failed.append(sym)
            good_records.append(rec)
            ok.append(sym)
        except Exception as e:
            print(f"  ERROR {sym}: {e} — existing file left untouched.")
            failed.append(sym)
        if i < len(symbols) - 1:
            time.sleep(CRAWL_DELAY)

    publish_derived(good_records, do_push)

    print(f"\nDone. OK={len(ok)}  Failed={len(failed)}"
          + (f"  (failed: {', '.join(failed)})" if failed else ""))


if __name__ == "__main__":
    main()
