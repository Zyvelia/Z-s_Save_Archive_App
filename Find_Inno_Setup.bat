@echo off
rem Shared Inno Setup compiler locator; called by both build scripts.
rem Optional override: set "ISCC_EXE=C:\path\to\ISCC.exe"
if defined ISCC_EXE call :check "%ISCC_EXE%"
if defined ISCC_FOUND exit /b 0
if defined ISCC call :check "%ISCC%"
if defined ISCC_FOUND exit /b 0
for %%D in (
  "%ProgramFiles(x86)%\Inno Setup 6"
  "%ProgramFiles%\Inno Setup 6"
  "%LocalAppData%\Programs\Inno Setup 6"
  "%LocalAppData%\Inno Setup 6"
  "%UserProfile%\AppData\Local\Programs\Inno Setup 6"
  "%ProgramFiles(x86)%\Inno Setup 7"
  "%ProgramFiles%\Inno Setup 7"
  "%LocalAppData%\Programs\Inno Setup 7"
) do (
  if not defined ISCC_FOUND call :check "%%~D\ISCC.exe"
)
if defined ISCC_FOUND exit /b 0
for /f "delims=" %%I in ('where ISCC.exe 2^>nul') do (
  if not defined ISCC_FOUND call :check "%%I"
)
if defined ISCC_FOUND exit /b 0
rem Registry entries from per-user and per-machine Inno Setup installers.
for %%R in (
  "HKCU\Software\Microsoft\Windows\CurrentVersion\Uninstall\Inno Setup 6_is1"
  "HKLM\Software\Microsoft\Windows\CurrentVersion\Uninstall\Inno Setup 6_is1"
  "HKLM\Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\Inno Setup 6_is1"
  "HKCU\Software\Microsoft\Windows\CurrentVersion\Uninstall\Inno Setup 7_is1"
  "HKLM\Software\Microsoft\Windows\CurrentVersion\Uninstall\Inno Setup 7_is1"
) do (
  if not defined ISCC_FOUND (
    for /f "tokens=2,*" %%A in ('reg query "%%~R" /v InstallLocation 2^>nul ^| findstr /i "InstallLocation"') do call :check "%%B\ISCC.exe"
  )
)
if defined ISCC_FOUND exit /b 0
exit /b 1

:check
if not exist "%~1" exit /b 1
for %%F in ("%~1") do set "ISCC_EXE=%%~fF"
set "ISCC_FOUND=1"
exit /b 0
