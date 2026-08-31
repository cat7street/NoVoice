Set sh = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
dir = fso.GetParentFolderName(WScript.ScriptFullName)
sh.CurrentDirectory = dir
exe = dir & "\NoVoice.exe"
gui = dir & "\first_run_setup_gui.py"
marker = dir & "\.env_ready"

If fso.FileExists(marker) Then
  If fso.FileExists(exe) Then sh.Run """" & exe & """", 1, False
  WScript.Quit 0
End If

If Not fso.FileExists(gui) Then
  If fso.FileExists(exe) Then sh.Run """" & exe & """", 1, False
  WScript.Quit 0
End If

On Error Resume Next
sh.Run "pyw -3 """ & gui & """", 0, False
If Err.Number = 0 Then WScript.Quit 0
Err.Clear
sh.Run "pythonw """ & gui & """", 0, False
If Err.Number = 0 Then WScript.Quit 0
Err.Clear
sh.Run "pyw """ & gui & """", 0, False
On Error GoTo 0
