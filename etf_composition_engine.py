"""
ETF Detail Page — Composition & Holdings Engine
=================================================
Two data sources, each used for what it's actually good at:

  1. etfrc.com/{TICKER} — Sector Breakdown, Country Exposure, Market Cap mix
     (incl. Developed/Emerging split) and the Herfindahl-Hirschman
     concentration index. This is REAL full-portfolio data (not a top-10
     approximation) — etfrc renders it as a Chart.js bar (sectors) and plain
     HTML tables (country / market cap), all present in the page's raw HTML,
     so it's fetched with a normal GET + parsed, no JS execution needed.
     Their "Complete holdings list" is explicitly paywalled (an alert(), not
     a real link) — this script does not attempt to access it.

  2. yfinance funds_data — Top 10 Holdings (ticker, name, weight) plus each
     holding's own sector via a follow-up .info call.

Existing fundamentals (AUM, expense ratio, P/E, beta, yield, holdings count,
inception) are already handled by update_fundamentals.py / yf_profiles.json —
NOT refetched here.

This script is intentionally NOT wired into the automatic daily/monthly cron.
It only runs when triggered manually (Ctrl+Shift+A on the ETF detail page ->
server.py's /api/refresh-etf-details), so it consumes external calls only
when you choose.

Scope: SYMBOLS below (QQQ, SMH). The etfrc.com URL and yfinance calls are
both ticker-templated, so extending to more ETFs later is just adding to
this list — nothing else needs to change.

Output: etf_detail_data.json (consumed only by etf.js's Portfolio Composition
and Top 10 Holdings sections)

Run: python etf_composition_engine.py
"""

import json, os, re, time
from datetime import datetime
import requests
from bs4 import BeautifulSoup
import yfinance as yf

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT = os.path.join(BASE_DIR, "etf_detail_data.json")

# ── Scope: extend this list to bring more ETFs onto this page ──
SYMBOLS = ["QQQ", "SMH"]

ETFRC_URL = "https://www.etfrc.com/{sym}"
ETFRC_HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")
}


