Z's Save Archive
================

A Windows desktop app for organizing, backing up, and inspecting PS3 and PC
saves, plus PS4 save archiving. It also includes PS3 FTP tools, a homebrew catalog, and GitHub publishing.

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
Starting with v3.6.28, the updater downloads the current GitHub main commit,
replaces modified app code, and removes obsolete files from app code folders.
Replaced and removed files are backed up under .update-backups. Saves, settings,
portable data, and custom editor definitions are preserved.

If you're on an older source build, run Update_Archive.bat once to install the
v3.6.28 bootstrap, then run it again to sync to main. For a Git checkout, manage
local changes and updates through Git.

On Windows, run Build_All.bat with Inno Setup 6 installed. Build_Windows.bat
creates dist\ZSaveArchive\ZSaveArchive.exe. Build_Installer.bat creates the
installer under installer_output. If Inno Setup detection fails, set ISCC_EXE
to the full path of ISCC.exe in Command Prompt and run Build_All.bat again.

Run python -m unittest discover -s tests -q to check the source.

PC save discovery
-----------------

Open Saves & Backups > Discover and import PC saves. The scan matches
known save locations and Steam Cloud cache folders to game names. Choose
a storefront to narrow the scan. Review the checked folders and click
Import selected saves to copy them into the archive. Re-running the scan
skips identical saves already archived.

Removing archived saves
-----------------------

Open Saves & Backups > Browse Saves, select one save or use Ctrl/Shift to select
several, then choose Remove from Archive in the inspector or right-click menu.
Removed saves disappear from the library and keep their files, metadata,
screenshots and versioned backups. In Saves & Backups > Recently Removed,
select entries and choose Restore selected to put them back. Entries stay
there until restored or permanently deleted. Permanent deletion removes the
archived copies and entries. Original saves and existing backup ZIPs stay on
disk. Versioned ZIPs for permanently deleted entries remain in the archive's
backups folder. Saves permanently deleted by an older version cannot be
restored through Recently Removed.

PS4 saves
---------

Choose Saves & Backups > Import PS4 Save to archive a local PS4 file or
folder, for example a USB export or files already downloaded to your PC.
PS4 imports are tagged PS4 and retain a CUSA title ID when present in the
source path. Use the PS4 filter in the dashboard or library. In Settings,
enable Hide PS3 tools and dashboard shortcuts for a PS4-focused layout.

Borderlands saves
----------------

In Save Editor, open Borderlands Save Editor. Choose the game and platform,
select an archived save or a decrypted export, and prepare a working copy.
Configure the corresponding Windows editor using the linked project. Use
its character and weapon controls to edit the working copy, then archive
the edited copy as a new entry. The available fields depend on the editor.
PS3 support covers Borderlands, Borderlands 2 and The Pre-Sequel. The PS4
choices are Borderlands 3 and Tiny Tina's Wonderlands.

PS4 dump to FPKG
----------------

On Windows, open Dump to FPKG Builder and select your local
orbis-pub-cmd.exe, the folder containing decrypted PS4 dumps, and an
output folder. Scan to see the available base games, patches, and add-ons
grouped by CUSA title ID and their matching archived save counts. Select
the packages to build. For patches, select the matching base dump, or leave
it unchecked and choose a previously built package in Existing base PKG.

Scan dumps finds matching GP4 projects in each dump folder or its immediate
parent within the selected input folder. The GP4 column shows which project
each row will use. Check any number of games or patches and click Build selected.
The app generates a GP4 if there is no unambiguous match. Use GP4 override to
pick a different existing project for one selected dump. The app resolves source
files from the dump and leaves the original project in place.

Before building, the app checks for a usable base-game eboot.bin and warns
if a requested keystone is missing. It checks the structure and identity of
each output package before saving it. Completed packages are grouped by game.

PS3 tools
---------

- Retail2Pkg ISO Launcher v3. Open it under PS3 Tools. Save Archive bundles
  the toolkit. Choose a PS3 disc ISO or PS3_GAME folder, then select an
  output folder and start the build. Windows mounts ISO input read-only.
  The builder copies PS3_GAME into a fresh work folder. The in-app
  log shows conversion and patch downloads. Open output folder shows the
  resulting packages. Some games require an online update.
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
