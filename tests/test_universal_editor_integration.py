"""Regression checks for the integrated Universal Save Editor.

Qt smoke tests use an offscreen platform when PySide6 is available.
"""
import os
import tempfile
import unittest
from pathlib import Path

from zarchive.game_targets_v19 import builtin_target, matching_saves


class TargetRegistryTests(unittest.TestCase):
    def test_bl3_is_native_pc_and_ps4(self):
        self.assertEqual(builtin_target('bl3-pc'), ('Borderlands 3', 'PC'))
        self.assertEqual(builtin_target('bl3-ps4'), ('Borderlands 3', 'PS4'))
        self.assertIsNone(builtin_target('borderlands-2'))

    def test_matching_archive_saves_is_platform_aware(self):
        rows = [
            {'game': 'Borderlands 3', 'platform': 'PC'},
            {'game': 'Borderlands 3', 'platform': 'PS4'},
            {'game': 'Borderlands 2', 'platform': 'PS3'},
        ]
        self.assertEqual(matching_saves(rows, 'bl3-ps4'), [rows[1]])
        self.assertEqual(matching_saves(rows, 'bl3-pc'), [rows[0]])


class FakeArchive:
    def __init__(self, root):
        self.root = root

    def list_saves(self, query=''):
        return []

    def editors(self, game, platform):
        return []


class UniversalEditorQtTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
        try:
            from PySide6.QtWidgets import QApplication
        except ImportError:
            raise unittest.SkipTest('PySide6 not installed in test environment')
        cls.application = QApplication.instance() or QApplication([])

    def test_embedded_bl3_visible_and_resets_when_switching(self):
        from zarchive.ui_v18 import EditorWorkspace
        with tempfile.TemporaryDirectory() as directory:
            window = EditorWorkspace(FakeArchive(Path(directory)))
            window.show()
            try:
                self.assertTrue(window.legacy_container.isVisible())
                self.assertFalse(window.native.isVisible())
                index = window.game_target.findData('bl3-ps4')
                self.assertGreaterEqual(index, 0)
                window.game_target.setCurrentIndex(index)
                self.assertTrue(window.native.isVisible())
                self.assertFalse(window.legacy_container.isVisible())
                self.assertEqual(window.native.game.currentData(), 'Borderlands 3')
                self.assertEqual(window.native.console.currentData(), 'PS4')
                self.assertFalse(window.native.game.isEnabled())
                self.assertFalse(window.native.console.isEnabled())
                self.assertTrue(window.native.load_buttons['character'].isEnabled())
                self.assertTrue(window.native.drop_zones['profile'].isEnabled())
                self.assertFalse(window.native.tabs.isTabEnabled(
                    window.native.profile_tab_index))
                window.native.loaded['profile'] = {
                    'path': str(Path(directory) / 'profile'),
                    'kind': 'profile',
                }
                window.game_target.setCurrentIndex(0)
                self.assertTrue(window.legacy_container.isVisible())
                self.assertFalse(window.native.isVisible())
                window.game_target.setCurrentIndex(index)
                self.assertFalse(window.native.loaded)
                self.assertFalse(window.native.tabs.isTabEnabled(
                    window.native.profile_tab_index))
                index_pc = window.game_target.findData('bl3-pc')
                window.game_target.setCurrentIndex(index_pc)
                self.assertEqual(window.native.console.currentData(), 'PC')
            finally:
                window.close()


if __name__ == '__main__':
    unittest.main()
