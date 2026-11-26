"""Cross-balance edit restrictions: experiments must remain opt-in, copy-only."""
import unittest
from unittest.mock import patch

from zarchive.bl3_advanced import _action, write_advanced_copy
from zarchive.bl3_visual_builders import transplant_part_experimental


class FakeItem:
    def __init__(self, balance, category, parts):
        self.balance = balance
        self._part_invkey = category
        self._parts = list(parts)
        self._generic_parts = []
        self.can_parse = True
        self.can_parse_parts = True
        self.changed_parts = False
        self.serial = b'unchanged'

    @property
    def level(self):
        return 72

    def _deparse_serial(self):
        self.serial = b'changed'

    def _update_superclass_serial(self):
        pass


class FakeSave:
    def __init__(self, category='Shotgun'):
        self.items = [
            FakeItem('Balance_A', 'Shotgun', [('Barrel_A', 1)]),
            FakeItem('Balance_B', category, [('Barrel_B', 2)]),
        ]

    def get_items(self):
        return self.items


class ItemExperimentTests(unittest.TestCase):
    def test_rejects_experiment_without_explicit_opt_in(self):
        save = FakeSave()
        action = {
            'op': 'weapon_part_experiment', 'index': 0, 'slot': 0,
            'donor_index': 1, 'donor_slot': 0,
        }
        with self.assertRaisesRegex(ValueError, 'exported to a new file'):
            _action(save, 'character', action)
        self.assertEqual(save.items[0]._parts[0][0], 'Barrel_A')
        self.assertEqual(
            _action(save, 'character', action, experimental_allowed=True),
            'weapon_part_experiment',
        )
        self.assertEqual(save.items[0]._parts[0][0], 'Barrel_B')

    def test_rejects_incompatible_categories_and_missing_slots(self):
        save = FakeSave(category='Pistol')
        with self.assertRaisesRegex(ValueError, 'not serial-compatible'):
            transplant_part_experimental(save, 0, 0, 1, 0)
        self.assertEqual(save.items[0]._parts[0][0], 'Barrel_A')
        save = FakeSave()
        with self.assertRaisesRegex(ValueError, 'matching valid slot'):
            transplant_part_experimental(save, 0, 0, 1, 1)

    @patch('zarchive.bl3_advanced._publish')
    def test_export_mode_remains_explicit(self, publish):
        publish.return_value = 'new_copy.sav'
        action = [{
            'op': 'weapon_part_experiment', 'index': 0, 'slot': 0,
            'donor_index': 1, 'donor_slot': 0,
        }]
        self.assertEqual(
            write_advanced_copy('original.sav', 'new_copy.sav',
                expected_sha256='sha', platform='PS4', kind='character',
                actions=action, experimental_allowed=True),
            'new_copy.sav',
        )
        self.assertEqual(publish.call_args.args[:2],
                         ('original.sav', 'new_copy.sav'))


if __name__ == '__main__':
    unittest.main()
