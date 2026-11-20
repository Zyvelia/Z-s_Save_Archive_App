# Z's Save Archive v2.4 — Homebrew Inventory & Package Inspection

Built directly on complete v2.3 source, preserving the PS3/PC save library, backup versioning, FTP support, ISO-to-XMB external converter assistant, GitHub publishing, and the universal save-editor framework. Windows-only PySide6 desktop source.

## New in v2.4 (implemented)
- **Homebrew installed-version inventory**: record an installed version *manually*, favorites, and watchlist preferences for the curated homebrew catalog. Local JSON atomic file: `<archive-home>/homebrew/installed_inventory.json`. The app does **not** claim to scan installed apps remotely.
- **GitHub release notes**: published GitHub release descriptions can be reviewed in the homebrew manager. The displayed comparison between an entered version and a published tag is text-based, **not** a firmware-compatibility assessment.
- **Offline catalog snapshot**: locally stored catalog at `<archive-home>/homebrew/offline_catalog.json`, with bundled fallback. Does not mirror executable files.
- **Batch read-only PKG inspector**: validate selected `.pkg` files, inspect a few common PKG header fields, compute SHA-256, flag size mismatch, and report errors individually. PKG inspection does not certify package origin, cryptographic signatures, compatibility, or malicious code.
- **Local staging space estimator API**: checks disk space for local staging only; PS3 storage capacity remains *unknown* without a trusted remote check.
- **Installation checklist**: displays manual steps to review source, verify package, approve transfer, install with Package Manager, and record installed version.
- **Optional bandwidth limit**: homebrew HTTPS PKG downloads can be capped in KiB/s (0 = unlimited), cancellable during throttling. This does not throttle FTP uploads or implement resumable range downloads.
- **v2.4 Homebrew Manager UI**: Installed & Watchlist tab, PKG Inspector tab, offline catalog refresh, release notes, download limit entry. Existing catalog, release lookup, queue, upload, and history tabs remain.

## Not implemented (all in ROADMAP.md)
There is no live PS3 installed-app scanning, console capacity or temperature dashboard, firmware/CFW capability detection, automatic install or PS3 write access beyond already-approved FTP uploads; no partial resume for homebrew HTTPS downloads; no encrypted private vault; no actual Borderlands 2 PS3 parser/editor until tested decrypted user samples; no Windows-native GUI smoke-test certification. See roadmap for all 26 requested features.

## Install and migration
1. Back up `<Documents>/Z PlayStation Save Archive` (or the folder defined in `Z_ARCHIVE_HOME`).
2. Extract to a new folder and run `Start_Archive.bat` on Windows.
3. Open **Tools → PS3 Homebrew Manager**, then **Installed & Watchlist**, **PKG Inspector**, or **Find Releases**.
4. Installed versions are typed by you; don't rely on them as verified console state.

New data lives in separate homebrew JSON files. There are no deliberate changes to the existing saves, archive database, backup ZIPs, or PS3 FTP overwrite policy. The script never installs packages to your PS3.

## Testing
From project root: `python -m unittest discover -s tests -q` and `python -m compileall -q .`.

**238 automated tests passed** (223 inherited + 15 new) on the current Linux test environment. ZIP CRC/integrity is verified on packaging. Actual PySide6 UI on Windows, live GitHub release downloads, CFW PS3 FTP, installed packages, firmware, and Borderlands 2 edits are **not tested** on physical hardware here.


## Windows build and organized Tools menu

Run `Build_Windows.bat` to create a PyInstaller one-folder EXE. Then run `Build_Installer.bat` with Inno Setup 6 installed to create a per-user installer. Read `BUILDING.md` for details. Tools are now grouped into categorized submenus, with a Find tool action at the top.

## TrueAncestor handoff update (v2.5 integration)
The existing **PS3 Package Builder & FTP Transfer** dialog now has **Prepare TrueAncestor handoff**. After CFW2OFW succeeds, choose a new destination folder. The app copies only detected converted game folders to `TrueAncestor_Handoff/game/`, writes a manifest and instructions, and never modifies the ISO. It intentionally does **not** bundle or run TrueAncestor; supported input layout and packaging commands vary by edition. Use **TrueAncestor PKG Repacker** for eligible installable packages, not **TrueAncestor BACKUP Retailer**, which serves backup injection. Once you've generated a valid `.pkg`, copy it into the conversion workspace for the existing PKG inspection/upload workflow. No game compatibility guarantee.

