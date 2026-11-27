"""
Holdings Sources — download each universe fund's latest FULL holdings list
=========================================================================
Official files only, straight from the fund company (or the US regulator):

    iShares (BlackRock)  daily CSV      found via the iShares fund list (no fixed links)
    State Street (SPDR)  daily Excel    holdings-daily-us-en-{sym}.xlsx
    VanEck               daily Excel    fund page (from VanEck's fund list) + downloads/holdings/
    Global X             daily CSV      dated file name; the fund PAGE blocks GitHub, the file does not
    First Trust          daily page     EtfHoldings.aspx?Ticker={sym}
    Vanguard             month-end      JSON API (weights rebuilt from market value — see vanguard())
    SEC Form N-PORT      fallback       latest official filing (usually 2-5 months old, clearly dated)
    Yahoo Finance        FNGS only      it is an ETN (a note), so no fund file or SEC filing exists

Every function returns (rows, as_of, source_label). Row format:
    {"t": ticker, "n": name, "w": weight %, "type": Equity | Cash/Other | ...,
     "sector", "country", "ccy", "exch", "isin", "cusip", "sedol", "figi"}
Anything that cannot be read raises — the engine then tries the next source and,
failing all, keeps the previously published file and reports the fund as FAILED.
No proxies, no browser disguises: if a company blocks automated downloads
(Invesco does), we use the SEC filing instead.
"""
import io
import re
import time
import xml.etree.ElementTree as ET

import pandas as pd
import requests

BROWSER = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                         "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"}
# SEC asks automated users to identify themselves in the User-Agent.
SEC_UA = {"User-Agent": "Armstrong Capital ETF Dashboard armstrong@example.com"}

# Funds with no stock holdings: what they physically / contractually hold.
COMMODITY_HOLDING = {
    "GLD": "Physical gold bullion", "IAU": "Physical gold bullion", "SLV": "Physical silver bullion",
    "PPLT": "Physical platinum bullion", "DBC": "Commodity futures (DBIQ diversified commodity index)",
    "BWET": "Tanker freight futures (Breakwave tanker index)",
}
YAHOO_ONLY = {"FNGS"}          # ETN: no holdings file, no SEC filing
FAMILY = {"iShares": "ishares", "State": "ssga", "SPDR": "ssga", "VanEck": "vaneck", "Vaneck": "vaneck",
          "Global": "globalx", "First": "firsttrust", "Vanguard": "vanguard"}


def get(url, headers=BROWSER, tries=3):
    last = None
    for i in range(tries):
        try:
            r = requests.get(url, headers=headers, timeout=(15, 90))
            if r.status_code == 200:
                return r
            last = f"HTTP {r.status_code}"
            if r.status_code in (403, 404, 406):
                break
        except Exception as e:
            last = type(e).__name__
        time.sleep(3 * (i + 1))
    raise RuntimeError(last)


def num(x):
    try:
        v = float(str(x).replace(",", "").replace("%", "").replace("$", "").strip())
    except ValueError:
        return None
    return v if v == v and abs(v) != float("inf") else None      # reject NaN / inf


def clean(v):
    s = str(v).strip() if v is not None else ""
    return None if s in ("", "-", "nan", "NaN", "None", "--") else s


def row(t=None, n=None, w=None, typ="Equity", sector=None, country=None, ccy=None, exch=None,
        isin=None, cusip=None, sedol=None, figi=None):
    return {"t": clean(t), "n": clean(n), "w": w, "type": typ, "sector": clean(sector), "country": clean(country),
            "ccy": clean(ccy), "exch": clean(exch), "isin": clean(isin), "cusip": clean(cusip),
            "sedol": clean(sedol), "figi": clean(figi)}


def iso(text, pattern):
    m = re.search(pattern, text)
    if not m:
        raise RuntimeError("holdings date not found in file")
    return pd.to_datetime(m.group(1)).date().isoformat()


# ── iShares ────────────────────────────────────────────────────────────────
_ISH = None


