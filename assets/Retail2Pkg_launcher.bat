@echo off

setlocal DisableDelayedExpansion
dir /s /b "*.666??" >nul 2>nul
if not errorlevel 1 (
    echo.
    echo Select the Retail2Pkg working folder in PS3Merge to merge split files before converting.
    PS3Merge.exe
)

cls

CFW2OFW_Helper.exe || goto conversionfailure

echo.
echo.

set "masterfld="

for /d %%v in (*BL???????*) do set "masterfld=%%v"
for /d %%v in (*BC???????*) do set "masterfld=%%v"

if not defined masterfld goto failure
pushd "%masterfld%" || goto failure

set game=
set ptch=

for /d %%v in (NP???????) do set game=%%v
for /d %%v in (BL???????) do set ptch=%%v
for /d %%v in (BC???????) do set ptch=%%v


popd
if not defined game goto failure
if not defined ptch goto failure

move "%masterfld%\%game%" "." >nul || goto failure
move "%masterfld%\%ptch%" "." >nul || goto failure

echo.
echo.
echo Creating GAME pkg...

>package.conf echo contentid = 000000-%game:~0,9%_00-1GAME00000000000
>>package.conf echo klicensee = 0x00000000000000000000000000000000
>>package.conf echo drmtype = Free
>>package.conf echo contenttype = GameExec
>>package.conf echo packagetype = HDDGamePatch
>>package.conf echo installdirectory = %game%
>>package.conf echo packageversion = 01.00

makepkg1.exe -n package.conf %game%>nul

if exist %game%\LICDIR xcopy "%game%\LICDIR\*.*" "%game%-LIC\LICDIR\" /E /I /Y >nul
if exist %game%\INSDIR xcopy "%game%\INSDIR\*.*" "%game%-LIC\INSDIR\" /E /I /Y >nul

echo Creating PATCH pkg...

>package.conf echo contentid = 000000-%game:~0,9%_00-2PATCH0000000000
>>package.conf echo klicensee = 0x00000000000000000000000000000000
>>package.conf echo drmtype = Free
>>package.conf echo contenttype = GameData
>>package.conf echo packagetype = DiscGamePatch
>>package.conf echo installdirectory = %ptch%
>>package.conf echo packageversion = 01.00

makepkg1.exe -n package.conf %ptch%>nul

if exist %game%-LIC (
	echo Creating LIC pkg...

	>package.conf echo contentid = 000000-%game:~0,9%_00-3LIC000000000000
	>>package.conf echo klicensee = 0x00000000000000000000000000000000
	>>package.conf echo drmtype = Free
	>>package.conf echo contenttype = GameExec
	>>package.conf echo packagetype = HDDGamePatch
	>>package.conf echo installdirectory = %game%
	>>package.conf echo packageversion = 01.00

	makepkg2.exe -n package.conf %game%-LIC>nul
	if not exist "*-3LIC*.pkg" goto packagefailure

	rd /S /Q "%game%-LIC">nul
)

del package.conf>nul

ren "*-1GAME*.pkg" "%masterfld%.pkg" >nul || goto packagefailure
ren "*-2PATCH*.pkg" "%masterfld%_-_Update.pkg" >nul || goto packagefailure
if exist "*-3LIC*.pkg" (
    ren "*-3LIC*.pkg" "%masterfld%_-_Fix.pkg" >nul || goto packagefailure
)

move "*.pkg" "%masterfld%\" >nul || goto packagefailure

rd %game% /s /q > nul
rd %ptch% /s /q > nul
rd patch /s /q > nul

echo.

echo Successfully created pkgs.

set "result=0"
goto end

:conversionfailure
echo CFW2OFW Helper failed. No packages were built.
set "result=1"
goto end

:packagefailure
echo Package creation failed. See the output above.
set "result=1"
goto end

:failure

echo Some folders are missing or could not be moved.
set "result=1"

:end
if /i not "%~1"=="/launcher" (
    echo.
    echo Press any key to exit.
    pause >nul
)
exit /b %result%
