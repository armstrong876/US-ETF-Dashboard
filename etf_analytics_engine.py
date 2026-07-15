"""
ETF Detail Page — Returns & Risk Analytics Engine
===================================================
Computes, for the individual ETF profile page (etf.html) only:
  1. Monthly Returns calendar (year x month, adjusted/total-return NAV)
  2. Real Nasdaq-100 trailing returns (replaces the hardcoded fallback in etf.js)
  3. Risk Analysis suite (Std Dev, Sharpe, Sortino, Beta, Alpha, Max Drawdown +
     Recovery, Upside/Downside Capture, Composite Score) vs a matched US benchmark

Data source: history.json's existing daily adjusted-close series — the SAME
series data_engine.py already produces and the price chart already reads.
No new price fetching. The only external call here is the US 3-Month T-Bill
yield (^IRX), needed as the risk-free rate input.

Scope: SYMBOLS below (QQQ, SMH for now). Add tickers to extend — nothing else
to change. Does NOT read or write dashboard.json / history.json / any file the
main dashboard or screener consumes.

Output: etf_analytics.json (consumed only by etf.js)
Run:    python etf_analytics_engine.py
"""

import json, os, math, time
from datetime import datetime
import numpy as np
import pandas as pd
import yfinance as yf

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
HISTORY  = os.path.join(BASE_DIR, "history.json")
OUTPUT   = os.path.join(BASE_DIR, "etf_analytics.json")

# ── Scope: extend this list (+ BENCH_MAP entry) to bring more ETFs onto this page ──
SYMBOLS = ["QQQ", "SMH"]

BENCH_MAP = {
    "QQQ": "^NDX",   # QQQ tracks the Nasdaq-100 exactly
    "SMH": "SOXX",   # semiconductor sector ETF -> iShares Semiconductor ETF as matched sector proxy
}
BENCH_LABEL = {
    "^NDX": "Nasdaq-100 Index",
    "SOXX": "iShares Semiconductor ETF (sector proxy)",
}

PERIODS = {            # identical trading-day lookback table used by data_engine.py
    "1W":  5, "15D": 15, "1M":  21, "2M":  42, "3M":  63,
    "6M":  126, "9M":  189, "12M": 252, "2Y":  504, "3Y":  756,
    "5Y":  1260, "7Y":  1764, "10Y": 2520,
}

MONTH_ABBR = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"]


def load_history():
    with open(HISTORY) as f:
        h = json.load(f)
    dates = pd.to_datetime(h["dates"])
    df = pd.DataFrame(h["series"], index=dates)
    return df


def pct_return(series, n_days, index):
    """Trailing % return: same lookback-window / CAGR-annualization logic as
    data_engine.py's pct_return(), applied to history.json's adjusted series."""
    s = series.dropna()
    if len(s) < 5:
        return None
    nav_pos = len(index) - 1
    target_pos = nav_pos - n_days
    if target_pos < 0:
        return None
    current = series.iloc[nav_pos]
    past = series.iloc[target_pos]
    if pd.isna(current) or pd.isna(past) or past == 0:
        return None
    if n_days >= 252:
        return round(((current / past) ** (252.0 / n_days) - 1) * 100, 2)
    return round((current / past - 1) * 100, 2)


def monthly_pct_series(series):
    """Month-end (last available obs per calendar month) % change. The
    current/incomplete month naturally uses the latest available NAV as its
    'end' value — i.e. a month-to-date return until the month closes."""
    s = series.dropna()
    monthly = s.resample("ME").last()
    return monthly.pct_change() * 100


def monthly_returns_calendar(series):
    rets = monthly_pct_series(series)
    calendar = {}
    for dt, val in rets.items():
        if pd.isna(val):
            continue
        calendar.setdefault(dt.year, {})[MONTH_ABBR[dt.month - 1]] = round(float(val), 2)
    totals = {}
    for y, months in calendar.items():
        prod = 1.0
        for v in months.values():
            prod *= (1 + v / 100)
        totals[y] = round((prod - 1) * 100, 2)
    return calendar, totals


