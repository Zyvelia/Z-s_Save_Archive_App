"""Optional native Borderlands 3 character editing for Apollo-decrypted PS4 exports.

Uses apocalyptech's bl3-cli-saveedit codec; never patches an unknown GVAS payload
by offset. Every edit is written to a NEW file and decoded again for validation.
"""
from __future__ import annotations

from pathlib import Path
import hashlib
import tempfile

MAX_SAVE_BYTES = 32 * 1024 * 1024


def _codec():
    try:
        from bl3save.bl3save import BL3Save
    except ImportError as exc:
        raise RuntimeError(
            'Native BL3 editing needs bl3-cli-saveedit. Install it into the '
            'same Python environment: python -m pip install bl3-cli-saveedit. '
            'The existing external editor is still available.'
        ) from exc
    return BL3Save


def _source(path):
    path = Path(path).expanduser()
    if path.is_symlink() or not path.is_file():
        raise ValueError('Choose a regular Apollo-exported character save file.')
    if not 32 <= path.stat().st_size <= MAX_SAVE_BYTES:
        raise ValueError('Unsupported or oversized Borderlands save.')
    with path.open('rb') as stream:
        if stream.read(4) != b'GVAS':
            raise ValueError('Not a decrypted GVAS save. Export using Apollo first.')
    return path.resolve(strict=True)


def load_character(path):
    """Read BL3 character details; never change the source file."""
    source = _source(path)
    try:
        save = _codec()(str(source))
        result = {
            'path': str(source),
            'sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
            'character': save.get_char_name(),
            'class': save.get_class(eng=True),
            'level': save.get_level(),
            'xp': save.get_xp(),
            'money': save.get_money(),
            'eridium': save.get_eridium(),
            'inventory_count': len(save.get_items()),
            'platform_build': save.build_id,
            'save_type': save.sg_type,
        }
    except Exception as exc:
        raise ValueError(f'Could not decode Borderlands 3 character save: {exc}') from exc
    return result


def write_character_copy(source, destination, *, name, level, money, eridium,
                         expected_sha256):
    """Save edits to an exclusive new file; reparse and verify changed values."""
    source = _source(source)
    destination = Path(destination).expanduser().absolute()
    if destination.exists() or destination.is_symlink():
        raise FileExistsError('Choose a NEW output filename; existing saves are never overwritten.')
    if not destination.parent.is_dir() or destination.parent.is_symlink():
        raise ValueError('Choose an existing, regular output directory.')
    if source == destination:
        raise ValueError('Cannot overwrite the original save.')
    if len(name) > 40 or not name or '\x00' in name:
        raise ValueError('Character name must be 1–40 characters.')
    if type(level) is not int or not 1 <= level <= 80:
        raise ValueError('Level must be between 1 and 80.')
    for title, value in [('Money', money), ('Eridium', eridium)]:
        if type(value) is not int or not 0 <= value <= 2_000_000_000:
            raise ValueError(f'{title} must be 0 to 2,000,000,000.')
    before = hashlib.sha256(source.read_bytes()).hexdigest()
    if before != expected_sha256:
        raise ValueError('The source file changed after loading. Reopen it before editing.')

    codec = _codec()
    try:
        save = codec(str(source))
    except Exception as exc:
        raise ValueError('The installed codec could not read this PS4 save. '
                         'Use the external BL3 editor for this game version.') from exc
    save.set_char_name(name)
    save.set_level(level)
    save.set_money(money)
    save.set_eridium(eridium)

    # Stage on the destination filesystem, but do not replace any existing file.
    temporary = None
    created = False
    try:
        with tempfile.NamedTemporaryFile(prefix='.bl3-edit-', suffix='.tmp',
                                         dir=destination.parent, delete=False) as stream:
            temporary = Path(stream.name)
        save.save_to(str(temporary))
        check = codec(str(temporary))
        if (check.get_char_name(), check.get_level(), check.get_money(), check.get_eridium()) != (
                name, level, money, eridium):
            raise ValueError('BL3 output verification failed; no save was published.')
        if hashlib.sha256(source.read_bytes()).hexdigest() != before:
            raise ValueError('Original changed during editing; no save was published.')
        # Exclusive destination creation prevents silently replacing another save.
        with destination.open('xb') as stream:
            created = True
            with temporary.open('rb') as result:
                while True:
                    block = result.read(1024 * 1024)
                    if not block:
                        break
                    stream.write(block)
        return destination
    except BaseException:
        if created:
            destination.unlink(missing_ok=True)
        raise
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
