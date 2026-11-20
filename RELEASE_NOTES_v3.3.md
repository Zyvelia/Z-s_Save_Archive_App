# v3.3 — Converter Progress, 7-Zip Detection, Saved Paths

Built from the complete v3.2 source. All existing PS3/PC save handling, FTP encoding workaround, editor framework, Homebrew/ISO/PKG tools, GitHub, violet icon, and one-click Windows/Inno build files are retained.

## Changes
- ISO conversion assistant auto-finds 7z.exe from `Z_ARCHIVE_7ZIP`, Program Files (both architectures), LocalAppData, PATH, and 7-Zip registry keys (when running on Windows). `Auto-find` button and manual Browse fallback are available.
- The ISO staging worker emits status updates for checking input, workspace creation, tool-copy, 7-Zip ISO extraction, PS3_GAME validation/movement or copy, and manifest creation.
- Conversion dialog shows an indeterminate animated progress bar, elapsed time and live text log while staging or the external helper runs. Indeterminate progress is intentional: this workflow does not yet have reliable byte-accurate progress or ETA.
- CFW2OFW helper output is appended live via QProcess, decoded with replacement for invalid UTF-8 bytes; exit code is shown but does not prove game compatibility.
- Source path, helper EXE path, 7z.exe path, and staging workspace path are automatically saved and restored via Windows-user QSettings (ZsSaveArchive / ZSaveArchive). No passwords stored.
- Existing stage-copy and external-helper confirmation safeguards remain.

## Tests and limitations
- `python -m unittest discover -s tests -q`: 311 passed (307 inherited, four new).
- Python compile and ZIP integrity verified in this build environment.
- Live Windows PySide6 rendering, actual ISO extraction/conversion and PlayStation 3 installation have not been tested here.
- A staging workspace must be new each time; do not reuse an already-created workspace path. Change the work directory before a new job.
- An animated progress bar means the worker is active; it is not a statement of percentage complete.
