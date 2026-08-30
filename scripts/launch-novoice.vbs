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

If fso.FileExists(gui) Then
  launched = False
  On Error Resume Next
  sh.Run "pyw -3 """ & gui & """", 1, False
  If Err.Number = 0 Then launched = True
  Err.Clear
  If Not launched Then
    sh.Run "pythonw """ & gui & """", 1, False
    If Err.Number = 0 Then launched = True
    Err.Clear
  End If
  If Not launched Then
    sh.Run "py -3 """ & gui & """", 1, False
    If Err.Number = 0 Then launched = True
    Err.Clear
  End If
  If Not launched Then
    sh.Run "python """ & gui & """", 1, False
  End If
  On Error GoTo 0
  WScript.Quit 0
End If

If fso.FileExists(bat) Then
  sh.Run """" & bat & """", 1, False
  WScript.Quit 0
End If

If fso.FileExists(exe) Then sh.Run """" & exe & """", 1, False
