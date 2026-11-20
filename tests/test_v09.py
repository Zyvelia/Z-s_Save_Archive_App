import tempfile
import unittest
from pathlib import Path
from zarchive.reliability_v09 import inspect_pc_candidate,recoverable_jobs,retry_failed
from zarchive.transfers_v08 import TransferQueue

P='/dev_hdd0/home/00000001/savedata/BLUS12345'

class RecoveryV09Tests(unittest.TestCase):
    def test_recovery_preserves_failure_history(self):
        with tempfile.TemporaryDirectory() as tmp:
            q=TransferQueue(Path(tmp)/'queue.json')
            q.add('192.168.1.9',21,P)
            q.update('192.168.1.9',21,P,'failed','timeout')
            self.assertEqual(len(recoverable_jobs(q,'192.168.1.9',21)),1)
            self.assertEqual(retry_failed(q,'192.168.1.9',21,[P]),1)
            self.assertEqual(retry_failed(q,'192.168.1.9',21,[P]),0)
            self.assertEqual([r['status'] for r in TransferQueue(q.path).jobs],['failed','pending'])
    def test_recovery_does_not_requeue_other_host(self):
        with tempfile.TemporaryDirectory() as tmp:
            q=TransferQueue(Path(tmp)/'q.json');q.add('192.168.1.9',21,P)
            q.update('192.168.1.9',21,P,'failed')
            self.assertEqual(retry_failed(q,'192.168.1.10',21,[P]),0)
    def test_pc_candidate_detects_extensions(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'game').mkdir();(root/'game'/'SAVE1.sav').write_bytes(b'abc')
            r=inspect_pc_candidate(root)
            self.assertEqual(r['status'],'candidate-files-found')
            self.assertEqual(r['file_count'],1)
            self.assertEqual(r['samples'],['game/SAVE1.sav'])
    def test_pc_scan_never_reads_contents(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'big.dat').write_bytes(b'X'*2048)
            r=inspect_pc_candidate(root)
            self.assertEqual(r['bytes'],2048)
    def test_pc_scan_limits(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            for i in range(10):(root/f'{i}.sav').write_bytes(b'x')
            r=inspect_pc_candidate(root,max_files=3)
            self.assertTrue(r['truncated'])
            self.assertEqual(r['file_count'],3)
    def test_pc_scan_skips_symlink(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'original.sav').write_bytes(b'a')
            try:(root/'link.sav').symlink_to(root/'original.sav')
            except (OSError,NotImplementedError):self.skipTest('symlinks unavailable')
            r=inspect_pc_candidate(root)
            self.assertEqual(r['file_count'],1)
            with self.assertRaises(ValueError):inspect_pc_candidate(root/'link.sav')
    def test_pc_empty_unconfirmed(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(inspect_pc_candidate(tmp)['status'],'unconfirmed')

if __name__=='__main__':unittest.main()
