# v3.2 — Local PKG generation, FTP optional

## Workflow
1. Convert your own supported PS3 game using the existing converter.
2. Open PS3 Tools → PS3 PKG Builder (Local / FTP).
3. Choose the completed **conversion workspace**, extracted **Retail2Pkg tools folder**, and a separate, existing **local PKG output folder** on your PC.
4. Click **Build PKGs Locally (No FTP)**. Explicitly confirm execution of the third-party batch file.
5. The app creates a unique isolated staging copy beneath your output folder, executes Retail2Pkg.bat within it, and copies recognizable PKG files to the selected output folder. No FTP connection or credentials are required.
6. You can later transfer PKGs using the optional upload button or any other method. No automatic installation is attempted.

## Safety and known limitations
- The provided Retail2Pkg.bat executes CFW2OFW_Helper and destructive move/remove commands. It runs **only in a newly prepared staging copy**, never against the original conversion workspace or tool folder.
- Creating the staging copy requires disk space potentially larger than the game. The staging folder is retained so you can inspect logs or recover results.
- The batch may pause or require user interaction and may time out; actual Windows runs are not verified.
- PKGs are checked for nontrivial size and PS3 PKG magic, **not** cryptographic authenticity, console compatibility, or installability.
- Existing named PKGs are never overwritten. The build is considered successful only after copying valid-looking PKGs.
- This feature is for legally obtained, supported game content; it cannot guarantee all titles can be converted.

## Verification
307 Python unittest tests passed (303 previous + 4 new local-builder cases). Compilation and ZIP integrity verified. Live PySide6, Inno Setup, Retail2Pkg execution, and PS3 installation unverified. Existing sqlite ResourceWarnings remain.
