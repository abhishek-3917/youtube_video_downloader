Set WshShell = CreateObject("WScript.Shell")
Set FSO = CreateObject("Scripting.FileSystemObject")
WshShell.CurrentDirectory = FSO.GetParentFolderName(WScript.ScriptFullName)
WshShell.Run "pythonw.exe app.py", 0, False
WScript.Sleep 2000
WshShell.Run "http://127.0.0.1:8000"
