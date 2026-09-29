@echo off
title Dubber AI Pro Studio - Windows Launcher [Auto-Reboot]
cd /d "%~dp0"
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8

:server_loop
echo ============================================================
echo   Starting Dubber AI Pro Studio [Auto-Reboot Active]
echo ============================================================
python main.py %*

:: If exit code is 0 (clean shutdown by user), exit cleanly
if %ERRORLEVEL% equ 0 (
    echo.
    echo [i] Server stopped cleanly.
    goto end
)

echo.
echo ============================================================
echo [!] Server encountered an error or crashed (Exit Code: %ERRORLEVEL%).
echo [!] Releasing port 8501 and auto-rebooting in 3 seconds...
echo [!] (Press Ctrl+C to cancel auto-reboot)
echo ============================================================

:: Force release port 8501
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":8501" 2^>nul') do taskkill /F /PID %%a >nul 2>&1
timeout /t 3 /nobreak >nul

goto server_loop

:end
pause
