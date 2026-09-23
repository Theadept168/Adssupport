@echo off
title Dubber AI Studio - Mobile & Web Launcher
cd /d "%~dp0"

echo =======================================================
echo    Dubber AI Pro Studio - Phone & Web Launcher
echo =======================================================
echo.
echo Local Phone / Network URL: http://192.168.1.7:8501
echo Local PC URL:              http://localhost:8501
echo.
echo Starting Streamlit server and Cloudflare Tunnel...
echo.

start "Streamlit Server" cmd /k "streamlit run app.py --server.address 0.0.0.0 --server.port 8501"
timeout /t 3 /nobreak >nul

if exist "cloudflared.exe" (
    echo Starting Cloudflare Tunnel for Remote Phone Access...
    start "Cloudflare Tunnel" cmd /k "cloudflared.exe tunnel --url http://localhost:8501"
)

echo.
echo Servers are now running! Check the Cloudflare window for your public HTTPS link.
pause
