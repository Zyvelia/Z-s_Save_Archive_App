# Windows packaging and Tools menu update (v2.4)

## Requirements

- Windows 10/11, Python 3.13 (recommended), internet for dependency installation.
- `Build_Windows.bat` installs PySide6 and PyInstaller into its own `.venv-build` and outputs `dist\ZSaveArchive\ZSaveArchive.exe` (one-folder portable program binaries).
- Install Inno Setup 6, then run `Build_Installer.bat`; the installer appears in `installer_output`.

## Save safety

By default the app stores archives in `Documents\Z PlayStation Save Archive`, outside installed program files. The Inno installer is per-user and uninstall does not remove this archive. An existing `portable.flag` beside the executable instead selects local `ArchiveData`, so do **not** use portable mode inside an Inno-installed Program Files directory. Installer packaging intentionally excludes `portable.flag`, databases and `ArchiveData`.

## Tools navigation

The previous long flat Tools list is regrouped into 8 functional submenus, keeping every original action and signal connection. Five frequently used tools remain directly available. **Find tool…** opens a searchable Qt item picker; the existing Ctrl+K command palette remains available.

## Verification limits

Automated Python tests and static packaging validation can run on Linux. **The actual PyInstaller build and Inno compilation require Windows and Inno Setup 6**, and the full Qt window must be smoke-tested on Windows before release.


## App branding assets

`assets/ZSaveArchive.png` supplies the PySide6 window and taskbar icon.
`assets/ZSaveArchive.ico` is embedded by PyInstaller into the EXE and by Inno Setup into the installer.
`assets/ZSaveArchive_Original.png` preserves the full-size image.

Build_Windows.bat copies these assets into the one-folder build. Build_Installer.bat embeds the ICO into the installer; the installed shortcuts use the EXE's embedded icon.

## One-click combined build

Run `Build_All.bat` from the extracted project folder. It locates Inno Setup, builds the one-folder PyInstaller application, and calls `Build_Installer.bat`. The installer script reads `AppVersion` from `ZSaveArchive.iss` and verifies `installer_output\ZSaveArchive_v<VERSION>_Setup.exe`. The individual build scripts are also available.
