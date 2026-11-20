import json
import tempfile
import unittest
from pathlib import Path
from zarchive.trueancestor_v25 import prepare_trueancestor

class TrueAncestorTests(unittest.TestCase):
    def setUp(self):
        self.t=tempfile.TemporaryDirectory(); self.addCleanup(self.t.cleanup)
        self.base=Path(self.t.name);self.workspace=self.base/'workspace';self.workspace.mkdir()
        (self.workspace/'conversion_manifest.json').write_text(json.dumps({'title':'Test Game','title_id':'BLUS30982'}))
        self.game=self.workspace/'BLUS30982';self.game.mkdir();(self.game/'PARAM.SFO').write_bytes(b'placeholder')
    def test_handoff_preserves_original(self):
        out=prepare_trueancestor(self.workspace,self.base/'handoff')
        self.assertEqual(out['folders'],['BLUS30982'])
        self.assertEqual((self.base/'handoff'/'game'/'BLUS30982'/'PARAM.SFO').read_bytes(),b'placeholder')
        self.assertEqual((self.game/'PARAM.SFO').read_bytes(),b'placeholder')
    def test_refuses_overwrite(self):
        out=self.base/'handoff';out.mkdir()
        with self.assertRaises(FileExistsError):prepare_trueancestor(self.workspace,out)
    def test_refuses_nested_destination(self):
        with self.assertRaises(ValueError):prepare_trueancestor(self.workspace,self.workspace/'handoff')
    def test_missing_converted_output(self):
        (self.game/'PARAM.SFO').unlink()
        with self.assertRaises(ValueError):prepare_trueancestor(self.workspace,self.base/'handoff')
    def test_refuses_symlinks(self):
        try:(self.game/'external').symlink_to(self.base,target_is_directory=True)
        except (OSError,NotImplementedError):self.skipTest('symlinks unavailable')
        with self.assertRaises(ValueError):prepare_trueancestor(self.workspace,self.base/'handoff')
