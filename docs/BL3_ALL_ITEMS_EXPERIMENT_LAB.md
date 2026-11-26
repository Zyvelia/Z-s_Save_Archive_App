# BL3 Weapon Workshop — All Items and Experimental Part Lab

## User-provided PS4 game data inspection
Uploaded: `OakGame.zip` (15.9 MB compressed; 358 ZIP entries, ~30.0 MB uncompressed).
The archive has 121 `.uasset` files, 121 matching `.uexp` files and
54 `.ubulk` files. It covers `OakGame/Content/Pickups`, primarily ammo,
health, money, Eridium, rarity-specific pickup effects, skins, and a handful
of other pickup meshes and textures. Representative inventory definitions:
`InvData_Ammo_Shotgun`, `InvData_Eridium_Ingot`, `DA_InventoryData_Health`,
and `NewBPInv_LootOGramData`.

**These are not sufficient to generate every weapon attachment.** Neither
the game's complete part index nor full weapon inventory balances are present
in the submitted slice. We therefore do not invent attachment identifiers,
weapon stat modifiers, names or descriptions based solely on asset filenames.

The ZIP does not need to be imported into the BL3 editor. The *loaded save*
supplies actual current inventory and decoded part slots. For a broader
named-item browse/import catalog, the existing optional user-provided BL3
item-code CSV/ZIP importer remains available.

## New workflow

1. Select **Borderlands 3 → PS4/PC → Load Character**.
2. Open **Weapon Workshop**. At the top, use **SELECT ITEM** and the
   **All inventory items** combo box. Item filters:
   - All inventory items (every decoded item).
   - Attachment-compatible items (parsed part slots available).
   - Unsupported / other items (no editable decoded parts).
3. Select a weapon or other inventory item. A summary states whether
   attachments are available from the existing decoder. Unsupported items
   remain visible, but swap controls are disabled.
4. Normal mode allows same-balance, same-part-category donors at matching
   slot positions.
5. For testing, enable **Experimental: allow different weapon balance
   (export copy only)**. This relaxes **balance equality**, not the
   serial-database category or matching-slot requirements. A different
   category or an undecodable item cannot safely receive these parts.
6. Queue the experimental swap and choose **Save + Backup**. Experimental
   actions prompt for a **new filename**, refuse existing output files, and
   present a warning. The original save is never touched by this path.
   Export uses the existing verified copy-writing pipeline, checking that
   the edited file round-trips through the BL3 codec.

## Limits

- A structurally valid BL3 serial is not proof that the game accepts a
  specific part combination. Experimental exports may fail to re-encode,
  decode, load in the game, or may have unexpected behavior.
- Experimental mode is **not** an arbitrary binary/protobuf editor, does not
  enable mismatched part database categories or attach parts to a consumable
  with no encoded part slots.
- Keep an untouched backup and test copied saves offline.
- The archive's game assets are not bundled or redistributed in this repo.
- Added unit tests for normal vs opt-in operations, category and slot bounds,
  and choosing a distinct export filename. Windows GUI and live PS4 restore
  are not yet verified.