def fetch_risk_free_rate():
    """US 3-Month T-Bill annualized yield (^IRX). Returns annual Rf as a decimal."""
    for attempt in range(3):
        try:
            h = yf.Ticker("^IRX").history(period="5d")
            if not h.empty:
                level = float(h["Close"].dropna().iloc[-1])
                return round(level / 100, 5)
        except Exception as e:
            print(f"  [{datetime.now():%H:%M:%S}] ^IRX fetch attempt {attempt+1} failed: {e}")
            time.sleep(2 * (attempt + 1))
    # Fallback: reuse whatever was cached from the previous run
    if os.path.exists(OUTPUT):
        try:
            prev = json.load(open(OUTPUT))
            if prev.get("risk_free_rate_annual") is not None:
                print("  Using previously cached risk-free rate (fetch failed this run).")
                return prev["risk_free_rate_annual"]
        except Exception:
            pass
    print("  WARNING: no risk-free rate available — Risk Analysis will be skipped.")
    return None


def compute_risk_metrics(etf_monthly, bench_monthly, etf_daily, rf_annual):
    """36-month risk analytics per spec: Std Dev, Sharpe, Sortino, Beta, Alpha,
    Max Drawdown + Recovery (daily), Upside/Downside Capture, Composite Score."""
    common = sorted(etf_monthly.dropna().index.intersection(bench_monthly.dropna().index))[-36:]
    if len(common) < 12 or rf_annual is None:
        return None

    e = np.array([etf_monthly[d] for d in common]) / 100.0
    b = np.array([bench_monthly[d] for d in common]) / 100.0
    n = len(e)

    rf_monthly = (1 + rf_annual) ** (1 / 12) - 1

    sigma_annual = float(np.std(e, ddof=1) * math.sqrt(12))
    cagr_e = float(np.prod(1 + e) ** (12.0 / n) - 1)
    cagr_b = float(np.prod(1 + b) ** (12.0 / n) - 1)

    sharpe = (cagr_e - rf_annual) / sigma_annual if sigma_annual else None

    downside = np.minimum(e - rf_monthly, 0)
    downside_dev = float(math.sqrt(np.mean(downside ** 2)) * math.sqrt(12))
    sortino = (cagr_e - rf_annual) / downside_dev if downside_dev else None

    var_b = np.var(b, ddof=1)
    beta = float(np.cov(e, b, ddof=1)[0, 1] / var_b) if var_b else None
    alpha_annual = (cagr_e - (rf_annual + beta * (cagr_b - rf_annual))) if beta is not None else None

    # Max Drawdown + Recovery — daily adjusted close, market-agnostic
    d = etf_daily.dropna()
    running_peak = d.cummax()
    drawdown = d / running_peak - 1
    trough_idx = drawdown.idxmin()
    max_dd = float(drawdown.min())
    peak_val_at_trough = running_peak.loc[trough_idx]
    after = d.loc[trough_idx:]
    recovered = after[after >= peak_val_at_trough]
    if len(recovered) > 1:
        recovery_date = recovered.index[1]
        recovery_days = (recovery_date - trough_idx).days
        recovery_status = "Recovered"
    else:
        recovery_date = None
        recovery_days = (d.index[-1] - trough_idx).days
        recovery_status = "Ongoing (not yet recovered)"

    def capture(mask):
        n_ = int(mask.sum())
        if n_ == 0:
            return None
        etf_g = np.prod(1 + e[mask]) ** (12.0 / n_) - 1
        bench_g = np.prod(1 + b[mask]) ** (12.0 / n_) - 1
        if bench_g == 0:
            return None
        return float(etf_g / bench_g * 100)

    upside_capture = capture(b > 0)
    downside_capture = capture(b < 0)

    # Composite score: raw weighted blend (0-100). NOT peer-percentile ranked —
    # that requires the full 80-ETF universe running through this same engine.
    def clamp01(x):
        return max(0.0, min(1.0, x))

    sharpe_score  = clamp01((sharpe + 1) / 3) * 100 if sharpe is not None else 50
    sortino_score = clamp01((sortino + 1) / 3) * 100 if sortino is not None else 50
    alpha_score   = clamp01((alpha_annual + 0.10) / 0.30) * 100 if alpha_annual is not None else 50
    maxdd_score   = clamp01(1 + max_dd / 0.60) * 100
    spread = (upside_capture if upside_capture is not None else 100) - \
             (downside_capture if downside_capture is not None else 100)
    capture_score = clamp01((spread + 50) / 100) * 100

    composite = (sharpe_score * 0.30 + sortino_score * 0.20 + alpha_score * 0.20
                 + maxdd_score * 0.15 + capture_score * 0.15)

    return {
        "window_months": n,
        "risk_free_rate_annual_pct": round(rf_annual * 100, 2),
        "std_dev_annual_pct": round(sigma_annual * 100, 2),
        "cagr_3y_pct": round(cagr_e * 100, 2),
        "benchmark_cagr_3y_pct": round(cagr_b * 100, 2),
        "sharpe_ratio": round(sharpe, 3) if sharpe is not None else None,
        "sortino_ratio": round(sortino, 3) if sortino is not None else None,
        "beta": round(beta, 3) if beta is not None else None,
        "alpha_annual_pct": round(alpha_annual * 100, 2) if alpha_annual is not None else None,
        "max_drawdown_pct": round(max_dd * 100, 2),
        "max_drawdown_trough_date": str(trough_idx.date()),
        "recovery_days": recovery_days,
        "recovery_date": str(recovery_date.date()) if recovery_date is not None else None,
        "recovery_status": recovery_status,
        "upside_capture_pct": round(upside_capture, 1) if upside_capture is not None else None,
        "downside_capture_pct": round(downside_capture, 1) if downside_capture is not None else None,
        "composite_score": round(composite, 1),
        "composite_note": ("Raw weighted blend (Sharpe 30% / Sortino 20% / Alpha 20% / "
                            "Max Drawdown 15% / Capture spread 15%). Peer-percentile ranking "
                            "will activate once the full 80-ETF universe runs through this engine."),
    }


