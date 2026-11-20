import tempfile,unittest
from pathlib import Path
from zarchive.game_targets_v19 import GAME_TARGETS,target_by_id,game_matches,matching_saves,sample_inventory

class GameTargetsTests(unittest.TestCase):
    def test_borderlands2_first(self):self.assertEqual(GAME_TARGETS[0]['id'],'borderlands-2')
    def test_unique_ids(self):self.assertEqual(len({g['id'] for g in GAME_TARGETS}),len(GAME_TARGETS))
    def test_all_are_placeholders(self):self.assertTrue(all(g['status'] in ('Planned','Awaiting decrypted sample') for g in GAME_TARGETS))
    def test_no_executable_definition(self):self.assertTrue(all('fields' not in g and 'file' not in g for g in GAME_TARGETS))
    def test_match_alias(self):self.assertTrue(game_matches(target_by_id('borderlands-2'),'BL2','PS3'))
    def test_no_cross_platform(self):self.assertFalse(game_matches(target_by_id('borderlands-2'),'BL2','PC'))
    def test_no_confuse_bl1_bl2(self):self.assertFalse(game_matches(target_by_id('borderlands-2'),'Borderlands','PS3'))
    def test_unknown_id(self):self.assertIsNone(target_by_id('no-such-game'))
    def test_matching_saves(self):
        rows=[{'game':'Borderlands 2','platform':'PS3'},{'game':'Borderlands','platform':'PS3'},{'game':'BL2','platform':'PC'}]
        self.assertEqual(len(matching_saves(rows,'borderlands-2')),1)
    def test_empty_inventory(self):
        with tempfile.TemporaryDirectory() as d:self.assertEqual(sample_inventory(d)['file_count'],0)
    def test_inventory_lists_structure(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d);(p/'data').mkdir();(p/'data'/'SAVEDATA').write_bytes(b'123')
            result=sample_inventory(d);self.assertEqual(result['files'],[{'relative_path':'data/SAVEDATA','size_bytes':3}])
    def test_inventory_bounded(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d)/'x').write_bytes(b'123')
            with self.assertRaises(ValueError):sample_inventory(d,max_bytes=2)
