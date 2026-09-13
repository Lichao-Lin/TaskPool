#define MyAppVersion "3.0.0"
[Setup]
AppId={{A03DF892-5585-40C9-B80C-40D4A2B96352}
AppName=Termxk
AppVersion={#MyAppVersion}
AppPublisher=Lichao-Lin
AppPublisherURL=https://github.com/Lichao-Lin/TaskPool
DefaultDirName={localappdata}\Programs\Termxk
DefaultGroupName=Termxk
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
DisableProgramGroupPage=yes
DisableWelcomePage=yes
DisableDirPage=yes
DisableReadyPage=yes
OutputDir=dist
OutputBaseFilename=Termxk-Setup-{#MyAppVersion}-windows-x64
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
SetupIconFile=assets\termxk.ico
UninstallDisplayIcon={app}\Termxk.exe
CloseApplications=yes
RestartApplications=no

[Files]
Source: "dist\Termxk.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "README.md"; DestDir: "{app}"; Flags: ignoreversion
Source: "LICENSE"; DestDir: "{app}"; Flags: ignoreversion
Source: "work\MicrosoftEdgeWebview2Setup.exe"; Flags: dontcopy

[InstallDelete]
Type: files; Name: "{app}\TaskPool.exe"
Type: files; Name: "{userdesktop}\TaskPool.lnk"
Type: files; Name: "{userprograms}\TaskPool.lnk"

[Icons]
Name: "{userdesktop}\Termxk"; Filename: "{app}\Termxk.exe"; WorkingDir: "{app}"
Name: "{userprograms}\Termxk"; Filename: "{app}\Termxk.exe"; WorkingDir: "{app}"

[Run]
Filename: "{app}\Termxk.exe"; Description: "Launch Termxk"; Flags: nowait postinstall skipifsilent

[Code]
function HasWebView2: Boolean;
var Version: String;
begin
  Result := (RegQueryStringValue(HKLM32, 'SOFTWARE\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}', 'pv', Version) and (Version <> '') and (Version <> '0.0.0.0')) or
            (RegQueryStringValue(HKCU, 'SOFTWARE\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}', 'pv', Version) and (Version <> '') and (Version <> '0.0.0.0'));
end;
function PrepareToInstall(var NeedsRestart: Boolean): String;
var ExitCode: Integer;
begin
  Result := '';
  if not HasWebView2 then begin
    ExtractTemporaryFile('MicrosoftEdgeWebview2Setup.exe');
    WizardForm.StatusLabel.Caption := 'Installing Microsoft WebView2 Runtime...';
    if not Exec(ExpandConstant('{tmp}\MicrosoftEdgeWebview2Setup.exe'), '/silent /install', '', SW_HIDE, ewWaitUntilTerminated, ExitCode) then
      Result := 'Could not install WebView2 Runtime. Check your connection and retry.'
    else if not HasWebView2 then
      Result := 'WebView2 Runtime is required. Connect to the internet and retry installation.';
  end;
end;
