Set sh = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
dir = fso.GetParentFolderName(WScript.ScriptFullName)
sh.CurrentDirectory = dir
exe = dir & "\NoVoice.exe"
gui = dir & "\first_run_setup_gui.py"
bat = dir & "\bootstrap-and-run.bat"
marker = dir & "\.env_ready"
If fso.FileExists(marker) Then
  If fso.FileExists(exe) Then sh.Run """" & exe & """", 1, False
  WScript.Quit 0
End If

pyCmd = ""
On Error Resume Next
Set wh = sh.Exec("where py")
out = wh.StdOut.ReadAll
On Error GoTo 0
If InStr(1, out, "py.exe", 1) > 0 Or InStr(1, out, "py.cmd", 1) > 0 Then
  pyCmd = "py -3"
Else
  pyCmd = "python"
End If

If fso.FileExists(gui) Then
  sh.Run pyCmd & " """ & gui & """", 0, True
ElseIf fso.FileExists(bat) Then
  sh.Run """" & bat & """", 1, True
ElseIf fso.FileExists(exe) Then
  sh.Run """" & exe & """", 1, False
End If
