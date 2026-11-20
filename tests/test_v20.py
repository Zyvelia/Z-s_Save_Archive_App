import tempfile, unittest, struct
from pathlib import Path
from zarchive.iso_converter_v20 import inspect_game, inspect_iso, stage_conversion, helper_command

# Minimal valid PSF fixture compatible with real parser.
def write_sfo(path, title_id='BLUS30982'):
    keys=b'TITLE_ID\0TITLE\0'
    vals=title_id.encode()+b'\0'+b'Borderlands 2\0'
    start=20+2*16
    table=struct.pack('<HHIII',0,0x204,len(title_id)+1,len(title_id)+1,0)
    table+=struct.pack('<HHIII',9,0x204,14,14,len(title_id)+1)
    path.write_bytes(struct.pack('<4sIIII',b'\0PSF',0x101,start,start+len(keys),2)+table+keys+vals)

class ConverterTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.game=self.root/'game'/'PS3_GAME';self.game.mkdir(parents=True)
        write_sfo(self.game/'PARAM.SFO')
        (self.game/'USRDIR').mkdir()
        (self.game/'USRDIR'/'EBOOT.BIN').write_bytes(b'sample original')
        self.tools=self.root/'tools';self.tools.mkdir()
        self.exe=self.tools/'CFW2OFW Helper.exe';self.exe.write_bytes(b'dummy-exe')
    def tearDown(self):self.temp.cleanup()
    def test_game_detection(self):
        info=inspect_game(self.root/'game')
        self.assertEqual(info['title_id'],'BLUS30982')
    def test_staging_preserves_original(self):
        work=self.root/'workspace'
        data=stage_conversion(self.root/'game',self.exe,work)
        self.assertEqual(data['title_id'],'BLUS30982')
        self.assertEqual((self.game/'USRDIR'/'EBOOT.BIN').read_bytes(),b'sample original')
        self.assertEqual((work/'PS3_GAME'/'USRDIR'/'EBOOT.BIN').read_bytes(),b'sample original')
        self.assertEqual(helper_command(work,self.exe.name),[str(work/self.exe.name)])
    def test_no_overwrite(self):
        work=self.root/'workspace';work.mkdir()
        with self.assertRaises(FileExistsError):stage_conversion(self.root/'game',self.exe,work)
    def test_reject_bad_title(self):
        write_sfo(self.game/'PARAM.SFO','BAD1234')
        with self.assertRaises(ValueError):inspect_game(self.game)
    def test_reject_symlinks(self):
        try:(self.game/'link').symlink_to(self.tools, target_is_directory=True)
        except OSError:self.skipTest('Symlinks unavailable')
        with self.assertRaises(ValueError):stage_conversion(self.root/'game',self.exe,self.root/'workspace')
    def test_iso_validation(self):
        iso=self.root/'bad.iso';iso.write_bytes(b'not an ISO')
        with self.assertRaises(ValueError):inspect_iso(iso)
    def test_iso_requires_extractor(self):
        iso=self.root/'disc.iso';iso.write_bytes(b'X'*32768 + b'CD001')
        with self.assertRaises(ValueError):stage_conversion(iso,self.exe,self.root/'workspace')
    def test_work_never_nested_in_game(self):
        with self.assertRaises(ValueError):stage_conversion(self.root/'game',self.exe,self.game/'output')
