# Z's Save Archive — Expanded Roadmap (v2.7)

Selected features are recorded here in phased releases. **Planned is not implemented.** An existing partial capability is never described as a new fully tested feature.

## v2.7 — Safe PS3 diagnostics and conversion preflight (this release)

**New and implemented:**
- User-triggered, bounded automatic PS3 *candidate* discovery on LAN (private IPv4, max 32 addresses, TCP/21 checks; no claim of PS3 identity)
- Read-only FTP TCP reachability diagnostics with response time and human-readable errors
- Read-only FTP SYST/STAT reporting API (may not be supported by PS3 FTP server)
- Privacy-filtered JSON console diagnostics report
- Automatic ISO9660 signature identification (existing inspector, preflight integrated)
- Source-type identification for ISO versus extracted `PS3_GAME`
- Conservative ISO work-directory space estimator (not a guarantee)
- CFW2OFW Helper presence validation
- 7-Zip dependency validation for ISO input
- Optional TrueAncestor tool presence check (not version-detection)
- Work-folder collision/source separation checks
- Converted-output inspection (existing v2.1, preserved)
- PKG signature and filename-derived title-ID *hint* (not decrypted metadata)
- Transfer-rate and ETA helper for completed samples when total bytes are known (not integrated into live FTP UI)
- New PS3 LAN Diagnostics dialog, plus ISO Conversion Preflight dialog in existing grouped Tools menu
- All existing v2.6 converter controls, icons, Windows build scripts, Inno Setup, FTP, save archives and homebrew tooling retained

**Already present (partial or established from older versions):**
- PS3 user-profile browser and profile backup; PS3 Console Center
- Homebrew installed-version *manual* inventory and update watchlist
- Basic batch PKG validation and header inspection
- Homebrew offline catalog, release links for selected projects
- CFW2OFW staging, TrueAncestor handoff, output inspection, file preservation
- PS3/PC archive, saved-game profiles, categories/tags, history, backups
- Multiple Steam libraries, Epic/GOG candidate discovery, Steam Cloud warnings
- GitHub draft publisher, website catalog, release safeguards
- Command palette, paged search, background task journal, compact UI settings

**Important constraints:**
- Generic FTP doesn't reliably report free PS3 HDD space, fan RPM, temperatures, CFW version, uptime, installed games or packages. These are not implemented or guessed.
- PS3 discovery identifies open FTP endpoints only, not confirmed PS3 hardware.
- ISO9660 does not prove a disc ISO is decrypted or convertable. Real conversion still requires separately installed tools and game compatibility tests.
- No real Borderlands 2 editor until real decrypted save samples are supplied and parser + checksum handling are validated.

## v2.8 — Console data and transfer reliability

**Planned:** firmware and CFW information via *supported, explicitly enabled* APIs; free/used HDD storage graph only from verified data; console temperature monitoring; fan-speed monitoring; uptime; network transfer speed history; installed game inventory; installed homebrew inventory; installed package version matching; PS3 system information export; console diagnostic reports; connection-loss notifications; work with the already-present user-profile browser; FTP upload resume where server supports REST; upload bandwidth limiter; reliable upload ETA; transfer speed graph. Never infer telemetry from FTP banners or guessed offsets. Add simulated server integration tests.

## v2.9 — ISO/PKG pipeline and curated homebrew library

**Planned:** encrypted ISO detection beyond basic format signatures; disc-key availability checker for user-provided legitimate keys; automatic converter dependency check refinements; actual TrueAncestor version detection; TrueAncestor packaging presets after version-specific validation; converted-game output validator; multi-stage conversion progress; ISO batch conversion queue; 100+ manually verified homebrew entries (not fabricated); official release download links; installed-version comparison; changelog comparison; screenshots/icons with licensed sources; CFW/HEN compatibility filters; offline homebrew library improvements; download queue priorities; advanced PKG metadata parser; trustworthy PKG title-ID detection; package type identification; batch PKG validation improvements; drag-and-drop package importing. Preserve original sources and require explicit approval for external tool execution.

## v3.0 — Save editor and game compatibility

**Planned:** Borderlands 2 character parser, money, Eridium, XP, skill points, inventory and weapon viewers; Borderlands 1 editor plugin; Diablo III placeholder upgrade; Resident Evil 5, GTA V story, Skyrim, Dead Space 3 and Gran Turismo 5 editor plugins; automatic game-editor matching; format-version detection; before/after field comparison; game-specific validation; internal checksum handlers; documented save-editor plugin SDK. Implement as separate validated game adapters with mandatory pre-edit backups. Proprietary parsers depend on actual user-provided decrypted saves; placeholders must stay disabled.

## v3.1 — Library, PC discovery and resilient backups

