import tempfile
import unittest
from pathlib import Path
from zarchive.iso_converter_v20 import next_workspace, stage_conversion
from test_v20 import write_sfo

class TestReusableWorkspace(unittest.TestCase):
    def test_existing_parent_works_and_retains_old_runs(self):
        with tempfile.TemporaryDirectory() as t:
            base = Path(t)
            source=base/'source'/'PS3_GAME';source.mkdir(parents=True)
            write_sfo(source/'PARAM.SFO')
            tool=base/'tool';tool.mkdir()
            helper=tool/'helper.exe';helper.write_bytes(b'exe')
            parent=base/'PS3_XMB_Conversion';parent.mkdir()
            old=parent/'previous_run';old.mkdir();(old/'keep.txt').write_text('keep')
            dest=next_workspace(parent,source,timestamp='20261120_030000')
            result=stage_conversion(source,helper,dest)
            self.assertEqual(Path(result['workspace']),dest)
            self.assertEqual((old/'keep.txt').read_text(),'keep')
            self.assertTrue((dest/'conversion_manifest.json').is_file())
            second=next_workspace(parent,source,timestamp='20261120_030000')
            self.assertNotEqual(dest,second)
            self.assertTrue(second.name.endswith('_001'))
            result2=stage_conversion(source,helper,second)
            self.assertTrue(Path(result2['workspace']).exists())
            self.assertTrue(dest.exists())

    def test_nonexistent_parent_is_not_created_during_selection(self):
        with tempfile.TemporaryDirectory() as t:
            parent=Path(t)/'new_parent'
            child=next_workspace(parent, 'mygame.iso',timestamp='20261120_030001')
            self.assertEqual(child.parent,parent)
            self.assertFalse(parent.exists())

    def test_existing_workspace_remains_protected(self):
        with tempfile.TemporaryDirectory() as t:
            base=Path(t);base.joinpath('run').mkdir()
            helper=base/'helper.exe';helper.write_bytes(b'exe')
            with self.assertRaises(FileExistsError):
                stage_conversion('anything',helper,base/'run')

    def test_not_a_directory_parent(self):
        with tempfile.TemporaryDirectory() as t:
            parent=Path(t)/'file';parent.write_text('x')
            with self.assertRaises(ValueError):
                next_workspace(parent,'game.iso')

    def test_timestamp_rejects_bad_input(self):
        with tempfile.TemporaryDirectory() as t:
            with self.assertRaises(ValueError):
                next_workspace(t,'game.iso',timestamp='../../bad')

if __name__=='__main__': unittest.main()
