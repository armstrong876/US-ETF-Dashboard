@echo off
title US ETF Spreadsheet Update
echo ══════════════════════════════════════════════════════════
echo        ARMSTRONG CAPITAL - SPREADSHEET AUTOMATION
echo ══════════════════════════════════════════════════════════
echo.
echo [1/2] Checking dependencies...
pip install yfinance pandas xlsxwriter --quiet

echo [2/2] Fetching market data and generating Excel...
python spreadsheet_engine.py

echo.
echo ══════════════════════════════════════════════════════════
echo        UPDATE COMPLETE! Check ETF_Momentum_Spreadsheet.xlsx
echo ══════════════════════════════════════════════════════════
pause
