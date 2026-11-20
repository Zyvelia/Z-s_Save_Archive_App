# v3.1 — Retail2Pkg selectable tool folder

The user-supplied `Retail2Pkg.zip` was inspected. It contains the CFW2OFW helper, `Retail2Pkg.bat`, `makepkg1.exe`, `makepkg2.exe`, `make_npdata.exe`, PS3Merge, dependencies and configuration files. The tools themselves are **not redistributed** in this source ZIP. Extract the tools you already possess on your PC and select their location in the UI.

## Using the option

1. Open **PS3 Tools → PS3 ISO → XMB Assistant**; choose **Retail2Pkg Folder…** and select the extracted folder containing `CFW2OFW_Helper.exe` and `Retail2Pkg.bat`. The helper field populates automatically.
2. Choose your ISO or `PS3_GAME`, optional 7-Zip, and a **new**, separate work folder. Stage & Convert only after reviewing the confirmation.
3. Open **PS3 Package Builder & FTP Transfer**. Choose your completed conversion workspace, then the same **Retail2Pkg tools folder**.
4. Click **Prepare Retail2Pkg handoff** and choose a destination parent. The app creates a `Retail2Pkg_Handoff` copy containing the toolkit and compatible converted game folders.
5. Review `RETAIL2PKG_HANDOFF_README.txt` and folder layout. If you decide to run `Retail2Pkg.bat`, run it **manually from that handoff only**. The script uses `move`, `rd /s /q` and `del`; do NOT run it against your original ISO, `PS3_GAME`, or conversion workspace. Inspect output files before attempting installation.

**Compatibility limitation:** The handoff requires a converted `BL*/BC*` container containing both an `NP*` game directory and a `BL*/BC*` patch directory. If conversion has not generated that layout, the app reports why rather than claiming it created PKGs. Encrypted disc ISOs still require separately supported extraction; conversion doesn't guarantee game support or valid installed PKGs. The UI does not execute Retail2Pkg.bat automatically.

## Preserved

All v3.0 functionality is retained: simplified sidebar, saves and backups, PC/PS3 save support, FTP legacy listing encoding fix, editors, Homebrew, ISO/PKG tools, GitHub, original icon, and one-click EXE/Inno build including custom Inno detection.

## Verification

303 Python unittest cases passed, including 5 new Retail2Pkg folder/handoff tests. Python source compilation and source ZIP integrity passed. Live Windows PySide6 layout, external tool execution, PKG output and PS3 installation were not tested.
