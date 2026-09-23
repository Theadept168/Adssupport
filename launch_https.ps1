# launch_https.ps1 - Starts Streamlit + Cloudflare detached, shows HTTPS URL
$dir        = Split-Path -Parent $MyInvocation.MyCommand.Path
$streamlit  = "C:\Users\RMT\AppData\Local\Programs\Python\Python312\Scripts\streamlit.exe"
$python     = "C:\Users\RMT\AppData\Local\Programs\Python\Python312\python.exe"
$cfExe      = "$dir\cloudflared.exe"
$cfOut      = "$dir\cloudflare_https.log"
$cfErr      = "$dir\cloudflare_err2.log"
$stLog      = "$dir\streamlit.log"
$stErr      = "$dir\streamlit_err.log"

Set-Location $dir

Write-Host "[1] Stopping old servers..." -ForegroundColor Cyan
Stop-Process -Name "streamlit"   -Force -ErrorAction SilentlyContinue
Stop-Process -Name "cloudflared" -Force -ErrorAction SilentlyContinue
# Kill anything on port 8501
$pids = netstat -ano | Select-String ":8501\s" | ForEach-Object { ($_ -split '\s+')[-1] } | Sort-Object -Unique
$pids | ForEach-Object { Stop-Process -Id $_ -Force -ErrorAction SilentlyContinue }
Start-Sleep 3

# Wait for port to be free
Write-Host "[2] Waiting for port 8501 to be free..." -ForegroundColor Cyan
for ($i = 0; $i -lt 15; $i++) {
    if (!(netstat -ano | Select-String ":8501")) { break }
    Start-Sleep 2
}

# Delete old logs
foreach ($f in @($cfOut, $cfErr, $stLog, $stErr)) {
    if (Test-Path $f) { Remove-Item $f -Force }
}

Write-Host "[3] Starting Streamlit silently..." -ForegroundColor Cyan
$st = Start-Process -FilePath $streamlit `
    -ArgumentList "run", "app.py", "--server.address", "0.0.0.0", "--server.port", "8501", "--server.headless", "true" `
    -WorkingDirectory $dir `
    -WindowStyle Hidden `
    -RedirectStandardOutput $stLog `
    -RedirectStandardError  $stErr `
    -PassThru
Write-Host "    Streamlit PID: $($st.Id)" -ForegroundColor Gray

# Wait until Streamlit listens on 8501
Write-Host "[4] Waiting for Streamlit on port 8501..." -ForegroundColor Cyan
$ready = $false
for ($i = 0; $i -lt 25; $i++) {
    if (netstat -ano | Select-String ":8501") { $ready = $true; break }
    Start-Sleep 2
}
if (!$ready) {
    Write-Host "[ERROR] Streamlit failed to start! Check streamlit_err.log" -ForegroundColor Red
    Get-Content $stErr -ErrorAction SilentlyContinue | Select-Object -Last 10
    Read-Host "Press Enter to exit"
    exit 1
}
Write-Host "    Streamlit is UP!" -ForegroundColor Green
Start-Sleep 2

Write-Host "[5] Starting Cloudflare HTTPS tunnel..." -ForegroundColor Cyan
$cf = Start-Process -FilePath $cfExe `
    -ArgumentList "tunnel", "--url", "http://localhost:8501" `
    -WorkingDirectory $dir `
    -WindowStyle Hidden `
    -RedirectStandardOutput $cfOut `
    -RedirectStandardError  $cfErr `
    -PassThru
Write-Host "    Cloudflare PID: $($cf.Id)" -ForegroundColor Gray

Write-Host "[6] Waiting for HTTPS URL..." -ForegroundColor Cyan
$url = ""
for ($i = 0; $i -lt 30; $i++) {
    Start-Sleep 2
    if (Test-Path $cfErr) {
        $match = Get-Content $cfErr | Select-String "https://[a-z0-9-]+\.trycloudflare\.com"
        if ($match) {
            $url = ($match[0].Line) -replace ".*?(https://[a-z0-9-]+\.trycloudflare\.com).*", '$1'
            $url = $url.Trim()
            break
        }
    }
}

# Show result
Clear-Host
Write-Host ""
Write-Host "  =====================================================" -ForegroundColor Green
Write-Host "    Dubber AI Pro Studio  |  HTTPS RUNNING!" -ForegroundColor Green
Write-Host "  =====================================================" -ForegroundColor Green
Write-Host ""

if ($url) {
    Write-Host "  +==================================================+" -ForegroundColor Yellow
    Write-Host "  |                                                  |" -ForegroundColor Yellow
    Write-Host "  |   SHARE THIS LINK with your users:              |" -ForegroundColor Yellow
    Write-Host "  |                                                  |" -ForegroundColor Yellow
    Write-Host "  |   $url" -ForegroundColor White
    Write-Host "  |                                                  |" -ForegroundColor Yellow
    Write-Host "  +==================================================+" -ForegroundColor Yellow
    Write-Host ""
    # Save to Desktop
    $desktop = [Environment]::GetFolderPath("Desktop")
    Set-Content "$desktop\Dubber_HTTPS_Link.txt" "SHARE LINK:`r`n$url`r`n`r`nLocal: http://localhost:8501`r`nNetwork: http://192.168.1.7:8501"
    Write-Host "  Link also saved to Desktop: Dubber_HTTPS_Link.txt" -ForegroundColor Cyan
} else {
    Write-Host "  [TIMEOUT] URL not detected. Check cloudflare_err2.log" -ForegroundColor Red
}

Write-Host ""
Write-Host "  Local PC      :  http://localhost:8501" -ForegroundColor White
Write-Host "  Local Network :  http://192.168.1.7:8501" -ForegroundColor White
Write-Host ""
Write-Host "  *** You can safely CLOSE this window ***" -ForegroundColor Green
Write-Host "  *** Streamlit + Cloudflare keep running in background ***" -ForegroundColor Green
Write-Host ""
Write-Host "  To stop servers: run stop_servers.bat"
Write-Host ""
Read-Host "  Press Enter to close"
