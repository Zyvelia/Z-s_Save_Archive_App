# Borderlands 3 — Visual Weapon and Skill Editors

This upgrade adds two game-specific dialogs to the PC and Apollo-exported PS4
Borderlands 3 Character Save workspace. The existing universal game/console
selection and gray/locked profile tabs are unchanged.

## Visual Weapon Parts Builder

Open a character save, select Inventory & Weapons → Advanced → Visual Weapon
Parts Builder. Choose a target item and a compatible donor from your existing
inventory. Only matching weapon balance and inventory-part database category
appear in the donor selector. Only matching part slot positions may be swapped.

A separate donor anointment selector permits moving a known anointment from a
compatible item. The underlying BL3 codec must recognize that anointment; the
editor will reject unsupported serials or items whose parts cannot be decoded.

This is a **conservative visual builder**, not a complete game-wide weapon
catalog. No arbitrary asset paths, random part IDs, cross-balance edits or
unsupported serials are accepted. To create a new weapon not currently present,
first import a compatible BL3(...) item code using the existing inventory editor.

## Individual Skill Tree Points

Open Skills / Mayhem / SDUs → Advanced → Individual Skill Tree Editor. It displays
each skill entry already present in the character's protobuf, its tree ID,
current points, and maximum points. Edit one skill at a time through the
visual point selector.

Points are conserved: spending an extra point reduces the unspent pool;
removing one returns it. The editor refuses overspending or exceeding a saved
skill maximum. To move points between skills, queue reductions first and
increases afterward. Absent skill entries cannot be fabricated.

This does not yet add a game art/icon skill-tree grid, all class skill
dependencies or DLC-specific skill definitions. It edits documented protobuf
skill records directly and validates that they survive serialization.

## Saving and backup behavior

Both dialogs enqueue actions in the existing BL3 advanced editor. After explicit
confirmation, edits go through round-trip decoding/encoding, the original is
backed up into the adjacent ZSaveArchive_Backups folder and verified by SHA-256,
then the original filename is updated atomically. Stale source hashes stop saving.

No direct changes are made to raw PS4 PFS container backups. PS4 saves must
first be exported by Apollo.

## Tests and remaining validation

Mocked regression tests for part compatibility, same-position swapping,
anointment donors and conservation of skill points are included, but they
have not been executed on the user's PC. A compiled Windows EXE and PS4
restore have not been tested here. Before restoring a modified save, compare
it with an independent compatible BL3 editor and retain an additional console
backup.
