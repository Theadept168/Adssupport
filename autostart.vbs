' Silent VBScript launcher - no window at all
' Starts Streamlit + Cloudflare tunnel fully in background
Dim objShell, strDir
Set objShell = CreateObject("WScript.Shell")
strDir = Left(WScript.ScriptFullName, InStrRev(WScript.ScriptFullName, "\"))

' Kill any existing instances
objShell.Run "cmd /c taskkill /F /IM cloudflared.exe >nul 2>&1", 0, True

' Start Streamlit server silently (stdout+stderr to log)
objShell.Run "cmd /c streamlit run """ & strDir & "app.py"" --server.address 0.0.0.0 --server.port 8501 > """ & strDir & "streamlit.log"" 2>&1", 0, False

' Wait 6 seconds for Streamlit to start
WScript.Sleep 6000

' Start Cloudflare tunnel silently (stderr captured for URL)
Dim objFSO
Set objFSO = CreateObject("Scripting.FileSystemObject")
If objFSO.FileExists(strDir & "cloudflared.exe") Then
    ' cloudflared writes URL to stderr, so redirect both
    objShell.Run "cmd /c """ & strDir & "cloudflared.exe"" tunnel --url http://localhost:8501 > """ & strDir & "cloudflare.log"" 2>&1", 0, False
End If
