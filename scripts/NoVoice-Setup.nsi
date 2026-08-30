Unicode true
!include "MUI2.nsh"

Name "NoVoice"
OutFile "..\release\NoVoice-Setup.exe"
InstallDir "$LOCALAPPDATA\NoVoice"
RequestExecutionLevel user
SetCompressor /SOLID lzma

!define MUI_ABORTWARNING
!define MUI_ICON "..\src-tauri\icons\icon.ico"
!define MUI_UNICON "..\src-tauri\icons\icon.ico"
!define MUI_WELCOMEFINISHPAGE_BITMAP "installer-art\wizard-sidebar.bmp"
!define MUI_UNWELCOMEFINISHPAGE_BITMAP "installer-art\wizard-sidebar.bmp"
!define MUI_HEADERIMAGE
!define MUI_HEADERIMAGE_BITMAP "installer-art\wizard-header.bmp"
!define MUI_HEADERIMAGE_RIGHT
!define MUI_WELCOMEPAGE_TITLE "Welcome to NoVoice"
!define MUI_WELCOMEPAGE_TEXT "NoVoice removes vocals from video while keeping the picture lossless.$\r$\n$\r$\nClick Next to continue."
!define MUI_FINISHPAGE_TITLE "Installation Complete"
!define MUI_FINISHPAGE_TEXT "NoVoice is ready.$\r$\n$\r$\nFirst launch will auto-setup Python / Demucs / models."
!define MUI_FINISHPAGE_RUN "$INSTDIR\bootstrap-and-run.bat"
!define MUI_FINISHPAGE_RUN_TEXT "Launch NoVoice now"

!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH
!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES
!insertmacro MUI_LANGUAGE "English"

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
SectionEnd

Section "Uninstall"
  Delete "$SMPROGRAMS\NoVoice\NoVoice.lnk"
  Delete "$SMPROGRAMS\NoVoice\Uninstall.lnk"
  RMDir "$SMPROGRAMS\NoVoice"
  Delete "$DESKTOP\NoVoice.lnk"
  RMDir /r "$INSTDIR"
SectionEnd