def _ishares_pages():
    global _ISH
    if _ISH is None:
        j = get("https://www.ishares.com/us/product-screener/product-screener-v3.1.jsn?dcrPath=/templatedata/"
                "config/product-screener-v3/data/en/us-ishares/ishares-product-screener-backend-config"
                "&siteEntryPassthrough=true").json()
        _ISH = {v.get("localExchangeTicker"): v.get("productPageUrl") for v in j.values() if isinstance(v, dict)}
    return _ISH


def ishares(sym):
    page = _ishares_pages().get(sym)
    if not page:
        raise RuntimeError("not in the iShares fund list")
    try:
        text = get(f"https://www.ishares.com{page}/latest-holdings.csv").text
        if "Ticker," not in text:
            raise RuntimeError("no csv")
    except Exception:                       # read the link from the fund page instead
        html = get(f"https://www.ishares.com{page}").text
        link = re.search(r'(/us/products/\d+/[^"\'\s]+/latest-holdings\.csv)', html)
        if not link:
            raise RuntimeError("holdings link not found on the fund page")
        text = get("https://www.ishares.com" + link.group(1)).text
    lines = text.splitlines()
    as_of = iso(lines[1], r'"([A-Za-z]{3} \d{1,2}, \d{4})"')
    h = next(i for i, l in enumerate(lines) if l.startswith("Ticker,"))
    df = pd.read_csv(io.StringIO("\n".join(lines[h:])), dtype=str, on_bad_lines="skip")
    wcol = "Market Weight" if "Market Weight" in df.columns else "Weight (%)"
    rows = []
    for _, x in df.iterrows():
        w = num(x.get(wcol))
        if w is None:
            continue
        rows.append(row(x.get("Ticker"), x.get("Name"), w, clean(x.get("Asset Class")) or "Equity",
                        x.get("Sector"), x.get("Location"), x.get("Market Currency") or x.get("Currency"),
                        x.get("Exchange")))
    return rows, as_of, "iShares (BlackRock) holdings file"


# ── State Street SPDR ──────────────────────────────────────────────────────
def ssga(sym):
    b = get(f"https://www.ssga.com/us/en/intermediary/library-content/products/fund-data/etfs/us/"
            f"holdings-daily-us-en-{sym.lower()}.xlsx").content
    raw = pd.read_excel(io.BytesIO(b), header=None)
    h = raw.index[raw.iloc[:, 0].astype(str).str.strip().eq("Name")][0]
    as_of = iso(" ".join(str(v) for v in raw.iloc[:h].values.ravel()), r'As of (\d{1,2}-[A-Za-z]{3}-\d{4})')
    df = pd.read_excel(io.BytesIO(b), header=h, dtype=str)
    rows = []
    for _, x in df.iterrows():
        w = num(x.get("Weight"))
        if w is None:
            continue
        t = clean(x.get("Ticker"))
        rows.append(row(t, x.get("Name"), w, "Equity" if t else "Cash/Other", x.get("Sector"), None,
                        x.get("Local Currency"), None, None, x.get("Identifier"), x.get("SEDOL")))
    return rows, as_of, "State Street (SPDR) holdings file"


# ── VanEck ─────────────────────────────────────────────────────────────────
_VE = None


def vaneck(sym):
    global _VE
    if _VE is None:
        _VE = get("https://www.vaneck.com/us/en/etf-mutual-fund-finder/").text
    m = re.search(rf'(/us/en/investments/[a-z0-9-]+-{sym.lower()}/)', _VE)
    if not m:
        raise RuntimeError("not in the VanEck fund list")
    b = get(f"https://www.vaneck.com{m.group(1)}downloads/holdings/").content
    if b[:2] != b"PK":
        raise RuntimeError("download is not an Excel file")
    raw = pd.read_excel(io.BytesIO(b), header=None)
    as_of = iso(" ".join(str(v) for v in raw.head(2).values.ravel()), r'(\d{1,2}/\d{1,2}/\d{4})')
    h = raw.index[raw.iloc[:, 1].astype(str).str.strip().eq("Ticker")][0]
    df = pd.read_excel(io.BytesIO(b), header=h, dtype=str)
    rows = []
    for _, x in df.iterrows():
        w = num(x.get("% of Net Assets"))
        if w is None:
            continue
        ac = clean(x.get("Asset Class")) or ""
        rows.append(row(x.get("Ticker"), x.get("Holding Name"), w, "Equity" if ac == "Stock" else (ac or "Other"),
                        figi=x.get("Identifier (FIGI)")))
    return rows, as_of, "VanEck holdings file"


