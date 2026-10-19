; Inno Setup 6 Installer Script for Sortify
; Produces: release\Sortify-Setup-1.0.0.exe
; Per-user install by default (no admin elevation required), preserving %APPDATA%\Sortify user data.

#define MyAppName "Sortify"
#define MyAppVersion "1.0.0"
#define MyAppExeName "Sortify.exe"
#define MyAppURL "https://github.com/hmmlavi/sortify"

[Setup]
AppId={{D48B92E4-7F3A-4E91-9A2D-8C6E4501FA10}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppName}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}
AppCopyright=Copyright (c) 2026 Sortify contributors
VersionInfoVersion={#MyAppVersion}.0
VersionInfoCompany={#MyAppName}
VersionInfoDescription={#MyAppName} - Order, by design
VersionInfoProductName={#MyAppName}
VersionInfoProductVersion={#MyAppVersion}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
MinVersion=10.0
LicenseFile=..\LICENSE
OutputDir=..\release
OutputBaseFilename=Sortify-Setup-{#MyAppVersion}
SetupIconFile=..\assets\sortify.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
UninstallDisplayName={#MyAppName} {#MyAppVersion}
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes
RestartApplications=no

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
; The recursive entry includes the launcher itself, so it must not be listed twice.
Source: "..\dist\Sortify\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Comment: "Order, by design - precise, reversible file renaming"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon; Comment: "Order, by design - precise, reversible file renaming"

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent

[Code]
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  UserDataDir: String;
begin
  if (CurUninstallStep = usPostUninstall) and (not UninstallSilent()) then
  begin
    UserDataDir := ExpandConstant('{userappdata}\Sortify');
    if DirExists(UserDataDir) then
    begin
      if MsgBox('Do you want to keep your Sortify settings and rename history in ' + UserDataDir + '?' + #13#10 + #13#10 +
                'Choose Yes (recommended) to preserve your settings and undo history, or No to delete them permanently.',
                mbConfirmation, MB_YESNO or MB_DEFBUTTON1) = IDNO then
      begin
        DelTree(UserDataDir, True, True, True);
      end;
    end;
  end;
end;
