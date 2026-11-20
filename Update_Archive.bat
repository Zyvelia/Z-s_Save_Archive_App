@echo off
setlocal EnableDelayedExpansion
cd /d "%~dp0"
(
    where py >nul 2>nul
    if errorlevel 1 (
        python "%~dp0update_archive.py"
    ) else (
        py -3 "%~dp0update_archive.py"
    )
    set "UPDATE_RESULT=!errorlevel!"
    pause
    exit /b !UPDATE_RESULT!
)
