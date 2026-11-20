import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from zarchive.console_v27 import (check_ftp,discover_ps3_hosts,read_ftp_storage,
    conversion_preflight,inspect_pkg_title,summarize_transfer,save_diagnostic_report)

class SocketFake:
    def __enter__(self):return self
    def __exit__(self,*args):pass

class V27Tests(unittest.TestCase):
    def test_local_ftp_reachable(self):
        row=check_ftp('192.168.1.20',dial=lambda *a,**kw:SocketFake())
        self.assertEqual(row['state'],'reachable')
        self.assertIn('not verified',row['note'])
    def test_unreachable(self):
        def fail(*args,**kw):raise OSError('closed')
        self.assertEqual(check_ftp('10.0.0.3',dial=fail)['state'],'unreachable')
    def test_public_address_rejected(self):
        with self.assertRaises(ValueError):check_ftp('8.8.8.8')
    def test_subnet_capped(self):
        with self.assertRaises(ValueError):discover_ps3_hosts('192.168.1.0/24',probe=lambda *a,**kw:None)
    def test_discovery_is_opt_in_and_bounded(self):
        seen=[]
        def fake(host,**kwargs):
            seen.append(host)
            return {'host':host,'state':'reachable' if host.endswith('.1') else 'unreachable'}
        row=discover_ps3_hosts('192.168.7.0/29',probe=fake)
        self.assertEqual(row['scanned'],6)
        self.assertEqual(len(row['reachable']),1)
        self.assertEqual(len(seen),6)
    def test_bad_subnet_rejected(self):
        for subnet in ('8.8.8.0/29','2001:db8::/126'):
            with self.subTest(subnet=subnet),self.assertRaises(ValueError):discover_ps3_hosts(subnet)
    def test_missing_tools_reported(self):
        row=conversion_preflight('missing.iso','missing.exe','/tmp/not-yet-created')
        self.assertFalse(row['ready_to_stage']);self.assertTrue(row['errors'])
    def test_iso_with_signature_and_no_extractor(self):
        with tempfile.TemporaryDirectory() as d:
            src=Path(d)/'game.iso';src.write_bytes(b'\0'*0x8000+b'CD001'+b'\0'*100)
            helper=Path(d)/'helper.exe';helper.write_bytes(b'PE')
            row=conversion_preflight(src,helper,Path(d)/'new-stage',free_bytes=10**10)
            self.assertIn('7z.exe', ' '.join(row['errors']))
            self.assertEqual(row['source_kind'],'iso')
    def test_existing_work_folder_refused(self):
        with tempfile.TemporaryDirectory() as d:
            row=conversion_preflight('missing.iso','missing.exe',d)
            self.assertTrue(any('NEW' in x for x in row['errors']))
    def test_disk_estimate_warning(self):
        with tempfile.TemporaryDirectory() as d:
            src=Path(d)/'game.iso';src.write_bytes(b'\0'*0x8000+b'CD001')
            tool=Path(d)/'tool.exe';tool.write_bytes(b'PE')
            extractor=Path(d)/'7z.exe';extractor.write_bytes(b'PE')
            row=conversion_preflight(src,tool,Path(d)/'stage',extractor=extractor,free_bytes=10)
            self.assertTrue(row['ready_to_stage'])
            self.assertTrue(row['warnings'])
    def test_pkg_header_and_filename_hint(self):
        with tempfile.TemporaryDirectory() as d:
            pkg=Path(d)/'BLUS30982_Game.pkg';pkg.write_bytes(b'\x7fPKG'+b'\0'*64)
            row=inspect_pkg_title(pkg)
            self.assertEqual(row['title_id_hint'],'BLUS30982')
            self.assertFalse(row['title_id_verified'])
    def test_bad_pkg_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            pkg=Path(d)/'bad.pkg';pkg.write_bytes(b'abcd')
            with self.assertRaises(ValueError):inspect_pkg_title(pkg)
    def test_transfer_summary(self):
        row=summarize_transfer([{'time':1,'bytes':0},{'time':3,'bytes':200,'total':400}])
        self.assertEqual(row['rate_bytes_per_second'],100)
        self.assertEqual(row['eta_seconds'],2)
    def test_transfer_unknown_total(self):
        row=summarize_transfer([{'time':0,'bytes':0},{'time':1,'bytes':99}])
        self.assertIsNone(row['eta_seconds'])
    def test_transfer_invalid_sample(self):
        with self.assertRaises(ValueError):summarize_transfer([{'time':3,'bytes':100},{'time':2,'bytes':101}])
    def test_diagnostic_export_is_redacted(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'report.json'
            save_diagnostic_report(p,{'host':'10.0.0.1','state':'reachable','password':'secret','ftp_status':'private banner'})
            blob=p.read_text();self.assertNotIn('secret',blob);self.assertNotIn('private banner',blob)
            self.assertEqual(json.loads(blob)['state'],'reachable')
            with self.assertRaises(ValueError):save_diagnostic_report(p,{})
    def test_read_only_ftp_metadata(self):
        class FakeFTP:
            def connect(self,*args,**kwargs):pass
            def login(self,*args,**kwargs):pass
            def sendcmd(self,c):return '215 UNIX' if c=='SYST' else '211 status'
            def quit(self):pass
        row=read_ftp_storage('192.168.1.2',factory=FakeFTP)
        self.assertIsNone(row['free_bytes'])
        self.assertIn('215',row['ftp_system'])

if __name__=='__main__':unittest.main()
