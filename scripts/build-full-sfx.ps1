$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
$seven = 'C:\Program Files\7-Zip\7z.exe'
$sfx = 'C:\Program Files\7-Zip\7z.sfx'
if (-not (Test-Path $seven)) { throw '7z.exe not found' }
if (-not (Test-Path $sfx)) { throw '7z.sfx not found' }
if (-not (Test-Path 'release\NoVoice-Full\NoVoice.exe')) { throw 'missing release\NoVoice-Full' }
$cfgPath = Join-Path (Get-Location) 'release\sfx-config.txt'
$lines = @(';!@Install@!UTF-8!','Title="NoVoice Full"','BeginPrompt="Install NoVoice Full package?"','RunProgram="NoVoice.exe"',';!@InstallEnd@!')
$cfg = ($lines -join ([string][char]13 + [string][char]10))
[System.IO.File]::WriteAllText($cfgPath, $cfg, (New-Object System.Text.UTF8Encoding $false))
$archive = Join-Path (Get-Location) 'release\NoVoice-Full-payload.7z'
$outExe = Join-Path (Get-Location) 'release\NoVoice-Full-OneClick.exe'
if (Test-Path $archive) { Remove-Item $archive -Force }
if (Test-Path $outExe) { Remove-Item $outExe -Force }
Write-Host '==> Compressing payload with 7z'
& $seven a -t7z -mx=5 -mmt=on -- $archive '.\release\NoVoice-Full'
if ($LASTEXITCODE -ne 0) { throw ('7z compress failed: ' + $LASTEXITCODE) }
Write-Host '==> Building SFX'
$cmd = 'copy /b "' + $sfx + '" + "' + $cfgPath + '" + "' + $archive + '" "' + $outExe + '"'
cmd.exe /c $cmd
if (-not (Test-Path $outExe)) { throw 'SFX output missing' }
Get-Item $outExe | Format-List FullName,Length,LastWriteTime
'sfx_gb=' + [math]::Round(((Get-Item $outExe).Length / 1GB), 2)