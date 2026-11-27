"""
Holdings Engine — official fund-company files (replaces the etfdb scraper)
=========================================================================
Runs on the 1st and 16th of each month from GitHub. For each of the 80 universe
funds it builds the composition the website and the Portfolio Builder read:

    1. FULL holdings list from the fund company's own file (holdings_sources.py);
       SEC filing when the company blocks downloads; Yahoo for FNGS (an ETN).
    2. Each stock's sector + country: iShares' official GICS classification
       (from iShares' own files — every stock they hold) first; Yahoo second
       (looked up once, then cached in Supabase).
    3. Each stock's market cap in USD (Yahoo bulk quote) -> Large/Mid/Small/Micro
       using the same cut-offs the site shows.
    4. Fund sector / country / market-cap split = sum of ITS OWN holdings' weights,
       so every number on a fund page comes from ONE file with ONE date.
       Nothing is guessed: unmatched holdings appear as "Unclassified", cash as
       "Cash & Other".

SAFETY (a fund is only published if it passes every check; otherwise its
previous file stays live and the GitHub run ends FAILED with the reason):
    * weights of the downloaded file add up to 90-110 %
    * holdings date is fresh for its source (company file 14 days, Vanguard 75,
      SEC filing 200)
    * at least 85 % of the fund's stock weight got a sector
    * holdings count did not collapse vs the previously published file (< 50 %)
    * a fund that normally uses its company file but fell back to the SEC
      filing is published (dated) but flagged, so someone looks at it

Outputs
    site-data/details/{SYM}.json   what the ETF page reads (same format as before)
    site-data/holdings/{SYM}.json  every holding with sector/country/cap (Portfolio Builder)
    ETF Data/composition/{SYM}.parquet   dated history (composition_store.py)
    ETF Data/nav/etf_derived.json  holdings count + top-10 % for the daily dashboard
    ETF Data/holdings/stock_cache.json   per-stock classifications reused next run

Run
    python holdings_engine.py --all          # every fund in etf_list.json, local only
    python holdings_engine.py QQQ IVV        # some funds
    PUSH=1 python holdings_engine.py --all   # also upload to Supabase (GitHub run)
"""
import difflib
import json
import os
import re
import sys
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime

import holdings_sources as S

try:
    import supabase_store as _sb
except Exception:
    _sb = None
try:
    import composition_store as _cs
except Exception:
    _cs = None

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ETF_LIST = os.path.join(BASE_DIR, "etf_list.json")
DETAILS_DIR = os.path.join(BASE_DIR, "details")
FULL_DIR = os.path.join(BASE_DIR, "holdings_full")
WORK_DIR = os.path.join(BASE_DIR, "holdings_work")
CACHE_FILE = os.path.join(WORK_DIR, "stock_cache.json")
CACHE_REMOTE = "holdings/stock_cache.json"            # private bucket
YF_FILE = os.path.join(BASE_DIR, "yf_profiles.json")
DERIVED_FILE = os.path.join(BASE_DIR, "etf_derived.json")
DERIVED_REMOTE = "nav/etf_derived.json"

LOOKUP_ONLY = ["IEMG", "IXUS", "EEMS", "SCZ"]   # broad iShares funds used ONLY as a classification lookup
MAX_AGE_DAYS = {"iShares": 14, "State Street": 14, "VanEck": 14, "Global X": 14, "First Trust": 14,
                "Vanguard": 75, "SEC": 200, "Yahoo": 3}
MIN_SECTOR_COVERAGE = 85.0
CAP_BANDS = [(12.9e9, "Large"), (2.7e9, "Mid"), (0.6e9, "Small"), (0, "Micro")]   # same cut-offs the site shows

GICS = ["Information Technology", "Health Care", "Financials", "Consumer Discretionary", "Communication Services",
        "Industrials", "Consumer Staples", "Energy", "Utilities", "Real Estate", "Materials"]
SECTOR_FIX = {"Communication": "Communication Services", "Technology": "Information Technology",
              "Financial Services": "Financials", "Healthcare": "Health Care",
              "Consumer Cyclical": "Consumer Discretionary", "Consumer Defensive": "Consumer Staples",
              "Basic Materials": "Materials"}
COUNTRY_FIX = {"Korea (South)": "South Korea", "Russian Federation": "Russia"}

