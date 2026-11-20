# v3.0 Navigation Consolidation

- Removed the visible Tools dropdown and hid the duplicate classic workspace sidebar.
- Replaced separate Saves and Backups sidebar items with Saves & Backups.
- Consolidated Homebrew / PKG / ISO under PS3 Tools (including direct Homebrew manager access).
- Moved GitHub publishing and release actions into Releases.
- Kept a dedicated Save Editor, PS3 Console FTP, and Game Library.
- Relocated library organization actions behind **Game Library → Organize**.
- Grouped existing legacy tool actions by function, preserving their original QAction callbacks.
- Advanced / experimental options are hidden behind an explicit checkbox, not deleted.
- Preserved entire original backend, FTP Latin-1 encoding fix, installer, icons, and build scripts.

## Limitations
This release changes navigation, not underlying feature readiness. Legacy experimental functionality has not been made production-ready. Windows GUI and PS3 live FTP must be validated on user hardware.
