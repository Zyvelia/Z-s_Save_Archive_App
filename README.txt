Z's Save Archive
================

A Windows desktop app for organizing, backing up, and inspecting PS3 and PC
saves. It also includes PS3 FTP tools, a homebrew catalog, and GitHub publishing.

Get started
-----------

1. Download and extract the latest desktop source ZIP:
   https://github.com/Zyvelia/Z-s_Save_Archive_App/tree/main/downloads
2. Install Python 3 on Windows 10 or 11, then run Start_Archive.bat.
   To run manually, install requirements.txt and run python main.py.
3. Use Game Library and Saves & Backups to organize saves. Use PS3 Console
   to connect to a PS3 on your LAN. The save editor supports specific
   formats and schemas. Check its format support before editing.

Archive data defaults to Documents\Z PlayStation Save Archive. Z_ARCHIVE_HOME
can override that path. A portable.flag beside the executable selects local
ArchiveData. The per-user Windows installer stores app files separately and
leaves the archive in place when uninstalled.

Update and build
----------------

Close the app, then run Update_Archive.bat from the extracted source folder.
It verifies the source ZIP against SHA-256 and backs up changed files in
.update-backups. It leaves local files that are absent from the new ZIP in
place. Extract a fresh source ZIP if you want a clean project folder. In a
Git checkout, use git pull.

On Windows, run Build_All.bat with Inno Setup 6 installed. Build_Windows.bat
creates dist\ZSaveArchive\ZSaveArchive.exe. Build_Installer.bat creates the
installer under installer_output. If Inno Setup detection fails, set ISCC_EXE
to the full path of ISCC.exe in Command Prompt and run Build_All.bat again.

Run python -m unittest discover -s tests -q to check the source.

PS3 tools
---------

- Retail2Pkg ISO Launcher v3. In PS3 Tools, select the launcher ZIP and click
  Open Retail2Pkg launcher. Its Windows dialogs ask for the ISO and output
  folder. It mounts the ISO read-only, stages PS3_GAME, and opens the package
  folder after a successful build. Some games require an online update.
- ISO to XMB Assistant. Choose CFW2OFW Helper and a workspace parent, then
  select a readable PS3 ISO or an extracted PS3_GAME. Each run gets its own
  folder. Use Workspace history to inspect earlier runs or copy a
  troubleshooting report with paths hidden.
- PKG Inspect and Upload. Inspect an existing package or upload it over FTP.
  The tool checks the remote file size before publishing the filename. Install
  packages on the PS3 through Game > Package Manager.
- Live Temperatures. On the same LAN, open PS3 Console > Live Temperatures
  and enter the IP of a PS3 running webMAN MOD with its web server enabled.

Standalone PS3 homebrew
-----------------------

Download PS3_Stats.pkg and Controller_Tester.pkg from the downloads folder.
Copy the desired PKG to a FAT32 USB drive and install it from Game >
Package Manager > Install Package Files on a compatible CFW console.

- PS3 Stats shows CELL and RSX temperatures after pressing Cross. Press
  Square for a one-time internal storage check or Circle to exit. If startup
  fails, the last line in /dev_hdd0/game/ZSTATS001/USRDIR/startup.log shows
  the last step reached.
- Controller Tester shows stick coordinates, button states, and trigger
  pressure where supported. Press Select and leave the sticks idle for
  three seconds to check drift. Hold Start for one second to exit.

To build either homebrew app, install PS3DEV and PSL1GHT and set PS3DEV and
PSL1GHT to their installation paths. From the repository root, run
make -C ps3-stats or make -C ps3-controller-tester. Use the corresponding
.gnpdrm.pkg from the build for CFW installation.

GitHub Manager
--------------

Open Releases > GitHub Manager. Install Git and GitHub CLI, then use Sign in
and Check sign-in. The manager can publish source or snapshots, save a local
repository bundle, and upload a selected backup ZIP to a private draft
release. Bundles preserve Git branches and tags. Issues, pull requests,
and release assets are stored separately.
