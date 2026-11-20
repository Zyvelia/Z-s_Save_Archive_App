"""Navigation regression tests; PySide6-specific GUI smoke tests require Windows."""
from pathlib import Path
import unittest
from zarchive.navigation_v30 import classify_action,is_advanced_action,collect_legacy_actions

ROOT=Path(__file__).resolve().parents[1]

class FakeAction:
    def __init__(self,name,menu=None,separator=False):self._name=name;self._menu=menu;self._separator=separator
    def isSeparator(self):return self._separator
    def menu(self):return self._menu
    def text(self):return self._name
class FakeMenu:
    def __init__(self,actions):self._actions=actions
    def actions(self):return self._actions

class NavigationTests(unittest.TestCase):
    def test_routing(self):
        cases={'GitHub Publishing Center':'Releases','PS3 Homebrew Manager':'PS3 Tools',
               'PKG Comparison & Compatibility':'PS3 Tools','PS3 ISO → XMB Assistant':'PS3 Tools',
               'Backup After Game Exit (opt-in)':'Saves & Backups',
               'Save profiles / characters':'Save Editor','Tag colors':'Game Library',
               'Archive/database health':'Settings','PS3 FTP':'PS3 Tools'}
        for label,section in cases.items():
            with self.subTest(label=label):self.assertEqual(classify_action(label),section)
    def test_advanced_hidden(self):
        self.assertTrue(is_advanced_action('ISO Conversion Preflight'))
        self.assertFalse(is_advanced_action('GitHub Publishing Center'))
    def test_nested_actions_preserved(self):
        a=FakeAction('GitHub Publishing Center');b=FakeAction('PKG Comparison')
        menu=FakeMenu([FakeAction('Group',FakeMenu([a,b])), FakeAction('Other',FakeMenu([a])),
                      FakeAction('Find tool…'),FakeAction('Separator',separator=True)])
        self.assertEqual(collect_legacy_actions(menu),[a,b])
    def test_no_exposed_tools_menu(self):
        source=(ROOT/'zarchive/ui_v29.py').read_text()
        self.assertIn('self.tools_btn.hide()',source)
        self.assertIn('self.sidebar.hide()',source)
        self.assertNotIn('self.tools_btn.showMenu()',source)
        self.assertIn("'Saves & Backups'",source)
        self.assertIn("'PS3 Tools'",source)
        self.assertIn('self._make_section(section)',source)
    def test_build_pipeline_preserved(self):
        self.assertIn('Build_Installer.bat',(ROOT/'Build_All.bat').read_text())
        self.assertTrue((ROOT/'assets/ZSaveArchive.ico').is_file())

if __name__=='__main__':unittest.main()