EXCH_SFX = {"NASDAQ": "", "NYSE": "", "Nyse Mkt Llc": "", "Cboe BZX": "", "TXE": "", "Non-Nms Quotation Service (Nnqs)": "",
            "Tokyo Stock Exchange": ".T", "Hong Kong Exchanges And Clearing Ltd": ".HK", "London Stock Exchange": ".L",
            "Shanghai Stock Exchange": ".SS", "Shenzhen Stock Exchange": ".SZ", "National Stock Exchange Of India": ".NS",
            "Bse Ltd": ".BO", "Xetra": ".DE", "Deutsche Boerse Xetra": ".DE", "Asx - All Markets": ".AX",
            "Nyse Euronext - Euronext Paris": ".PA", "SIX Swiss Exchange": ".SW", "Taiwan Stock Exchange": ".TW",
            "Gretai Securities Market": ".TWO", "Borsa Italiana": ".MI", "Tel Aviv Stock Exchange": ".TA",
            "Toronto Stock Exchange": ".TO", "Euronext Amsterdam": ".AS", "Bolsa De Madrid": ".MC", "XBSP": ".SA",
            "Singapore Exchange": ".SI", "Korea Exchange (Stock Market)": ".KS", "Korea Exchange (Kosdaq)": ".KQ",
            "Oslo Bors Asa": ".OL", "Nyse Euronext - Euronext Brussels": ".BR", "Nasdaq Omx Helsinki Ltd.": ".HE",
            "Omx Nordic Exchange Copenhagen A/S": ".CO", "Wiener Boerse Ag": ".VI", "Saudi Stock Exchange": ".SR",
            "Johannesburg Stock Exchange": ".JO", "Nyse Euronext - Euronext Lisbon": ".LS",
            "Irish Stock Exchange - All Market": ".IR", "Bolsa Mexicana De Valores": ".MX", "Bursa Malaysia": ".KL",
            "New Zealand Exchange Ltd": ".NZ", "Warsaw Stock Exchange/Equities/Main Market": ".WA",
            "Stock Exchange Of Thailand": ".BK", "Athens Exchange S.A. Cash Market": ".AT", "Istanbul Stock Exchange": ".IS",
            "Santiago Stock Exchange": ".SN", "Qatar Exchange": ".QA", "Indonesia Stock Exchange": ".JK",
            "Philippine Stock Exchange Inc.": ".PS", "Kuwait Stock Exchange": ".KW", "Budapest Stock Exchange": ".BD",
            "Bolsa De Valores De Colombia": ".CL", "Prague Stock Exchange": ".PR", "Egyptian Exchange": ".CA",
            "Abu Dhabi Securities Exchange": ".AD", "Dubai Financial Market": ".AE"}
NORDIC = {"SEK": ".ST", "EUR": ".HE", "DKK": ".CO"}
BBG_SFX = {"US": "", "UW": "", "UN": "", "UQ": "", "CN": ".TO", "CT": ".TO", "AU": ".AX", "LN": ".L", "JP": ".T",
           "JT": ".T", "TT": ".TW", "HK": ".HK", "KS": ".KS", "KQ": ".KQ", "SJ": ".JO", "NA": ".AS", "FP": ".PA",
           "GR": ".DE", "GY": ".DE", "IM": ".MI", "SM": ".MC", "BB": ".BR", "FH": ".HE", "ID": ".IR", "SW": ".SW",
           "SE": ".SW", "SS": ".ST", "NO": ".OL", "DC": ".CO", "IN": ".NS", "IB": ".BO", "SP": ".SI", "BZ": ".SA",
           "MM": ".MX", "C1": ".SS", "C2": ".SZ", "CH": ".SS", "TB": ".BK", "MK": ".KL", "IJ": ".JK", "PM": ".PS",
           "LI": ".IL", "IT": ".TA", "PW": ".WA", "TI": ".IS", "AB": ".SR", "QD": ".QA", "CI": ".SN", "NZ": ".NZ",
           "AV": ".VI", "PL": ".LS", "GA": ".AT", "DH": ".AE", "UH": ".AD"}
ISIN_SFX = {"TW": [".TW", ".TWO"], "IN": [".NS", ".BO"], "BR": [".SA"], "TH": [".BK"], "KR": [".KS", ".KQ"],
            "ZA": [".JO"], "MX": [".MX"], "MY": [".KL"], "ID": [".JK"], "PH": [".PS"], "SA": [".SR"], "AE": [".AE", ".AD"],
            "QA": [".QA"], "KW": [".KW"], "TR": [".IS"], "PL": [".WA"], "CL": [".SN"], "GR": [".AT"], "HU": [".BD"],
            "CZ": [".PR"], "EG": [".CA"], "CO": [".CL"], "GB": [".L"], "FR": [".PA"], "DE": [".DE"], "CH": [".SW"],
            "NL": [".AS"], "SE": [".ST"], "DK": [".CO"], "ES": [".MC"], "IT": [".MI"], "FI": [".HE"], "BE": [".BR"],
            "NO": [".OL"], "AT": [".VI"], "IE": [".IR", ".L"], "PT": [".LS"], "JE": [".L"], "GG": [".L"], "IM": [".L"],
            "LU": [".AS", ".PA", ".DE"], "JP": [".T"], "AU": [".AX"], "CA": [".TO", ".V"], "SG": [".SI"], "IL": [".TA"],
            "NZ": [".NZ"], "PE": [".LM"], "HK": [".HK"], "KY": [".HK"], "BM": [".HK"], "CN": [".SS", ".SZ", ".HK"]}

