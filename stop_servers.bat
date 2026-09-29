@echo off
title Stop Dubber AI Studio Servers
echo =======================================================
echo    Stopping Dubber AI Pro Studio Servers...
echo =======================================================
echo.

echo Stopping Streamlit server on port 8501...
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":8501" 2^>nul') do (
    taskkill /F /PID %%a >nul 2>&1
)

echo Stopping Cloudflare Tunnel...
taskkill /F /IM cloudflared.exe >nul 2>&1

echo Stopping Dubber AI supervisor and python processes...
taskkill /F /IM streamlit.exe >nul 2>&1
powershell -Command "Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like '*main.py*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }" >nul 2>&1

echo.
echo [✓] All servers and background supervisors stopped!
timeout /t 2 /nobreak >nul

