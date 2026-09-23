@echo off
setlocal
cd /d "%~dp0"
echo ====================================================
echo        Dubber AI - Push to GitHub Helper
echo ====================================================
echo.

git remote get-url origin >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo [!] No GitHub remote found.
    echo.
    echo Step 1: Create a new repository on https://github.com/new
    echo Step 2: Copy the repository URL (e.g., https://github.com/username/repo-name.git)
    echo.
    set /p REPO_URL="Enter your GitHub Repository URL: "
    if "%REPO_URL%"=="" (
        echo [X] Error: URL cannot be empty.
        pause
        exit /b 1
    )
    git remote add origin %REPO_URL%
)

echo [*] Current Remote:
git remote -v
echo.
echo [*] Pushing to GitHub (main branch)...
git branch -M main
git push -u origin main

if %ERRORLEVEL% EQU 0 (
    echo.
    echo ====================================================
    echo [OK] Pushed to GitHub successfully!
    echo.
    echo Next:
    echo 1. Open https://share.streamlit.io
    echo 2. Click "Create app"
    echo 3. Select your repository and main file: app.py
    echo 4. Click "Deploy"!
    echo ====================================================
) else (
    echo.
    echo [!] If Git asked for password, use a GitHub Personal Access Token (PAT).
)
echo.
pause