SUFFIX_WORDS = re.compile(r"\b(INC|INCORPORATED|CORP|CORPORATION|CO|COMPANY|COS|LTD|LIMITED|PLC|SA|AG|NV|SE|SPA|AB|ASA|"
                          r"OYJ|HOLDINGS?|HLDGS?|GROUP|GRP|CLASS|CL|SHS|ORD|ADR|SPON|SPONSORED|THE|REIT|TRUST|LP|BHD|"
                          r"TBK|PCL|JSC|PJSC|SAB|CV|DE|NPV|REGS|GDR|PT|FOREIGN|N|V|A|B|C|H|K|R|F|P|DR|PREF|PFD)\b")


def log(msg):
    print(f"[{datetime.now():%H:%M:%S}] {msg}", flush=True)


# ── name / ticker helpers ──────────────────────────────────────────────────
def nname(s):
    s = re.sub(r"[^A-Z0-9 ]", " ", str(s or "").upper().replace("&", " AND ").replace("+", " AND "))
    return " ".join(SUFFIX_WORDS.sub(" ", s).split())


def sim(a, b):
    a, b = nname(a), nname(b)
    if not a or not b:
        return 0.0
    if a in b or b in a:
        return 1.0
    return difflib.SequenceMatcher(None, a, b).ratio()


def ntick(t):
    return re.sub(r"[^A-Z0-9]", "", str(t or "").upper())


def plain_ticker(t, source, ysym):
    """Ticker as shown on the site: the plain local code ('AEC CN' -> 'AEC', 'VWS.DC' -> 'VWS')."""
    t = (t or "").strip()
    if t:
        p = t.split()
        if len(p) >= 2 and p[-1].upper() in BBG_SFX:
            t = " ".join(p[:-1])
        m = re.match(r"^(.+)\.([A-Z]{2})$", t)
        if m and m.group(2) in BBG_SFX and source.startswith("First"):
            t = m.group(1)
        return t.replace("*", "").rstrip("/").strip()
    if ysym:
        return re.sub(r"\.[A-Z]{1,3}$", "", ysym)
    return ""


def yahoo_candidates(r, source):
    """Possible Yahoo symbols for one holding, most likely first."""
    t = (r.get("t") or "").strip()
    if not t or t.startswith("$"):
        return []

    def fmt(base, sfx):
        b = base.strip().upper()
        if sfx == ".HK" and b.isdigit():
            b = b.lstrip("0").zfill(4)
        if sfx in (".L", ".IR"):
            b = b.rstrip(".")
        if sfx == ".BK":
            b = re.sub(r"-(F|R|NVDR)$", "", b)
        if sfx in (".T", ".TW", ".TWO", ".KS", ".KQ", ".SS", ".SZ") and b.isdigit():
            b = b.zfill({".KS": 6, ".KQ": 6, ".SS": 6, ".SZ": 6}.get(sfx, 4))
        b = b.replace(" ", "-")
        if sfx == "":
            b = b.replace(".", "-").replace("/", "-")
        return b + sfx

    def variants(base, sfx):
        base = base.replace("*", "").rstrip("/").strip()
        v = [fmt(base, sfx)]
        v += [fmt(base, e) for e in {".TO": [".V"], ".SS": [".SZ"], ".KS": [".KQ"], ".TW": [".TWO"]}.get(sfx, [])]
        if sfx in (".ST", ".CO", ".HE", ".OL") and len(base) > 3 and base[-1] in "AB" and "-" not in base:
            v.append(fmt(base[:-1] + "-" + base[-1], sfx))         # Nordic B-shares: HEXAB -> HEXA-B
        return v

    p = t.split()
    if len(p) >= 2 and p[-1].upper() in BBG_SFX:                    # Bloomberg style 'AEC CN'
        return variants(" ".join(p[:-1]), BBG_SFX[p[-1].upper()])
    m = re.match(r"^(.+)\.([A-Z]{2})$", t)                            # First Trust style 'VWS.DC'
    if m and m.group(2) in BBG_SFX and source.startswith("First"):
        return variants(m.group(1), BBG_SFX[m.group(2)])
    if source.startswith("iShares"):
        sfx = EXCH_SFX.get(r.get("exch") or "")
        if r.get("exch") == "Nasdaq Omx Nordic":
            sfx = NORDIC.get(r.get("ccy"), ".ST")
        if sfx is None:
            return []
        out = [fmt(t, sfx)]
        if sfx == "" and len(ntick(t)) >= 4 and ntick(t)[-1] in "ABC":   # BRKB -> BRK-B
            out.append(ntick(t)[:-1] + "-" + ntick(t)[-1])
        return out
    out = []
    isin = (r.get("isin") or "")[:2]
    us_issuer = source.startswith(("State", "VanEck", "First", "Global"))
    if us_issuer or isin == "US" or (r.get("ccy") == "USD" and not isin):
        out.append(fmt(t, ""))
    if isin and isin != "US" and not (us_issuer and len(t) <= 5 and t.isalpha()):
        for sfx in ISIN_SFX.get(isin, []):
            if sfx == ".SS" and t.isdigit() and not t.startswith("6"):
                continue
            if sfx == ".SZ" and t.isdigit() and t.startswith("6"):
                continue
            out.append(fmt(t, sfx))
    return out or [fmt(t, "")]


