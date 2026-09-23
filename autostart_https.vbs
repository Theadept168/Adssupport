Dim objShell, objFSO, strDir, logPath
Set objShell = CreateObject("WScript.Shell")
Set objFSO   = CreateObject("Scripting.FileSystemObject")
strDir = Left(WScript.ScriptFullName, InStrRev(WScript.ScriptFullName, "\"))
logPath = strDir & "cloudflare_https.log"

' --- Kill existing ---
objShell.Run "cmd /c taskkill /F /IM streamlit.exe >nul 2>&1", 0, True
objShell.Run "cmd /c taskkill /F /IM cloudflared.exe >nul 2>&1", 0, True
objShell.Run "cmd /c for /f ""tokens=5"" %a in (""netstat -ano ^| findstr :8501"") do taskkill /F /PID %a >nul 2>&1", 0, True
WScript.Sleep 4000

' --- Wait for port 8501 to be truly free (up to 30s) ---
Dim portFree, tries
portFree = False
For tries = 1 To 15
    Dim chk
    chk = objShell.Run("cmd /c netstat -ano | findstr :8501 > nul 2>&1", 0, True)
    If chk <> 0 Then
        portFree = True
        Exit For
    End If
    WScript.Sleep 2000
Next

If Not portFree Then
    MsgBox "Port 8501 could not be freed after 30 seconds." & Chr(13) & "Please restart Windows and try again.", 16, "Dubber - Port Error"
    WScript.Quit
End If

' --- Delete old logs ---
If objFSO.FileExists(logPath) Then objFSO.DeleteFile logPath, True
If objFSO.FileExists(strDir & "streamlit.log") Then objFSO.DeleteFile strDir & "streamlit.log", True

' --- Start Streamlit silently ---
objShell.Run "cmd /c streamlit run """ & strDir & "app.py"" --server.address 0.0.0.0 --server.port 8501 --server.headless true > """ & strDir & "streamlit.log"" 2>&1", 0, False

' --- Wait until Streamlit is actually listening on 8501 ---
Dim stReady
stReady = False
For tries = 1 To 20
    WScript.Sleep 2000
    Dim r
    r = objShell.Run("cmd /c netstat -ano | findstr :8501 > nul 2>&1", 0, True)
    If r = 0 Then
        stReady = True
        Exit For
    End If
Next

If Not stReady Then
    MsgBox "Streamlit failed to start on port 8501." & Chr(13) & "Check streamlit.log for errors.", 16, "Dubber - Streamlit Error"
    WScript.Quit
End If

WScript.Sleep 2000

' --- Start Cloudflare tunnel silently ---
If Not objFSO.FileExists(strDir & "cloudflared.exe") Then
    MsgBox "cloudflared.exe not found in:" & Chr(13) & strDir, 16, "Dubber - Error"
    WScript.Quit
End If
objShell.Run "cmd /c """ & strDir & "cloudflared.exe"" tunnel --url http://localhost:8501 > """ & logPath & """ 2>&1", 0, False

' --- Poll for URL (up to 60s) ---
Dim urlFound, fileContent
urlFound = ""
For tries = 1 To 30
    WScript.Sleep 2000
    If objFSO.FileExists(logPath) Then
        Dim ts
        Set ts = objFSO.OpenTextFile(logPath, 1)
        fileContent = ts.ReadAll
        ts.Close
        Dim lineArr, j
        lineArr = Split(fileContent, Chr(10))
        For j = 0 To UBound(lineArr)
            Dim curLine
            curLine = Trim(lineArr(j))
            If InStr(curLine, "https://") > 0 And InStr(curLine, "trycloudflare.com") > 0 Then
                Dim startPos, rest, k
                startPos = InStr(curLine, "https://")
                rest = Mid(curLine, startPos)
                Dim endPos
                endPos = 0
                For k = 1 To Len(rest)
                    Dim c
                    c = Mid(rest, k, 1)
                    If c = " " Or c = "|" Or c = Chr(13) Or c = Chr(10) Or c = Chr(9) Then
                        endPos = k - 1 : Exit For
                    End If
                Next
                If endPos > 0 Then urlFound = Left(rest, endPos) Else urlFound = rest
                urlFound = Trim(urlFound)
            End If
        Next
    End If
    If urlFound <> "" Then Exit For
Next

' --- Save to Desktop ---
Dim desktopPath, urlFilePath
desktopPath = objShell.SpecialFolders("Desktop")
urlFilePath = desktopPath & "\Dubber_HTTPS_Link.txt"
Dim outFile
Set outFile = objFSO.CreateTextFile(urlFilePath, True)
outFile.WriteLine "====================================="
outFile.WriteLine " Dubber AI Pro Studio - HTTPS Link"
outFile.WriteLine "====================================="
outFile.WriteLine ""
If urlFound <> "" Then
    outFile.WriteLine " SHARE THIS LINK:"
    outFile.WriteLine " " & urlFound
    outFile.WriteLine ""
    outFile.WriteLine " Works on any phone, tablet, or PC worldwide."
Else
    outFile.WriteLine " [ERROR] URL not detected. Check cloudflare_https.log"
End If
outFile.WriteLine ""
outFile.WriteLine " Local PC:      http://localhost:8501"
outFile.WriteLine " Local Network: http://192.168.1.7:8501"
outFile.WriteLine ""
outFile.WriteLine " To stop: run stop_servers.bat"
outFile.Close

' --- Popup ---
If urlFound <> "" Then
    MsgBox "Dubber AI Pro Studio is RUNNING!" & Chr(13) & Chr(13) & _
           "SHARE LINK:" & Chr(13) & Chr(13) & _
           urlFound & Chr(13) & Chr(13) & _
           "Also saved to Desktop: Dubber_HTTPS_Link.txt", _
           64, "Dubber AI Studio - HTTPS Ready!"
Else
    MsgBox "Server started but HTTPS URL was not detected." & Chr(13) & _
           "Check: cloudflare_https.log", _
           48, "Dubber AI Studio - Warning"
End If
