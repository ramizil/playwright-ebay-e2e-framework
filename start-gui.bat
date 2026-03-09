@echo off
title eBay E2E Test Runner GUI
cd /d "%~dp0"

echo.
echo  ============================================
echo    eBay E2E Test Runner GUI
echo  ============================================
echo.
echo    URL:  http://localhost:5000
echo    Logs: server.log
echo.
echo  ============================================
echo.

:: Clear old log
if exist server.log del server.log

:: Start Flask in a minimized background window
start "FlaskServer" /min cmd /c "python gui\app.py > server.log 2>&1"

:: Wait for Flask to boot (typically 2-3 seconds)
echo  Starting server...
timeout /t 4 /nobreak >nul

:: Open browser
echo  Opening browser...
start "" "http://localhost:5000"

echo.
echo  Server is running. To stop it, close this window.
echo.

:: Keep alive — press Ctrl+C or close the window to stop
cmd /k
