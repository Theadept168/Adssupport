@echo off
title Setup Auto-Start on Windows Boot
cd /d "%~dp0"

echo =======================================================
echo    Setting up Auto-Start on Windows Boot...
echo =======================================================
echo.

:: Register Task Scheduler to run at login (no window)
schtasks /create /tn "DubberAIStudio" /tr "wscript.exe //nologo \"%~dp0autostart.vbs\"" /sc onlogon /rl highest /f >nul 2>&1

if %errorlevel% == 0 (
    echo [OK] Task created: DubberAIStudio will auto-start on login!
) else (
    echo [WARN] Could not create scheduled task. Try running as Administrator.
)

echo.
echo To remove auto-start, run: remove_autostart.bat
echo.
pause
