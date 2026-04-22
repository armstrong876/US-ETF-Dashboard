@echo off
setlocal enabledelayedexpansion

echo ============================================================
echo   Armstrong Capital — ETF Dashboard Dynamic Server
echo ============================================================
echo.

:: Check for dependencies
echo [1/3] Checking Python dependencies...
python -m pip install flask requests >nul 2>&1

:: Check if port 5000 is in use
echo [2/3] Preparing server...
netstat -ano | findstr :5000 >nul
if %ERRORLEVEL% EQU 0 (
    echo.
    echo WARNING: Port 5000 is already in use. 
    echo If the dashboard doesn't load, please close other Python windows.
    echo.
)

echo [3/3] Starting local dashboard server...
echo.
echo TIP: To update the LIVE dashboard for your team:
echo      1. Use the dashboard at http://127.0.0.1:5000
echo      2. Click 'Refresh'
echo      3. The system will automatically push data to Netlify.
echo.

:: Start the server in a new window and wait 2 seconds before opening browser
start "ETF Dashboard Server" /min python server.py
timeout /t 2 >nul
start "" http://127.0.0.1:5000

echo Server is running! 
echo Keep this window open. 
pause
