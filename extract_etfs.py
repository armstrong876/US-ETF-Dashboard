import openpyxl
import json
import shutil
import tempfile
import os

excel_path = r'C:\Users\Armstrong Admin\OneDrive - ARMSTRONG CAPITAL AND FINANCIAL SERVICES PRIVATE LIMITED\Projects\US Whitelist\ETF Database.xlsx'
temp_dir = tempfile.gettempdir()
temp_excel = os.path.join(temp_dir, 'temp_etf_db.xlsx')

shutil.copy2(excel_path, temp_excel)

wb = openpyxl.load_workbook(temp_excel)
ws = wb['etfdb_screener']

rows = list(ws.iter_rows(values_only=True))
# Row 0 = date label row, Row 1 = actual headers, Row 2+ = data
headers = list(rows[1])
print('Headers:', headers)

def parse_aum(val):
    if not val:
        return 0
    try:
        s = str(val).replace('$','').replace(',','').strip()
        return float(s)
    except:
        return 0

etfs = []
for row in rows[2:]:
    sym = row[0]
    if not sym or not isinstance(sym, str):
        continue
    inverse  = row[6]
    leveraged = row[7]
    if inverse or leveraged:
        continue
    aum = parse_aum(row[3])
    price_raw = str(row[5]).replace('$','').replace(',','') if row[5] else '0'
    try:
        price = float(price_raw)
    except:
        price = 0

    def safe_float(val):
        try:
            return float(str(val).replace('%','').replace(',',''))
        except:
            return None

    def safe_int(val):
        try:
            return int(str(val).replace(',',''))
        except:
            return None

    etfs.append({
        'symbol':     sym.strip(),
        'name':       str(row[1]) if row[1] else '',
        'asset_class': str(row[2]) if row[2] else '',
        'aum':        aum,
        'category':   str(row[10]) if row[10] else '',
        'inception':  str(row[11])[:10] if row[11] else '',
        'er':         float(row[12]) if row[12] else 0,
        'pe':         safe_float(row[19]),
        'beta':       safe_float(row[20]),
        'holdings':   safe_int(row[22]),
        'top10_pct':  safe_float(row[23]) * 100 if safe_float(row[23]) is not None else None,
        'price':      price,
    })

TARGET_TICKERS = [
    "QQQ", "XLP", "GLD", "XLY", "VOO", "SMH", "URA", "AIQ", "CIBR", "REMX", 
    "BOTZ", "UFO", "SKYY", "PPA", "ESPO", "OZEM", "PJP", "SLV", "FNGS", "BBP", 
    "SPY", "XLE", "XLF", "IWM", "EWZ", "FXI", "GDX", "IEFA", "IAU", "XLI", 
    "VWO", "EWJ", "INDA", "IVV", "SOXX", "EWT", "ACWI", "IVW", "VGK", "MCHI", 
    "IWD", "SIL", "SPMD", "IWF", "SPSM", "EWG", "EWU", "IHI", "EZU", "SDVY", 
    "IBB", "DBC", "FTXO", "CQQQ", "SPTM", "IXC", "VFH", "PPLT", "NLR", "IWY", 
    "IWO", "XMMO", "IWV", "FLBR", "XSMO", "XMHQ", "IEO", "BWET", "IVOO", "SMHX", 
    "FAN", "AQWA", "PXJ", "DRIV", "IXG", "FPX", "IBBQ", "QMOM", "IBOT", "SMOG"
]

# Create a dictionary for quick lookup from the extracted data
etf_dict = {e['symbol']: e for e in etfs}

# Build the final sorted list based exactly on the TARGET_TICKERS array
etfs_sorted = []
for t in TARGET_TICKERS:
    if t in etf_dict:
        etfs_sorted.append(etf_dict[t])
    else:
        print(f"WARNING: Ticker {t} not found in database!")

print(f'\nTotal non-inverse/non-leveraged ETFs in DB: {len(etfs)}')
print(f'\nSelected {len(etfs_sorted)} ETFs from the target list:')
for i, e in enumerate(etfs_sorted, 1):
    print(f"{i:3}. {e['symbol']:8}  AUM: {e['aum']:>20,.0f}  {e['name'][:50]}")

tickers = [e['symbol'] for e in etfs_sorted]
print('\nTicker list:')
print(tickers)

# Save to JSON for dashboard usage
with open(r'C:\Users\Armstrong Admin\OneDrive - ARMSTRONG CAPITAL AND FINANCIAL SERVICES PRIVATE LIMITED\Projects\US Whitelist\etf_list.json', 'w') as f:
    json.dump(etfs_sorted, f, indent=2)

print('\nSaved to etf_list.json')
