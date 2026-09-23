@echo off
title Dubber AI Pro Studio - Windows Launcher
cd /d "%~dp0"

python main.py %*

if %ERRORLEVEL% neq 0 (
    echo.
    echo [!] Server exited or encountered an error.
    pause
)
