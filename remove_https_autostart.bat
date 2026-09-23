@echo off
title Remove HTTPS Auto-Start
cd /d "%~dp0"

echo.
echo  Removing DubberAIStudio_HTTPS from Task Scheduler...
schtasks /delete /tn "DubberAIStudio_HTTPS" /f >nul 2>&1

if %errorlevel% == 0 (
    echo  [OK] Auto-start removed successfully.
) else (
    echo  [INFO] Task was not found (already removed).
)

echo.
echo  Stopping running servers...
taskkill /F /IM cloudflared.exe >nul 2>&1
taskkill /F /IM streamlit.exe >nul 2>&1

echo  [OK] Servers stopped.
echo.
pause
