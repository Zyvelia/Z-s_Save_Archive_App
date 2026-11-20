# Inno Setup detection fix (v3.0)

`Build_All.bat` and `Build_Installer.bat` now use `Find_Inno_Setup.bat` to locate `ISCC.exe` under standard Program Files, per-user AppData installs, PATH and Inno Setup uninstall registry keys. `Build_All.bat` accepts a manually entered full path if auto-detection fails.

To override manually in a Command Prompt:

```bat
set "ISCC_EXE=C:\My Apps\Inno Setup 6\ISCC.exe"
call Build_All.bat
```

This patch changes only the Windows build scripts and adds this note. It does not alter the application's runtime features.

Validation performed: required files inspected, scripts checked for consistent success/failure handling, ZIP integrity verified. Inno Setup execution on Windows was not performed in this Linux environment.
