import tempfile
import unittest
from pathlib import Path
from zarchive.appdata_v34 import AppPaths

class StorageTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.base=Path(self.tmp.name)
        self.paths=AppPaths.discover({'APPDATA':str(self.base/'roam'),'LOCALAPPDATA':str(self.base/'local')},self.base)
    def test_layout(self):
        self.paths.initialize()
        self.assertTrue((self.paths.local/'logs').is_dir())
        self.assertTrue((self.paths.roaming/'presets').is_dir())
    def test_settings_roundtrip_and_whitelist(self):
        self.paths.remember_path('extractor','C:/7z.exe')
        self.assertEqual(self.paths.path('extractor'),'C:/7z.exe')
        with self.assertRaises(ValueError):self.paths.remember_path('password','secret')
    def test_cache_clear_preserves_data(self):
        self.paths.initialize()
        (self.paths.local/'cache'/'covers'/'x.png').write_bytes(b'abc')
        (self.paths.local/'logs'/'log.txt').write_text('keep')
        self.assertEqual(self.paths.clear_cache(),3)
        self.assertTrue((self.paths.local/'logs'/'log.txt').exists())
    def test_import_is_non_destructive_and_no_overwrite(self):
        source=self.base/'old.json';source.write_text('{"theme": "dark"}')
        self.assertTrue(self.paths.import_legacy_json(source))
        self.assertFalse(self.paths.import_legacy_json(source))
        self.assertTrue(source.exists())
    def test_invalid_json_not_overwritten_on_read(self):
        self.paths.initialize();self.paths.settings.write_text('bad')
        self.assertEqual(self.paths.load_settings(),{})
        self.assertEqual(self.paths.settings.read_text(),'bad')
    def test_cache_rejects_symlink(self):
        self.paths.initialize()
        a=self.paths.local/'cache'/'shortcut'
        try:a.symlink_to(self.base, target_is_directory=True)
        except (OSError,NotImplementedError):self.skipTest('Symlinks unavailable')
        with self.assertRaises(ValueError):self.paths.clear_cache()
