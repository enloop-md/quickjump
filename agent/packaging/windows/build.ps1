# Builds dist\QuickJump_Agent-<version>-windows.zip (CI: windows-latest).
# Unzip anywhere and run quickjump-agent.exe; "Start the agent when I log in"
# registers it under HKCU\...\Run. An installer (Inno Setup) and code signing
# can come later.
#
# Status: the build is wired up; global hotkeys on Windows are not implemented
# yet (the tray icon, window, autostart and browser support are).

$ErrorActionPreference = 'Stop'
$Repo = Resolve-Path "$PSScriptRoot\..\..\.."
Set-Location $Repo
$Version = (Select-String -Path agent\quickjump_agent\__init__.py -Pattern "__version__ = '(.*)'").Matches[0].Groups[1].Value
$Work = Join-Path $env:TEMP "qj-build-$([guid]::NewGuid())"

python -m venv "$Work\venv"
& "$Work\venv\Scripts\pip" install -q -r agent\packaging\requirements.txt
& "$Work\venv\Scripts\pyinstaller" --noconfirm --log-level WARN `
  --distpath "$Work\dist" --workpath "$Work\build" agent\packaging\quickjump-agent.spec

New-Item -ItemType Directory -Force dist | Out-Null
Compress-Archive -Force -Path "$Work\dist\quickjump-agent" -DestinationPath "dist\QuickJump_Agent-$Version-windows.zip"
Remove-Item -Recurse -Force $Work
Write-Host "Built dist\QuickJump_Agent-$Version-windows.zip"
