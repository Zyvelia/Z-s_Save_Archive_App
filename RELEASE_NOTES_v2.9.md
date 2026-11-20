# v2.9 — Neon Dashboard Preview (review build)

Built on **the complete v2.8 source**. This release prioritizes comparing the app's new navigation and dashboard with the provided mockup; it does not claim the UI is pixel-identical.

## Implemented

- New charcoal/violet PySide6 landing page with persistent navigation and separate panels for archive counts, PC saves, PS3 saves, backups, recent saves, library, PS3 tools, and quick actions.
- Live archive reads for save totals, game list, game filtering, and recent save entries. No invented sample saves, disk space, PS3 connection, or health metrics.
- Game selection and recent-save selection open the existing working archive interface.
- Legacy interface and all preexisting tools kept available as the **classic workspace**, including the v2.8 grouped Tools menus.
- Sidebar entry points to current backup history, PS3 FTP tools, Editor, Homebrew, releases (through existing grouped Tools), and Settings.
- Replaced the application icon assets with the selected neon violet Z archive icon; original logo retained in `ZSaveArchive_Original.png`.
- Packaged the supplied dashboard mockup as `assets/Dashboard_Design_Reference.png` for design comparison, not as a fake interactive window.
- Existing PyInstaller/Inno Setup build scripts remain included and point to the updated app entry point and icon.

## Still to refine

- A pixel-perfect implementation of the concept screenshot, compact adaptive grids, artwork downloaded with permission, and responsive breakpoints.
- Native live console connection/storage indicator (no unsupported or fabricated values shown).
- Dedicated Releases pane and integrated one-click backup from dashboard without entering the full workspace.
- Native PySide6 run/screenshot on Windows, plus live FTP, release, build and installer validation.

## Testing

- All 285 inherited tests pass on Linux with Python.
- Five source/package/image regression tests added; PySide6 is unavailable in the current runner, so GUI visual tests are not claimed.
- `compileall` passes. ZIP integrity checked after packaging.
