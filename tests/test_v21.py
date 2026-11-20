import json, tempfile, unittest
from pathlib import Path
from zarchive.converter_output_v21 import (inspect_conversion_output,validate_pkg,builder_command,upload_pkg_ftp)
class FakeFTP:
    def __init__(self):self.files={};self.renamed=[]
    def connect(self,*a,**kw):pass
    def login(self,*a,**kw):pass
    def cwd(self,p):assert p=='/dev_hdd0/packages'
    def nlst(self):return list(self.files)
    def storbinary(self,cmd,stream,blocksize,callback):
        name=cmd.split(' ',1)[1];self.files[name]=stream.read();callback(self.files[name])
    def size(self,name):return len(self.files[name])
    def rename(self,a,b):self.renamed.append((a,b));self.files[b]=self.files.pop(a)
    def delete(self,x):self.files.pop(x,None)
    def quit(self):pass
class V21(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);self.w=self.root/'work';self.w.mkdir()
        (self.w/'conversion_manifest.json').write_text(json.dumps({'title_id':'BLUS30982','title':'Borderlands 2'}))
        self.pkg=self.w/'game.pkg';self.pkg.write_bytes(b'\x7fPKG'+b'0'*100)
    def tearDown(self):self.tmp.cleanup()
    def test_find_pkg(self):self.assertEqual(inspect_conversion_output(self.w)['status'],'packages_found')
    def test_find_folder(self):
        self.pkg.unlink();p=self.w/'BLUS30982';p.mkdir();(p/'PARAM.SFO').write_bytes(b'a')
        self.assertEqual(inspect_conversion_output(self.w)['status'],'folders_found')
    def test_validate(self):self.assertEqual(validate_pkg(self.w,self.pkg)['filename'],'game.pkg')
    def test_reject_invalid_pkg(self):
        self.pkg.write_bytes(b'BAD'+b'0'*100)
        with self.assertRaises(ValueError):validate_pkg(self.w,self.pkg)
    def test_inspection_ignores_invalid_pkg(self):
        self.pkg.write_bytes(b'BAD' + b'0' * 100)
        self.assertEqual(inspect_conversion_output(self.w)['packages'], [])
    def test_reject_outside(self):
        p=self.root/'outside.pkg';p.write_bytes(b'\x7fPKG'+b'x'*100)
        with self.assertRaises(ValueError):validate_pkg(self.w,p)
    def test_no_builder_script(self):
        x=self.root/'builder.bat';x.write_text('echo test')
        with self.assertRaises(ValueError):builder_command(self.w,x)
    def test_ftp_upload(self):
        f=FakeFTP();res=upload_pkg_ftp(self.w,self.pkg,'192.168.1.12',ftp_factory=lambda:f)
        self.assertEqual(res['verified'],'size only');self.assertEqual(f.files['game.pkg'],self.pkg.read_bytes())
    def test_no_overwrite(self):
        f=FakeFTP();f.files['game.pkg']=b'other'
        with self.assertRaises(FileExistsError):upload_pkg_ftp(self.w,self.pkg,'192.168.1.12',ftp_factory=lambda:f)
        self.assertEqual(f.files['game.pkg'],b'other')
    def test_bad_host(self):
        with self.assertRaises(ValueError):upload_pkg_ftp(self.w,self.pkg,'http://evil',ftp_factory=FakeFTP)
if __name__=='__main__':unittest.main()
