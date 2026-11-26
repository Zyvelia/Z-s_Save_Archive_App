"""Tests for independent PS4 game and update PKG selection."""
import unittest
from types import SimpleNamespace

from zarchive.ps4_build_modes import BUILD_MODES, choose_build_dumps


def dump(title, category):
    return SimpleNamespace(title_id=title, category=category)


class BuildModeTests(unittest.TestCase):
    def setUp(self):
        self.base = dump('CUSA27677', 'gd')
        self.patch = dump('CUSA27677', 'gp')
        self.other_base = dump('CUSA03817', 'gd')
        self.dlc = dump('CUSA27677', 'ac')

    def test_mode_list(self):
        self.assertEqual(set(BUILD_MODES), {'selected', 'separate', 'base', 'update'})

    def test_default_keeps_original_selected_rows(self):
        chosen = [self.patch, self.other_base, self.dlc]
        self.assertEqual(choose_build_dumps(chosen), chosen)

    def test_base_only_filters_patches_and_dlc(self):
        self.assertEqual(choose_build_dumps([self.base, self.patch, self.dlc], 'base'),
                         [self.base])

    def test_separate_base_and_patch_keeps_two_independent_jobs(self):
        self.assertEqual(choose_build_dumps([self.base, self.patch, self.dlc], 'separate'),
                         [self.base, self.patch])

    def test_separate_rejects_unmatched_games(self):
        with self.assertRaisesRegex(ValueError, 'SAME CUSA'):
            choose_build_dumps([self.other_base, self.patch], 'separate')

    def test_update_only_requires_existing_base_pkg(self):
        with self.assertRaisesRegex(ValueError, 'existing matching base'):
            choose_build_dumps([self.base, self.patch], 'update')
        self.assertEqual(choose_build_dumps([self.base, self.patch, self.dlc], 'update',
                                           existing_base='C:/Base.pkg'), [self.patch])

    def test_update_only_rejects_multiple_game_ids(self):
        other_patch = dump('CUSA03817', 'gp')
        with self.assertRaisesRegex(ValueError, 'exactly one'):
            choose_build_dumps([self.patch, other_patch], 'update', existing_base='C:/Base.pkg')

    def test_missing_category_is_actionable(self):
        with self.assertRaisesRegex(ValueError, 'Patch'):
            choose_build_dumps([self.base], 'update', existing_base='C:/Base.pkg')

    def test_empty_selection(self):
        with self.assertRaisesRegex(ValueError, 'Check at least'):
            choose_build_dumps([], 'selected')


if __name__ == '__main__':
    unittest.main()