# ── Yahoo ──────────────────────────────────────────────────────────────────
_YD = None


def yquote(symbols):
    """Bulk quote (150 symbols per request): market cap, currency, names."""
    global _YD
    from yfinance.data import YfData
    _YD = _YD or YfData()
    res = {}
    syms = sorted(set(symbols))
    for i in range(0, len(syms), 150):
        chunk = syms[i:i + 150]
        for attempt in range(4):
            try:
                r = _YD.get("https://query1.finance.yahoo.com/v7/finance/quote",
                            params={"symbols": ",".join(chunk),
                                    "fields": "marketCap,currency,quoteType,longName,shortName,regularMarketPrice"})
                for q in r.json().get("quoteResponse", {}).get("result", []):
                    res[q["symbol"]] = q
                break
            except Exception:
                time.sleep(5 * (attempt + 1))
        time.sleep(0.3)
    return res


def yahoo_profile(sym):
    import yfinance as yf
    for attempt in range(3):
        try:
            i = yf.Ticker(sym).info or {}
            if not i.get("sector"):
                return None                      # never cache an empty answer
            return {"sector": SECTOR_FIX.get(i["sector"], i["sector"]), "country": i.get("country"), "src": "Yahoo"}
        except Exception:
            time.sleep(3 * (attempt + 1))
    return None


def fx_to_usd(ccys, quotes_fn=yquote):
    """1 unit of currency -> USD (Yahoo 'XXX=X' = XXX per 1 USD)."""
    need = sorted({c.upper() for c in ccys if c and c.upper() != "USD"})
    q = quotes_fn([f"{c}=X" for c in need])
    rate = {"USD": 1.0}
    for c in need:
        p = (q.get(f"{c}=X") or {}).get("regularMarketPrice")
        if p:
            rate[c] = 1.0 / p
    return rate


# ── Supabase helpers ───────────────────────────────────────────────────────
def sb_on():
    return bool(_sb and _sb.enabled())


def load_cache(do_push):
    os.makedirs(WORK_DIR, exist_ok=True)
    if do_push and sb_on():
        _sb.download_file(CACHE_REMOTE, CACHE_FILE)
    try:
        c = json.load(open(CACHE_FILE, encoding="utf-8"))
    except Exception:
        c = {}
    return {k: v for k, v in c.items() if v and v.get("sector")}


def save_cache(cache, do_push):
    json.dump(cache, open(CACHE_FILE, "w", encoding="utf-8"), ensure_ascii=False)
    if do_push and sb_on():
        ok = _sb.upload_file(CACHE_FILE, CACHE_REMOTE, content_type="application/json")
        log(f"stock cache ({len(cache)} stocks) -> Supabase {'OK' if ok else 'FAILED'}")


def previous_file(sym, do_push):
    """The currently published details file (for the 'collapsed?' and 'older?' checks)."""
    path = os.path.join(WORK_DIR, f"prev_{sym}.json")
    try:
        if do_push and sb_on():
            if not _sb.download_file(f"details/{sym}.json", path, bucket=_sb.SITE_BUCKET):
                return {}
        else:
            path = os.path.join(DETAILS_DIR, f"{sym}.json")
        return json.load(open(path, encoding="utf-8")) or {}
    except Exception:
        return {}


# ── step 1: download every fund ────────────────────────────────────────────
def collect(meta, symbols):
    got, failed = {}, {}
    for sym in symbols:
        m = meta.get(sym, {})
        order = S.plan(sym, m.get("name"))
        if not order:
            got[sym] = {"commodity": True}
            continue
        errs = []
        for src in order:
            try:
                rows, as_of, label = S.SOURCES[src](sym)
                total = sum(r["w"] or 0 for r in rows)
                if not rows or not (90 <= total <= 110) and src != "yahoo":
                    raise RuntimeError(f"failed check: {len(rows)} rows, weights add up to {total:.1f}%")
                got[sym] = {"rows": rows, "as_of": as_of, "source": label, "first_choice": src == order[0],
                            "errors_before": errs}
                log(f"{sym:5s} {label:38s} as of {as_of}  {len(rows):5d} rows"
                    + (f"   (after: {'; '.join(errs)})" if errs else ""))
                break
            except Exception as e:
                errs.append(f"{src}: {str(e)[:150]}")
        else:
            failed[sym] = "; ".join(errs)
            log(f"{sym:5s} FAILED — {failed[sym]}")
        time.sleep(0.5)
    return got, failed


