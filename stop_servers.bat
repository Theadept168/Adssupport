@echo off
title Stop Dubber AI Studio Servers
echo =======================================================
echo    Stopping Dubber AI Pro Studio Servers...
echo =======================================================
echo.

echo Stopping Streamlit server...
for /f "tokens=5" %%a in ('netstat -aon ^| findstr :8501') do (
    taskkill /F /PID %%a >nul 2>&1
)

echo Stopping Cloudflare Tunnel...
taskkill /F /IM cloudflared.exe >nul 2>&1

echo Stopping any Python Streamlit processes...
wmic process where "commandline like '%%streamlit%%'" delete >nul 2>&1

echo.
echo All servers stopped!
timeout /t 2 /nobreak >nul
