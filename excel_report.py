import json
import os
import pandas as pd
from datetime import datetime

def generate_report():
    print("Generating Excel Momentum Report...")
    
    # Load dashboard data
    try:
        with open('dashboard.json', 'r') as f:
            data = json.load(f)
    except FileNotFoundError:
        print("Error: dashboard.json not found. Run data_engine.py first.")
        return

    writer = pd.ExcelWriter('ETF_Momentum_Report.xlsx', engine='xlsxwriter')
    workbook = writer.book

    # --- FORMATS ---
    header_fmt = workbook.add_format({
        'bold': True, 'bg_color': '#1a1f2e', 'font_color': 'white', 
        'border': 1, 'align': 'center', 'valign': 'vcenter'
    })
    
    pos_fmt = workbook.add_format({'bg_color': '#064e1c', 'font_color': '#4ade80'})
    neg_fmt = workbook.add_format({'bg_color': '#4d0606', 'font_color': '#ef4444'})
    neu_fmt = workbook.add_format({'bg_color': '#1e1e24', 'font_color': '#94a3b8'})
    
    pct_fmt = workbook.add_format({'num_format': '0.0%', 'align': 'center'})
    score_fmt = workbook.add_format({'num_format': '0.0', 'bold': True, 'align': 'center'})

    # --- 1. OVERVIEW SHEET ---
    overview_data = []
    
    # Market Indices
    for ticker, name in data.get('market_indices', {}).items():
        # Note: market_indices in dashboard.json is a simple dict, but we want the price/change
        # This data is usually inside the etfs list if indexed, but for simplicity:
        pass

    # Top 10
    top10_df = pd.DataFrame(data.get('top10', []))
    if not top10_df.empty:
        top10_df = top10_df[['rank', 'symbol', 'name', 'score', 'signal']]
        top10_df.columns = ['#', 'Ticker', 'Name', 'Momentum Score', 'Signal']
        top10_df.to_excel(writer, sheet_name='Summary', startrow=2, index=False)
        
    worksheet = writer.sheets['Summary']
    worksheet.write(0, 0, f"ETF Momentum Report - {data.get('as_of_date', '')}", workbook.add_format({'bold': True, 'font_size': 14}))
    worksheet.write(1, 0, "Top 10 Momentum ETFs", workbook.add_format({'bold': True, 'font_color': '#22c55e'}))

    # --- 2. HEATMAP SHEET ---
    etfs = data.get('etfs', [])
    rows = []
    for e in etfs:
        row = {
            'Ticker': e['symbol'],
            'Name': e['name'],
            'Category': e['category'],
            'Score': e.get('momentum_score'),
            'Signal': e.get('signal')
        }
        # Add all returns
        for p, v in e.get('returns', {}).items():
            row[p] = v
        rows.append(row)
    
    heatmap_df = pd.DataFrame(rows)
    # Sort by score
    heatmap_df = heatmap_df.sort_values(by='Score', ascending=False)
    heatmap_df.to_excel(writer, sheet_name='Universe Heatmap', index=False)
    
    ws_heat = writer.sheets['Universe Heatmap']
    
    # Apply conditional formatting to returns
    # Columns are Ticker, Name, Category, Score, Signal, then periods...
    return_cols = ['1W', '15D', '1M', '2M', '3M', '6M', '9M', '12M', '2Y', '3Y', '5Y', '7Y', '10Y']
    for i, col in enumerate(heatmap_df.columns):
        if col in return_cols:
            col_letter = chr(65 + i) if i < 26 else f"{chr(64 + i // 26)}{chr(65 + i % 26)}"
            ws_heat.conditional_format(f'{col_letter}2:{col_letter}{len(heatmap_df)+1}', {
                'type': '3_color_scale',
                'min_color': '#ef4444',
                'mid_color': '#1e1e24',
                'max_color': '#22c55e'
            })
            ws_heat.set_column(i, i, 10, pct_fmt)
        elif col == 'Score':
            ws_heat.set_column(i, i, 10, score_fmt)
        elif col == 'Name':
            ws_heat.set_column(i, i, 30)
        else:
            ws_heat.set_column(i, i, 12)

    writer.close()
    print("Report saved as ETF_Momentum_Report.xlsx")

if __name__ == "__main__":
    generate_report()
