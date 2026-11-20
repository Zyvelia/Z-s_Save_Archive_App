import tempfile,unittest
from pathlib import Path
from unittest.mock import MagicMock
from zarchive.transfers_v08 import TransferQueue,ResumablePS3FTP,_remote_meta
from zarchive.workflows_v07 import discover_game_locations

class TransferV08Tests(unittest.TestCase):
 def test_queue_survives_restart(self):
  with tempfile.TemporaryDirectory() as t:
   p=Path(t)/'queue.json';q=TransferQueue(p)
   self.assertTrue(q.add('192.168.1.10',21,'/dev_hdd0/home/00000001/savedata/BLES12345'))
   self.assertFalse(q.add('192.168.1.10',21,'/dev_hdd0/home/00000001/savedata/BLES12345'))
   loaded=TransferQueue(p);self.assertEqual(len(loaded.jobs),1)
   self.assertEqual(loaded.jobs[0]['status'],'pending')
   self.assertTrue(loaded.update('192.168.1.10',21,'/dev_hdd0/home/00000001/savedata/BLES12345','completed'))
   self.assertEqual(TransferQueue(p).jobs[0]['status'],'completed')
 def test_queue_rejects_bad_paths(self):
  with tempfile.TemporaryDirectory() as t:
   q=TransferQueue(Path(t)/'q.json')
   with self.assertRaises(ValueError):q.add('192.168.0.1',21,'/dev_hdd0/etc')
 def test_queue_no_credentials_on_disk(self):
  with tempfile.TemporaryDirectory() as t:
   p=Path(t)/'q.json';q=TransferQueue(p);q.add('192.168.0.1',21,'/dev_hdd0/home/00000001/savedata/TEST')
   self.assertNotIn('password',p.read_text())
 def test_resume_requires_size_and_mdtm(self):
  ftp=MagicMock();ftp.size.return_value=10;ftp.sendcmd.return_value='213 20261116170000'
  self.assertEqual(_remote_meta(ftp,'DATA'),{'size':10,'modified':'20261116170000'})
  ftp.sendcmd.return_value='500 Unsupported';self.assertIsNone(_remote_meta(ftp,'DATA'))
 def test_full_save_download_with_mock_ftp(self):
  with tempfile.TemporaryDirectory() as t:
   api=ResumablePS3FTP('127.0.0.1',staging_root=Path(t)/'staging')
   ftp=MagicMock();ftp.__enter__.return_value=ftp
   ftp.mlsd.return_value=[('PARAM.SFO',{'type':'file'}),('PARAM.PFD',{'type':'file'})]
   data={'PARAM.SFO':b'abc','PARAM.PFD':b'def'}
   ftp.size.side_effect=lambda name:len(data[name]);ftp.sendcmd.return_value='213 20261116170000'
   ftp.retrbinary.side_effect=lambda cmd,cb,**kw:cb(data[cmd.split(' ',1)[1]])
   api.connect=lambda:ftp
   archive=MagicMock();archive.import_save.return_value={'id':'saved'}
   self.assertEqual(api.download_save('/dev_hdd0/home/00000001/savedata/TEST',archive),{'id':'saved'})
   self.assertFalse(any((Path(t)/'staging').iterdir()))
 def test_partial_resume_uses_rest(self):
  with tempfile.TemporaryDirectory() as t:
   api=ResumablePS3FTP('127.0.0.1',staging_root=Path(t)/'staging')
   ftp=MagicMock();ftp.__enter__.return_value=ftp
   ftp.mlsd.return_value=[('PARAM.SFO',{'type':'file'})]
   ftp.size.return_value=6;ftp.sendcmd.return_value='213 20261116170000'
   attempts=[]
   def retr(cmd,cb,**kw):
    attempts.append(kw.get('rest'))
    if len(attempts)==1:
     cb(b'abc');raise ConnectionError('dropped')
    cb(b'def')
   ftp.retrbinary.side_effect=retr;api.connect=lambda:ftp
   archive=MagicMock();archive.import_save.return_value={'id':'ok'}
   path='/dev_hdd0/home/00000001/savedata/TEST'
   with self.assertRaises(ConnectionError):api.download_save(path,archive)
   self.assertEqual(api.download_save(path,archive),{'id':'ok'})
   self.assertEqual(attempts,[None,3])
 def test_missing_metadata_falls_back_to_full(self):
  with tempfile.TemporaryDirectory() as t:
   api=ResumablePS3FTP('127.0.0.1',staging_root=Path(t)/'staging')
   ftp=MagicMock();ftp.__enter__.return_value=ftp
   ftp.mlsd.return_value=[('PARAM.SFO',{'type':'file'})]
   ftp.size.side_effect=Exception('unsupported')
   calls=[]
   ftp.retrbinary.side_effect=lambda cmd,cb,**kw:(calls.append(kw.get('rest')),cb(b'full'))
   api.connect=lambda:ftp
   archive=MagicMock();archive.import_save.return_value={'id':'ok'}
   self.assertEqual(api.download_save('/dev_hdd0/home/00000001/savedata/TEST',archive)['id'],'ok')
   self.assertEqual(calls,[None])

if __name__=='__main__':unittest.main()
