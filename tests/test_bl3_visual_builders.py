"""Unit tests for game-specific BL3 weapon-part and skill-point editing."""
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from zarchive.bl3_visual_builders import (
    weapon_part_slots, compatible_part_sources, transplant_part,
    skill_rows, skill_point_budget, set_existing_skill_points,
)
from zarchive.bl3_advanced import _action, _fingerprint


class FakeItem:
    def __init__(self, balance, parts, *, category='Weapons.Pistol'):
        self.balance = balance
        self._parts = [(part, index) for index, part in enumerate(parts, 1)]
        self._part_invkey = category
        self._generic_parts = []
        self.can_parse = True
        self.can_parse_parts = True
        self.level = 15
        self.changed_parts = False
        self.deparsed = False

    def _deparse_serial(self):
        self.deparsed = True

    def _update_superclass_serial(self):
        pass

    def get_serial_base64(self):
        return 'BL3(' + ','.join(part for part, _ in self._parts) + ')'


class FakeSkill:
    def __init__(self, name, pts, maxpts, tree):
        self.item_asset_path = name
        self.points = pts
        self.max_points = maxpts
        self.tree_identifier = tree


class FakeSave:
    def __init__(self):
        self.items = [
            FakeItem('/Game/WeaponA', ['Barrel_A', 'Grip_A']),
            FakeItem('/Game/WeaponA', ['Barrel_B', 'Grip_B']),
            FakeItem('/Game/WeaponB', ['Barrel_C', 'Grip_C']),
        ]
        ability = SimpleNamespace(
            ability_points=2,
            tree_grade=2,
            tree_item_list=[
                FakeSkill('/Game/Skill/Alpha', 3, 5, 1),
                FakeSkill('/Game/Skill/Beta', 1, 3, 2),
            ],
        )
        self.save = SimpleNamespace(ability_data=ability)

    def get_items(self):
        return self.items

    def get_pt_mayhem_levels(self):
        return []

    def get_sdus(self):
        return {}


class VisualBuilderTests(unittest.TestCase):
    def setUp(self):
        self.save = FakeSave()

    def test_weapon_compatible_sources_only_same_balance_and_category(self):
        options = compatible_part_sources(self.save, 0)
        self.assertEqual([x['item_index'] for x in options], [1])

    def test_transplant_from_same_balance_reencodes_serial(self):
        transplant_part(self.save, 0, 0, 1, 0)
        self.assertEqual(self.save.items[0]._parts[0][0], 'Barrel_B')
        self.assertTrue(self.save.items[0].deparsed)
        self.assertEqual(weapon_part_slots(self.save, 0)['parts'][0]['asset'], 'Barrel_B')

    def test_incompatible_weapon_and_invalid_slot_rejected(self):
        for donor, slot in [(2, 0), (1, 99)]:
            with self.subTest(donor=donor, slot=slot):
                with self.assertRaises(ValueError):
                    transplant_part(self.save, 0, slot, donor, 0)

    def test_skill_budget_conserved(self):
        old = skill_point_budget(self.save)
        self.assertEqual(old, {'remaining': 2, 'spent': 4, 'total': 6})
        new = set_existing_skill_points(self.save, 0, 5)
        self.assertEqual(new, {'remaining': 0, 'spent': 6, 'total': 6})
        self.assertEqual(skill_rows(self.save)[0]['points'], 5)

    def test_overspend_missing_skill_and_excess_max_rejected(self):
        before = skill_point_budget(self.save)
        for idx, value in [(1, 4), (0, 6), (20, 0)]:
            with self.subTest(idx=idx, value=value), self.assertRaises(ValueError):
                set_existing_skill_points(self.save, idx, value)
        self.assertEqual(skill_point_budget(self.save), before)

    def test_action_queue_updates_skill_and_weapon_fingerprint(self):
        _action(self.save, 'character', {'op': 'skill_points', 'index': 0, 'points': 4})
        _action(self.save, 'character', {'op': 'weapon_part', 'index': 0,
                                         'slot': 0, 'donor_index': 1, 'donor_slot': 0})
        fingerprint = _fingerprint(self.save, 'character')
        self.assertEqual(fingerprint['skill_tree'][0][1], 4)
        self.assertIn('Barrel_B', fingerprint['items'][0])

    def test_skill_cannot_be_created_from_arbitrary_asset(self):
        with self.assertRaises((KeyError, ValueError)):
            _action(self.save, 'character',
                    {'op': 'skill_points', 'asset': '/Fake/Unknown', 'points': 1})


if __name__ == '__main__':
    unittest.main()
