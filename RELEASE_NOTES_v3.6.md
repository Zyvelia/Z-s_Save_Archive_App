# v3.6 — Reusable conversion workspace

Fixes the PS3 ISO → XMB Assistant's repeated "Choose a new, empty workspace path" error.

- The work-folder field now represents a **reusable parent directory**, not a one-time staging directory.
- Clicking Stage only / Stage & Convert proposes a **new timestamped, game-named subdirectory** beneath the saved parent on each attempt; collision suffixes prevent overwrites.
- Existing converter workspaces and failed partial workspaces remain untouched. No automatic deletion occurs.
- The selected parent is remembered through the existing v3.4 AppData path preferences.
- The confirmation dialog and log show the exact new workspace for the run.
- The low-level conversion staging function still refuses to overwrite an existing destination.
- New tests cover reuse of existing parents, collisions, no premature directory creation, invalid parent types, and protection of existing directories.

Keep the parent folder selected after upgrading. The first run creates a child folder under it; later runs create additional child folders. Clean up old staging folders manually after verifying the outputs you need.

Run tests: `python -m unittest discover -s tests -q` from the extracted project folder.
