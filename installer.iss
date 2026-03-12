; Inno Setup script for Soft Support (Windows)
; Download Inno Setup: https://jrsoftware.org/isdl.php

[Setup]
AppName=Soft Support
AppVersion=1.0.0
AppPublisher=LimanSoft
DefaultDirName={autopf}\SoftSupport
DefaultGroupName=Soft Support
OutputDir=dist
OutputBaseFilename=SoftSupport_Setup
SetupIconFile=assets\icon.ico
UninstallDisplayIcon={app}\SoftSupport.exe
Compression=lzma2
SolidCompression=yes
WizardStyle=modern

[Files]
Source: "dist\SoftSupport.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "config.json"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\Soft Support"; Filename: "{app}\SoftSupport.exe"; IconFilename: "{app}\SoftSupport.exe"
Name: "{autodesktop}\Soft Support"; Filename: "{app}\SoftSupport.exe"; IconFilename: "{app}\SoftSupport.exe"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Створити ярлик на робочому столi"; GroupDescription: "Додатковi дiї:"; Flags: checked

[Run]
Filename: "{app}\SoftSupport.exe"; Description: "Запустити Soft Support"; Flags: nowait postinstall skipifsilent
