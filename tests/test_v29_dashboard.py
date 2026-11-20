"""Non-GUI packaging checks; these do not substitute for Windows GUI smoke tests."""
from pathlib import Path
import unittest
from PIL import Image

ROOT=Path(__file__).resolve().parents[1]
class DashboardReleaseTests(unittest.TestCase):
    def test_main_launches_new_dashboard(self):
        self.assertIn('zarchive.ui_v29 import main',(ROOT/'main.py').read_text())
    def test_dashboard_retains_previous_window(self):
        src=(ROOT/'zarchive'/'ui_v29.py').read_text()
        self.assertIn('class Window(ExistingWindow)',src)
        self.assertIn('self.classic_content=self.takeCentralWidget()',src)
        self.assertIn('self.shell_stack.addWidget(self.classic_content)',src)
    def test_real_archive_sources(self):
        src=(ROOT/'zarchive'/'ui_v29.py').read_text()
        for api in ('self.archive.dashboard()', 'self.archive.list_saves()', 'self.archive.games(query,platform)'):
            self.assertIn(api,src)
    def test_icon_outputs(self):
        with Image.open(ROOT/'assets'/'ZSaveArchive.png') as im:self.assertGreaterEqual(im.width,512)
        with Image.open(ROOT/'assets'/'ZSaveArchive.ico') as im:self.assertEqual(im.format,'ICO')
    def test_design_reference_in_source(self):
        self.assertTrue((ROOT/'assets'/'Dashboard_Design_Reference.png').is_file())

if __name__=='__main__':unittest.main()