References: https://consolemods.org/wiki/PS3:CFW2OFW_Helper and https://consolemods.org/wiki/PS3:TrueAncestor . The original CFW2OFW Helper repository is archived and describes itself as obsolete.


### Integrated app icon
The generated violet Z archive logo is now included under `assets/` and connected to the PySide6 main window, PyInstaller EXE, and Inno Setup installer. No save/archive data files were changed.


## v2.6 converter button and homebrew catalog fix
- **Stage & Convert** stages a safe copy and (after confirmation) runs CFW2OFW Helper. The old **Run staged converter** button stays disabled until staging succeeds, by design.
- Status line explains current step and failures. Encrypted PS3 disc ISOs are not automatically decrypted by 7-Zip. Use an extractable backup or already extracted `PS3_GAME`. After a staging failure, use a **new** working directory.
- Homebrew catalog expanded from 6 to 20 entries with more categories and official/reference links. Automatic release lookup is enabled only for supported GitHub project repositories; other entries are reference links.
- No automatic PS3 installation, ISO decryption, or game-compatibility guarantee.

---

## v2.7 additions

This source release extends v2.6 with **PS3 LAN Diagnostics** and **ISO Conversion Preflight** (both under the categorized Tools menu). See `RELEASE_NOTES_v2.7.md` and `ROADMAP.md` for instructions and complete planned-versus-implemented status. All previous tools and archive formats are preserved. These two new dialogs require a real Windows/PySide6 smoke test before treating the build as a stable native Windows release.

### v2.8 additions
Use **Tools → Homebrew, ISO & Packages → PKG Comparison & Compatibility** to compare local PKGs by SHA-256 or review advisory compatibility/restore warnings. Use **Tools → PC Discovery & Backups → Backup After Game Exit (opt-in)** to monitor a specified executable during an open session and trigger existing enabled backup rules after the process exits. The app never launches or terminates games and never automatically installs PKGs.

Editor integration remains format-gated: Borderlands 2 is currently a placeholder, not a functioning money/XP/inventory editor. See ROADMAP.md for explicit statuses.

## v2.9 design-preview release

The default entry point opens the new neon Z Save Archive dashboard (`zarchive/ui_v29.py`). The sidebar switches between the redesign and the existing full workspace: prior v2.8 capabilities and data remain intact. The dashboard uses actual local archive data and deliberately does not simulate console connections, game artwork, or backups. The mockup is included as a visual reference in `assets/Dashboard_Design_Reference.png`.

To run: `python main.py` (install `requirements.txt` first). To build on Windows use `Build_Windows.bat`, then optionally `Build_Installer.bat`. The new dashboard is a preview to review for additions/removals, not yet a pixel-identical reproduction. See `RELEASE_NOTES_v2.9.md`.

## v3.0 navigation consolidation

The main sidebar now uses Dashboard, Game Library, Saves & Backups, PS3 Console, Save Editor, PS3 Tools, Releases, and Settings. The Tools dropdown and duplicate classic sidebar are hidden. Existing actions retain their callbacks and live under the relevant section. Find library organization actions under Game Library → Organize, and less frequently needed/experimental options under each section’s advanced toggle. Existing source, FTP encoding fix, and one-click build are preserved. See `RELEASE_NOTES_v3.0.md`. Run `Build_All.bat` to create the v3.0 EXE and Inno installer on Windows.


## v3.1 Retail2Pkg folder integration
See `RELEASE_NOTES_v3.1.md` for safe tool-folder selection and separate PKG handoff instructions.


## v3.2 Local PKG Builder (no FTP required)
Open **PS3 Tools → PS3 PKG Builder (Local / FTP)**. Choose a completed conversion workspace, your extracted Retail2Pkg tools directory, and a separate output folder. Click **Build PKGs Locally (No FTP)** and confirm running the third-party batch in an isolated staging copy. Finished PKGs with a recognizable header are copied to the output directory; they are not installed on the console. See `RELEASE_NOTES_v3.2.md`. `Build_All.bat` still builds the Windows EXE followed by the Inno installer.


### Run Retail2Pkg with disc input

In **PS3 ISO → XMB Assistant**, choose a disc ISO or PS3_GAME folder and use **Retail2Pkg Folder…** to select the toolkit containing your working `Retail2Pkg.bat`. Click **Build PKG from disc input…**, choose an output folder, and click **Build PKGs with Retail2Pkg.bat**. The batch handles conversion and packaging on a copy. Follow any prompts in its Windows console, including its final key prompt. Finished PKGs are copied to the chosen output folder. To run the batch by hand from the general PKG builder, click **Prepare batch folder** and then **Open batch folder**. Run the staged batch beside the extracted `PS3_GAME` folder. For ISO input, choose `7z.exe` in the builder if it cannot find 7-Zip automatically.

