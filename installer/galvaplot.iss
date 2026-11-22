; Inno Setup script for the Windows installer.
; Built by GitHub Actions (.github/workflows/build.yml) after PyInstaller has produced dist\GalvaPlot\.
; Manual build on Windows:  ISCC.exe /DMyAppVersion=0.1.0 installer\galvaplot.iss
;
; Installs for the current user by default (no administrator password needed, goes to
; %LOCALAPPDATA%\Programs\GalvaPlot); the user can choose "all users" in the first dialog.

#ifndef MyAppVersion
  #define MyAppVersion "0.0.0"
#endif
#define MyAppName "GalvaPlot"
#define MyAppExe "GalvaPlot.exe"

[Setup]
; AppId identifies the program for upgrades and uninstall: never change it.
AppId={{9BDACDDD-97AA-49AD-8DC8-2F80B081866D}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher=GalvaPlot contributors
AppPublisherURL=https://github.com/690463389xkc-collab/galvaplot
AppSupportURL=https://github.com/690463389xkc-collab/galvaplot/issues
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog commandline
ArchitecturesAllowed=x64
ArchitecturesInstallIn64BitMode=x64
OutputDir=..\dist
OutputBaseFilename=GalvaPlot-{#MyAppVersion}-Windows-Setup
SetupIconFile=..\assets\icon.ico
UninstallDisplayIcon={app}\{#MyAppExe}
UninstallDisplayName={#MyAppName}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
; force: if GalvaPlot does not close when asked, end it instead of cancelling the installation
; (a silent in-app update otherwise rolled back when the app was still quitting)
CloseApplications=force

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
Source: "..\dist\GalvaPlot\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
; licenses also at the top of the install folder, where people look for them
Source: "..\LICENSE"; DestDir: "{app}"; DestName: "LICENSE.txt"; Flags: ignoreversion
Source: "..\build\third_party_licenses\*"; DestDir: "{app}\licenses"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExe}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExe}"; Description: "{cm:LaunchProgram,{#MyAppName}}"; Flags: nowait postinstall skipifsilent
; in-app update (the update button) runs Setup /SILENT /RELAUNCH=1: reopen the program afterwards
Filename: "{app}\{#MyAppExe}"; Flags: nowait runasoriginaluser; Check: ShouldRelaunch

[Code]
function ShouldRelaunch: Boolean;
begin
  Result := ExpandConstant('{param:RELAUNCH|0}') = '1';
end;

{ True while a process named GalvaPlot.exe is running (WMI); False if that cannot be checked }
function GalvaPlotRunning: Boolean;
var
  Locator, Service, Procs: Variant;
begin
  Result := False;
  try
    Locator := CreateOleObject('WbemScripting.SWbemLocator');
    Service := Locator.ConnectServer('.', 'root\CIMV2');
    Procs := Service.ExecQuery('SELECT ProcessId FROM Win32_Process WHERE Name = ''GalvaPlot.exe''');
    Result := Procs.Count > 0;
  except
    Result := False;
  end;
end;

{ The in-app update starts Setup /SILENT just before the app quits: give the app up to 15 s
  to quit, so that it is not still running when Setup replaces its files. }
function InitializeSetup: Boolean;
var
  I: Integer;
begin
  if WizardSilent then
    for I := 1 to 60 do
    begin
      if not GalvaPlotRunning then
        Break;
      Sleep(250);
    end;
  Result := True;
end;

[UninstallDelete]
; the font cache the app builds on first launch (user settings in the registry are kept)
Type: filesandordirs; Name: "{localappdata}\GalvaPlot\matplotlib"
