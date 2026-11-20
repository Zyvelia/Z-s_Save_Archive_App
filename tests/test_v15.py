import json, tempfile, unittest
from pathlib import Path
from unittest.mock import patch
from zarchive.upgrade_v14 import ArchiveV14
from zarchive.upgrade_v15 import ArchiveV15

class PublishingTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.base=Path(self.tmp.name);self.src=self.base/'source';self.src.mkdir()
        (self.src/'data.sav').write_bytes(b'some normal save bytes')
        self.arc=ArchiveV15(self.base/'library');self.addCleanup(self.arc.close)
        self.sid=self.arc.import_pc_save(self.src,'Test Game')['id']
    def ready(self):
        self.arc.set_visibility(self.sid,'Public');self.arc.conn.execute("UPDATE saves SET status='Verified' WHERE id=?",(self.sid,));self.arc.conn.commit()
    def test_repo_validation_and_persistence(self):
        self.assertEqual(self.arc.set_publishing_repo('Example','My-Saves'),'Example/My-Saves')
        self.assertEqual(self.arc.publishing_repo(),'Example/My-Saves')
        for owner in ('../bad','no space',''):
            with self.assertRaises(ValueError):self.arc.set_publishing_repo(owner,'repo')
    def test_private_cannot_publish(self):
        self.assertFalse(self.arc.publication_preflight(self.sid,privacy_reviewed=True)['ready'])
        with self.assertRaises(ValueError):self.arc.upload_publisher_save('owner','repo',123,self.sid,privacy_reviewed=True,token='test')
    def test_review_and_integrity_required(self):
        self.ready()
        self.assertFalse(self.arc.publication_preflight(self.sid)['ready'])
        self.assertTrue(self.arc.publication_preflight(self.sid,privacy_reviewed=True)['ready'])
        (self.arc.root/self.arc._save(self.sid)['stored_path']/'data.sav').write_bytes(b'changed')
        result=self.arc.publication_preflight(self.sid,privacy_reviewed=True)
        self.assertFalse(result['ready']);self.assertTrue(any('integrity' in s.lower() for s in result['errors']))
    def test_draft_explicit_and_recorded(self):
        with patch.object(self.arc,'github_publish_draft',return_value={'id':34,'html_url':'https://github.com/owner/repo/releases/tag/v1','draft':True}) as mock:
            r=self.arc.create_publisher_draft('owner','repo','v1','One')
        self.assertEqual(r['id'],34);mock.assert_called_once()
        self.assertEqual(self.arc.publication_history()[0]['state'],'draft')
    def test_upload_mock_and_history(self):
        self.ready()
        with patch.object(self.arc,'github_upload_verified_save',return_value={'name':'save.zip','url':'https://github.com/owner/repo/releases/download/tag/save.zip','sha256':'a'*64}) as mock:
            result=self.arc.upload_publisher_save('owner','repo',34,self.sid,privacy_reviewed=True,token='test')
        self.assertEqual(result['name'],'save.zip');mock.assert_called_once()
        self.assertEqual(self.arc.publication_history()[0]['state'],'uploaded')
    def test_no_upload_without_review(self):
        self.ready()
        with patch.object(self.arc,'github_upload_verified_save') as mocked:
            with self.assertRaises(ValueError):self.arc.upload_publisher_save('owner','repo',34,self.sid)
            mocked.assert_not_called()
    def test_public_site_filters_private_and_escapes_html(self):
        self.ready()
        second=self.base/'another';second.mkdir();(second/'a').write_bytes(b'2')
        self.arc.import_pc_save(second,'Secret Game')
        self.arc.conn.execute('UPDATE saves SET notes=? WHERE id=?',('<script>alert(1)</script>',self.sid));self.arc.conn.commit()
        result=self.arc.export_public_site(self.base/'site')
        content=(self.base/'site'/'index.html').read_text()
        self.assertEqual(result['entries'],1)
        self.assertIn('Test Game',content)
        self.assertNotIn('Secret Game',content)
        self.assertNotIn('<script>alert(1)</script>',content)
        self.assertIn('type="search"',content)
        self.assertIn('replaceChildren()',content)
    def test_site_does_not_overwrite(self):
        self.arc.export_public_site(self.base/'site')
        with self.assertRaises(ValueError):self.arc.export_public_site(self.base/'site')
        with self.assertRaises(ValueError):self.arc.export_public_site(self.arc.root/'site')
    def test_migration_from_v14(self):
        self.arc.close()
        self.arc=ArchiveV15(self.base/'library')
        self.assertEqual(self.arc._save(self.sid)['game'],'Test Game')
        self.assertEqual(self.arc.publication_history(),[])
    def test_saved_download_url_whitelisted(self):
        self.ready()
        with self.arc.conn:
            self.arc.conn.execute('INSERT INTO published_assets VALUES (?,?,?,?,?,?,?,?,?,?)',
              ('fake',self.sid,'o/r',3,'t','a','javascript:alert(1)','x','uploaded','2026-01-01'))
        self.arc.export_public_site(self.base/'site')
        self.assertNotIn('javascript:alert(1)',(self.base/'site'/'index.html').read_text())

if __name__=='__main__':unittest.main()