# ── Global X (dated file; try the last 12 days, newest first) ──────────────
def globalx(sym):
    for d in pd.date_range(end=pd.Timestamp.today().normalize(), periods=12)[::-1]:
        try:
            r = get(f"https://assets.globalxetfs.com/funds/holdings/{sym.lower()}_full-holdings_{d:%Y%m%d}.csv", tries=1)
        except Exception:
            continue
        if "% of Net Assets" not in r.text:
            continue
        lines = r.text.splitlines()
        as_of = iso(lines[1], r'(\d{1,2}/\d{1,2}/\d{4})')
        df = pd.read_csv(io.StringIO("\n".join(lines[2:])), dtype=str)
        rows = []
        for _, x in df.iterrows():
            w = num(x.get("% of Net Assets"))
            if w is None:
                continue
            t = clean(x.get("Ticker"))
            rows.append(row(t, x.get("Name"), w, "Equity" if t and clean(x.get("SEDOL")) else "Cash/Other",
                            sedol=x.get("SEDOL")))
        return rows, as_of, "Global X holdings file"
    raise RuntimeError("no Global X file in the last 12 days")


# ── First Trust ────────────────────────────────────────────────────────────
def firsttrust(sym):
    html = get(f"https://www.ftportfolios.com/Retail/Etf/EtfHoldings.aspx?Ticker={sym}").text
    t = max(pd.read_html(io.StringIO(html)), key=len)
    t.columns = [str(c) for c in t.iloc[0]]
    t = t.iloc[1:]
    text = re.sub(r'<[^>]+>', ' ', html)
    m = re.search(r'[Hh]oldings[^0-9]{0,80}?(\d{1,2}/\d{1,2}/\d{4})', text) or re.search(r'(\d{1,2}/\d{1,2}/\d{4})', text)
    if not m:
        raise RuntimeError("holdings date not found on page")
    as_of = pd.to_datetime(m.group(1)).date().isoformat()
    rows = []
    for _, x in t.iterrows():
        w = num(x.get("Weighting"))
        if w is None:
            continue
        tk = clean(x.get("Identifier"))
        rows.append(row(tk, x.get("Security Name"), w, "Cash/Other" if (tk or "").startswith("$") else "Equity",
                        x.get("Classification"), cusip=x.get("CUSIP")))
    return rows, as_of, "First Trust holdings page"


# ── Vanguard (month-end) ───────────────────────────────────────────────────
def vanguard(sym):
    j = get(f"https://investor.vanguard.com/vmf/api/{sym}/portfolio-holding/stock?start=1&count=20000").json()
    ents = j["fund"]["entity"]
    if int(j.get("size") or len(ents)) != len(ents):
        raise RuntimeError(f"Vanguard returned {len(ents)} of {j.get('size')} holdings")
    as_of = (j.get("asOfDate") or "")[:10]
    # Vanguard rounds % to 2 decimals, so thousands of small holdings read 0.00%.
    # Weights are rebuilt from market value and scaled to Vanguard's own % on the
    # holdings >= 0.5% (so the stock total keeps the fund's real cash gap).
    mv = sum(float(e.get("marketValue") or 0) for e in ents)
    big = [e for e in ents if (num(e.get("percentWeight")) or 0) >= 0.5]
    k = (sum(num(e["percentWeight"]) for e in big) / (sum(float(e["marketValue"]) for e in big) / mv * 100)) if big else 1.0
    rows = [row(e.get("ticker"), e.get("longName"), float(e.get("marketValue") or 0) / mv * 100 * k, "Equity",
                isin=e.get("isin"), cusip=e.get("cusip"), sedol=e.get("sedol")) for e in ents]
    return rows, as_of, "Vanguard holdings (month-end)"


