@echo off
title Remove Auto-Start
schtasks /delete /tn "DubberAIStudio" /f >nul 2>&1
echo Auto-start removed! DubberAIStudio will no longer start on login.
timeout /t 3 /nobreak >nul
