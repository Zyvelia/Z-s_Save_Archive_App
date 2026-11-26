"""Native Borderlands 3 PC and Apollo-exported PS4 save editing.

Uses apocalyptech's bl3-cli-saveedit for the game's protobuf schema and
PC serialization. A checked translation layer maps PS4 game-level encryption
to/from the PC codec without changing the GVAS header. Original saves are never
modified. All outputs are decoded and validated before publishing.
"""
from __future__ import annotations

from pathlib import Path
import hashlib
import tempfile

from .bl3_platform_codec import convert_platform, gvas_payload_bounds
from .universal_editor_profiles import validate_profile

MAX_SAVE_BYTES = 32 * 1024 * 1024


def _codec(kind):
    try:
        if kind == 'character':
            from bl3save.bl3save import BL3Save
            return BL3Save
        from bl3save.bl3profile import BL3Profile
        return BL3Profile
    except ImportError as exc:
        raise RuntimeError('BL3 codec missing. Install bl3-cli-saveedit into the '
                           'Python environment used to run Z Save Archive.') from exc


def _source(path):
    source = Path(path).expanduser()
    if source.is_symlink() or not source.is_file():
        raise ValueError('Choose a regular Apollo-exported or PC save file.')
    size = source.stat().st_size
    if not 32 <= size <= MAX_SAVE_BYTES:
        raise ValueError('Unsupported or oversized Borderlands save.')
    return source.resolve(strict=True)


def _read_codec(path, platform, kind):
    """Load one save using the PC protobuf backend after platform conversion."""
    source = _source(path)
    payload = source.read_bytes()
    _, _, actual_kind = gvas_payload_bounds(payload)
    if actual_kind != kind:
        raise ValueError(f'Selected a {kind} profile but this file is a {actual_kind} save.')
    pc_bytes = convert_platform(payload, platform, 'PC', expected_kind=kind)
    with tempfile.TemporaryDirectory(prefix='bl3-codec-') as temp:
        pc_file = Path(temp) / 'decoded.sav'
        pc_file.write_bytes(pc_bytes)
        try:
            return _codec(kind)(str(pc_file))
        except Exception as exc:
            raise ValueError('The save cannot be decoded with the selected platform profile. '
                             'Check PC vs PS4 and whether Apollo exported decrypted files.') from exc


def load_character(path, platform='PS4'):
    source = _source(path)
    validate_profile(f'bl3-{platform.lower()}-character')
    save = _read_codec(source, platform, 'character')
    return {
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
        'platform': platform,
        'kind': 'character',
    }


def load_profile(path, platform='PS4'):
    source = _source(path)
    validate_profile(f'bl3-{platform.lower()}-profile')
    save = _read_codec(source, platform, 'profile')
    return {
        'path': str(source),
        'sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
        'golden_keys': save.get_golden_keys(),
        'diamond_keys': save.get_diamond_keys(),
        'bank_count': len(save.get_bank_items()),
        'platform_build': save.build_id,
        'save_type': save.sg_type,
        'platform': platform,
        'kind': 'profile',
    }


def _publish(source, destination, expected_sha256, platform, kind, change, verify):
    source = _source(source)
    validate_profile(f'bl3-{platform.lower()}-{kind}')
    destination = Path(destination).expanduser().absolute()
    if destination.is_symlink() or destination.exists():
        raise FileExistsError('Choose a NEW filename; no existing save is overwritten.')
    if not destination.parent.is_dir() or destination.parent.is_symlink():
        raise ValueError('Choose an existing, non-linked output directory.')
    before = hashlib.sha256(source.read_bytes()).hexdigest()
    if before != expected_sha256:
        raise ValueError('Save changed since it was opened. Reopen it and retry.')

    save = _read_codec(source, platform, kind)
    change(save)
    with tempfile.TemporaryDirectory(prefix='bl3-export-', dir=destination.parent) as temp:
        pc_file = Path(temp) / 'modified_pc.sav'
        save.save_to(str(pc_file))
        encoded = convert_platform(pc_file.read_bytes(), 'PC', platform, expected_kind=kind)
        wrapped = Path(temp) / 'verified.sav'
        wrapped.write_bytes(encoded)
        check = _read_codec(wrapped, platform, kind)
        if not verify(check):
            raise ValueError('Output verification failed. Nothing was published.')
        if hashlib.sha256(source.read_bytes()).hexdigest() != before:
            raise ValueError('Original changed during export. Nothing was published.')
        created = False
        try:
            with destination.open('xb') as stream:
                created = True
                stream.write(encoded)
        except BaseException:
            if created:
                destination.unlink(missing_ok=True)
            raise
    return destination


def write_character_copy(source, destination, *, name, level, money, eridium,
                         expected_sha256, platform='PS4'):
    if not isinstance(name, str) or not 1 <= len(name) <= 40 or '\x00' in name:
        raise ValueError('Character name must be 1–40 characters.')
    if type(level) is not int or not 1 <= level <= 80:
        raise ValueError('Level must be between 1 and 80.')
    for title, value in [('Money', money), ('Eridium', eridium)]:
        if type(value) is not int or not 0 <= value <= 2_000_000_000:
            raise ValueError(f'{title} must be 0 to 2,000,000,000.')

    def change(save):
        save.set_char_name(name)
        save.set_level(level)
        save.set_money(money)
        save.set_eridium(eridium)

    def verify(save):
        return (save.get_char_name(), save.get_level(), save.get_money(),
                save.get_eridium()) == (name, level, money, eridium)

    return _publish(source, destination, expected_sha256, platform, 'character',
                    change, verify)


def write_profile_copy(source, destination, *, golden_keys, diamond_keys,
                       expected_sha256, platform='PS4'):
    for title, count in [('Golden keys', golden_keys), ('Diamond keys', diamond_keys)]:
        if type(count) is not int or not 0 <= count <= 2_000_000_000:
            raise ValueError(f'{title} must be 0 to 2,000,000,000.')

    def change(save):
        save.set_golden_keys(golden_keys)
        save.set_diamond_keys(diamond_keys)

    def verify(save):
        return save.get_golden_keys() == golden_keys and save.get_diamond_keys() == diamond_keys

    return _publish(source, destination, expected_sha256, platform, 'profile',
                    change, verify)
