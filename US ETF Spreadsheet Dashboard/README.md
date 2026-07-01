# US ETF Spreadsheet Dashboard

This folder contains a standalone, automated solution for tracking ETF momentum in **Excel** or **Google Sheets**.

## Option 1: Automated Excel Dashboard (Python)

This method uses Python to fetch real-time data and generate a beautifully formatted Excel dashboard with one click.

### Files:
- `spreadsheet_engine.py`: The data engine that fetches market data and calculates momentum.
- `Update_Spreadsheet.bat`: Double-click this to refresh the data and generate the report.
- `ETF_Momentum_Spreadsheet.xlsx`: The generated dashboard (created after running).

### Instructions:
1. Ensure Python is installed.
2. Double-click `Update_Spreadsheet.bat`.
3. Open `ETF_Momentum_Spreadsheet.xlsx` to see your dashboard.
4. **Note**: Close the Excel file before running the update script, or it will give a "Permission Denied" error.

---

## Option 2: Google Sheets Dashboard (Real-time)

This method uses Google's built-in financial functions and a small script for automation.

### Instructions:
1. Open a new [Google Sheet](https://sheets.new).
2. Go to **Extensions** > **Apps Script**.
3. Open the file `Google_Sheets_Setup.gs` in this folder, copy the code, and paste it into the Google Apps Script editor.
4. Click **Save** and then **Run** the `initializeDashboard` function.
5. Grant permissions when asked.
6. A new sheet named "ETF Momentum" will be created with all formulas, data, and a color-coded heatmap.
7. You can now refresh data anytime using the new **🚀 ETF Dashboard** menu at the top.

---

## Features
- **Market Overview**: Live prices and 1-month changes for major indices (S&P 500, Nasdaq, etc.).
- **Top 10 / Bottom 10**: Automatic ranking of ETFs by Momentum Score.
- **Visual Heatmap**: Color-coded grid showing performance across 1W, 1M, 3M, 6M, and 1Y.
- **Momentum Score**: Calculated exactly like the web dashboard:
  - 1 Month: 20%
  - 3 Month: 30%
  - 6 Month: 30%
  - 12 Month: 20%
