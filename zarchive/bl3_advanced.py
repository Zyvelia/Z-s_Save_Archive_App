"""Validated BL3 advanced editing actions for PC and Apollo-exported PS4 saves.

vNext 1: inventory serials, duplication, item level/Mayhem.
vNext 2: Mayhem, Guardian tokens, max SDUs, skill-tree unlock.
vNext 3: bank item import, Vault Card keys/chests, cosmetic unlocks.

All operations use the existing protobuf backend and verified copy writer.
The UI's in-place save path MUST use save_with_backup before replacement.
Unsupported per-skill trees, DLC mission mutations and raw PS4 containers
are deliberately NOT implemented here.
"""
from __future__ import annotations

from .bl3_native import _publish, _read_codec

MAX_ITEMS = 2500
MAX_ACTIONS = 40
MAX_CODE_LENGTH = 8192
MAX_CURRENCY = 2_000_000_000
COSMETICS = {
    'heads': ('unlock_char_heads', 'get_char_heads'),
    'skins': ('unlock_char_skins', 'get_char_skins'),
    'emotes': ('unlock_emotes', 'get_emotes'),
    'echo_themes': ('unlock_echo_themes', 'get_echo_themes'),
    'room_decorations': ('unlock_room_decos', 'get_room_decos'),
    'weapon_skins': ('unlock_weapon_skins', 'get_weapon_skins'),
    'weapon_trinkets': ('unlock_weapon_trinkets', 'get_weapon_trinkets'),
}
KEYS = {n: (f'get_vaultcard{n}_keys', f'set_vaultcard{n}_keys') for n in (1, 2, 3)}
CHESTS = {n: (f'get_vaultcard{n}_chests', f'set_vaultcard{n}_chests') for n in (1, 2, 3)}


def _int(value, label, low=0, high=MAX_CURRENCY):
    if type(value) is not int or not low <= value <= high:
        raise ValueError(f'{label} must be an integer from {low} to {high}.')
    return value


def _index(save, value):
    items = save.get_items()
    idx = _int(value, 'Item index', 0, len(items) - 1)
    return items[idx]


def _code(value):
    if not isinstance(value, str) or not (5 <= len(value) <= MAX_CODE_LENGTH):
        raise ValueError('Supply one valid BL3(...) item code under 8192 characters.')
    value = value.strip()
    if not value.startswith('BL3(') or not value.endswith(')'):
        raise ValueError('Expected a BL3(...) item serial code.')
    return value


def _action(save, kind, action):
    op = action['op']
    if kind == 'character':
        if op == 'item_add':
            if len(save.get_items()) >= MAX_ITEMS:
                raise ValueError('Maximum inventory size reached.')
            save.add_new_item_encoded(_code(action['code']))
        elif op == 'item_replace':
            from bl3save.datalib import BL3Serial
            item = _index(save, action['index'])
            item.set_serial(BL3Serial.decode_serial_base64(_code(action['code'])))
        elif op == 'item_duplicate':
            item = _index(save, action['index'])
            if len(save.get_items()) >= MAX_ITEMS:
                raise ValueError('Maximum inventory size reached.')
            save.add_new_item_encoded(item.get_serial_base64())
        elif op == 'item_level':
            item = _index(save, action['index'])
            if item.level is None or not getattr(item, 'can_parse', False):
                raise ValueError('Item serial cannot be safely parsed for level editing.')
            item.level = _int(action['level'], 'Item level', 1, 100)
        elif op == 'item_mayhem':
            item = _index(save, action['index'])
            if not item.can_have_mayhem():
                raise ValueError('Selected item cannot be assigned a Mayhem level.')
            item.mayhem_level = _int(action['level'], 'Item Mayhem', 0, 10)
        elif op == 'mayhem_all':
            save.set_all_mayhem_level(_int(action['level'], 'Mayhem', 0, 11))
        elif op == 'max_sdu':
            save.set_max_sdus()
        elif op == 'unlock_skill_tree':
            save.unlock_skill_tree(save.get_level())
        else:
            raise ValueError('Unsupported character editing action: ' + str(op))
    elif kind == 'profile':
        if op == 'bank_add':
            if len(save.get_bank_items()) >= MAX_ITEMS:
                raise ValueError('Maximum bank size reached.')
            item = save.create_new_item_encoded(_code(action['code']))
            save.add_bank_item(item)
        elif op == 'guardian_tokens':
            save.set_guardian_rank_tokens(_int(action['value'], 'Guardian tokens'))
        elif op == 'max_sdu':
            save.set_max_sdus()
        elif op in ('vault_keys', 'vault_chests'):
            card = _int(action['card'], 'Vault Card', 1, 3)
            _, setter = (KEYS if op == 'vault_keys' else CHESTS)[card]
            getattr(save, setter)(_int(action['value'], 'Vault Card amount'))
        elif op == 'unlock_cosmetic':
            category = action['category']
            if category not in COSMETICS:
                raise ValueError('Unknown cosmetic category.')
            getattr(save, COSMETICS[category][0])()
        else:
            raise ValueError('Unsupported profile editing action: ' + str(op))
    else:
        raise ValueError('Invalid save type.')
    return op


def _fingerprint(save, kind):
    if kind == 'character':
        return {
            'items': tuple(item.get_serial_base64() for item in save.get_items()),
            'mayhem': tuple(save.get_pt_mayhem_levels()),
            'sdus': tuple(sorted(save.get_sdus().items())),
            'skill_tree_grade': save.save.ability_data.tree_grade,
        }
    return {
        'bank': tuple(item.get_serial_base64() for item in save.get_bank_items()),
        'guardian_tokens': save.get_guardian_rank_tokens(),
        'sdus': tuple(sorted(save.get_sdus().items())),
        'vault_keys': tuple(getattr(save, KEYS[n][0])() for n in (1, 2, 3)),
        'vault_chests': tuple(getattr(save, CHESTS[n][0])() for n in (1, 2, 3)),
        'cosmetics': tuple(
            (key, tuple(sorted(getattr(save, names[1])())))
            for key, names in COSMETICS.items()
        ),
    }


def write_advanced_copy(source, destination, *, expected_sha256, platform,
                        kind, actions):
    """Edit multiple actions in one validated, all-or-nothing output file."""
    if kind not in ('character', 'profile'):
        raise ValueError('Choose Character or Profile.')
    if not isinstance(actions, list) or not 1 <= len(actions) <= MAX_ACTIONS:
        raise ValueError('Choose 1–40 editing actions.')
    if not all(isinstance(x, dict) and isinstance(x.get('op'), str) for x in actions):
        raise ValueError('Invalid editing action.')
    expected = []

    def change(save):
        for action in actions:
            _action(save, kind, action)
        expected.append(_fingerprint(save, kind))

    def verify(check):
        return bool(expected) and _fingerprint(check, kind) == expected[0]

    return _publish(source, destination, expected_sha256, platform, kind, change, verify)


def list_inventory(source, platform, kind):
    """Read-only item data for game-specific inventory and bank UIs."""
    save = _read_codec(source, platform, kind)
    items = save.get_items() if kind == 'character' else save.get_bank_items()
    records = []
    for idx, item in enumerate(items):
        def field(fn, fallback=None):
            try:
                return fn()
            except (AttributeError, KeyError, ValueError, TypeError, IndexError):
                return fallback
        records.append({
            'index': idx,
            'name': field(lambda: item.eng_name, 'Unknown item'),
            'balance': field(lambda: item.balance_short, ''),
            'level': field(lambda: item.level),
            'mayhem': field(lambda: item.mayhem_level),
            'code': field(item.get_serial_base64),
        })
    return records
