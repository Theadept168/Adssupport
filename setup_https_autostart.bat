@echo off
title Setup HTTPS Auto-Start on Windows Boot
cd /d "%~dp0"
color 0B

echo.
echo  =====================================================
echo    Dubber AI Pro Studio - HTTPS Auto-Start Setup
echo  =====================================================
echo.

REM --- Kill any existing instances first ---
echo  Stopping any existing servers...
taskkill /F /IM streamlit.exe >nul 2>&1
taskkill /F /IM cloudflared.exe >nul 2>&1
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":8501" 2^>nul') do taskkill /F /PID %%a >nul 2>&1
timeout /t 2 /nobreak >nul

REM --- Register Task Scheduler (run at every login, highest privileges) ---
echo  Registering auto-start task...
schtasks /create /tn "DubberAIStudio_HTTPS" /tr "wscript.exe //nologo \"%~dp0autostart_https.vbs\"" /sc onlogon /rl highest /f >nul 2>&1

if %errorlevel% == 0 (
    echo  [OK] Auto-start registered!
) else (
    echo  [WARN] Registration failed - try running as Administrator.
)

echo.
echo  Starting server NOW in background...
start "" /B wscript.exe //nologo "%~dp0autostart_https.vbs"

echo.
echo  =====================================================
echo   Server is launching silently in the background.
echo.
echo   Wait ~25 seconds then you will see a POPUP
echo   with your HTTPS share link.
echo.
echo   The link is also saved to your Desktop as:
echo     Dubber_HTTPS_Link.txt
echo.
echo   From next Windows login, it starts AUTOMATICALLY.
echo.
echo   To STOP server:        stop_servers.bat
echo   To REMOVE auto-start:  remove_https_autostart.bat
echo  =====================================================
echo.
pause
