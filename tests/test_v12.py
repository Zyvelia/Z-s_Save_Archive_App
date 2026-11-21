import tempfile, unittest
from pathlib import Path
from zarchive.upgrade_v12 import ArchiveV12, inspect_source

class V12Tests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.p=Path(self.tmp.name)
        self.save=self.p/'source';self.save.mkdir()
        (self.save/'game.sav').write_bytes(b'abc')
        self.archive=ArchiveV12(self.p/'archive')
        self.sid=self.archive.import_pc_save(self.save,'Test Game')['id']
    def tearDown(self):self.archive.close();self.tmp.cleanup()
    def test_preflight(self):
        self.assertTrue(self.archive.restore_conflict_check(self.sid,self.p/'new')['safe'])
        self.assertFalse(self.archive.restore_conflict_check(self.sid,self.save)['safe'])
    def test_states(self):
        self.assertEqual(self.archive.workflow_state(self.sid),'Working')
        self.archive.set_workflow_state(self.sid,'Testing')
        self.assertEqual(self.archive.workflow_state(self.sid),'Testing')
        with self.assertRaises(ValueError):self.archive.set_workflow_state(self.sid,'unknown')
    def test_inspect(self):
        x=self.archive.inspect_archived(self.sid)
        self.assertEqual(x['file_count'],1)
        self.assertEqual(x['total_bytes'],3)
        self.assertEqual(self.archive.inspect_archived(self.sid)['file_count'],1)
    def test_storage(self):
        r=self.archive.storage_report()
        self.assertEqual(r['games'][0]['saves'],1)
        self.assertGreater(r['archive_disk_bytes'],0)
    def test_hex_diff(self):
        (self.save/'game.sav').write_bytes(b'aXc')
        other=self.archive.import_pc_save(self.save,'Test Game')['id']
        d=self.archive.hex_difference(self.sid,other,'game.sav')
        self.assertEqual(d['differences'][0]['offset'],1)
        with self.assertRaises(ValueError):self.archive.hex_difference(self.sid,other,'../secret')
    def test_symlink_reject(self):
        link=self.p/'link'
        try:link.symlink_to(self.save,target_is_directory=True)
        except (OSError,NotImplementedError):self.skipTest('Symlink creation unavailable')
        with self.assertRaises(ValueError):inspect_source(link)
    def test_invalid_sfo(self):
        with self.assertRaises(ValueError):self.archive.ps3_sfo(self.sid)
    def test_preview_bound(self):
        with self.assertRaises(ValueError):inspect_source(self.save,max_bytes=1)
