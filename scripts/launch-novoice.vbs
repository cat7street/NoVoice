Set sh = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
dir = fso.GetParentFolderName(WScript.ScriptFullName)
sh.CurrentDirectory = dir
exe = dir & "\NoVoice.exe"
bat = dir & "\bootstrap-and-run.bat"
marker = dir & "\.env_ready"
If Not fso.FileExists(marker) Then
  If fso.FileExists(bat) Then sh.Run """" & bat & """", 1, True
Else
  If fso.FileExists(exe) Then sh.Run """" & exe & """", 1, False
End If
