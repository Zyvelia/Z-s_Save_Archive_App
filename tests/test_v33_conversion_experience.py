import tempfile, unittest
from pathlib import Path
from zarchive.iso_converter_v20 import find_7zip, stage_conversion
from test_v20 import write_sfo

class TestConverterExperience(unittest.TestCase):
    def test_autofind_program_files(self):
        with tempfile.TemporaryDirectory() as t:
            exe=Path(t)/'7-Zip'/'7z.exe';exe.parent.mkdir();exe.write_bytes(b'test')
            self.assertEqual(find_7zip(env={'ProgramFiles':t,'PATH':''},registry=[]),exe)
    def test_autofind_path(self):
        with tempfile.TemporaryDirectory() as t:
            exe=Path(t)/'7z.exe';exe.write_bytes(b'test')
            self.assertEqual(find_7zip(env={'PATH':t},registry=[]),exe)
    def test_autofind_absent(self):
        self.assertIsNone(find_7zip(env={'PATH':''},registry=[]))
    def test_stage_progress_messages(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);game=root/'source'/'PS3_GAME';game.mkdir(parents=True)
            write_sfo(game/'PARAM.SFO');tool=root/'tool';tool.mkdir()
            exe=tool/'helper.exe';exe.write_bytes(b'1')
            messages=[]
            result=stage_conversion(game,exe,root/'work',progress=messages.append)
            self.assertEqual(result['title_id'],'BLUS30982')
            self.assertTrue(any('Copying PS3_GAME' in msg for msg in messages))
            self.assertEqual(messages[-1],'Staging completed successfully.')
