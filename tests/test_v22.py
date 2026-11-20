import json
import tempfile
import unittest
from pathlib import Path
from zarchive.homebrew_v22 import CATALOG, inspect_homebrew_pkg, upload_homebrew_pkg, read_history, record_history

class FakeFTP:
    def __init__(self): self.files={}
    def connect(self,*a,**kw):pass
    def login(self,*a,**kw):pass
    def cwd(self,p):assert p=='/dev_hdd0/packages'
    def nlst(self):return list(self.files)
    def storbinary(self,cmd,stream,blocksize,callback):
        data=stream.read();self.files[cmd.split(' ',1)[1]]=data;callback(data)
    def size(self,name):return len(self.files[name])
    def rename(self,a,b):self.files[b]=self.files.pop(a)
    def delete(self,name):self.files.pop(name,None)
    def quit(self):pass

class HomebrewV22(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        self.pkg=self.root/'homebrew.pkg';self.pkg.write_bytes(b'\x7fPKG'+b'x'*100)
    def test_catalog_urls(self):
        self.assertTrue(len(CATALOG)>=5)
        self.assertTrue(all(x['url'].startswith('https://') for x in CATALOG))
    def test_inspection_hash(self):
        info=inspect_homebrew_pkg(self.pkg)
        self.assertEqual(len(info['sha256']),64)
        self.assertEqual(info['filename'],'homebrew.pkg')
    def test_bad_pkg(self):
        self.pkg.write_bytes(b'bad'*100)
        with self.assertRaises(ValueError):inspect_homebrew_pkg(self.pkg)
    def test_symlink_rejected(self):
        link=self.root/'link.pkg'
        try:link.symlink_to(self.pkg)
        except (OSError,NotImplementedError):self.skipTest('No symlinks')
        with self.assertRaises(ValueError):inspect_homebrew_pkg(link)
    def test_upload(self):
        ftp=FakeFTP()
        result=upload_homebrew_pkg(self.pkg,'192.168.1.5',ftp_factory=lambda:ftp)
        self.assertEqual(result['verified'],'size only')
        self.assertEqual(ftp.files['homebrew.pkg'],self.pkg.read_bytes())
    def test_upload_no_overwrite(self):
        ftp=FakeFTP();ftp.files['homebrew.pkg']=b'original'
        with self.assertRaises(FileExistsError):upload_homebrew_pkg(self.pkg,'192.168.1.5',ftp_factory=lambda:ftp)
        self.assertEqual(ftp.files['homebrew.pkg'],b'original')
    def test_upload_invalid_host(self):
        with self.assertRaises(ValueError):upload_homebrew_pkg(self.pkg,'http://bad',ftp_factory=FakeFTP)
    def test_history(self):
        path=self.root/'records.json'
        self.assertEqual(read_history(path),[])
        record_history(path,filename=str(self.pkg),status='uploaded',details='size only')
        self.assertEqual(read_history(path)[0]['filename'],'homebrew.pkg')
    def test_history_corruption(self):
        p=self.root/'bad.json';p.write_text('not-json')
        self.assertEqual(read_history(p),[])
    def test_history_invalid_status(self):
        with self.assertRaises(ValueError):record_history(self.root/'h.json',filename='x',status='unknown')
if __name__=='__main__':unittest.main()
