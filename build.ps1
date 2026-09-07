param([string]$Python = 'python', [string]$ISCC = "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe")
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
& $Python -m pip install -r requirements-build.txt
if ($LASTEXITCODE) { throw 'Dependency installation failed' }
& $Python -m unittest discover -s tests -v
if ($LASTEXITCODE) { throw 'Tests failed' }
& $Python -m PyInstaller --noconfirm --clean --onefile --windowed --name TaskPool --icon assets/taskpool.ico --exclude-module numpy --exclude-module matplotlib --exclude-module IPython app.py
if ($LASTEXITCODE) { throw 'Executable build failed' }
& $ISCC installer.iss
if ($LASTEXITCODE) { throw 'Installer build failed' }
Write-Host 'Ready: dist/TaskPool-Setup-2.0.1-windows-x64.exe'
