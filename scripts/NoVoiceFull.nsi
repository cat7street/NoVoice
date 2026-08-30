Unicode true
Name "NoVoice Full"
OutFile "..\release\NoVoice-Full-Setup.exe"
InstallDir "$LOCALAPPDATA\NoVoice"
RequestExecutionLevel user
SetCompressor /SOLID lzma

Page directory
Page instfiles

Section "Install"
  SetOutPath "$INSTDIR"
  File /r "..\release\NoVoice-Full\*.*"

  CreateDirectory "$SMPROGRAMS\NoVoice"
  CreateShortCut "$SMPROGRAMS\NoVoice\NoVoice.lnk" "$INSTDIR\NoVoice.exe"
  CreateShortCut "$DESKTOP\NoVoice.lnk" "$INSTDIR\NoVoice.exe"

  WriteUninstaller "$INSTDIR\Uninstall.exe"
SectionEnd

Section "Uninstall"
  Delete "$SMPROGRAMS\NoVoice\NoVoice.lnk"
  RMDir "$SMPROGRAMS\NoVoice"
  Delete "$DESKTOP\NoVoice.lnk"
  Delete "$INSTDIR\Uninstall.exe"
  RMDir /r "$INSTDIR"
SectionEnd
