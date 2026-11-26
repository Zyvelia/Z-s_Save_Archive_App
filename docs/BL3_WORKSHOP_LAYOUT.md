# Borderlands 3 Workspace — Workshop Design

The Borderlands 3 editor now uses a larger charcoal/violet/yellow workspace
inside **Universal Save Editor → Borderlands 3 → Console: PC or PS4**.

## Layout

- **Compact header:** game title and selectable PC/PS4 console.
- **Two shallow file cards:** Character Save and Profile Data, each with
  Load, Unload, a local-file drag-and-drop zone and current filename.
- **Left sidebar:** Character Overview, Inventory & Weapons, Weapon Workshop,
  Skills & Progression, Profile Overview, Guardian & Vault, Cosmetics & Bank.
- **Large editing pane:** the sidebar replaces the previous cramped horizontal
  tabs; resize the horizontal splitter to change sidebar/content proportions.
- **Character Overview:** hero details, class placeholder panel, editable
  character name, level, money and Eridium; quick links to weapon and skills.
- **Weapon Workshop:** searchable decoded inventory, item names/levels,
  import/duplicate codes, level/Mayhem action controls, decoded parts,
  compatible donors, recognized anointments, and a read-only item code field.
- **Persistent footer:** save status and prominent yellow Save + Backup.

## File requirements

Character-only screens remain disabled/gray until a compatible character save
is loaded. Profile-only screens remain disabled/gray until a compatible profile
file is loaded. A character save **does not** unlock profile tabs.

Changing console or unloading a file clears stale character details and
pending weapon edits. Failed imports do not leave an editable stale weapon
list. PC uses game-supported GVAS format. PS4 requires an Apollo-exported GVAS
file: raw encrypted PFS containers are not directly editable.

## Saving

The **Save + Backup** control applies character stats or profile values on the
corresponding page, or queued weapon operations from Weapon Workshop. If there
are queued workshop edits while another page is selected, the application
navigates to the workshop instead of silently saving unrelated controls.

The existing save engine creates a timestamped, verified original in
`ZSaveArchive_Backups` and updates the selected source filename only after
codec verification and backup success.

## Fidelity and supported editing

This update recreates the **layout pattern** of the chosen visual reference,
not every illustrated in-game graphic. Official character portraits and weapon
render images are **not bundled**. Placeholder panels display accurate data
from the loaded save.

Weapon parts/anointments can only be transferred from supported compatible
inventory items. Arbitrary part creation, complete rarity selection, weapon
art rendering, and game-wide catalogs are not implemented in this UI. Existing
advanced editors remain available from Inventory & Weapons and Skills.

## Verification

Additional offscreen PySide6 UI tests are included. Windows GUI execution,
compiled EXE packaging, full save-codec round-trips and PS4 restore have
**not** been executed as part of this design change.