def main():
    print("=" * 60)
    print("  ETF Detail Page — Returns & Risk Analytics Engine")
    print(f"  Run date : {datetime.now():%Y-%m-%d %H:%M:%S}")
    print(f"  Symbols  : {', '.join(SYMBOLS)}")
    print("=" * 60)

    df = load_history()
    idx = df.index
    nav_date = str(idx[-1].date())

    rf_annual = fetch_risk_free_rate()

    ndx_series = df["^NDX"] if "^NDX" in df.columns else None
    nasdaq100_trailing_returns = (
        {label: pct_return(ndx_series, n, idx) for label, n in PERIODS.items()}
        if ndx_series is not None else {}
    )

    out = {
        "as_of_date": nav_date,
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "risk_free_rate_annual": rf_annual,
        "nasdaq100_trailing_returns": nasdaq100_trailing_returns,
        "etfs": {},
    }

    bench_monthly_cache = {}
    for sym in SYMBOLS:
        if sym not in df.columns:
            print(f"  Skipping {sym} — not present in history.json")
            continue

        etf_series = df[sym]
        calendar, totals = monthly_returns_calendar(etf_series)

        bench_sym = BENCH_MAP.get(sym)
        risk = None
        if bench_sym and bench_sym in df.columns:
            if bench_sym not in bench_monthly_cache:
                bench_monthly_cache[bench_sym] = monthly_pct_series(df[bench_sym])
            etf_monthly = monthly_pct_series(etf_series)
            risk = compute_risk_metrics(etf_monthly, bench_monthly_cache[bench_sym], etf_series, rf_annual)
        else:
            print(f"  Warning: benchmark {bench_sym} not found in history.json for {sym} — skipping Risk Analysis")

        out["etfs"][sym] = {
            "benchmark_symbol": bench_sym,
            "benchmark_label": BENCH_LABEL.get(bench_sym, bench_sym),
            "monthly_returns_calendar": calendar,
            "monthly_returns_annual_total": totals,
            "risk_analysis": risk,
        }
        print(f"  {sym}: monthly calendar ({len(calendar)} years), "
              f"risk analysis {'OK' if risk else 'unavailable'}")

    with open(OUTPUT, "w") as f:
        json.dump(out, f, indent=2, default=str)
    print(f"\n[{datetime.now():%H:%M:%S}] Wrote {OUTPUT}")


if __name__ == "__main__":
    main()
