# BL3 Save Editor Reference Review — FromDarkHell

## Evidence reviewed

User-provided ZIP: `Borderlands 3 Save Editor (From DarkHellFork)(1).zip`.

Archive inspection (no executables were run):
- Windows WPF .NET app (`BL3SaveEditor.exe`) and associated `BL3Tools.dll`.
- `INVENTORY_PARTS_INFO_ALL.csv`: 2,113 data rows, columns `Part`,
  `Positives`, `Negatives`, `Effects`.
- `LOOTLEMON_BL3_ITEMS.csv`: 535 data rows, columns `Name`, `Code`, `Link`.
- Reference GVAS data, starter character/profile files, debug symbols and
  third-party .NET dependencies.
- Static .NET metadata names suggest inventory/part selection and searching,
  missions and skill import, Guardian, Mayhem, SDU and character/profile
  features. These are *capability indicators*, not proof every UI workflow
  works in the supplied binary.

Upstream: https://github.com/FromDarkHell/BL3SaveEditor
The upstream repository uses **GPL-3.0**. The bundled catalog data may have
additional content/database rights or attribution requirements. We do **not**
copy upstream C# or bundled CSV content into Z's Save Archive.

## Comparison with Z's Save Archive

| Area | FromDarkHell package | Z's Save Archive |
| --- | --- | --- |
| Platform / interface | Windows .NET/WPF standalone | Python/PySide6, game profile within universal editor |
| PC and exported PS4 GVAS | Upstream documents PC/PS4 support | Built-in PC/PS4 translation + BL3 protobuf codec |
| Character and profile editing | Distinct save/profile workflows | Independent character/profile loading and locked tabs |
| Inventory/weapon parts | Embedded part metadata and reference lookup | Existing decoded parts and compatible-donor editing |
| Item code catalog | Packaged item CSV | New optional user-provided CSV or ZIP search |
| Part effect explanations | Packaged part CSV | New optional exact asset-name lookup |
| Skill and mission data | Static executable metadata suggests related tools | Existing skill entries and constrained progression actions |
| Save safety | Upstream documents backup and save-as | Verified timestamped backup before same-file replacement |

This is a structural comparison, not a claim of full feature parity.
The supplied ZIP was not executed.

## Implemented in this update

1. An original CSV/ZIP reader in `zarchive/bl3_reference_catalog.py` accepts the
   two documented column schemas. It does **not** execute the EXE or load
   any DLLs.
2. In **Borderlands 3 → Weapon Workshop**, click **Load catalog ZIP / CSV…**
   and select your *own local archive*. Search the 535 item entries and
   transfer a selected code to the normal item-code import control.
3. Weapon part descriptions show positive, negative and effect fields when
   a decoded part name exactly matches a user-loaded reference entry.
4. Lowercase `bl3(...)` codes (as present in the supplied CSV) normalize to
   `BL3(...)` before validation by the existing BL3 serial codec.
5. Inventory browsing remains usable even if detailed optional part decoding
   fails for a game version or unsupported serial.

## Security, authorship, and redistribution

- New implementation is original Python code based on documented CSV schema,
  not a port or a copied implementation of the GPL C# program.
- Bundled copyrighted binaries/CSVs, game item names, descriptions and source
  datasets have **not** been committed to this repository.
- Catalog is entirely opt-in, imported from a ZIP/CSV the user chooses. The
  import has archive size, CSV size, row count, URL and code-format limits.
- A catalog entry **does not** automatically alter a save. User selects an
  entry, then explicitly imports/queues it. The existing codec and backup-first
  save checks still apply.
- Listing item descriptions is informational; it is not confirmation that
  the item is legal/compatible with every game patch or DLC installation.

## Next independent improvements

- Character/item compatibility filter to validate item codes against a known
  supported data schema *before* queueing.
- Searchable part effect browser with multiple matching categories, e.g.
  artifacts, class mods, guns, shields, and grenades.
- Item stat calculator backed by independent public game formulas or
  user-provided, appropriately licensed definitions.
- UI-native mission tree and equipped-slot inspection, followed by save
  format/round-trip testing and authoring of original edit controls.

## Validation

Tests were added for schema recognition, case-insensitive item codes, part
matching, and archive import limitations. Windows UI execution and end-to-end
PS4 restore have **not** been verified in this environment.
