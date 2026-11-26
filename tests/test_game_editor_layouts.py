"""Game-specific layout and independent profile-file tab lock tests."""
import unittest

from zarchive.game_editor_layouts import layout_for, section_enabled
from zarchive.universal_editor_profiles import PROFILES


class GameLayoutTests(unittest.TestCase):
    def enabled(self, game, platform, section, loaded=()):
        return section_enabled(game, platform, section, loaded, PROFILES)

    def test_borderlands_3_has_separate_character_and_profile_designs(self):
        layout = layout_for('Borderlands 3')
        self.assertEqual(layout.designer, 'bl3')
        self.assertEqual([x.label for x in layout.sections],
                         ['Character Save', 'Profile Data'])

    def test_no_file_loaded_both_tabs_locked(self):
        for platform in ('PC', 'PS4'):
            with self.subTest(platform=platform):
                self.assertFalse(self.enabled('Borderlands 3', platform, 'character'))
                self.assertFalse(self.enabled('Borderlands 3', platform, 'profile'))

    def test_character_file_does_not_unlock_profile(self):
        self.assertTrue(self.enabled('Borderlands 3', 'PS4', 'character',
                                     ('character',)))
        self.assertFalse(self.enabled('Borderlands 3', 'PS4', 'profile',
                                      ('character',)))

    def test_profile_file_does_not_unlock_character(self):
        self.assertTrue(self.enabled('Borderlands 3', 'PC', 'profile', ('profile',)))
        self.assertFalse(self.enabled('Borderlands 3', 'PC', 'character',
                                      ('profile',)))

    def test_both_files_enable_both_tabs(self):
        loaded = ('character', 'profile')
        for platform in ('PC', 'PS4'):
            self.assertTrue(self.enabled('Borderlands 3', platform, 'character', loaded))
            self.assertTrue(self.enabled('Borderlands 3', platform, 'profile', loaded))

    def test_unknown_game_and_unsupported_platform_remain_locked(self):
        self.assertIsNone(layout_for('Borderlands 2'))
        for game, platform in [('Borderlands 2', 'PS3'),
                               ('Borderlands 3', 'Xbox'),
                               ('Borderlands 3', None),
                               (None, 'PS4')]:
            for section in ('character', 'profile'):
                self.assertFalse(self.enabled(game, platform, section,
                                              ('character', 'profile')))

    def test_missing_section_is_never_unlocked(self):
        self.assertFalse(self.enabled('Borderlands 3', 'PS4', 'future-tab',
                                      ('future-tab',)))


if __name__ == '__main__':
    unittest.main()
