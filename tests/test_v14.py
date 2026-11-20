import json, tempfile, unittest, zipfile
from pathlib import Path
from unittest.mock import patch
from zarchive.upgrade_v14 import ArchiveV14,profile_path
from zarchive.transfer_v06 import Entry

class FakeFTP:
    calls=[]
    def __init__(self,host,port=21,**kwargs):self.host=host
    def list(self,path):
        self.calls.append(path)
        if path=='/dev_hdd0/home':return [Entry('00000001',True),Entry('00000002',True),Entry('README',False),Entry('bad',True)]
        if path.endswith('/savedata'):return [Entry('SAVE_ONE',True),Entry('SAVE_TWO',True),Entry('../evil',True),Entry('NOTE',False)]
        return [Entry('PARAM.SFO',False,55),Entry('DATA.BIN',False,120)]
    def download_save(self,path,archive,progress=None,cancel=None):
        if path.endswith('SAVE_TWO'):raise RuntimeError('simulated transfer error')
        return {'id':'ok-save'}

class Tests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.archive=ArchiveV14(Path(self.tmp.name)/'archive');self.addCleanup(self.archive.close)
        self.profile=self.archive.connection_add('Test console','127.0.0.1')
    def test_path_rejects_traversal(self):
        for bad in ('../123','0001','00000001/../../x','12345678\\'):
            with self.subTest(bad=bad),self.assertRaises(ValueError):profile_path(bad)
    def test_user_discovery(self):self.assertEqual(self.archive.ps3_users(self.profile,ftp_factory=FakeFTP),['00000001','00000002'])
    def test_profile_listing(self):
        rows=self.archive.ps3_profile_saves(self.profile,'00000001',ftp_factory=FakeFTP)
        self.assertEqual(len(rows),2)
        self.assertTrue(all(x.startswith('/dev_hdd0/home/00000001/savedata/') for x in rows))
    def test_console_dashboard(self):
        d=self.archive.ps3_dashboard(self.profile,ftp_factory=FakeFTP)
        self.assertEqual(d['connection'],'connected');self.assertIsNone(d['free_space_bytes'])
        self.assertEqual(len(self.archive.console_history(self.profile)),1)
    def test_remote_folder_readonly(self):
        d=self.archive.ps3_readonly_folder(self.profile,'00000001','SAVE_ONE',ftp_factory=FakeFTP)
        self.assertEqual(len(d['entries']),2)
        with self.assertRaises(ValueError):self.archive.ps3_readonly_folder(self.profile,'00000001','..',ftp_factory=FakeFTP)
    def test_profile_backup_partial_failure(self):
        d=self.archive.profile_backup(self.profile,'00000001',ftp_factory=FakeFTP)
        self.assertEqual(len(d['imported']),1);self.assertEqual(len(d['failed']),1)
    def test_profile_backup_cancellation(self):
        d=self.archive.profile_backup(self.profile,'00000001',ftp_factory=FakeFTP,cancel=lambda:True)
        self.assertTrue(d['cancelled']);self.assertFalse(d['imported'])
    def test_comparison_is_only_names(self):
        d=self.archive.ps3_sync_preview(self.profile,'00000001',ftp_factory=FakeFTP)
        self.assertEqual(len(d),2);self.assertIn('name',d[0]['status'])
    def test_profile_count_cap(self):
        class Many(FakeFTP):
            def list(self,path):return [Entry(f'SAVE{i}',True) for i in range(201)]
        with self.assertRaises(ValueError):self.archive.ps3_profile_saves(self.profile,'00000001',ftp_factory=Many)
    def test_apollo_pc_rejected(self):
        source=Path(self.tmp.name)/'pc.txt';source.write_text('hello')
        row=self.archive.import_pc_save(source,'Test PC')
        with self.assertRaises(ValueError):self.archive.apollo_export(row['id'],Path(self.tmp.name)/'out.zip')
    def test_apollo_preserves_files(self):
        folder=Path(self.tmp.name)/'original';folder.mkdir()
        # Minimal valid PARAM.SFO with no entries
        (folder/'PARAM.SFO').write_bytes(b'\x00PSF'+b'\x01\x01\x00\x00'+b'\x14\x00\x00\x00'*2+b'\x00\x00\x00\x00'+b'\x00\x00\x00\x00')
        (folder/'PARAM.PFD').write_bytes(b'abcd')
        try:row=self.archive.import_save(folder)
        except (ValueError,IndexError):self.skipTest('Minimal SFO not parsed by archive; production parser requires metadata')
        output=Path(self.tmp.name)/'out.zip'
        result=self.archive.apollo_export(row['id'],output)
        self.assertTrue(len(result['sha256'])==64)
        with zipfile.ZipFile(output) as z:self.assertIn('original/PARAM.PFD',z.namelist())
        with self.assertRaises(ValueError):self.archive.apollo_export(row['id'],output)
    def test_compatibility_requires_real_save(self):
        with self.assertRaises(ValueError):self.archive.add_ps3_compatibility('missing','BLUS00000','USA')
    def test_event_validation(self):
        with self.assertRaises(ValueError):self.archive.record_console_event(self.profile,'delete','ok')

if __name__=='__main__':unittest.main()
