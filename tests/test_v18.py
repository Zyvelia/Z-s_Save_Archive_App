import json,tempfile,unittest
from pathlib import Path
from zarchive.editor_v18 import ArchiveV18,validate_definition,compare_binary

SCHEMA={"schema_version":1,"id":"example-json","name":"Example Game JSON Editor","game":"Example Game","platforms":["PC"],"file":"save.json","fields":[
    {"key":"money","type":"integer","min":0,"max":999999},
    {"key":"unlocked","type":"boolean"},
    {"key":"name","type":"string","max_length":80}]}

class EditorTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.path=Path(self.tmp.name)
        self.arc=ArchiveV18(self.path/'archive');self.source=self.path/'source';self.source.mkdir()
        self.data={'money':12,'unlocked':False,'name':'Hero'}
        (self.source/'save.json').write_text(json.dumps(self.data),encoding='utf-8')
        self.row=self.arc.import_pc_save(self.source,'Example Game');self.arc.install_editor(SCHEMA)
    def tearDown(self):self.arc.close();self.tmp.cleanup()
    def test_schema_roundtrip(self):
        self.assertEqual(self.arc.editors('Example Game','PC')[0]['id'],'example-json')
    def test_match_rejects_wrong_game(self):
        with self.assertRaises(ValueError):self.arc.inspect_editor(self.row['id'],'unknown')
    def test_preview_fields(self):
        data=self.arc.inspect_editor(self.row['id'],'example-json');self.assertEqual(data['values'],self.data)
    def test_real_export_and_immutable_original(self):
        result=self.arc.edit_copy(self.row['id'],'example-json',{'money':500,'unlocked':True},self.path/'new-copy')
        self.assertEqual(json.loads((self.path/'new-copy'/'save.json').read_text())['money'],500)
        self.assertEqual(json.loads((self.source/'save.json').read_text())['money'],12)
        _,archived=self.arc.save_for_edit(self.row['id'])
        self.assertEqual(json.loads((archived/'save.json').read_text()),self.data)
        self.assertTrue(Path(result['backup']).exists());self.assertEqual(len(self.arc.edit_history(self.row['id'])),1)
        backup=self.arc.backup_history(self.row['id'])[0]
        self.assertTrue(self.arc.verify_backup(backup['id']))
    def test_reject_out_of_range_without_backup(self):
        with self.assertRaises(ValueError):self.arc.edit_copy(self.row['id'],'example-json',{'money':1000000},self.path/'bad')
        self.assertFalse((self.path/'bad').exists());self.assertEqual(self.arc.backup_history(self.row['id']),[])
    def test_reject_undeclared_field(self):
        with self.assertRaises(ValueError):self.arc.edit_copy(self.row['id'],'example-json',{'password':'x'},self.path/'bad')
    def test_reject_overwriting_existing_output(self):
        (self.path/'exists').mkdir()
        with self.assertRaises(FileExistsError):self.arc.edit_copy(self.row['id'],'example-json',{'money':2},self.path/'exists')
    def test_reject_archive_output(self):
        with self.assertRaises(ValueError):self.arc.edit_copy(self.row['id'],'example-json',{'money':2},self.arc.root/'somewhere')
    def test_decrypted_working_folder_keeps_original(self):
        external=self.path/'decrypted';external.mkdir()
        (external/'save.json').write_text('{"money": 30,"unlocked": false,"name":"Hero"}')
        self.arc.edit_copy(self.row['id'],'example-json',{'money':70},self.path/'out',working_folder=external)
        self.assertEqual(json.loads((self.path/'out'/'save.json').read_text())['money'],70)
        self.assertEqual(json.loads((external/'save.json').read_text())['money'],30)
    def test_reject_dangerous_plugin_path(self):
        bad={**SCHEMA,'file':'../secret.json'}
        with self.assertRaises(ValueError):validate_definition(bad)
    def test_reject_code_plugin(self):
        bad={**SCHEMA,'fields':[{'key':'money','type':'python','code':'print(1)'}]}
        with self.assertRaises(ValueError):validate_definition(bad)
    def test_reject_wrong_type(self):
        with self.assertRaises(ValueError):self.arc.edit_copy(self.row['id'],'example-json',{'unlocked':1},self.path/'bad')
    def test_schema_persists(self):
        self.arc.close();self.arc=ArchiveV18(self.path/'archive')
        self.assertEqual(len(self.arc.editors('Example Game','PC')),1)
    def test_missing_file_fails(self):
        working=self.path/'empty';working.mkdir()
        with self.assertRaises(ValueError):self.arc.inspect_editor(self.row['id'],'example-json',working)
    def test_hex_diff_read_only(self):
        a=self.path/"a.bin";b=self.path/"b.bin";a.write_bytes(b"\x00\x01\x02");b.write_bytes(b"\x00\x07\x02")
        result=compare_binary(a,b)
        self.assertEqual(result["differences"],[{"offset":1,"left":"01","right":"07"}])
        self.assertEqual(a.read_bytes(),b"\x00\x01\x02")
    def test_no_change_fails(self):
        with self.assertRaises(ValueError):self.arc.edit_copy(self.row['id'],'example-json',{},self.path/'bad')

if __name__=='__main__':unittest.main()
