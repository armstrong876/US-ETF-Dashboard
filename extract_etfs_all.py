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

    def safe_float(val):
        try:
            return float(str(val).replace('%','').replace(',','').strip())
        except:
            return None

    etfs.append({
        'symbol':     sym.strip(),
        'name':       str(row[1]) if row[1] else '',
        'asset_class': str(row[2]) if row[2] else '',
        'aum':        aum,
        'category':   str(row[10]) if row[10] else '',
        'er':         safe_float(row[12]),
        'price':      price,
        'inception':  str(row[11]).split()[0] if row[11] else None, # e.g. 2010-09-07
        'pe':         safe_float(row[19]),
        'beta':       safe_float(row[20]),
        'holdings':   safe_float(row[22]),
        'top10_pct':  safe_float(row[23])
    })

# Sort by AUM descending, keep ALL
etfs_sorted = sorted(etfs, key=lambda x: x['aum'], reverse=True)

print(f'\nTotal non-inverse/non-leveraged ETFs: {len(etfs)}')

# Save to JSON for dashboard usage
with open(r'C:\Users\Armstrong Admin\OneDrive - ARMSTRONG CAPITAL AND FINANCIAL SERVICES PRIVATE LIMITED\Projects\US Whitelist\etf_list_all.json', 'w') as f:
    json.dump(etfs_sorted, f, indent=2)

print('\nSaved to etf_list_all.json')
