# v2.9 one-click Windows packaging

- Added `Build_All.bat` (EXE then Inno Setup installer).
- Checks prerequisites before starting; stops on any failure and validates resulting EXE and setup file.
- Corrected Inno Setup AppVersion from stale 2.5 to 2.9.
- Retained original independent build scripts, branding, assets, source, tests, and all save/FTP/ISO/homebrew/GitHub features.
- Actual EXE and installer not compiled in this Linux environment.