def load_existing():
    if os.path.exists(OUTPUT):
        try:
            with open(OUTPUT, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


# Fields fetched by this script (as opposed to hand-written / preserved
# fields like "description"). If a fetch attempt comes back empty for one
# of these, keep whatever was already saved for THAT field specifically —
# don't let one source's rate-limit blank out another source's good data.
FETCHED_LIST_FIELDS = ["sector_holdings", "country_exposure", "market_cap", "top10_holdings"]
FETCHED_SCALAR_FIELDS = ["developed_markets_pct", "emerging_markets_pct",
                          "concentration_hhi", "weighted_avg_market_cap"]


def merge_with_existing(sym, new_result, existing_data):
    old = existing_data.get(sym, {})
    merged = dict(new_result)

    for field in FETCHED_LIST_FIELDS:
        if not merged.get(field) and old.get(field):
            print(f"    {sym}.{field}: new fetch was empty — keeping previously saved value.")
            merged[field] = old[field]

    for field in FETCHED_SCALAR_FIELDS:
        if merged.get(field) is None and old.get(field) is not None:
            merged[field] = old[field]

    if old.get("description"):
        merged["description"] = old["description"]

    return merged


def fetch_with_retry(fn, tries=3, delay=3):
    last_err = RuntimeError("fetch_with_retry called with tries <= 0")
    for i in range(tries):
        try:
            return fn()
        except Exception as e:
            last_err = e
            print(f"    retry {i+1}/{tries} after error: {e}")
            time.sleep(delay * (i + 1))
    raise last_err


def parse_number(text):
    if text is None:
        return None
    cleaned = text.replace("%", "").replace(",", "").replace("$", "").strip()
    try:
        return float(cleaned)
    except ValueError:
        return None


def fetch_etfrc(sym):
    """Sector Breakdown, Country Exposure, Market Cap mix (incl. Developed/
    Emerging) and HHI concentration index — real, full-portfolio data."""
    def _get():
        r = requests.get(ETFRC_URL.format(sym=sym), headers=ETFRC_HEADERS, timeout=15)
        r.raise_for_status()
        return r.text

    html = fetch_with_retry(_get, tries=3, delay=4)
    soup = BeautifulSoup(html, "html.parser")

    result = {
        "sector_holdings": [],
        "country_exposure": [],
        "market_cap": [],
        "developed_markets_pct": None,
        "emerging_markets_pct": None,
        "concentration_hhi": None,
        "weighted_avg_market_cap": None,
        "holdings_count_etfrc": None,
    }

    # ── Sector Breakdown — embedded as JS arrays (Chart.js canvas, not a table) ──
    weights_match = re.search(r"var\s+weights\s*=\s*\[([^\]]*)\]", html)
    labels_match = re.search(r"labels:\s*\[([^\]]*)\]", html)
    if weights_match and labels_match:
        weights = [parse_number(w) for w in weights_match.group(1).split(",") if w.strip()]
        labels = [l.strip().strip('"').strip("'") for l in labels_match.group(1).split(",") if l.strip()]
        for label, pct in zip(labels, weights):
            if pct:
                result["sector_holdings"].append({"sector": label, "pct": pct})
        result["sector_holdings"].sort(key=lambda x: -x["pct"])

    # ── Panel tables (Country Exposure / Constituent Breakdown) ──
    for panel in soup.select(".panel"):
        heading_el = panel.select_one(".panel-heading")
        if not heading_el:
            continue
        heading = heading_el.get_text(strip=True)
        rows = panel.select("table tbody tr")

        if heading.startswith("Country Exposure"):
            for row in rows:
                cells = row.find_all("td")
                if len(cells) >= 2:
                    country = cells[-2].get_text(strip=True)
                    pct = parse_number(cells[-1].get_text(strip=True))
                    if country and pct is not None:
                        result["country_exposure"].append({"country": country.title(), "pct": pct})

        elif heading.startswith("Constituent Breakdown"):
            for row in rows:
                cells = row.find_all("td")
                if len(cells) != 2:
                    continue
                label = cells[0].get_text(strip=True)
                value_text = cells[1].get_text(strip=True)
                if label.startswith("Number of holdings"):
                    result["holdings_count_etfrc"] = int(parse_number(value_text) or 0)
                elif label.startswith("Herfindahl"):
                    result["concentration_hhi"] = parse_number(value_text)
                elif label.startswith("Wgt avg mkt cap"):
                    result["weighted_avg_market_cap"] = value_text
                elif label.startswith("Large cap"):
                    result["market_cap"].append({"cap": "Large Cap (>$10B)", "pct": parse_number(value_text)})
                elif label.startswith("Mid cap"):
                    result["market_cap"].append({"cap": "Mid Cap ($2B–$10B)", "pct": parse_number(value_text)})
                elif label.startswith("Small cap"):
                    result["market_cap"].append({"cap": "Small Cap (<$2B)", "pct": parse_number(value_text)})
                elif label.startswith("Developed mkts"):
                    result["developed_markets_pct"] = parse_number(value_text)
                elif label.startswith("Emerging mkts"):
                    result["emerging_markets_pct"] = parse_number(value_text)

    return result


def fetch_top10_yfinance(sym):
    """Top 10 Holdings (ticker, name, weight, sector) via yfinance funds_data."""
    fd = yf.Ticker(sym).funds_data
    th = fetch_with_retry(lambda: fd.top_holdings, tries=3, delay=3)
    if th is None or th.empty:
        return []

    df = th.reset_index()
    cols = list(df.columns)
    ticker_col = cols[0]
    name_col = next((c for c in cols if "name" in c.lower()), None)
    pct_col = next((c for c in cols if "percent" in c.lower() or "weight" in c.lower()), None)

    holdings = []
    for _, row in df.iterrows():
        ticker = str(row[ticker_col])
        name = str(row[name_col]) if name_col else ticker
        pct_val = float(row[pct_col]) if pct_col is not None and row[pct_col] is not None else 0.0
        weight = round(pct_val * 100, 2) if pct_val < 1 else round(pct_val, 2)
        holdings.append({"ticker": ticker, "name": name, "weight": weight})

    top10_holdings = []
    for h in holdings[:10]:
        sector = "—"
        try:
            info = fetch_with_retry(lambda t=h["ticker"]: yf.Ticker(t).info, tries=2, delay=2)
            sector = info.get("sector") or info.get("industry") or "—"
        except Exception as e:
            print(f"    Warning: .info failed for holding {h['ticker']}: {e}")
        top10_holdings.append({
            "rank": len(top10_holdings) + 1,
            "ticker": h["ticker"], "name": h["name"], "weight": h["weight"], "sector": sector,
        })
        time.sleep(0.6)

    return top10_holdings


def fetch_symbol(sym):
    print(f"\n[{datetime.now():%H:%M:%S}] {sym} — fetching etfrc.com (sector/country/market cap)...")
    etfrc_data = {}
    try:
        etfrc_data = fetch_etfrc(sym)
    except Exception as e:
        print(f"  Warning: etfrc.com fetch failed for {sym}: {e}")

    print(f"[{datetime.now():%H:%M:%S}] {sym} — fetching yfinance (top 10 holdings)...")
    top10_holdings = []
    try:
        top10_holdings = fetch_top10_yfinance(sym)
    except Exception as e:
        print(f"  Warning: yfinance top_holdings failed for {sym}: {e}")

    return {
        "sector_holdings": etfrc_data.get("sector_holdings", []),
        "country_exposure": etfrc_data.get("country_exposure", []),
        "market_cap": etfrc_data.get("market_cap", []),
        "developed_markets_pct": etfrc_data.get("developed_markets_pct"),
        "emerging_markets_pct": etfrc_data.get("emerging_markets_pct"),
        "concentration_hhi": etfrc_data.get("concentration_hhi"),
        "weighted_avg_market_cap": etfrc_data.get("weighted_avg_market_cap"),
        "top10_holdings": top10_holdings,
        "data_source": "Sector/Country/Market Cap: etfrc.com (full portfolio). Top 10 Holdings: Yahoo Finance (yfinance).",
        "last_updated": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }


def main():
    print("=" * 60)
    print("  ETF Detail Page — Composition & Holdings Engine (manual trigger)")
    print(f"  Run date : {datetime.now():%Y-%m-%d %H:%M:%S}")
    print(f"  Symbols  : {', '.join(SYMBOLS)}")
    print("=" * 60)

    data = load_existing()
    for sym in SYMBOLS:
        try:
            result = fetch_symbol(sym)
            merged = merge_with_existing(sym, result, data)

            if not merged["sector_holdings"] and not merged["top10_holdings"]:
                print(f"  {sym}: nothing fetched and nothing previously saved — skipping write.")
                continue

            data[sym] = merged
            with open(OUTPUT, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            print(f"  {sym}: saved ({len(merged['sector_holdings'])} sectors, "
                  f"{len(merged['country_exposure'])} countries, "
                  f"{len(merged['top10_holdings'])} holdings)")
        except Exception as e:
            print(f"  ERROR fetching {sym}: {e} — keeping existing saved data untouched.")
        time.sleep(1)

    print(f"\n[{datetime.now():%H:%M:%S}] Done. Wrote {OUTPUT}")


if __name__ == "__main__":
    main()
