@echo off
title Dubber AI Studio - Background Launcher
cd /d "%~dp0"

echo =======================================================
echo    Dubber AI Pro Studio - Background Auto-Start
echo =======================================================
echo.

:: Kill any existing instances first
taskkill /F /IM streamlit.exe >nul 2>&1
taskkill /F /IM cloudflared.exe >nul 2>&1

:: Wait a moment for ports to free up
timeout /t 2 /nobreak >nul

echo [1/2] Starting Streamlit server in background...
start /B "" /MIN pythonw -c "import subprocess; subprocess.Popen(['streamlit', 'run', 'app.py', '--server.address', '0.0.0.0', '--server.port', '8501'], creationflags=0x08000000)" >nul 2>&1

:: Use VBScript to run silently without any window
echo Set objShell = CreateObject("WScript.Shell") > "%TEMP%\run_streamlit.vbs"
echo objShell.Run "cmd /c streamlit run ""%~dp0app.py"" --server.address 0.0.0.0 --server.port 8501 > ""%~dp0streamlit.log"" 2>&1", 0, False >> "%TEMP%\run_streamlit.vbs"
cscript //nologo "%TEMP%\run_streamlit.vbs"

echo [*] Streamlit started. Waiting for it to be ready...
timeout /t 5 /nobreak >nul

:: Start Cloudflare tunnel silently
if exist "%~dp0cloudflared.exe" (
    echo [2/2] Starting Cloudflare Tunnel in background...
    echo Set objShell = CreateObject("WScript.Shell") > "%TEMP%\run_cloudflare.vbs"
    echo objShell.Run "cmd /c ""%~dp0cloudflared.exe"" tunnel --url http://localhost:8501 > ""%~dp0cloudflare.log"" 2>&1", 0, False >> "%TEMP%\run_cloudflare.vbs"
    cscript //nologo "%TEMP%\run_cloudflare.vbs"
) else (
    echo [2/2] cloudflared.exe not found, skipping tunnel.
)

echo.
echo =======================================================
echo  Both servers are running silently in the background!
echo.
echo  Local URL:   http://localhost:8501
echo  Network URL: http://192.168.1.7:8501
echo  Public URL:  Check cloudflare.log for HTTPS link
echo.
echo  Logs saved to:
echo    - streamlit.log
echo    - cloudflare.log
echo =======================================================
echo.
timeout /t 5 /nobreak >nul
