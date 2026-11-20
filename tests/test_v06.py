import tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from zarchive.transfer_v06 import PS3FTP,Entry,validate_path,child_path,pc_save_candidates

class FTPTests(unittest.TestCase):
    def test_validate_navigation(self):
        self.assertEqual(child_path('/dev_hdd0/home','00000001'),'/dev_hdd0/home/00000001')
        self.assertEqual(child_path('/dev_hdd0/home/00000001','savedata'),'/dev_hdd0/home/00000001/savedata')
        self.assertEqual(child_path('/dev_hdd0/home/00000001/savedata','BLUS12345-SAVE'),'/dev_hdd0/home/00000001/savedata/BLUS12345-SAVE')
        for path in ('/dev_hdd0','/dev_hdd0/home/00000001/trophy','/dev_hdd0/home/00000001/savedata/../secret','/dev_hdd0/home/00000001/savedata/foo/other'):
            with self.assertRaises(ValueError):validate_path(path)
        with self.assertRaises(ValueError):child_path('/dev_hdd0/home','../secret')
    def test_reject_invalid_host_and_port(self):
        for host in ('user@host','a/b','bad host',''):
            with self.assertRaises(ValueError):PS3FTP(host)
        with self.assertRaises(ValueError):PS3FTP('127.0.0.1',port=0)
    def test_read_only_browse_mlsd(self):
        class MockFTP:
            def __enter__(self):return self
            def __exit__(self,*a):pass
            def cwd(self,p):self.path=p
            def mlsd(self):return iter([('00000002',{'type':'dir'}),('00000001',{'type':'dir'}),('secret',{'type':'link'})])
        api=PS3FTP('127.0.0.1')
        with patch.object(api,'connect',return_value=MockFTP()):
            self.assertEqual([x.name for x in api.list()],["00000001","00000002"])
    def test_download_mock_and_progress(self):
        class MockFTP:
            def __enter__(self):return self
            def __exit__(self,*a):pass
            def cwd(self,p):self.path=p
            def mlsd(self):return iter([('PARAM.SFO',{'type':'file'}),('DATA.BIN',{'type':'file'})])
            def retrbinary(self,cmd,callback,blocksize=65536):callback(b'hello')
        class MockArchive:
            def import_save(self,p):
                assert (p/'PARAM.SFO').read_bytes()==b'hello'
                return {'id':'sample'}
        api=PS3FTP('127.0.0.1');progress=[]
        with patch.object(api,'connect',return_value=MockFTP()):
            self.assertEqual(api.download_save('/dev_hdd0/home/00000001/savedata/BLES12345',MockArchive(),lambda n,f:progress.append((n,f)))['id'],'sample')
        self.assertEqual(len(progress),2)
    def test_cancellation(self):
        api=PS3FTP('127.0.0.1')
        with self.assertRaises(InterruptedError):api.download_save('/dev_hdd0/home/00000001/savedata/BLES12345',None,cancel=lambda:True)
    def test_pc_candidates_deduplicate(self):
        with tempfile.TemporaryDirectory() as d:
            home=Path(d);(home/'Documents').mkdir();(home/'Saved Games').mkdir()
            rows=pc_save_candidates(home,env={'APPDATA':str(home/'Documents')},steam=[])
            self.assertEqual(len(rows),2)
            self.assertTrue(all('certainty' in row for row in rows))

if __name__=='__main__':unittest.main()
