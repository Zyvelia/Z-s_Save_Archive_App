"""Read-only BL3 mission catalog from a user's exported Unreal mission ZIP.

Uses filenames and bounded UE-readable reference strings, not a guessed cooked
Blueprint serializer. Never executes assets, extracts game binaries to disk,
or silently infers rewards/dependencies from ordinary asset references.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path, PurePosixPath
import re
import zipfile

MAX_ZIP_BYTES = 160 * 1024 * 1024
MAX_ENTRIES = 25000
MAX_ASSET_BYTES = 3 * 1024 * 1024
MAX_SCAN_TOTAL = 100 * 1024 * 1024
MAX_REFS = 60
ASSET_REF = re.compile(rb'/Game/[A-Za-z0-9_/.-]{6,240}')
MISSION_NAME = re.compile(r'^Mission_[A-Za-z0-9_-]+$', re.I)
SUFFIX = re.compile(r'(?:_C|\\.uasset|\\.uexp)$', re.I)


@dataclass(frozen=True)
class MissionDefinition:
    asset_path: str
    name: str
    category: str
    references: tuple[str, ...]

    @property
    def asset_id(self) -> str:
        return mission_key(self.asset_path)


def mission_key(value: str) -> str:
    """Canonical last asset name for matching _C save class paths and .uasset files."""
    candidate = str(value).replace('\\', '/').split('/')[-1].split('.')[-1]
    return SUFFIX.sub('', candidate).casefold()


def classify_mission(path: str) -> str:
    value = '/' + path.casefold().replace('\\', '/')
    if '/plot/' in value:
        return 'Main Story'
    if '/rarespawn/' in value:
        return 'Rare Spawn'
    if '/provinggrounds/' in value:
        return 'Proving Grounds'
    if '/slaughters/' in value:
        return 'Slaughter'
    if '/raid/' in value:
        return 'Raid'
    if '/side/' in value:
        return 'Side Mission'
    return 'Other'


def _asset_references(data: bytes) -> tuple[str, ...]:
    # Cooked Unreal name tables carry literal paths. References are candidates,
    # not proof of a dependency, reward grant or gameplay objective.
    seen = set()
    for match in ASSET_REF.finditer(data):
        ref = match.group().decode('ascii', errors='ignore').rstrip('.')
        if ref not in seen:
            seen.add(ref)
            if len(seen) == MAX_REFS:
                break
    return tuple(sorted(seen))


def parse_missions_zip(source: str | Path) -> tuple[MissionDefinition, ...]:
    path = Path(source).expanduser()
    if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_ZIP_BYTES:
        raise ValueError('Choose a regular mission ZIP no larger than 160 MiB.')
    results: dict[str, MissionDefinition] = {}
    total_read = 0
    try:
        with zipfile.ZipFile(path) as archive:
            entries = archive.infolist()
            if len(entries) > MAX_ENTRIES:
                raise ValueError('Archive has too many entries.')
            for entry in entries:
                if entry.is_dir() or not entry.filename.lower().endswith('.uasset'):
                    continue
                if entry.flag_bits & 1 or entry.file_size > MAX_ASSET_BYTES:
                    continue
                normalized = entry.filename.replace('\\', '/')
                parts = PurePosixPath(normalized).parts
                if not parts or not any(p.casefold() == 'missions' for p in parts[:-1]):
                    continue
                name = PurePosixPath(normalized).stem
                if not MISSION_NAME.fullmatch(name):
                    continue
                if total_read + entry.file_size > MAX_SCAN_TOTAL:
                    raise ValueError('Mission asset scanning exceeds 100 MiB.')
                total_read += entry.file_size
                data = archive.read(entry)
                # Only keep safe catalog metadata; never persist raw cooked assets.
                gamepath = '/Game/' + normalized[normalized.lower().find('missions/'):].rsplit('.', 1)[0]
                results[gamepath.casefold()] = MissionDefinition(
                    asset_path=gamepath,
                    name=name,
                    category=classify_mission(normalized),
                    references=_asset_references(data),
                )
    except (zipfile.BadZipFile, OSError, RuntimeError, EOFError) as exc:
        raise ValueError('Unable to read the selected missions archive.') from exc
    if not results:
        raise ValueError('No Mission_*.uasset definitions found in a Missions directory.')
    return tuple(sorted(results.values(), key=lambda m: (m.category, m.name.casefold())))


def mission_status_lookup(character_save) -> dict[tuple[int, str], str]:
    """Read actual per-playthrough mission entries from a decoded character save.

    The underlying codec exposes mission_list.status; no mutation occurs.
    A missing entry is 'Not recorded', never a claimed 'Not started'.
    """
    output: dict[tuple[int, str], str] = {}
    playthroughs = character_save.save.mission_playthroughs_data
    for playthrough, state in enumerate(playthroughs):
        for mission in state.mission_list:
            key = mission_key(mission.mission_class_path)
            if not key:
                continue
            status_number = int(mission.status)
            # BL3 protobuf status enum maps these values in the codec.
            from bl3save.bl3save import MissionState
            if status_number == int(MissionState.MS_Active):
                status = 'Active'
            elif status_number == int(MissionState.MS_Complete):
                status = 'Completed'
            else:
                status = f'State {status_number}'
            output[(playthrough, key)] = status
    return output