def is_stock(r):
    if r["type"] != "Equity":
        return False
    t, n = (r["t"] or ""), (r["n"] or "").upper()
    if t.startswith("$") or re.search(r"\b(JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)\d{2}\b", n):
        return False          # cash lines / index futures
    return True


# ── step 2: classify every stock ───────────────────────────────────────────
def classify(funds, cache):
    """Adds to every stock row: _y (validated Yahoo symbol), _ish (official iShares row)."""
    look = []
    for sym in LOOKUP_ONLY:
        try:
            rows, as_of, _ = S.ishares(sym)
            look.append(rows)
            log(f"lookup fund {sym}: {len(rows)} rows, as of {as_of}")
        except Exception as e:
            log(f"lookup fund {sym} unavailable ({e}) — coverage check will catch any gap")

    master = defaultdict(list)
    for d in funds.values():
        if d.get("source", "").startswith("iShares"):
            look.append(d["rows"])
    for rows in look:
        for r in rows:
            if is_stock(r) and r["sector"] and r["sector"] != "Cash and/or Derivatives":
                master[ntick(r["t"])].append(r)
    usd_master, name_idx = {}, {}
    for k, lst in master.items():
        for e in lst:
            if e["ccy"] == "USD" and EXCH_SFX.get(e["exch"] or "x") == "":
                usd_master.setdefault(k, e)
            nn = nname(e["n"])
            if len(nn) >= 4:
                name_idx.setdefault(nn, e)
    name_keys = list(name_idx)

    def us_like(r, src):
        isin = (r.get("isin") or "")[:2]
        if isin:
            return isin == "US"
        if r.get("ccy"):
            return r["ccy"] == "USD"
        return bool(re.fullmatch(r"[A-Z][A-Z.\-/]{0,6}", r["t"] or "")) and \
            src.startswith(("State", "VanEck", "First", "Global", "Vanguard"))

    def by_name(n):
        nn = nname(n)
        if len(nn) < 4:
            return None
        if nn in name_idx:
            return name_idx[nn]
        m = difflib.get_close_matches(nn, name_keys, n=1, cutoff=0.9)
        return name_idx[m[0]] if m else None

    id2t = {}
    for d in funds.values():
        for r in d.get("rows", []):
            if r["t"] and not str(r["t"]).startswith("$"):
                for k in ("cusip", "isin"):
                    if r.get(k):
                        id2t.setdefault(r[k], (r["t"], d["source"]))

    items = []
    for sym, d in funds.items():
        for r in d.get("rows", []):
            if not is_stock(r):
                continue
            src = d["source"]
            if not r["t"]:
                for k in ("cusip", "isin"):
                    if r.get(k) in id2t:
                        r["t"], src = id2t[r[k]]
                        break
            if src.startswith("iShares") and r["sector"]:
                r["_ish"] = r                                   # its own official classification
            elif r["t"]:
                best = max(master.get(ntick(r["t"]), []), key=lambda e: sim(e["n"], r["n"]), default=None)
                if best and sim(best["n"], r["n"]) >= 0.6:
                    r["_ish"] = best                            # same ticker + same company name
                elif us_like(r, src) and ntick(r["t"]) in usd_master:
                    r["_ish"] = usd_master[ntick(r["t"])]       # same US ticker = same company (renamed firms)
            r["_src"] = src
            items.append((sym, r))

    for _, r in items:
        r["_cands"] = yahoo_candidates(r["_ish"], "iShares") if r.get("_ish") else yahoo_candidates(r, r["_src"])
    quotes = yquote({c for _, r in items for c in r["_cands"]})
    log(f"{len(items)} stock rows; Yahoo returned {len(quotes)} quotes")

    def validate(r, ref_name):
        for c in r["_cands"]:
            q = quotes.get(c)
            if q and q.get("quoteType") in ("EQUITY", "ETF", "MUTUALFUND") and \
                    max(sim(q.get("longName"), ref_name), sim(q.get("shortName"), ref_name),
                        sim(q.get("longName"), (r.get("_ish") or {}).get("n"))) >= 0.5:
                return c
        return None

    for _, r in items:
        r["_y"] = validate(r, r["n"])

    # still unresolved: match the company NAME to the official list (very close names only)
    extra = []
    for _, r in items:
        if not r.get("_ish") and not r["_y"]:
            e = by_name(r["n"])
            if e:
                r["_ish"] = e
                r["_cands"] = yahoo_candidates(e, "iShares")
                extra += r["_cands"]
    quotes.update(yquote(set(extra) - set(quotes)))
    for _, r in items:
        if r.get("_ish") and not r["_y"]:
            r["_y"] = validate(r, r["_ish"]["n"])

    # last resort for holdings >= 0.1 %: Yahoo name search, strict
    import yfinance as yf
    left = defaultdict(list)
    for _, r in items:
        if not r.get("_ish") and not r["_y"] and (r["w"] or 0) >= 0.1 and r["n"]:
            left[r["n"]].append(r)
    for n, rs in left.items():
        try:
            hits = yf.Search(re.sub(r"[^A-Za-z0-9 &.'-]", " ", n), max_results=6).quotes
        except Exception:
            hits = []
        best = max((h for h in hits if h.get("quoteType") == "EQUITY"),
                   key=lambda h: sim(h.get("longname") or h.get("shortname"), n), default=None)
        if best and sim(best.get("longname") or best.get("shortname"), n) >= 0.85:
            for r in rs:
                r["_y"] = best["symbol"]
            quotes.update(yquote([best["symbol"]]))
        time.sleep(0.5)

    # Yahoo sector/country only for stocks with no official classification (cached forever)
    need = sorted({r["_y"] for _, r in items if r["_y"] and not r.get("_ish") and r["_y"] not in cache})
    log(f"Yahoo profile lookups needed: {len(need)} (cached: {len(cache)})")
    with ThreadPoolExecutor(4) as ex:
        for s_, prof in zip(need, ex.map(yahoo_profile, need)):
            if prof:
                cache[s_] = prof
    for s_ in [x for x in need if x not in cache]:                # slow retry for rate-limited ones
        prof = yahoo_profile(s_)
        if prof:
            cache[s_] = prof
        time.sleep(0.7)
    return items, quotes


