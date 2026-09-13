param([string]$Python = 'python', [string]$ISCC = "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe")
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
& $Python -m pip install -r requirements-build.txt
if ($LASTEXITCODE) { throw 'Dependency installation failed' }
& $Python -m unittest discover -s tests -v
if ($LASTEXITCODE) { throw 'Tests failed' }
New-Item -ItemType Directory -Force work | Out-Null
if (!(Test-Path work/MicrosoftEdgeWebview2Setup.exe)) {
  Invoke-WebRequest -Uri 'https://go.microsoft.com/fwlink/p/?LinkId=2124703' -OutFile work/MicrosoftEdgeWebview2Setup.exe
}
$signature = Get-AuthenticodeSignature work/MicrosoftEdgeWebview2Setup.exe
if ($signature.Status -ne 'Valid' -or $signature.SignerCertificate.Subject -notmatch 'Microsoft Corporation') { throw 'Runtime installer signature is invalid' }
& $Python -m PyInstaller --noconfirm --clean --onefile --windowed --name Termxk --icon assets/termxk.ico --manifest assets/termxk.manifest --add-data 'frontend.html;.' --add-data 'assets/termxk.ico;assets' --collect-data webview --exclude-module tkinter --exclude-module numpy --exclude-module matplotlib --exclude-module IPython --exclude-module PyQt5 --exclude-module PyQt6 --exclude-module PySide2 --exclude-module PySide6 app.py
if ($LASTEXITCODE) { throw 'Executable build failed' }
& $ISCC installer.iss
if ($LASTEXITCODE) { throw 'Installer build failed' }
Write-Host 'Ready: dist/Termxk-Setup-3.0.0-windows-x64.exe'
