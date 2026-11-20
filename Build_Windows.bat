@echo off
setlocal EnableExtensions
cd /d "%~dp0"
set "PROJECT=%CD%"
set "PYTHON=python"
where py >nul 2>&1 && set "PYTHON=py -3.13"
%PYTHON% --version >nul 2>&1
if errorlevel 1 (
  set "PYTHON=python"
  python --version >nul 2>&1 || (echo ERROR: Install Python 3.13 first. & exit /b 1)
)
if not exist ".venv-build\Scripts\python.exe" (
  echo Creating isolated build environment...
  %PYTHON% -m venv ".venv-build" || exit /b 1
)
set "VENV_PY=%PROJECT%\.venv-build\Scripts\python.exe"
"%VENV_PY%" -m pip install --disable-pip-version-check -r requirements.txt "pyinstaller>=6.10,<7" || exit /b 1
if exist "build" rmdir /s /q "build"
if exist "dist\ZSaveArchive" rmdir /s /q "dist\ZSaveArchive"
"%VENV_PY%" -m PyInstaller --noconfirm --clean --windowed --onedir --name "ZSaveArchive" --icon "assets\ZSaveArchive.ico" --add-data "assets;assets" --collect-submodules zarchive --add-data "editor_definitions;editor_definitions" main.py || exit /b 1
if not exist "dist\ZSaveArchive\ZSaveArchive.exe" (echo ERROR: Executable not found. & exit /b 1)
echo.
echo Build succeeded: dist\ZSaveArchive\ZSaveArchive.exe
echo To create an installer, run Build_Installer.bat (Inno Setup 6 required).
exit /b 0
