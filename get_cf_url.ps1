$log = "cloudflare_err2.log"
if (!(Test-Path $log)) { exit 1 }
$lines = Get-Content $log | Select-String "https://[a-z0-9-]+\.trycloudflare\.com"
if (!$lines) { exit 1 }
$url = ($lines[0].Line) -replace ".*?(https://[a-z0-9-]+\.trycloudflare\.com).*",'$1'
Write-Output $url.Trim()
