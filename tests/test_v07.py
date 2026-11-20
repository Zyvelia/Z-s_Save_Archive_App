import tempfile,unittest
from pathlib import Path
from unittest.mock import Mock
from zarchive.enhanced import EnhancedArchive
from zarchive.workflows_v07 import discover_game_locations,download_with_retry,export_many

class V07Tests(unittest.TestCase):
    def test_discovery_specific_existing_only(self):
        with tempfile.TemporaryDirectory() as d:
            home=Path(d)
            folder=home/'AppData'/'Roaming'/'StardewValley'/'Saves'
            folder.mkdir(parents=True)
            games=[{'name':'Stardew Valley'},{'name':'Other Game'}]
            rows=discover_game_locations(home,env={},games=games)
            self.assertEqual(len(rows),1)
            self.assertEqual(rows[0]['name'],'Stardew Valley')
            self.assertIn('candidate',rows[0]['certainty'])
    def test_retry_restarts_after_connection_failure(self):
        api=Mock();api.download_save.side_effect=[ConnectionError('broken'),{'id':'ok'}]
        notify=[]
        result=download_with_retry(api,'remote',object(),max_attempts=2,sleep=lambda n:None,notify=lambda a,m:notify.append(a))
        self.assertEqual(result['id'],'ok')
        self.assertEqual(api.download_save.call_count,2)
        self.assertEqual(notify,[1])
    def test_invalid_and_cancel_never_retry(self):
        api=Mock();api.download_save.side_effect=ValueError('invalid save')
        with self.assertRaises(ValueError):download_with_retry(api,'remote',object(),sleep=lambda n:None)
        self.assertEqual(api.download_save.call_count,1)
        api.download_save.reset_mock()
        with self.assertRaises(InterruptedError):download_with_retry(api,'remote',object(),cancel=lambda:True,sleep=lambda n:None)
        api.download_save.assert_not_called()
    def test_retry_bounded(self):
        api=Mock();api.download_save.side_effect=TimeoutError('timeout')
        with self.assertRaises(TimeoutError):download_with_retry(api,'remote',object(),max_attempts=3,sleep=lambda n:None)
        self.assertEqual(api.download_save.call_count,3)
    def test_batch_only_public_verified_and_no_overwrites(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);archive=EnhancedArchive(root/'archive')
            try:
                a=root/'a.sav';b=root/'b.sav';a.write_text('a');b.write_text('b')
                s1=archive.import_pc_save(a,'Game A')['id'];s2=archive.import_pc_save(b,'Game B')['id']
                archive.set_visibility(s1,'Public')
                archive.update(s1,category='Legit',label='Test',notes='',status='Verified')
                results,manifest=export_many(archive,[s1,s2],root/'out')
                self.assertEqual([r['status'] for r in results],['exported','skipped'])
                self.assertTrue(manifest.exists());self.assertEqual(len(list((root/'out').glob('*.zip'))),1)
                # Never overwrite an existing ZIP on a repeated batch request.
                results2,_=export_many(archive,[s1],root/'out')
                self.assertEqual(results2[0]['status'],'skipped')
            finally:archive.close()

if __name__=='__main__':unittest.main()