**Planned/improve existing:** game title ID auto-matching; multi-character save profiles; custom tag presets; colored tag groups; advanced bulk metadata editing; save notes and descriptions; save favorites and pinning; status workflows; archived save comparison; expanded Steam game database; multiple Steam library scanning; Steam userdata identification; Steam Cloud conflict warnings; Epic installation detection; Epic save-folder definitions; GOG Galaxy detection; Xbox PC paths; EA app, Ubisoft Connect and Battle.net discovery; portable game profiles; multiple Windows user profiles; multi-drive scanning; path relocation detection; missing-installation warnings; real-time save folder monitoring; automatic change-triggered backups; per-game backup rules; backup compression presets; optional encrypted backups (authenticated encryption and key recovery); external drive mirroring. Distinguish known save paths from installation-only guesses.

## v3.2 — Sharing and large-scale desktop UX

**Planned/improve existing:** full GitHub Release Publisher; draft release management; metadata sanitization previews; shareable download pages; searchable GitHub Pages catalog; cover art on website; website themes; complete sidebar redesign; reduce Tools menu clutter; contextual navigation; unified global search; Ctrl+K command palette; high-performance game grid; virtualized save table; customizable dashboard widgets; unified background task queue; transfer notification center; high-DPI scaling; screen-reader accessibility; Windows taskbar progress; system tray minimization; toast notifications; Inno Setup hardening; automated Windows GUI smoke tests.

## Release discipline

- Preserve PS3 and PC archive formats, category values (`Legit`, `Modded`, `Unsorted`), and user data under the separate archive path.
- Never silently overwrite source game data, remote console files, backup files or public GitHub releases.
- Add regression tests alongside actual implemented code, and clearly distinguish mocked tests, native Windows/UI tests, live PS3 tests and game-save compatibility.
- A release does not need to hit an arbitrary item count when doing so undermines reliability.

## v2.8 — Safeguarded workflow tools

Implemented in v2.8:
- Read-only PKG metadata comparisons, SHA-256 duplicate identification, and batch report.
- Conservative firmware compatibility matrix/advisory: unknown compatibility remains unknown.
- Steam/launcher cloud restore preview with existing-destination warning (does not inspect actual cloud state).
- Opt-in session-only Windows process-exit monitor invoking existing per-game backup rules; no full background service.
- Transfer ETA and confidence range estimator backend for known remaining byte counts, tested with synthetic samples; **not** yet integrated with live FTP taskbar progress.
- Reusable inventory name filtering helper for future Borderlands 2 inventory screens.
- Grouped Tools menu entry points for PKG checks and game-exit backups.

Planned / blocked:
- **Borderlands 2 actual character editing, inventory parsing/search, currency/XP/Eridium/skills**: requires real Apollo-decrypted save samples and format-specific checksum/codec validation. The existing game-target placeholder remains disabled.
- Detailed PS3 firmware matrix tied to particular homebrew/PKG revisions needs verified compatibility evidence, not inferred from firmware strings.
- Read-only PS3 storage explorer with measured free/used capacity: requires validated FTP/console hardware responses.
- Real transfer ETA and Windows taskbar progress: requires connecting the estimator to a transfer size/progress source; ETA unknown when remote total unknown.
- PS3 PKG installation records currently remain manually reported; remote installed-package inventory is not verified.
- True always-on game-exit backups would require a separate configured Windows service/scheduler; v2.8 monitors only during the open dialog.
- Windows UI, CFW hardware interoperability, and live package installations require native Windows/PS3 validation.

## v3.0 — Simplified Navigation (implemented source / Windows GUI unverified)
- Hide duplicate Tools dropdown and nested classic sidebar; retain underlying QAction callbacks
- Merge Saves & Backups and Homebrew / PKG / ISO into PS3 Tools
- Move GitHub publishing under Releases; relocate organization to Game Library
- Hide advanced/experimental features behind explicit show-advanced toggle
- Preserve v2.9 FTP decoding fixes and Build_All.bat pipeline


## v3.1 Retail2Pkg integration
Implemented: extracted toolkit folder selection, CFW2OFW helper auto-selection, validation, independent handoff staging, and tests. Planned: live Windows integration and PKG build verification.


## v3.2 — Local PKG generation (implemented; Windows execution unverified)
- Local output picker and standalone PKG build button; no FTP dependency.
- Isolated Retail2Pkg staging folder; originals preserved; no output overwrites.
- Detect and copy PKGs with signature checks; report unsuccessful builds truthfully.
- Remaining: test actual third-party batch and generated PKGs on Windows; improve live build progress and cancellation.

## v3.5 — Starter tags and save origin (implemented)
- Add a suggested-tags picker while preserving custom tags and categories Legit / Modded / Unsorted.
- Add optional per-save provenance: origin type, source/creator, source URL, notes.
- Migrate existing SQLite archives with optional fields; include provenance in backups.
- Future: privacy controls and source links in user-reviewed public exports; bulk origin editing.

## v3.6 — Reusable Conversion Workspace (implemented)
The PS3 ISO conversion assistant remembers a reusable workspace parent folder and automatically chooses a unique game-named, timestamped staging subfolder for each run. Previous workspaces are protected and never overwritten or deleted automatically. Includes five workspace regression tests.
