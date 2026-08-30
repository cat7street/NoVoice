Unicode true
Name "NoVoice"
OutFile "..\release\NoVoice-Setup.exe"
InstallDir "$LOCALAPPDATA\NoVoice"
RequestExecutionLevel user
SetCompressor /SOLID lzma
Icon "..\src-tauri\icons\icon.ico"
UninstallIcon "..\src-tauri\icons\icon.ico"

Page directory
Page instfiles

Section "Install"
  SetOutPath "$INSTDIR"
  File "/oname=NoVoice.exe" "..\release\NoVoice\NoVoice.exe"
  File "/oname=bootstrap-and-run.bat" "..\scripts\bootstrap-and-run.bat"
  File "/oname=requirements.txt" "..\requirements.txt"
  CreateDirectory "$INSTDIR\models"
  File "/oname=models\README.md" "..\models\README.md"
  CreateDirectory "$SMPROGRAMS\NoVoice"
  CreateShortCut "$SMPROGRAMS\NoVoice\NoVoice.lnk" "$INSTDIR\bootstrap-and-run.bat"
  CreateShortCut "$DESKTOP\NoVoice.lnk" "$INSTDIR\bootstrap-and-run.bat"
  CreateShortCut "$SMPROGRAMS\NoVoice\Uninstall.lnk" "$INSTDIR\Uninstall.exe"
  WriteUninstaller "$INSTDIR\Uninstall.exe"
  Exec '"$INSTDIR\bootstrap-and-run.bat"'
SectionEnd

Section "Uninstall"
  Delete "$SMPROGRAMS\NoVoice\NoVoice.lnk"
  Delete "$SMPROGRAMS\NoVoice\Uninstall.lnk"
  RMDir "$SMPROGRAMS\NoVoice"
  Delete "$DESKTOP\NoVoice.lnk"
  RMDir /r "$INSTDIR"
SectionEnd