# ── step 3: one fund's record ──────────────────────────────────────────────
def build_record(sym, d, rows, quotes, cache, rate, meta):
    def usd_cap(q):
        cap, ccy = q.get("marketCap"), (q.get("currency") or "USD")
        if not cap:
            return None
        ccy = {"GBp": "GBP", "GBX": "GBP", "ILA": "ILS", "ZAc": "ZAR"}.get(ccy, ccy).upper()
        return cap * rate[ccy] if ccy in rate else None

    stock_w = sum(r["w"] for r in rows)
    full = []
    sector, country, mcap = defaultdict(float), defaultdict(float), defaultdict(float)
    unc_s = unc_c = unc_m = 0.0
    for r in rows:
        ish = r.get("_ish")
        q = quotes.get(r["_y"]) if r["_y"] else None
        prof = cache.get(r["_y"]) if r["_y"] else None
        sec_ = SECTOR_FIX.get(ish["sector"], ish["sector"]) if ish else (prof or {}).get("sector")
        cty = COUNTRY_FIX.get(ish["country"], ish["country"]) if ish else (prof or {}).get("country")
        cty = COUNTRY_FIX.get(cty, cty)
        if sec_ not in GICS and q and (q.get("quoteType") in ("ETF", "MUTUALFUND") or
                                       re.search("PHYSICAL.*(TRUST| TR$| TR )",
                                                 ((r["n"] or "") + " " + (q.get("longName") or "")).upper())):
            sec_ = "Fund / Trust"
        cap = usd_cap(q) if q else None
        band = next(b for lim, b in CAP_BANDS if cap >= lim) if cap else None
        if sec_ in GICS or sec_ == "Fund / Trust":
            sector[sec_] += r["w"]
        else:
            sec_ = None
            unc_s += r["w"]
        if cty:
            country[cty] += r["w"]
        else:
            unc_c += r["w"]
        if band:
            mcap[band] += r["w"]
        else:
            unc_m += r["w"]
        # Display name: Yahoo's (proper capitalisation) unless Yahoo returned a damaged
        # accented letter (it does, e.g. 'Ørsted'), then the fund company's own name.
        yname = (q or {}).get("longName") or (q or {}).get("shortName")
        full.append({"sym": plain_ticker(r["t"], r["_src"], r["_y"]),
                     "name": yname if yname and "�" not in yname else (r["n"] or yname or ""),
                     "wt": round(r["w"], 4), "sector": sec_, "country": cty, "band": band,
                     "mcap_usd": round(cap) if cap else None})
    full.sort(key=lambda h: -h["wt"])
    other = max(0.0, 100.0 - stock_w)

    def split(dct, unc):
        out = {k: round(v, 2) for k, v in sorted(dct.items(), key=lambda kv: -kv[1]) if round(v, 2) != 0}
        if unc >= 0.005:
            out["Unclassified"] = round(unc, 2)
        if other >= 0.005:
            out["Cash & Other"] = round(other, 2)
        return out

    m = meta.get(sym, {})
    cov = lambda unc: round(100 - unc / stock_w * 100, 2) if stock_w else 0.0
    rec = {"symbol": sym, "name": m.get("name") or sym, "asset_class": m.get("asset_class"),
           "category": m.get("category"), "has_breakdown": True, "as_of": d["as_of"],
           "fetched_on": date.today().isoformat(), "source": d["source"],
           "holdings_count": len(rows),
           "top10_pct": round(sum(h["wt"] for h in full[:10]), 2),
           "holdings": [{"sym": h["sym"], "name": h["name"], "wt": round(h["wt"], 2)} for h in full[:15]],
           "sector": split(sector, unc_s), "country": split(country, unc_c),
           "market_cap": {k: round(mcap.get(k, 0), 2) for k in ("Large", "Mid", "Small", "Micro")}
                         | ({"Unclassified": round(unc_m, 2)} if unc_m >= 0.005 else {}),
           "coverage": {"stocks_pct": round(stock_w, 2), "sector_pct": cov(unc_s), "country_pct": cov(unc_c),
                        "mcap_pct": cov(unc_m)}}
    return rec, full


