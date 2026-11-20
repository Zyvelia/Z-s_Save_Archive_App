import unittest
from unittest.mock import patch
from zarchive.workflows_v28 import estimate_transfer,firmware_compatibility,cloud_conflict_preview,ExitBackupMonitor,inventory_search,compare_pkgs

class V28Tests(unittest.TestCase):
 def test_eta_insufficient(self):self.assertEqual(estimate_transfer([(0,0),(1,10)],100)['status'],'insufficient_data')
 def test_eta_steady(self):
  r=estimate_transfer([(i,i*100) for i in range(12)],1000)
  self.assertEqual(r['eta_seconds'],10);self.assertEqual(r['confidence'],'high')
 def test_eta_zero_reject(self):
  with self.assertRaises(ValueError):estimate_transfer([], -1)
 def test_eta_stalled(self):self.assertEqual(estimate_transfer([(i,0) for i in range(9)],1)['status'],'insufficient_data')
 def test_compat_unverified(self):self.assertEqual(firmware_compatibility(firmware='4.91')['compatibility'],'unverified')
 def test_cloud(self):self.assertFalse(cloud_conflict_preview('C:/Games',launcher='Steam',exists=True)['safe_for_unattended_restore'])
 def test_cloud_missing(self):self.assertFalse(cloud_conflict_preview('x',exists=False)['destination_exists'])
 def test_exit(self):
  calls=[];m=ExitBackupMonitor('game.exe',lambda:calls.append('ok'),minimum_interval=30)
  self.assertEqual(m.check(['game.exe'],now=0),'running')
  self.assertEqual(m.check([],now=1),'backup_triggered');self.assertEqual(calls,['ok'])
  self.assertEqual(m.check([],now=2),'idle')
 def test_relaunch_throttle(self):
  calls=[];m=ExitBackupMonitor('game.exe',lambda:calls.append('ok'),minimum_interval=30)
  for t,names in [(0,['game.exe']),(1,[]),(2,['game.exe']),(3,[])]:m.check(names,now=t)
  self.assertEqual(len(calls),1)
 def test_inventory(self):self.assertEqual(inventory_search([{'name':'Apollo'},{'name':'webMAN'}],'apollo'),[{'name':'Apollo'}])
 def test_pkg_invalid(self):self.assertFalse(compare_pkgs(['/missing.pkg'])[0]['valid_header'])
 def test_pkg_duplicates(self):
  info={'sha256':'a'*64,'bytes':128,'package_type':1,'header_revision':0}
  with patch('zarchive.workflows_v28.inspect_pkg_metadata',return_value=info):
   rows=compare_pkgs(['a.pkg','b.pkg']);self.assertEqual(rows[1]['duplicate_of'],'a.pkg')
 def test_pkg_limit(self):
  with self.assertRaises(ValueError):compare_pkgs(['x']*101)
 def test_process_invalid(self):
  with self.assertRaises(ValueError):ExitBackupMonitor('../game.exe',lambda:None)

if __name__=='__main__':unittest.main()
