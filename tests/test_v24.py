import json,tempfile,unittest,hashlib
from pathlib import Path
from zarchive.homebrew_v24 import (set_app_record,read_app_records,offline_catalog,inspect_pkg_metadata,
  batch_inspect_pkgs,local_upload_space_check,installation_checklist,release_note_text,update_compatibility_record)

class TestV24(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
  self.root=Path(self.tmp.name);self.records=self.root/'records.json'
 def test_record_and_favorite(self):
  set_app_record(self.records,'Apollo Save Tool',installed_version='v1.0',favorite=True,watch=True)
  data=read_app_records(self.records)['Apollo Save Tool'];self.assertEqual(data['installed_version'],'v1.0');self.assertTrue(data['watch'])
 def test_records_persist(self):
  set_app_record(self.records,'webMAN MOD',installed_version='1.5')
  set_app_record(self.records,'webMAN MOD',favorite=True)
  self.assertEqual(read_app_records(self.records)['webMAN MOD']['installed_version'],'1.5')
 def test_unknown_app(self):
  with self.assertRaises(ValueError):set_app_record(self.records,'Unapproved application',favorite=True)
 def test_long_version_rejected(self):
  with self.assertRaises(ValueError):set_app_record(self.records,'Apollo Save Tool',installed_version='X'*500)
 def test_offline_fallback(self):
  info=offline_catalog(self.root/'missing.json');self.assertTrue(info['bundled']);self.assertGreaterEqual(len(info['items']),6)
 def test_offline_snapshot(self):
  p=self.root/'catalog.json';offline_catalog(p,refresh=True)
  self.assertTrue(p.exists());self.assertFalse(offline_catalog(p)['bundled'] if 'bundled' in offline_catalog(p) else False)
 def test_corrupt_catalog_fallback(self):
  p=self.root/'catalog.json';p.write_text('{bad',encoding='utf8');self.assertTrue(offline_catalog(p)['bundled'])
 def test_pkg_too_short(self):
  p=self.root/'foo.pkg';p.write_bytes(b'\x7fPKG')
  with self.assertRaises(ValueError):inspect_pkg_metadata(p)
 def test_batch_failure_isolated(self):
  rows=batch_inspect_pkgs([self.root/'missing.pkg',self.root/'other.pkg']);self.assertEqual(len(rows),2);self.assertFalse(rows[0]['ok'])
 def test_batch_limit(self):
  with self.assertRaises(ValueError):batch_inspect_pkgs([self.root/'missing.pkg']*151)
 def test_local_space_does_not_claim_ps3(self):
  p=self.root/'foo.pkg';p.write_bytes(b'\x7fPKG'*5)
  item=local_upload_space_check(p,self.root/'staging',reserve_bytes=0)
  self.assertTrue(item['local_staging_ok']);self.assertFalse(item['ps3_capacity_verified'])
 def test_install_checklist(self):
  self.assertEqual(len(installation_checklist('Apollo Save Tool')),5)
 def test_release_notes(self):
  self.assertEqual(release_note_text({'body':'hi'}),'hi')
 def test_version_comparison(self):
  self.assertEqual(update_compatibility_record('v1','1')['status'],'matching_tag')
  self.assertEqual(update_compatibility_record('','1')['status'],'unknown')
if __name__=='__main__':unittest.main()

class TestBandwidth(unittest.TestCase):
 def test_invalid_bandwidth_rejected(self):
  from zarchive.homebrew_v23 import download_queued_asset
  for value in (0,1,1023,-42, 200*1024*1024+1, 'fast'):
   with self.assertRaises(ValueError):
    download_queued_asset('missing.json','missing','/tmp',bandwidth_limit=value)
