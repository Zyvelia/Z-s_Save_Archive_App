@echo off
setlocal EnableExtensions DisableDelayedExpansion
cd /d "%~dp0"
if not exist "dist\ZSaveArchive\ZSaveArchive.exe" (
  echo ERROR: Build_Windows.bat must complete successfully first.
  exit /b 1
)
if not exist "ZSaveArchive.iss" (
  echo ERROR: ZSaveArchive.iss missing.
  exit /b 1
)
set "ARCHIVE_VERSION="
for /f "tokens=2,3" %%A in (ZSaveArchive.iss) do if "%%A"=="AppVersion" set "ARCHIVE_VERSION=%%~B"
if not defined ARCHIVE_VERSION (
  echo ERROR: AppVersion missing from ZSaveArchive.iss.
  exit /b 1
)
set "ARCHIVE_INSTALLER=installer_output\ZSaveArchive_v%ARCHIVE_VERSION%_Setup.exe"
call "%~dp0Find_Inno_Setup.bat"
if not defined ISCC_FOUND (
  echo ERROR: Could not find ISCC.exe. Set ISCC_EXE to its full path or run Build_All.bat.
  exit /b 1
)
echo Using Inno Setup: "%ISCC_EXE%"
"%ISCC_EXE%" "ZSaveArchive.iss"
if errorlevel 1 exit /b 1
if not exist "%ARCHIVE_INSTALLER%" (
  echo ERROR: Inno Setup did not produce expected installer.
  exit /b 1
)
echo Installer created: %ARCHIVE_INSTALLER%
exit /b 0