# ── SEC Form N-PORT (official filing; fallback) ────────────────────────────
_SECMAP = None


def sec(sym):
    global _SECMAP
    if _SECMAP is None:
        m = get("https://www.sec.gov/files/company_tickers_mf.json", SEC_UA).json()
        f = m["fields"]
        _SECMAP = {d[f.index("symbol")]: d[f.index("seriesId")] for d in m["data"]}
    series = _SECMAP.get(sym)
    if not series:
        raise RuntimeError("not in the SEC fund list")
    atom = get(f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={series}&type=NPORT-P"
               f"&dateb=&owner=include&count=10&output=atom", SEC_UA).text
    links = re.findall(r'<filing-href>([^<]+)</filing-href>', atom)
    if not links:
        raise RuntimeError("no N-PORT filing found")
    idx = get(links[0], SEC_UA).text
    xml_url = "https://www.sec.gov" + [u for u in re.findall(r'href="([^"]+primary_doc\.xml)"', idx) if "xsl" not in u][0]
    root = ET.fromstring(get(xml_url, SEC_UA).content)
    ns = {"n": "http://www.sec.gov/edgar/nport"}
    as_of = root.findtext(".//n:repPdDate", namespaces=ns)
    rows = []
    for s in root.findall(".//n:invstOrSec", ns):
        isin = s.find(".//n:isin", ns)
        tick = s.find(".//n:ticker", ns)
        ac = s.findtext("n:assetCat", default="", namespaces=ns)
        rows.append(row(tick.get("value") if tick is not None else None, s.findtext("n:name", namespaces=ns),
                        num(s.findtext("n:pctVal", default="0", namespaces=ns)),
                        "Equity" if ac in ("EC", "EP") else (ac or "Other"),
                        None, s.findtext("n:invCountry", namespaces=ns), s.findtext("n:curCd", namespaces=ns), None,
                        isin.get("value") if isin is not None else None, s.findtext("n:cusip", namespaces=ns)))
    # N-PORT also lists securities-lending cash collateral, so totals can pass 100%.
    # Keep the stocks; everything else becomes one "Cash & other" line = 100 - stocks.
    eq = [r for r in rows if r["type"] == "Equity"]
    rest = round(100 - sum(r["w"] or 0 for r in eq), 4)
    if rest > 0:
        eq.append(row(None, "Cash & other", rest, "Cash/Other"))
    return eq, as_of, "SEC Form N-PORT filing"


# ── Yahoo top 10 (FNGS only) ───────────────────────────────────────────────
def yahoo_top(sym):
    import yfinance as yf
    th = yf.Ticker(sym).funds_data.top_holdings
    if th is None or th.empty:
        raise RuntimeError("Yahoo has no holdings for this fund")
    rows = [row(idx, r.get("Name"), float(r.get("Holding Percent")) * 100, "Equity", ccy="USD")
            for idx, r in th.iterrows()]
    from datetime import date
    return rows, date.today().isoformat(), "Yahoo Finance top holdings (fund date not published)"


SOURCES = {"ishares": ishares, "ssga": ssga, "vaneck": vaneck, "globalx": globalx,
           "firsttrust": firsttrust, "vanguard": vanguard, "sec": sec, "yahoo": yahoo_top}


def plan(symbol, fund_name):
    """Order of sources to try for one fund. [] = commodity fund (no stock holdings)."""
    if symbol in COMMODITY_HOLDING:
        return []
    if symbol in YAHOO_ONLY:
        return ["yahoo"]
    fam = FAMILY.get((fund_name or "").split()[0] if fund_name else "")
    return [fam, "sec"] if fam else ["sec"]