def commodity_record(sym, meta):
    m = meta.get(sym, {})
    return {"symbol": sym, "name": m.get("name") or sym, "asset_class": m.get("asset_class"),
            "category": m.get("category"), "has_breakdown": False, "as_of": date.today().isoformat(),
            "fetched_on": date.today().isoformat(), "source": "Fund structure (no stock holdings)",
            "holdings_count": 1, "top10_pct": 100.0,
            "holdings": [{"sym": "", "name": S.COMMODITY_HOLDING[sym], "wt": 100.0}],
            "sector": {}, "country": {}, "market_cap": {}}


# ── step 4: checks ─────────────────────────────────────────────────────────
def problems(sym, d, rec, prev):
    """Reasons NOT to publish (hard) and things to flag (soft)."""
    hard, soft = [], []
    prev_count = prev.get("holdings_count")
    # Never replace published holdings with OLDER ones (e.g. a company file fails
    # and the SEC fallback is months behind). Legacy etfdb files carry no "source"
    # field and are being retired, so they may be replaced.
    if prev.get("source") and prev.get("as_of") and d["as_of"] < prev["as_of"]:
        hard.append(f"new holdings date {d['as_of']} is older than the published {prev['as_of']} "
                    f"({prev['source']}) — kept the newer published file")
    src_key = next((k for k in MAX_AGE_DAYS if d["source"].startswith(k)), "SEC")
    try:
        age = (date.today() - date.fromisoformat(d["as_of"])).days
    except Exception:
        age = 9999
    if age > MAX_AGE_DAYS[src_key]:
        hard.append(f"holdings date {d['as_of']} is {age} days old (limit {MAX_AGE_DAYS[src_key]} for {src_key})")
    if rec["coverage"]["sector_pct"] < MIN_SECTOR_COVERAGE and not d["source"].startswith("Yahoo"):
        hard.append(f"only {rec['coverage']['sector_pct']}% of stock weight classified (minimum {MIN_SECTOR_COVERAGE}%)")
    if prev_count and rec["holdings_count"] < prev_count * 0.5 and not d["source"].startswith("Yahoo"):
        hard.append(f"holdings count fell from {prev_count} to {rec['holdings_count']}")
    if not d["first_choice"]:
        soft.append(f"fund company file unavailable ({'; '.join(d['errors_before'])}) — used {d['source']} as of {d['as_of']}")
    return hard, soft


