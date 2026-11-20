import unittest
from pathlib import Path
from zarchive.app_assets import asset_path

class AssetTests(unittest.TestCase):
    def test_png_and_ico_exist(self):
        for name in ('ZSaveArchive.png', 'ZSaveArchive.ico', 'ZSaveArchive_Original.png'):
            self.assertTrue(asset_path(name).is_file())
            self.assertGreater(asset_path(name).stat().st_size, 100)

    def test_no_unsafe_asset_paths(self):
        with self.assertRaises(ValueError):
            asset_path('../README.md')

    def test_build_scripts_reference_icon(self):
        root = Path(__file__).resolve().parent.parent
        self.assertIn('--icon "assets\\ZSaveArchive.ico"', (root/'Build_Windows.bat').read_text())
        self.assertIn('SetupIconFile=assets\\ZSaveArchive.ico', (root/'ZSaveArchive.iss').read_text())
