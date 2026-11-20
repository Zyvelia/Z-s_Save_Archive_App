import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from zarchive.retail2pkg_v31 import REQUIRED_FILES, inspect_retail2pkg_folder, prepare_retail2pkg_handoff

class Retail2PkgTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.tools=self.root/'Retail2Pkg';self.tools.mkdir()
        for name in REQUIRED_FILES:(self.tools/name).write_bytes(b'test')
    def test_detects_supplied_layout(self):
        info=inspect_retail2pkg_folder(self.tools)
        self.assertEqual(Path(info['helper']).name,'CFW2OFW_Helper.exe')
    def test_missing_tool_rejected(self):
        (self.tools/'makepkg1.exe').unlink()
        with self.assertRaisesRegex(ValueError,'makepkg1.exe'):inspect_retail2pkg_folder(self.tools)
    def test_missing_conversion_rejected_without_destination(self):
        work=self.root/'work';work.mkdir();(work/'conversion_manifest.json').write_text('{}')
        with self.assertRaises(ValueError):prepare_retail2pkg_handoff(work,self.tools,self.root/'out')
        self.assertFalse((self.root/'out').exists())
    def test_existing_output_refused(self):
        target=self.root/'out';target.mkdir()
        with self.assertRaises(FileExistsError):prepare_retail2pkg_handoff(self.root,self.tools,target)
    def test_success_is_copy_and_never_executes_batch(self):
        work=self.root/'work';work.mkdir();(work/'conversion_manifest.json').write_text('{"title":"Test"}')
        parent=work/'BLUS12345';parent.mkdir()
        for name in ('NPUB12345','BLUS12345'):
            folder=parent/name;folder.mkdir();(folder/'PARAM.SFO').write_bytes(b'fixture');(folder/'DATA.BIN').write_bytes(b'abcd')
        with patch('zarchive.retail2pkg_v31.inspect_conversion_output',return_value={
            'folders':[{'relative_path':'BLUS12345/NPUB12345'},{'relative_path':'BLUS12345/BLUS12345'}]}):
            out=prepare_retail2pkg_handoff(work,self.tools,self.root/'out')
        self.assertTrue((self.root/'out'/'Retail2Pkg.bat').exists())
        self.assertEqual((parent/'BLUS12345'/'DATA.BIN').read_bytes(),b'abcd')
        self.assertTrue((self.root/'out'/'BLUS12345'/'NPUB12345'/'DATA.BIN').exists())
        self.assertIn('MOVES and DELETES',out['instructions'])

    def test_flat_converted_pair_is_arranged_for_builder(self):
        work = self.root / 'work'
        work.mkdir()
        (work / 'conversion_manifest.json').write_text('{"title_id":"BLUS12345"}')
        for title in ('NPUB12345', 'BLUS12345'):
            folder = work / title
            folder.mkdir()
            (folder / 'PARAM.SFO').write_bytes(b'fixture')
        target = self.root / 'out'
        prepare_retail2pkg_handoff(work, self.tools, target)
        for title in ('NPUB12345', 'BLUS12345'):
            self.assertTrue((target / 'BLUS12345' / title / 'PARAM.SFO').is_file())
            self.assertTrue((work / title / 'PARAM.SFO').is_file())

    def test_single_title_folder_is_reported_as_incomplete(self):
        work = self.root / 'work'
        game = work / 'NPUB12345'
        game.mkdir(parents=True)
        (work / 'conversion_manifest.json').write_text('{"title_id":"BLUS12345"}')
        (game / 'PARAM.SFO').write_bytes(b'fixture')
        target = self.root / 'out'
        with self.assertRaisesRegex(ValueError, r'matching disc-ID patch folder.*NPUB12345'):
            prepare_retail2pkg_handoff(work, self.tools, target)
        self.assertFalse(target.exists())

if __name__=='__main__':unittest.main()
