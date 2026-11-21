from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from zarchive.pc_save_discovery import detect_pc_saves, import_detected_saves
from zarchive.upgrade_v13 import ArchiveV13


class PCSaveDiscoveryTests(unittest.TestCase):
    def test_maps_steam_cloud_and_known_paths_and_imports_under_game_names(self):
        with TemporaryDirectory() as scratch:
            root = Path(scratch)
            cloud = root / 'Steam' / 'userdata' / '1234' / '42' / 'remote'
            cloud.mkdir(parents=True)
            (cloud / 'Cloud.sav').write_bytes(b'cloud')
            (cloud.parent / 'remotecache.vdf').write_bytes(b'cache')
            unrelated = cloud.parent.parent / '999' / 'remote'
            unrelated.mkdir(parents=True)
            (unrelated / 'other.sav').touch()
            known = root / 'KnownSave'
            known.mkdir()
            (known / 'Slot.sav').write_bytes(b'known')

            archive = ArchiveV13(root / 'archive')
            try:
                with patch.object(archive, 'steam_installations', return_value={
                    'libraries': [str(root / 'Steam')],
                    'games': [{'appid': '42', 'name': 'Cloud Game'}, {'appid': '17', 'name': 'Known Game'}],
                }), patch.object(archive, 'candidate_paths', return_value=[
                    {'game': 'Known Game', 'path': str(known), 'exists': True}
                ]):
                    rows = detect_pc_saves(archive, 'Steam')

                self.assertEqual([(row['game'], Path(row['path'])) for row in rows],
                                 [('Cloud Game', cloud), ('Known Game', known)])
                self.assertEqual(import_detected_saves(archive, rows), ['Imported', 'Imported'])
                self.assertEqual(import_detected_saves(archive, rows), ['Already archived', 'Already archived'])
                saves = {row['game']: row for row in archive.list_saves(platform='PC')}
                stored = archive.root / saves['Cloud Game']['stored_path']
                self.assertEqual([file.name for file in stored.iterdir()], ['Cloud.sav'])
                self.assertTrue((cloud / 'Cloud.sav').is_file())
            finally:
                archive.close()
