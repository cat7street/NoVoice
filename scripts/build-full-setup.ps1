$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)

$makensis = Get-ChildItem "$env:LOCALAPPDATA\tauri\NSIS" -Recurse -Filter makensis.exe -ErrorAction SilentlyContinue |
  Select-Object -First 1 -ExpandProperty FullName
if (-not $makensis) { throw "makensis.exe not found under %LOCALAPPDATA%\tauri\NSIS" }

if (-not (Test-Path "release\NoVoice-Full\NoVoice.exe")) {
  throw "missing release\NoVoice-Full. Build full portable package first."
}

Write-Host "Using $makensis"
& $makensis "scripts\NoVoiceFull.nsi"
if ($LASTEXITCODE -ne 0) { throw "makensis failed: $LASTEXITCODE" }

Get-Item "release\NoVoice-Full-Setup.exe" | Format-List FullName,Length,LastWriteTime
'setup_gb=' + [math]::Round(((Get-Item "release\NoVoice-Full-Setup.exe").Length/1GB),2)
