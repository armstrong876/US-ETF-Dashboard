import os
import sys
import json
import time
from datetime import datetime, timedelta
import pandas as pd
import yfinance as yf

# ── CONFIGURATION ────────────────────────────────────────────────────────────
TICKERS = [
    "QQQ", "XLP", "GLD", "XLY", "VOO", "SMH", "URA", "AIQ", "CIBR", "REMX",
    "BOTZ", "UFO", "SKYY", "PPA", "ESPO", "OZEM", "PJP", "SLV", "FNGS", "BBP",
    "SPY", "XLE", "XLF", "IWM", "EWZ", "FXI", "GDX", "IEFA", "IAU", "XLI",
    "VWO", "EWJ", "INDA", "IVV", "SOXX", "EWT", "ACWI", "IVW", "VGK", "MCHI",
    "IWD", "SIL", "SPMD", "IWF", "SPSM", "EWG", "EWU", "IHI", "EZU", "SDVY",
    "IBB", "DBC", "FTXO", "CQQQ", "SPTM", "IXC", "VFH", "XLV", "XLK", "XLU",
    "XLC", "XLB", "XRT", "ITA", "KBE", "KRE", "VNQ", "IYR", "SCHD", "DVY",
    "VYM", "TLT", "IEF", "SHY", "LQD", "HYG", "TIP", "EMB", "VIG", "NOBL"
]

MARKET_INDICES = {
    "^GSPC": "S&P 500",
    "^NDX": "Nasdaq 100",
    "^DJI": "Dow Jones",
    "^RUT": "Russell 2000",
    "^VIX": "Volatility Index"
}

MOMENTUM_WEIGHTS = {"1M": 0.20, "3M": 0.30, "6M": 0.30, "12M": 0.20}

PERIODS = {
    "1W": 5, "1M": 21, "3M": 63, "6M": 126, "12M": 252
}

def get_returns(series):
    res = {}
    if series.empty: return res
    last_price = series.iloc[-1]
    for label, days in PERIODS.items():
        if len(series) > days:
            prev_price = series.iloc[-(days+1)]
            res[label] = (last_price / prev_price) - 1
        else:
            res[label] = None
    return res

def run():
    print("Starting US ETF Spreadsheet Data Fetch...")
    
    # 1. Fetch Market Indices
    print("Fetching Market Indices...")
    idx_data = yf.download(list(MARKET_INDICES.keys()), period="1mo", interval="1d", progress=False)['Close']
    indices_res = []
    for sym, name in MARKET_INDICES.items():
        if sym in idx_data.columns:
            s = idx_data[sym].dropna()
            if not s.empty:
                change = (s.iloc[-1] / s.iloc[0]) - 1 if len(s) > 1 else 0
                indices_res.append({'Index': name, 'Price': round(s.iloc[-1], 2), '1M Change': change})

    # 2. Fetch ETF Data
    print(f"Fetching {len(TICKERS)} ETFs (this takes a moment)...")
    all_data = yf.download(TICKERS + ["SPY"], period="2y", interval="1d", progress=False)['Close']
    
    results = []
    for ticker in TICKERS:
        if ticker not in all_data.columns: continue
        series = all_data[ticker].dropna()
        if series.empty: continue
        
        rets = get_returns(series)
        
        # Calculate Momentum Score
        score = 0
        valid = True
        for p, w in MOMENTUM_WEIGHTS.items():
            val = rets.get(p)
            if val is not None: score += val * w
            else: valid = False
            
        results.append({
            'Ticker': ticker,
            'Price': round(series.iloc[-1], 2),
            '1W': rets.get('1W'),
            '1M': rets.get('1M'),
            '3M': rets.get('3M'),
            '6M': rets.get('6M'),
            '12M': rets.get('12M'),
            'Momentum Score': score if valid else 0
        })

    df = pd.DataFrame(results).sort_values('Momentum Score', ascending=False)
    df['Rank'] = range(1, len(df) + 1)
    
    # 3. Create Excel Report
    print("Creating Formatted Excel Dashboard...")
    output_file = 'ETF_Momentum_Spreadsheet.xlsx'
    writer = pd.ExcelWriter(output_file, engine='xlsxwriter')
    workbook = writer.book

    # --- FORMATS ---
    title_fmt = workbook.add_format({'bold': True, 'font_size': 18, 'font_color': '#6366f1'})
    header_fmt = workbook.add_format({'bold': True, 'bg_color': '#1a1f2e', 'font_color': 'white', 'border': 1, 'align': 'center'})
    pct_fmt = workbook.add_format({'num_format': '0.0%', 'align': 'center'})
    num_fmt = workbook.add_format({'num_format': '#,##0.00', 'align': 'center'})
    score_fmt = workbook.add_format({'num_format': '0.0', 'bold': True, 'align': 'center'})

    # --- SHEET: DASHBOARD ---
    ws_dash = workbook.add_worksheet('Momentum Dashboard')
    ws_dash.write(0, 0, "US ETF MOMENTUM DASHBOARD", title_fmt)
    ws_dash.write(1, 0, f"Updated: {datetime.now().strftime('%Y-%m-%d %H:%M')}", workbook.add_format({'italic': True}))

    # Market Indices Table
    ws_dash.write(3, 0, "MARKET OVERVIEW", workbook.add_format({'bold': True, 'underline': True}))
    ws_dash.write_row(4, 0, ['Index', 'Price', '1M Change'], header_fmt)
    for i, idx in enumerate(indices_res):
        ws_dash.write(5+i, 0, idx['Index'])
        ws_dash.write(5+i, 1, idx['Price'], num_fmt)
        ws_dash.write(5+i, 2, idx['1M Change'], pct_fmt)

    # Top 10 Table
    ws_dash.write(3, 4, "TOP 10 MOMENTUM ETFS", workbook.add_format({'bold': True, 'font_color': '#22c55e'}))
    top10 = df.head(10)[['Rank', 'Ticker', 'Price', 'Momentum Score']]
    ws_dash.write_row(4, 4, top10.columns, header_fmt)
    for i, row in enumerate(top10.values):
        ws_dash.write_row(5+i, 4, row)

    # Bottom 10 Table
    ws_dash.write(17, 4, "BOTTOM 10 MOMENTUM ETFS", workbook.add_format({'bold': True, 'font_color': '#ef4444'}))
    bottom10 = df.tail(10)[['Rank', 'Ticker', 'Price', 'Momentum Score']]
    ws_dash.write_row(18, 4, bottom10.columns, header_fmt)
    for i, row in enumerate(bottom10.values):
        ws_dash.write_row(19+i, 4, row)

    ws_dash.set_column('A:F', 15)

    # --- SHEET: VISUAL HEATMAP ---
    df.to_excel(writer, sheet_name='Heatmap & Data', index=False)
    ws_heat = writer.sheets['Heatmap & Data']
    
    # Conditional Formatting for Heatmap
    # Columns B:F are Returns (Price, 1W, 1M, 3M, 6M, 12M)
    ws_heat.conditional_format('C2:G500', {
        'type': '3_color_scale',
        'min_color': '#ef4444', # Red
        'mid_color': '#ffffff', # White
        'max_color': '#22c55e'  # Green
    })
    
    # Format columns
    ws_heat.set_column('C:G', 12, pct_fmt)
    ws_heat.set_column('H:H', 15, score_fmt)
    ws_heat.set_column('A:B', 12)

    writer.close()
    print(f"Success! Report generated: {output_file}")


if __name__ == "__main__":
    run()
