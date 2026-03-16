; Inno Setup script for LimanSoft Support (Windows)
; Download Inno Setup: https://jrsoftware.org/isdl.php

[Setup]
AppName=LimanSoft Support
AppVersion=1.0.0
AppPublisher=LimanSoft
DefaultDirName={autopf}\SoftSupport
DefaultGroupName=LimanSoft Support
OutputDir=dist
OutputBaseFilename=SoftSupport_Setup
SetupIconFile=assets\icon.ico
UninstallDisplayIcon={app}\SoftSupport.exe
Compression=lzma2
SolidCompression=yes
WizardStyle=modern

[Files]
Source: "dist\SoftSupport.exe"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\LimanSoft Support"; Filename: "{app}\SoftSupport.exe"; IconFilename: "{app}\SoftSupport.exe"
Name: "{autodesktop}\LimanSoft Support"; Filename: "{app}\SoftSupport.exe"; IconFilename: "{app}\SoftSupport.exe"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Створити ярлик на робочому столi"; GroupDescription: "Додатковi дiї:"
Name: "autostart"; Description: "Запускати при завантаженнi Windows"; GroupDescription: "Додатковi дiї:"

[Registry]
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "SoftSupport"; ValueData: """{app}\SoftSupport.exe"""; Flags: uninsdeletevalue; Tasks: autostart

[UninstallDelete]
Type: filesandordirs; Name: "{userappdata}\LimanSoft"

[Run]
Filename: "{app}\SoftSupport.exe"; Description: "Запустити LimanSoft Support"; Flags: nowait postinstall skipifsilent
