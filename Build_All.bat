@echo off
setlocal EnableExtensions DisableDelayedExpansion
cd /d "%~dp0"
title Z Save Archive - EXE and Installer Builder

echo ============================================================
echo  Z's Save Archive - Windows EXE + Inno Setup Installer
echo ============================================================
echo.

if not exist "Build_Windows.bat" (echo ERROR: Missing Build_Windows.bat & goto :failed)
if not exist "Build_Installer.bat" (echo ERROR: Missing Build_Installer.bat & goto :failed)
if not exist "Find_Inno_Setup.bat" (echo ERROR: Missing Find_Inno_Setup.bat & goto :failed)
if not exist "ZSaveArchive.iss" (echo ERROR: Missing ZSaveArchive.iss & goto :failed)

call "%~dp0Find_Inno_Setup.bat"
if not defined ISCC_FOUND call :manual_inno
if not defined ISCC_FOUND (
  echo ERROR: Could not locate ISCC.exe. Inno Setup may be installed to a custom folder.
  echo Supply the exact path to ISCC.exe when prompted, or set ISCC_EXE.
  goto :failed
)
echo Inno Setup compiler: "%ISCC_EXE%"
echo.

echo [1/3] Building Windows executable...
call "%~dp0Build_Windows.bat"
if errorlevel 1 (echo ERROR: EXE build failed. Installer was not built. & goto :failed)
if not exist "dist\ZSaveArchive\ZSaveArchive.exe" (echo ERROR: Expected EXE was not produced. & goto :failed)

echo.
echo [2/3] Compiling Inno Setup installer...
call "%~dp0Build_Installer.bat"
if errorlevel 1 (echo ERROR: Installer build failed. & goto :failed)

echo.
echo [3/3] Build complete.
echo Portable EXE: "%CD%\dist\ZSaveArchive\ZSaveArchive.exe"
echo.
choice /c YN /n /m "Open installer output folder? [Y/N] "
if errorlevel 2 goto :success
start "" "%CD%\installer_output"
:success
echo Completed successfully.
pause
exit /b 0

:manual_inno
echo.
echo Inno Setup wasn't found in standard folders, PATH, or the registry.
echo Enter the full path to ISCC.exe, or leave blank to stop.
set "MANUAL_ISCC="
set /p "MANUAL_ISCC=ISCC.exe path: "
if not defined MANUAL_ISCC exit /b 1
set "MANUAL_ISCC=%MANUAL_ISCC:"=%"
for %%F in ("%MANUAL_ISCC%") do set "ISCC_EXE=%%~fF"
if exist "%ISCC_EXE%" (set "ISCC_FOUND=1" & exit /b 0)
echo ERROR: That file does not exist: "%ISCC_EXE%"
exit /b 1

:failed
echo.
echo Build stopped. No installer success was claimed.
pause
exit /b 1
