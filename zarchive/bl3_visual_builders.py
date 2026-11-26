"""Conservative Borderlands 3 visual weapon/skill editing primitives.

Weapon parts are copied only from another *decoded* item with the exact same
balance and inventory-part category. This prevents arbitrary asset paths or
incompatible part indices being written from free-form UI input.

Skill edits operate only on abilities already present in this character's
protobuf and conserve the save's existing spent+unspent point pool.
"""
from __future__ import annotations


def _items(save):
    return save.get_items()


def _parsed_item(item):
    # Trigger lazy parsing before checking the codec flags.
    _ = item.level
    if not getattr(item, 'can_parse', False) or not getattr(item, 'can_parse_parts', False):
        raise ValueError('This item has an unsupported serial/part format.')
    if not getattr(item, '_part_invkey', None):
        raise ValueError('No item-part database category was recognized.')
    return item


def weapon_part_slots(save, index):
    items = _items(save)
    if type(index) is not int or index < 0 or index >= len(items):
        raise ValueError('Invalid inventory item index.')
    item = _parsed_item(items[index])
    return {
        'item_index': index,
        'balance': item.balance,
        'category': item._part_invkey,
        'parts': [
            {'slot': i, 'asset': str(name), 'db_index': number}
            for i, (name, number) in enumerate(item._parts)
        ],
        'anointments': [
            {'asset': str(name), 'db_index': number}
            for name, number in item._generic_parts
        ],
    }


def compatible_part_sources(save, target_index):
    """Offer only existing same-balance inventory parts, not guessed game data."""
    target = weapon_part_slots(save, target_index)
    matches = []
    for idx in range(len(_items(save))):
        if idx == target_index:
            continue
        try:
            candidate = weapon_part_slots(save, idx)
        except ValueError:
            continue
        if (candidate['balance'], candidate['category']) != (
                target['balance'], target['category']):
            continue
        matches.append(candidate)
    return matches


def transplant_part(save, target_index, target_slot, donor_index, donor_slot):
    target = weapon_part_slots(save, target_index)
    donor = weapon_part_slots(save, donor_index)
    if target['balance'] != donor['balance'] or target['category'] != donor['category']:
        raise ValueError('Weapon parts must come from an identical item balance/category.')
    if type(target_slot) is not int or not 0 <= target_slot < len(target['parts']):
        raise ValueError('Invalid target part slot.')
    if type(donor_slot) is not int or not 0 <= donor_slot < len(donor['parts']):
        raise ValueError('Invalid donor part slot.')
    obj = _items(save)[target_index]
    source = _items(save)[donor_index]
    replacement = source._parts[donor_slot]
    if str(replacement[0]).lower() == 'unknown':
        raise ValueError('The donor contains an unknown part.')
    # Copy from a decoded, same-balance donor rather than taking arbitrary indices.
    obj._parts[target_slot] = replacement
    obj.changed_parts = True
    obj._deparse_serial()
    obj._update_superclass_serial()
    # Require the generated part to survive another parse.
    actual = weapon_part_slots(save, target_index)
    if actual['parts'][target_slot]['asset'] != str(replacement[0]):
        raise ValueError('Weapon part did not survive serialization.')


def skill_rows(save):
    ability = save.save.ability_data
    rows = []
    for i, entry in enumerate(ability.tree_item_list):
        rows.append({
            'index': i,
            'asset': entry.item_asset_path,
            'points': int(entry.points),
            'max_points': int(entry.max_points),
            'tree': int(entry.tree_identifier),
        })
    return rows


def skill_point_budget(save):
    ability = save.save.ability_data
    remaining = int(ability.ability_points)
    spent = sum(row['points'] for row in skill_rows(save))
    return {'remaining': remaining, 'spent': spent, 'total': remaining + spent}


def set_existing_skill_points(save, index, amount):
    entries = save.save.ability_data.tree_item_list
    if type(index) is not int or not 0 <= index < len(entries):
        raise ValueError('Select an existing skill from the save.')
    entry = entries[index]
    maximum = int(entry.max_points)
    if maximum <= 0 or maximum > 100:
        raise ValueError('Unknown or unsupported skill maximum.')
    if type(amount) is not int or not 0 <= amount <= maximum:
        raise ValueError(f'Skill points must be between 0 and {maximum}.')
    old = int(entry.points)
    remaining = int(save.save.ability_data.ability_points)
    new_remaining = remaining + old - amount
    if new_remaining < 0:
        raise ValueError('Not enough unspent points. Lower another skill first.')
    entry.points = amount
    save.save.ability_data.ability_points = new_remaining
    return skill_point_budget(save)


def compatible_donor_anointments(save, target_index):
    """Known generic parts from same-balance donors, excluding Mayhem bonuses.

    The BL3 codec's existing set_anointment() validates the generic-part DB.
    """
    target = weapon_part_slots(save, target_index)
    result = []
    for donor in compatible_part_sources(save, target_index):
        obj = _items(save)[donor['item_index']]
        for name, index in obj._generic_parts:
            text = str(name)
            if 'mayhem' in text.casefold():
                continue
            if text.casefold() == 'unknown':
                continue
            if not _items(save)[target_index].can_have_anointment():
                continue
            result.append({
                'donor_index': donor['item_index'],
                'asset': text,
            })
    return result


def transplant_anointment(save, target_index, donor_index, asset):
    target = weapon_part_slots(save, target_index)
    donor = weapon_part_slots(save, donor_index)
    if target['balance'] != donor['balance'] or target['category'] != donor['category']:
        raise ValueError('Anointments must come from compatible same-balance items.')
    options = compatible_donor_anointments(save, target_index)
    if not any(row['donor_index'] == donor_index and row['asset'] == asset for row in options):
        raise ValueError('That anointment was not found on a compatible donor.')
    obj = _items(save)[target_index]
    if obj.set_anointment(asset) is not True:
        raise ValueError('The codec declined this anointment.')
    check = weapon_part_slots(save, target_index)
    if not any(row['asset'] == asset for row in check['anointments']):
        raise ValueError('Anointment did not survive serial re-encoding.')
