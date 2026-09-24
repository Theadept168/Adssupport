@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion
title Dubber AI - Easy One-Click Push to GitHub
cd /d "%~dp0"

echo ================================================================
echo             🚀 DUBBER AI - EASY PUSH TO GITHUB
echo ================================================================
echo.

git status --porcelain > "%temp%\git_status.tmp"
set HAS_CHANGES=0
for /f "usebackq delims=" %%A in ("%temp%\git_status.tmp") do set HAS_CHANGES=1
del "%temp%\git_status.tmp" >nul 2>&1

echo [*] Target Repository: https://github.com/Theadept168/Adssupport
echo [*] Target Branch:     main
echo.

if %HAS_CHANGES% EQU 0 (
    echo [i] No local file changes detected. Checking remote status...
    echo.
    git status -s
    echo.
    set /p FORCE_PUSH="Do you still want to run 'git push origin main'? (Y/N, default Y): "
    if /i "!FORCE_PUSH!"=="N" (
        echo [i] Cancelled.
        goto DONE
    )
    echo [*] Pushing existing commits to GitHub...
    git push origin main
    goto CHECK_RESULT
)

echo [!] The following files have been modified / added:
echo ----------------------------------------------------------------
git status -s
echo ----------------------------------------------------------------
echo.

set DEFAULT_MSG=Update Dubber AI - %DATE% %TIME%
set "USER_MSG="
set /p USER_MSG="Enter commit message (Press ENTER to use auto date/time): "

if "!USER_MSG!"=="" (
    set "FINAL_MSG=!DEFAULT_MSG!"
) else (
    set "FINAL_MSG=!USER_MSG!"
)

echo.
echo [*] Staging all files (git add -A)...
git add -A

echo [*] Committing: "!FINAL_MSG!"...
git commit -m "!FINAL_MSG!"

echo [*] Pushing to GitHub (origin main)...
git push origin main

:CHECK_RESULT
if %ERRORLEVEL% EQU 0 (
    echo.
    echo ================================================================
    echo     ✅ [SUCCESS] Changes pushed to GitHub successfully!
    echo ================================================================
    echo Repository: https://github.com/Theadept168/Adssupport
) else (
    echo.
    echo ================================================================
    echo     ❌ [ERROR] Push failed! (Exit Code: %ERRORLEVEL%)
    echo ================================================================
    echo Tips:
    echo 1. Check your internet connection.
    echo 2. If prompted for GitHub credentials:
    echo    - Username: Your GitHub username
    echo    - Password: Use a GitHub Personal Access Token (PAT)
    echo 3. Try pulling remote updates: git pull origin main
)

:DONE
echo.
echo Press any key to close this window...
pause >nul
