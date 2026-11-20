from pathlib import Path
import unittest
from zarchive.tools_menu import category_for,CATEGORIES

ROOT=Path(__file__).resolve().parents[1]

class TestMenuAndPackaging(unittest.TestCase):
    def test_categories(self):
        samples={
          'PS3 Homebrew Manager':'Homebrew, ISO & Packages',
          'PS3 Console Center':'PS3 & Connections',
          'GitHub Publishing Center':'Publishing & Releases',
          'Save profiles / characters':'Save Editing & Metadata',
          'PC discovery: Steam / Epic / GOG / Xbox':'PC Discovery & Backups',
          'Tag colors':'Library & Organization',
          'Appearance':'Appearance & Maintenance',
        }
        for label,expected in samples.items():
            self.assertEqual(category_for(label),expected)
        self.assertEqual(len(CATEGORIES),8)
    def test_build_files(self):
        self.assertTrue((ROOT/'Build_Windows.bat').is_file())
        self.assertTrue((ROOT/'Build_Installer.bat').is_file())
        self.assertTrue((ROOT/'ZSaveArchive.iss').is_file())
        s=(ROOT/'ZSaveArchive.iss').read_text()
        self.assertIn('PrivilegesRequired=lowest',s)
        self.assertIn('ArchiveData',s)
        self.assertNotIn('[UninstallDelete]',s)
    def test_tools_connected(self):
        self.assertIn('reorganize_tools_menu(self.tools_btn, self)',(ROOT/'zarchive/ui_v24.py').read_text())

if __name__=='__main__':unittest.main()
