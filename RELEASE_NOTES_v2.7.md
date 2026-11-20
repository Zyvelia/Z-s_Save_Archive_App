# v2.7 — Conservative PS3 Diagnostics and Conversion Preflight

## How to use

Run `Start_Archive.bat`. In the grouped **Tools** menu, open:

- **PS3 & Connections → PS3 LAN Diagnostics (read-only)**. Enter your private LAN PS3 IP to test FTP reachability, or supply a small private CIDR such as `192.168.1.0/27` to scan 30 possible endpoints. This is opt-in and checks only FTP port 21. An open port does not prove a console is a PS3. Save a privacy-filtered JSON report if needed.
- **Homebrew, ISO & Packages → ISO Conversion Preflight**. Select your existing game ISO or extracted PS3_GAME folder, `CFW2OFW Helper.exe`, `7z.exe` for ISOs, optional TrueAncestor executable, and a *new* work directory. Run preflight before starting the existing **PS3 ISO → XMB Assistant** conversion.

The ISO preflight reports hard errors separately from warnings. An ISO9660 signature cannot reveal whether disc sectors are encrypted; extraction or game-specific processing may still fail.

## Existing features retained

All v2.6 features, including full PS3 and PC save archive, versioned ZIP backups, safe local restore, homebrew catalog/downloads, ISO/XMB conversion helper, TrueAncestor staging, FTP tools, GitHub publishing, app PNG/ICO, Windows PyInstaller build and Inno Setup scripts, are copied from the verified v2.6 source tree. No archive database migration was introduced.

## Testing limits

`python -m unittest discover -s tests -q` includes inherited regression tests and v2.7 unit tests. FTP and LAN behavior uses socket fakes, not a real PS3. The new dialogs have not been rendered on Windows because PySide6 is unavailable in this environment. No ISO conversion or PKG install was attempted.

## Safety

All new diagnostics are read-only, initiated only by user clicks, and restricted to private IPv4. The discovery scan is limited to 32 targets, and public internet ranges are refused. No credentials or sensitive FTP banners are included in generated diagnostics reports.
