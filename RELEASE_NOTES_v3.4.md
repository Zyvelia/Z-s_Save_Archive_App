# v3.4 AppData Storage

- Introduced `%APPDATA%\ZSaveArchive` for JSON path preferences and user presets.
- Introduced `%LOCALAPPDATA%\ZSaveArchive` for generated caches, logs, temporary metadata and crash reports.
- Converted ISO assistant path persistence to JSON settings, with fallback reading previous QSettings/registry values.
- Settings > AppData Storage Manager displays cache usage, opens directories, clears generated cache, and changes archive root for the *next* launch.
- Archive data continues to default to the existing Documents folder unless changed, overridden by Z_ARCHIVE_HOME, or portable.flag. The app **does not move old archive data automatically**.
- ISO and PKG files, full save backups and staging workspaces are kept in explicitly selected folders outside AppData.
- Old legacy JSON preference files can be imported through the backend `AppPaths.import_legacy_json` method, but no destructive migrations occur.
- FTP passwords are not written by the new AppData settings module. Existing credential handling was not redesigned; Windows Credential Manager/DPAPI integration remains future work.
- Installation of Windows PyInstaller/Inno and real PS3 workflows not validated in this environment.
