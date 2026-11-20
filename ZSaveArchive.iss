#define AppName "Z's Save Archive"
#define AppVersion "3.6.11"
#define AppExe "ZSaveArchive.exe"

[Setup]
AppId={{C2E9C196-32AC-43B3-AC70-27C0C878B7E7}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher=Z's Save Archive
DefaultDirName={localappdata}\Programs\ZSaveArchive
DefaultGroupName={#AppName}
PrivilegesRequired=lowest
OutputDir=installer_output
OutputBaseFilename=ZSaveArchive_v{#AppVersion}_Setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes
RestartApplications=no
SetupIconFile=assets\ZSaveArchive.ico
UninstallDisplayIcon={app}\{#AppExe}

[Files]
Source: "dist\ZSaveArchive\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs; Excludes: "ArchiveData\*,*.db,*.sqlite,*.sqlite3,portable.flag"

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional shortcuts:"; Flags: unchecked

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExe}"; Description: "Launch {#AppName}"; Flags: nowait postinstall skipifsilent

; User archive data lives outside the installation directory and is never removed by uninstall.
