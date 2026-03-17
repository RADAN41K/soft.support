; Inno Setup script for LimanSoft Support (Windows)
; Download Inno Setup: https://jrsoftware.org/isdl.php

#define FileHandle FileOpen("VERSION")
#define AppVer FileRead(FileHandle)
#expr FileClose(FileHandle)

[Setup]
AppName=LimanSoft Support
AppVersion={#AppVer}
AppPublisher=LimanSoft
DefaultDirName={localappdata}\LimanSoftSupport
DefaultGroupName=LimanSoft Support
PrivilegesRequired=lowest
OutputDir=dist
OutputBaseFilename=SoftSupport_Setup
SetupIconFile=assets\icon.ico
UninstallDisplayIcon={app}\SoftSupport.exe
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
UsedUserAreasWarning=no
CloseApplications=force
CloseApplicationsFilter=SoftSupport.exe

[Files]
Source: "dist\SoftSupport.exe"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{userprograms}\LimanSoft Support"; Filename: "{app}\SoftSupport.exe"; IconFilename: "{app}\SoftSupport.exe"
Name: "{userdesktop}\LimanSoft Support"; Filename: "{app}\SoftSupport.exe"; IconFilename: "{app}\SoftSupport.exe"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Створити ярлик на робочому столi"; GroupDescription: "Додатковi дiї:"
Name: "autostart"; Description: "Запускати при завантаженнi Windows"; GroupDescription: "Додатковi дiї:"

[Registry]
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "SoftSupport"; ValueData: """{app}\SoftSupport.exe"""; Flags: uninsdeletevalue; Tasks: autostart

[Run]
Filename: "{app}\SoftSupport.exe"; Description: "Запустити LimanSoft Support"; Flags: nowait postinstall skipifsilent

[Code]
function InitializeUninstall(): Boolean;
var
  ResultCode: Integer;
begin
  Result := True;
  if Exec('taskkill', '/F /IM SoftSupport.exe', '', SW_HIDE, ewWaitUntilTerminated, ResultCode) then
    Sleep(1000);
end;
