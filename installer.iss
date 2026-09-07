#define MyAppVersion "2.0.1"
[Setup]
AppId={{A03DF892-5585-40C9-B80C-40D4A2B96352}
AppName=TaskPool
AppVersion={#MyAppVersion}
AppPublisher=Lichao-Lin
AppPublisherURL=https://github.com/Lichao-Lin/TaskPool
DefaultDirName={localappdata}\Programs\TaskPool
DefaultGroupName=TaskPool
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
DisableProgramGroupPage=yes
DisableWelcomePage=yes
DisableDirPage=yes
DisableReadyPage=yes
OutputDir=dist
OutputBaseFilename=TaskPool-Setup-{#MyAppVersion}-windows-x64
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
SetupIconFile=assets\taskpool.ico
UninstallDisplayIcon={app}\TaskPool.exe
CloseApplications=yes
RestartApplications=no

[Files]
Source: "dist\TaskPool.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "README.md"; DestDir: "{app}"; Flags: ignoreversion
Source: "LICENSE"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{userdesktop}\TaskPool"; Filename: "{app}\TaskPool.exe"; WorkingDir: "{app}"
Name: "{userprograms}\TaskPool"; Filename: "{app}\TaskPool.exe"; WorkingDir: "{app}"

[Run]
Filename: "{app}\TaskPool.exe"; Description: "Launch TaskPool"; Flags: nowait postinstall skipifsilent
