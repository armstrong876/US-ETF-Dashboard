"""
ONE-OFF TEST — can GitHub's servers download each official holdings source?

Read-only: downloads one sample fund per source and prints what it got.
It does NOT write any file, does NOT touch Supabase, uses NO secrets.
Run from GitHub: Actions tab -> "TEST holdings sources (read-only)" -> Run workflow.
Delete this file and its workflow after the test.
"""
import io
import re
import sys
import time

import pandas as pd
import requests

BROWSER = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                         "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"}
SEC_UA = {"User-Agent": "Armstrong Capital ETF Dashboard armstrong@example.com"}
results = []


def get(url, headers=BROWSER):
    return requests.get(url, headers=headers, timeout=(15, 60))


def check(source, fund, fn):
    t = time.time()
    try:
        rows, as_of, wsum = fn()
        ok = rows > 0 and 95 <= wsum <= 105
        results.append((source, fund, "PASS" if ok else "FAIL", f"{rows} holdings, weights {wsum:.1f}%, as of {as_of}"))
    except Exception as e:
        results.append((source, fund, "FAIL", f"{type(e).__name__}: {str(e)[:150]}"))
    print(f"{results[-1][2]:4s} {source:12s} {fund:5s} {results[-1][3]}  ({time.time() - t:.0f}s)", flush=True)


def num(s):
    return pd.to_numeric(s.astype(str).str.replace(",", "").str.rstrip("%"), errors="coerce")


def ishares():
    page = get("https://www.ishares.com/us/products/239726/ishares-core-sp-500-etf").text
    link = re.search(r'(/us/products/\d+/[^"\'\s]+/latest-holdings\.csv)', page).group(1)
    lines = get("https://www.ishares.com" + link).text.splitlines()
    h = next(i for i, l in enumerate(lines) if l.startswith("Ticker,"))
    df = pd.read_csv(io.StringIO("\n".join(lines[h:])), dtype=str, on_bad_lines="skip")
    w = num(df["Market Weight"]).dropna()
    return len(w), lines[1], w.sum()


def ssga():
    b = get("https://www.ssga.com/us/en/intermediary/library-content/products/fund-data/etfs/us/holdings-daily-us-en-spy.xlsx").content
    raw = pd.read_excel(io.BytesIO(b), header=None)
    h = raw.index[raw.iloc[:, 0].astype(str).str.strip().eq("Name")][0]
    w = num(pd.read_excel(io.BytesIO(b), header=h)["Weight"]).dropna()
    return len(w), raw.iloc[2, 1], w.sum()


def vaneck():
    b = get("https://www.vaneck.com/us/en/etf/equity/smh/holdings/download/xlsx/").content
    raw = pd.read_excel(io.BytesIO(b), header=None)
    w = num(pd.read_excel(io.BytesIO(b), header=2)["% of Net Assets"]).dropna()
    return len(w), raw.iloc[0, 1], w.sum()


def globalx():
    page = get("https://www.globalxetfs.com/funds/ura/").text
    m = re.search(r'URA-holdings-([A-Za-z]{3})-(\d+)-(\d{4})\.csv', page)
    d = pd.to_datetime(f"{m.group(1)} {m.group(2)} {m.group(3)}").strftime("%Y%m%d")
    lines = get(f"https://assets.globalxetfs.com/funds/holdings/ura_full-holdings_{d}.csv").text.splitlines()
    w = num(pd.read_csv(io.StringIO("\n".join(lines[2:])), dtype=str)["% of Net Assets"]).dropna()
    return len(w), lines[1], w.sum()


def firsttrust():
    page = get("https://www.ftportfolios.com/Retail/Etf/EtfHoldings.aspx?Ticker=CIBR").text
    t = max(pd.read_html(io.StringIO(page)), key=len)
    t.columns = t.iloc[0]
    w = num(t.iloc[1:]["Weighting"]).dropna()
    m = re.search(r'[Hh]oldings? as of[^0-9]*([0-9/]+)', page)
    return len(w), m.group(1) if m else "?", w.sum()


def vanguard():
    j = get("https://investor.vanguard.com/vmf/api/VOO/portfolio-holding/stock").json()
    return j.get("size", 0), j.get("asOfDate", "?")[:10], 100.0  # count only; weights checked in step 3


def invesco():
    r = get("https://www.invesco.com/us/financial-products/etfs/holdings/main/holdings/0?audienceType=Investor&action=download&ticker=QQQ")
    if r.status_code != 200:
        raise RuntimeError(f"HTTP {r.status_code}")
    df = pd.read_csv(io.StringIO(r.text))
    w = num(df[[c for c in df.columns if "Weight" in c][0]]).dropna()
    return len(w), "?", w.sum()


def sec():
    import xml.etree.ElementTree as ET
    atom = get("https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK=S000004310&type=NPORT-P"
               "&dateb=&owner=include&count=10&output=atom", SEC_UA).text
    idx = get(re.findall(r'<filing-href>([^<]+)</filing-href>', atom)[0], SEC_UA).text
    xml_url = "https://www.sec.gov" + [u for u in re.findall(r'href="([^"]+primary_doc\.xml)"', idx) if "xsl" not in u][0]
    root = ET.fromstring(get(xml_url, SEC_UA).content)
    ns = {"n": "http://www.sec.gov/edgar/nport"}
    w = [float(s.findtext("n:pctVal", default="0", namespaces=ns)) for s in root.findall(".//n:invstOrSec", ns)]
    return len(w), root.findtext(".//n:repPdDate", namespaces=ns), sum(w)


def yahoo_stock():
    import yfinance as yf
    got = 0
    for s in ["AAPL", "UBER", "ASML", "AEC.V", "KAP.IL"]:
        if yf.Ticker(s).info.get("sector"):
            got += 1
    return got, "per-stock sector lookup", got / 5 * 100


for source, fund, fn in [("iShares", "IVV", ishares), ("StateStreet", "SPY", ssga), ("VanEck", "SMH", vaneck),
                         ("GlobalX", "URA", globalx), ("FirstTrust", "CIBR", firsttrust), ("Vanguard", "VOO", vanguard),
                         ("Invesco", "QQQ", invesco), ("SEC", "IVV", sec), ("Yahoo", "5stk", yahoo_stock)]:
    check(source, fund, fn)

print("\n=========== SUMMARY (GitHub servers) ===========")
for r in results:
    print(f"{r[2]:4s}  {r[0]:12s} {r[1]:5s} {r[3]}")
print(f"\n{sum(r[2] == 'PASS' for r in results)} of {len(results)} sources reachable from GitHub.")
sys.exit(0)  # a test: always finish so the full summary is visible
