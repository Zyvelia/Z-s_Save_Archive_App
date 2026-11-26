# Borderlands 3 Advanced Editor — vNext 1–3

Access through Borderlands Save Editor → Prepare working copy → Universal Save
Editor. Explicitly select Borderlands 3 and PC or PS4. Character and Profile
load independently; their tabs are gray until the matching file decodes.

## vNext 1 — Inventory and weapons

- Search existing items by name, balance and level.
- Copy existing BL3(...) item serial codes to the clipboard.
- Import compatible BL3(...) item codes and duplicate inventory items.
- Replace an existing item using a compatible BL3(...) code.
- Edit supported item level and item Mayhem.

**Not implemented:** visual weapon part builder, direct rarity changes,
anointment catalog/picker, equipment removal. Use a compatible item code
builder for unsupported serial modifications.

## vNext 2 — Progression

- Character: Mayhem level on existing playthroughs, max known SDUs, unlock
  skill-tree availability if the character level permits.
- Profile: Guardian unspent tokens and max known profile SDUs.

**Not implemented:** individual skill-point allocations, detailed Guardian
reward selection and mission editing. The game may reconcile Guardian
progression internally.

## vNext 3 — Profile bank, cosmetics, Vault Cards and DLC gear

- Search bank items, copy item serials and import compatible BL3(...) codes.
- Edit keys and unopened chests for Vault Cards 1–3.
- Unlock supported categories of heads, skins, emotes, ECHO themes,
  decorations, weapon skins and trinkets.
- DLC gear codes can be imported where installed game assets support them.

**Not implemented:** DLC entitlement, DLC mission progression, automatic
DLC item catalogs, deleting bank items, individual cosmetic picking.

## Source edits and automatic backups

The editor modifies the loaded source file after confirmation. It first
generates and codec-validates a proposed edit, writes an SHA-256-verified
timestamped original into the adjacent ZSaveArchive_Backups directory, and
atomically replaces the original filename. It rejects changes to the source
since it was loaded.

Only PC GVAS files and Apollo-exported PS4 GVAS files are supported. Raw PS4
PFS encrypted savedata and companion .bin files are **not** directly editable.
Keep an independent backup before restoring anything to the PS4.

## Test status

Unit tests for advanced actions and backup-first writes are committed but
have **not been executed in this environment**. No compiled Windows EXE
or actual PS4 restore was verified. Validate your modified files with
another compatible BL3 editor before console restoration.

Run locally (with the project dependencies installed):

    python -m unittest tests.test_bl3_native tests.test_bl3_inplace tests.test_bl3_advanced tests.test_bl3_advanced_backup tests.test_game_editor_layouts
