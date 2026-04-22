@echo off
cd /d "%~dp0"
echo ========================================= >> auto_update.log
echo Starting Auto Update at %date% %time% >> auto_update.log
python auto_update.py >> auto_update.log 2>&1
echo Finished Auto Update at %date% %time% >> auto_update.log
echo ========================================= >> auto_update.log
