Set WshShell = CreateObject("WScript.Shell")
Set FSO = CreateObject("Scripting.FileSystemObject")
WshShell.CurrentDirectory = FSO.GetParentFolderName(WScript.ScriptFullName)

Function IsServerRunning()
    On Error Resume Next
    Dim http
    Set http = CreateObject("MSXML2.ServerXMLHTTP.6.0")
    http.Open "GET", "http://127.0.0.1:8000/api/default-dir", False
    http.setTimeouts 500, 500, 500, 500
    http.Send
    If Err.Number = 0 And http.Status = 200 Then
        IsServerRunning = True
    Else
        IsServerRunning = False
    End If
    On Error GoTo 0
End Function

If Not IsServerRunning() Then
    WshShell.Run "pythonw.exe app.py", 0, False
    For i = 1 To 16
        WScript.Sleep 500
        If IsServerRunning() Then Exit For
    Next
End If

WshShell.Run "http://127.0.0.1:8000"
