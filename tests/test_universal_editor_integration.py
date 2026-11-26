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
                index = window.game_target.findData('bl3')
                self.assertGreaterEqual(index, 0)
                self.assertEqual(sum(1 for i in range(window.game_target.count())
                                     if 'Borderlands 3' in window.game_target.itemText(i)), 1)
                window.game_target.setCurrentIndex(index)
                self.assertTrue(window.native.isVisible())
                self.assertFalse(window.legacy_container.isVisible())
                self.assertEqual(window.native.game.currentData(), 'Borderlands 3')
                self.assertIsNone(window.native.console.currentData())
                self.assertTrue(window.native.console.isEnabled())
                self.assertTrue(window.native.empty_hint.isVisible())
                self.assertFalse(window.native.tabs.isVisible())
                index_ps4 = window.native.console.findData('PS4')
                window.native.console.setCurrentIndex(index_ps4)
                self.assertEqual(window.native.console.currentData(), 'PS4')
                self.assertFalse(window.native.game.isEnabled())
                self.assertTrue(window.native.console.isEnabled())
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
                self.assertIsNone(window.native.console.currentData())
                self.assertFalse(window.native.tabs.isTabEnabled(
                    window.native.profile_tab_index))
                pc = window.native.console.findData('PC')
                window.native.console.setCurrentIndex(pc)
                self.assertEqual(window.native.console.currentData(), 'PC')
                self.assertFalse(window.native.loaded)
                self.assertFalse(window.native.tabs.isVisible())
            finally:
                window.close()

    def test_bl3_layout_navigation_and_save_file_gating(self):
        from unittest.mock import patch
        from zarchive.ui_v18 import EditorWorkspace
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / '1.sav'
            source.write_bytes(b'GVAS' + b'0' * 40)
            window = EditorWorkspace(FakeArchive(root))
            window.show()
            try:
                window.game_target.setCurrentIndex(window.game_target.findData('bl3'))
                editor = window.native
                self.assertTrue(editor.navigation.isVisible())
                self.assertEqual(editor.navigation.count(), 9)
                self.assertIs(editor.workspace_split.widget(0), editor.navigation)
                self.assertTrue(editor.empty_hint.isVisible())
                editor.console.setCurrentIndex(editor.console.findData('PS4'))
                self.assertTrue(editor.load_buttons['character'].isEnabled())
                self.assertTrue(editor.drop_zones['profile'].isEnabled())
                char_details = {
                    'path': str(source), 'kind': 'character', 'platform': 'PS4',
                    'character': 'Zane', 'class': 'Operative', 'level': 1,
                    'money': 10, 'eridium': 0, 'inventory_count': 0, 'xp': 0,
                    'sha256': 'test', 'preview': {},
                }
                with patch('zarchive.ui_bl3_native.load_character', return_value=char_details), \\
                     patch('zarchive.ui_bl3_workshop.list_inventory', return_value=[]), \\
                     patch('zarchive.ui_bl3_workshop.list_visual_weapons', return_value=[]):
                    self.assertTrue(editor.open_save(source, 'character'))
                self.assertTrue(editor.tabs.isVisible())
                self.assertFalse(editor.empty_hint.isVisible())
                self.assertEqual(editor.hero_character.text(), 'Zane  /  Operative')
                self.assertTrue(editor.tabs.isTabEnabled(editor.workshop_index))
                self.assertFalse(editor.tabs.isTabEnabled(editor.profile_tab_index))
                self.assertEqual(editor.navigation.item(0).text(), 'CHARACTER')
                for row in range(editor.navigation.count()):
                    item = editor.navigation.item(row)
                    if item.data(0x0100) == editor.workshop_index:
                        editor.navigation.setCurrentRow(row)
                        break
                self.assertEqual(editor.tabs.currentIndex(), editor.workshop_index)
                editor.unload('character')
                self.assertFalse(editor.tabs.isVisible())
                self.assertFalse(editor.export_character_button.isEnabled())
                self.assertEqual(editor.workshop.queue, [])
            finally:
                window.close()


if __name__ == '__main__':
    unittest.main()
