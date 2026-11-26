# Borderlands 3 Mission Explorer

## Source data

User-provided PS4 dump `Missions.zip` inspected on 2026-11-26:
- 1,495 ZIP entries; 680 `.uasset` / 680 `.uexp`, 135 directories
- 5.1 MB ZIP, 23.6 MB unpacked.
- 115 actual `Mission_*.uasset` definitions identified by bounded filename pattern (other assets include scripted actions, spawners, pickups, and effects).
- Folders: `Missions/Plot`, `Missions/Side/Zone_0` ... `Zone_4`, `Missions/Side/RareSpawn`, `ProvingGrounds`, `Slaughters`, `Raid`.
- Main-story example: `Missions/Plot/Mission_Ep01_ChildrenOfTheVault.uasset` references challenge paths, dialog and first gun/shield item pool assets.

## Use

From Universal Save Editor → Borderlands 3 → Skills & Progression,
select **Browse BL3 missions from extracted ZIP**. Load a ZIP containing the
`Missions/` asset tree and search or filter by category, playthrough
(Normal/TVHM), and status. The dialog works as a read-only asset catalog
without a loaded save; progress appears if a valid character save is loaded.

## Technical contract

- Bounded `.uasset` ZIP reads; no extraction to disk, execution or modification.
- Catalog provides internal `/Game/Missions/...` identifiers, category
  inferred from folder path, and **possible** referenced `/Game/...` paths.
- Character progress is taken exclusively from decoded mission
  playthrough protobuf records. This is not inferred from assets.
- `Not recorded` means absent from the playthrough's mission list; it does
  **not** automatically mean `Not started`.
- Asset reference strings do not prove dependencies, objective structure,
  or reward grants. Those require a version-aware cooked-UE parser and
  cross-asset validation. No quest progress mutation is implemented.
- Mission-name suffix matching is a best-effort fallback; if distinct
  mission assets share the same basename, additional path-aware matching
  is required.
- PS4 retail save files must already be available in the supported
  Apollo-exported GVAS format; raw PS4 encrypted PFS containers are not supported.

## QA

Unit tests added for catalog recognition, filtering, path normalization and
decoded save-status mapping. Current-turn ZIP was inspected with Python's
zipfile module; runtime UI and Windows end-to-end tests were not run.