# ── step 5: save + publish ─────────────────────────────────────────────────
def save_and_upload(rec, full, do_push):
    sym = rec["symbol"]
    os.makedirs(DETAILS_DIR, exist_ok=True)
    os.makedirs(FULL_DIR, exist_ok=True)
    p1 = os.path.join(DETAILS_DIR, f"{sym}.json")
    json.dump(rec, open(p1, "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
    p2 = os.path.join(FULL_DIR, f"{sym}.json")
    fields = ["sym", "name", "wt", "sector", "country", "band"]
    json.dump({"symbol": sym, "as_of": rec["as_of"], "source": rec["source"], "fields": fields,
               "rows": [[h.get(f) for f in fields] for h in (full or rec["holdings"])]},
              open(p2, "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
    if not (do_push and sb_on()):
        return True
    ok1 = _sb.upload_file(p1, f"details/{sym}.json", bucket=_sb.SITE_BUCKET,
                          content_type="application/json", cache_control="max-age=300")
    ok2 = _sb.upload_file(p2, f"holdings/{sym}.json", bucket=_sb.SITE_BUCKET,
                          content_type="application/json", cache_control="max-age=300")
    return ok1 and ok2


def store_history(rec, full, profile, do_push):
    """Append this snapshot (EVERY holding) to the fund's Parquet history."""
    if _cs is None:
        return "skipped (composition_store unavailable)"
    sym = rec["symbol"]
    if do_push:
        _cs.pull(sym)
    seen = defaultdict(int)
    hist_holdings = []
    for h in full or rec["holdings"]:
        key = h["sym"] or h["name"]
        seen[key] += 1
        hist_holdings.append({"sym": key if seen[key] == 1 else f"{key} ({seen[key]})", "name": h["name"], "wt": h["wt"]})
    rows = _cs.composition_rows({**rec, "holdings": hist_holdings, "history_source": rec["source"]})
    if profile:
        rows += _cs.fundamental_rows(rec["as_of"], profile)
    n, snaps = _cs.upsert_month(sym, rows)
    pushed = _cs.push(sym) if do_push else False
    return f"{n} rows, {len(snaps)} snapshot(s)" + (" -> Supabase OK" if pushed else (" -> Supabase FAILED" if do_push else ""))


def publish_derived(records, do_push):
    """{SYMBOL: {holdings, top10_pct, as_of}} for the daily dashboard (merged, never wiped)."""
    existing = {}
    if do_push and sb_on() and _sb.download_file(DERIVED_REMOTE, DERIVED_FILE):
        pass
    try:
        existing = json.load(open(DERIVED_FILE, encoding="utf-8")) or {}
    except Exception:
        existing = {}
    for rec in records:
        existing[rec["symbol"]] = {"holdings": rec.get("holdings_count"), "top10_pct": rec.get("top10_pct"),
                                   "as_of": rec.get("as_of")}
    json.dump(existing, open(DERIVED_FILE, "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    if do_push and sb_on():
        ok = _sb.upload_file(DERIVED_FILE, DERIVED_REMOTE)
        log(f"etf_derived.json ({len(existing)} funds) -> Supabase {'OK' if ok else 'FAILED'}")


def load_profiles(do_push):
    if do_push and sb_on():
        _sb.download_file("nav/yf_profiles.json", YF_FILE)
    try:
        return json.load(open(YF_FILE, encoding="utf-8"))
    except Exception:
        return {}


# ── driver ─────────────────────────────────────────────────────────────────
def main():
    args = sys.argv[1:]
    do_push = os.environ.get("PUSH") == "1"
    meta_list = json.load(open(ETF_LIST, encoding="utf-8"))
    meta = {e["symbol"]: e for e in meta_list}
    symbols = [e["symbol"] for e in meta_list] if "--all" in args else [a.upper() for a in args if not a.startswith("--")]
    if not symbols:
        print("usage: python holdings_engine.py --all | SYM [SYM ...]")
        return 2
    print("=" * 70)
    print(f"  Holdings Engine — official fund-company files   {datetime.now():%Y-%m-%d %H:%M}")
    print(f"  Funds: {len(symbols)}   Upload: {'YES' if do_push and sb_on() else 'no (local only)'}")
    print("=" * 70)

    cache = load_cache(do_push)
    profiles = load_profiles(do_push)
    funds, failed = collect(meta, symbols)
    stock_funds = {s: d for s, d in funds.items() if not d.get("commodity")}
    items, quotes = classify(stock_funds, cache)
    save_cache(cache, do_push)
    rate = fx_to_usd({(quotes.get(r["_y"]) or {}).get("currency") for _, r in items if r["_y"]} | {"GBP", "ILS", "ZAR"})

    by_fund = defaultdict(list)
    for sym, r in items:
        by_fund[sym].append(r)

    published, blocked, flagged = [], {}, {}
    for sym in symbols:
        if sym in failed:
            continue
        d = funds[sym]
        try:
            if d.get("commodity"):
                rec, full = commodity_record(sym, meta), None
                hard, soft = [], []
            else:
                rec, full = build_record(sym, d, by_fund[sym], quotes, cache, rate, meta)
                hard, soft = problems(sym, d, rec, previous_file(sym, do_push))
            if hard:
                blocked[sym] = "; ".join(hard)
                log(f"{sym:5s} NOT PUBLISHED — {blocked[sym]} (previous file stays live)")
                continue
            if soft:
                flagged[sym] = "; ".join(soft)
            ok = save_and_upload(rec, full, do_push)
            if not ok:
                blocked[sym] = "upload failed"
                continue
            hist = store_history(rec, full, profiles.get(sym), do_push)
            published.append(rec)
            c = rec.get("coverage", {})
            log(f"{sym:5s} OK  as of {rec['as_of']}  {rec['holdings_count']:5d} holdings  "
                f"sector {c.get('sector_pct', '-')}%  country {c.get('country_pct', '-')}%  "
                f"mcap {c.get('mcap_pct', '-')}%  | history {hist}")
        except Exception as e:
            blocked[sym] = f"error: {e}"
            log(f"{sym:5s} ERROR {e} (previous file stays live)")

    publish_derived(published, do_push)

    print("\n" + "=" * 70)
    print(f"  Published: {len(published)}   Download failed: {len(failed)}   Not published (checks): {len(blocked)}"
          f"   Flagged: {len(flagged)}")
    for s, why in failed.items():
        print(f"  FAILED    {s}: {why}")
    for s, why in blocked.items():
        print(f"  BLOCKED   {s}: {why}")
    for s, why in flagged.items():
        print(f"  ATTENTION {s}: {why}")
    print("=" * 70)
    # Any failure, block or fallback makes the GitHub run show FAILED, so it is noticed.
    return 1 if (failed or blocked or flagged) else 0


if __name__ == "__main__":
    sys.exit(main())
