@echo off
title Dubber AI Studio - Background Launcher (Auto-Reboot Active)
cd /d "%~dp0"
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8

echo =======================================================
echo    Dubber AI Pro Studio - Background Auto-Start
echo =======================================================
echo.

:: Kill any existing instances first
taskkill /F /IM streamlit.exe >nul 2>&1
taskkill /F /IM cloudflared.exe >nul 2>&1
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":8501" 2^>nul') do taskkill /F /PID %%a >nul 2>&1
powershell -Command "Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like '*main.py*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }" >nul 2>&1

:: Wait a moment for ports to free up
timeout /t 2 /nobreak >nul

echo Starting Dubber AI Studio Supervisor (with Auto-Reboot)...
:: Use VBScript to run pythonw main.py completely silently in background
echo Set objShell = CreateObject("WScript.Shell") > "%TEMP%\run_dubber_bg.vbs"
echo objShell.Run "pythonw ""%~dp0main.py"" --no-browser", 0, False >> "%TEMP%\run_dubber_bg.vbs"
cscript //nologo "%TEMP%\run_dubber_bg.vbs" >nul 2>&1

echo [*] Supervisor launched. Waiting for server to initialize...
timeout /t 6 /nobreak >nul

echo.
echo =======================================================
echo  Server is running silently in the background!
echo  🛡️ Auto-Reboot: Active (restarts automatically on error)
echo.
echo  Local URL:   http://localhost:8501
echo  Public URL:  Check cloudflare.log for HTTPS link
echo.
echo  To STOP all servers, run: stop_servers.bat
echo =======================================================
echo.
timeout /t 5 /nobreak >nul

