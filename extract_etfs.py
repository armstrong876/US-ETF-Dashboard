import openpyxl
import json

wb = openpyxl.load_workbook(
    r'C:\Users\Armstrong Admin\OneDrive - ARMSTRONG CAPITAL AND FINANCIAL SERVICES PRIVATE LIMITED\Projects\US Whitelist\ETF Database.xlsx'
)
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

    etfs.append({
        'symbol':     sym.strip(),
        'name':       str(row[1]) if row[1] else '',
        'asset_class': str(row[2]) if row[2] else '',
        'aum':        aum,
        'category':   str(row[10]) if row[10] else '',
        'er':         float(row[12]) if row[12] else 0,
        'price':      price,
    })

etfs_sorted = sorted(etfs, key=lambda x: x['aum'], reverse=True)[:100]

print(f'\nTotal non-inverse/non-leveraged ETFs: {len(etfs)}')
print('\nTop 100 ETFs by AUM:')
for i, e in enumerate(etfs_sorted, 1):
    print(f"{i:3}. {e['symbol']:8}  AUM: {e['aum']:>20,.0f}  {e['name'][:50]}")

tickers = [e['symbol'] for e in etfs_sorted]
print('\nTicker list:')
print(tickers)

# Save to JSON for dashboard usage
with open(r'C:\Users\Armstrong Admin\OneDrive - ARMSTRONG CAPITAL AND FINANCIAL SERVICES PRIVATE LIMITED\Projects\US Whitelist\etf_list.json', 'w') as f:
    json.dump(etfs_sorted, f, indent=2)

print('\nSaved to etf_list.json')
