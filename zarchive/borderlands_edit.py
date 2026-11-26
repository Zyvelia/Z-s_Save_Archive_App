"""Stage decrypted Borderlands saves for game-specific desktop editors."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
import shutil
import subprocess
import uuid

from .iso_converter_v20 import safe_copy_tree
from .storage import MAX_IMPORT_BYTES, folder_digest


@dataclass(frozen=True)
class BorderlandsEditor:
    key: str
    game: str
    platform: str
    editor: str
    source_url: str
    character: str
    weapons: str


EDITORS = (
    BorderlandsEditor('bl1_ps3', 'Borderlands', 'PS3', 'WillowTree#',
                      'https://sourceforge.net/projects/willowtree/',
                      'Use the General, Skills and Quests tabs for character progress.',
                      'Use the Weapons and Items tabs to inspect, edit, or add gear.'),
    BorderlandsEditor('bl2_ps3', 'Borderlands 2', 'PS3', 'Gibbed Borderlands 2',
                      'https://github.com/gibbed/Gibbed.Borderlands2',
                      'Select PlayStation 3 in Gibbed’s Open dialog. Use the Character, Currency, and Raw tabs.',
                      'Use Backpack and Bank to edit weapons or paste Gibbed item codes.'),
    BorderlandsEditor('tps_ps3', 'Borderlands: The Pre-Sequel', 'PS3', 'Gibbed Pre-Sequel',
                      'https://github.com/gibbed/Gibbed.BorderlandsOz',
                      'Select PlayStation 3 in Gibbed’s Open dialog. Use the Character, Currency, and Raw tabs.',
                      'Use Backpack and Bank to edit gear or paste Pre-Sequel item codes.'),
    BorderlandsEditor('bl3_ps4', 'Borderlands 3', 'PS4', 'Zak’s BL3 Save Editor',
                      'https://github.com/ZakisM/bl3_save_edit',
                      'Load the decrypted PS4 character save to edit the character. A profile is a separate file.',
                      'Open Inventory or the profile Bank to edit saved gear.'),
    BorderlandsEditor('bl3_pc', 'Borderlands 3', 'PC', 'Zak’s BL3 Save Editor',
                      'https://github.com/ZakisM/bl3_save_edit',
                      'Load a PC Borderlands 3 character save or profile.',
                      'Use Inventory or Bank to inspect saved gear.'),
    BorderlandsEditor('ttwl_ps4', 'Tiny Tina’s Wonderlands', 'PS4', 'TTWL Save Editor',
                      'https://github.com/xcier/TTWLSaveEditor',
                      'Open the decrypted PS4 character save. Use the character tabs and Raw for exposed fields.',
                      'Use Inventory for character weapons and open the profile separately for bank gear.'),
)
EDITOR_SETTINGS = frozenset('borderlands_' + editor.key for editor in EDITORS)
CUSA = re.compile(r'CUSA[0-9]{5}', re.I)


def match_editor(editor, row):
    game = ' '.join(re.findall(r'[a-z0-9]+', row['game'].casefold()))
    if row['platform'] != editor.platform:
        return False
    if editor.key == 'bl1_ps3':
        return game == 'borderlands' or game.startswith(('borderlands goty', 'borderlands game of the year'))
    fragment = {'bl2_ps3': 'borderlands 2', 'tps_ps3': 'borderlands the pre sequel',
                'bl3_ps4': 'borderlands 3', 'bl3_pc': 'borderlands 3', 'ttwl_ps4': 'wonderlands'}[editor.key]
    return fragment in game


def validate_editor(path):
    executable = Path(path).expanduser().resolve(strict=True)
    if executable.suffix.casefold() != '.exe' or not executable.is_file():
        raise ValueError('Choose an installed Windows editor executable.')
    with executable.open('rb') as stream:
        if stream.read(2) != b'MZ':
            raise ValueError('The selected file is not a Windows executable.')
    return executable


def stage_save(source, output, archive_root, *, platform, title_id=''):
    """Copy the full export so console metadata stays with the edited payload."""
    original = Path(source).expanduser()
    if original.is_symlink() or getattr(original, 'is_junction', lambda: False)():
        raise ValueError('Select a regular save file or folder.')
    source = original.resolve(strict=True)
    output = Path(output).expanduser().resolve(strict=True)
    archive = Path(archive_root).resolve(strict=True)
    if not output.is_dir() or output == archive or archive in output.parents:
        raise ValueError('Choose an output directory outside the archive.')
    if not (source.is_file() or source.is_dir()):
        raise ValueError('Select a save file or directory.')
    if source.is_dir() and (source == output or source in output.parents):
        raise ValueError('Choose an output directory outside the source save.')
    project = output / ('Borderlands_Edit_' + uuid.uuid4().hex[:10])
    project.mkdir()
    try:
        name = source.name if source.is_dir() else 'Save'
        if platform == 'PS4':
            candidates = [title_id, source.name, *(parent.name for parent in source.parents)]
            title = next((candidate.upper() for candidate in candidates if CUSA.fullmatch(candidate)), 'PS4')
            container = project / title
            container.mkdir()
        else:
            container = project
        destination = container / name
        if source.is_dir():
            original_digest = folder_digest(source)
            safe_copy_tree(source, destination)
            copied_digest = folder_digest(destination)
            if copied_digest != original_digest or folder_digest(source) != original_digest:
                raise ValueError('The source changed while it was being copied.')
        else:
            if source.stat().st_size > MAX_IMPORT_BYTES:
                raise ValueError('Save exceeds the 512 MiB import limit.')
            destination.mkdir()
            shutil.copyfile(source, destination / source.name)
        for path in destination.rglob('*'):
            if path.is_file():
                path.chmod(path.stat().st_mode | 0o200)
        return destination
    except BaseException:
        shutil.rmtree(project, ignore_errors=True)
        raise


def open_editor(executable, working_folder, *, runner=subprocess.Popen):
    """Launch the configured editor. The working folder becomes its starting directory."""
    executable = validate_editor(executable)
    working_folder = Path(working_folder).resolve(strict=True)
    if not working_folder.is_dir():
        raise ValueError('Prepare a working copy before opening the editor.')
    return runner([str(executable)], cwd=working_folder)
