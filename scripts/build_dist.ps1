# Build ocrTable distribution (PyInstaller onedir)
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

$Pyi = Join-Path $Root ".venv\Scripts\pyinstaller.exe"
if (-not (Test-Path $Pyi)) {
    Write-Error "PyInstaller not found. Run: .\.venv\Scripts\pip.exe install pyinstaller"
}

Write-Host ">>> PyInstaller (ocrTable.spec) ..."
& $Pyi -y ocrTable.spec
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

$Dist = Join-Path $Root "dist\ocrTable"
New-Item -ItemType Directory -Force -Path (Join-Path $Dist "data\images") | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $Dist "data\exports") | Out-Null
Copy-Item (Join-Path $Root ".env.example") (Join-Path $Dist ".env.example") -Force

$BatContent = "@echo off`r`ncd /d `"%~dp0`"`r`nstart ``"``" `"ocrTable.exe`"`r`n"
[System.IO.File]::WriteAllText((Join-Path $Dist "启动.bat"), $BatContent, [System.Text.Encoding]::ASCII)

Write-Host ""
Write-Host "Done: $Dist\ocrTable.exe"