### If conversion leaves a BLUS or NPUB folder

The ISO → XMB Assistant runs CFW2OFW Helper and puts its results into a workspace. Open that workspace in **Inspect output / Build PKG / Upload to PS3** to see what was produced. Retail2Pkg needs a converted NP title folder and its matching disc-ID patch folder. If only one is present, check the helper's output and the requirements for that title before running the PKG builder. Select the workspace containing `conversion_manifest.json` and choose a separate folder for the finished PKGs.


## v3.5 — Starter tags and save provenance
The save inspector includes a **Choose Starter Tags** dialog (suggested options, without forcing them onto existing records). Custom tags and the existing three save categories remain unchanged. Each archived save may also have user-entered origin type, source/creator, optional HTTP(S) URL, and notes. Existing archives migrate by adding optional columns, without altering save files. Provenance is unverified user-supplied metadata. ZIP backups include origin metadata; public site export does not expose it.

### Reusing PS3 conversion workspace folders (v3.6)
In **PS3 Tools → PS3 ISO → XMB Assistant**, choose your workspace **parent** folder once. The assistant will create a uniquely named work folder underneath it for each new stage/conversion. Existing conversions are never overwritten or automatically deleted; old incomplete runs can be reviewed and cleaned up manually.

### Conversion workspace history (v3.6.1)

In the PS3 ISO → XMB Conversion Assistant, choose **Workspace history…** to reopen a run under the selected workspace parent. The list shows its game, date, size, and recorded status. Open the run folder, inspect its output, or open the PKG builder for that specific run.

The assistant checks available space before copying. If the drive has less space than the conservative estimate, it asks whether to continue. **Cancel staging** stops copying or 7-Zip extraction and retains any partial workspace for review. A converter exit status records what the process reported. Use **Inspect output** to check which files it produced.

Run `Build_All.bat` for the Windows EXE and installer. The installer filename uses the version in `ZSaveArchive.iss`.

### Troubleshooting reports and PKG upload progress (v3.6.2)

**Copy troubleshooting report** in the PS3 ISO → XMB Conversion Assistant copies the current or failed step, any converter exit code, and recent log lines. **Hide paths in report** starts enabled and omits log lines containing possible paths. Review the report before sharing it.

The PS3 PKG Builder shows upload percentage, recent throughput and ETA once enough data is available. It checks the uploaded size before finalizing the package. If the server refuses the size check or reports a mismatch, the upload fails without publishing the final filename.

### PS3 Stats homebrew

The standalone XMB app shows CELL and RSX temperatures when enabled. Version 1.3 checks free internal storage when you press Square. See [PS3 Stats](ps3-stats/README.md) for build, installation, and hardware verification instructions.

Download the [Save Archive v3.6.8 desktop source ZIP](downloads/Z_Save_Archive_v3.6.8_Source.zip). The [downloads folder](downloads/) also contains the PS3 homebrew packages and SHA-256 checksums.

### Update the Windows source folder

Close Save Archive and double-click **Update_Archive.bat** in the source folder. The updater downloads the desktop ZIP listed in `downloads/SHA256SUMS.txt`, checks its SHA-256, and updates the source in place. It leaves archive data and local settings alone. Previous copies of changed source files go into `.update-backups`.

For an older source ZIP, download [update_archive.py](update_archive.py) once, put it next to `main.py`, and run `py -3 update_archive.py` from that directory. The update installs the batch launcher. If you cloned the repository with Git, use `git pull`. For a packaged Windows EXE, rebuild it after updating the source.

When publishing a desktop update, use a fresh versioned source ZIP and update its single desktop entry in `downloads/SHA256SUMS.txt` in the same commit. Keep `update_archive.py` and `Update_Archive.bat` in the ZIP.

### View PS3 temperatures on your PC

On the same LAN as a PS3 running webMAN MOD with its web server available, open **PS3 Console → Live Temperatures**. Enter the PS3’s IP address and choose **Start monitoring**. The app reads CELL and RSX temperatures from webMAN MOD every five seconds until you stop or close the window. The console’s Temperature Information menu and the PS3 Stats PKG can stay closed.

### Controller Tester homebrew

The [Controller Tester](ps3-controller-tester/) shows live stick coordinates, button presses, trigger pressure where supported, and a three-second drift check. [Download the PS3 package](downloads/Controller_Tester.pkg).
