import tempfile,unittest,time,threading
from pathlib import Path
from zarchive.upgrade_v17 import ArchiveV17,JobRunner

class V17Tests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)/'archive';self.a=ArchiveV17(self.root)
    def tearDown(self):self.a.close();self.tmp.cleanup()
    def test_default_order(self):self.assertEqual(self.a.dashboard_order(),['stats','recent','quick','storage'])
    def test_widget_order(self):
        order=['quick','recent','stats','storage'];self.a.set_dashboard_order(order);self.assertEqual(self.a.dashboard_order(),order)
    def test_bad_order(self):
        for o in (['stats'],['stats']*4,['stats','recent','quick','unsafe']):
            with self.assertRaises(ValueError):self.a.set_dashboard_order(o)
    def test_preferences_roundtrip(self):
        self.a.set_ui_setting('library_page_size',200);self.assertEqual(self.a.ui_setting('library_page_size'),200)
    def test_bad_settings(self):
        with self.assertRaises(ValueError):self.a.set_ui_setting('library_page_size','100')
        with self.assertRaises(ValueError):self.a.set_ui_setting('other',3)
    def test_job_lifecycle(self):
        jid=self.a.create_job('backup','game');self.a.update_job(jid,'running',current=1,total=2);self.a.update_job(jid,'completed',current=2)
        self.assertEqual(self.a.jobs()[0]['state'],'completed')
    def test_invalid_states(self):
        j=self.a.create_job('backup','game')
        with self.assertRaises(ValueError):self.a.update_job(j,'completed')
        with self.assertRaises(ValueError):self.a.update_job(j,'running',current=4,total=2)
    def test_recovery_on_start(self):
        j=self.a.create_job('ftp','download');self.a.update_job(j,'running');self.a.close();self.a=ArchiveV17(self.root);self.a.recover_interrupted_jobs()
        self.assertEqual(self.a.jobs()[0]['state'],'interrupted')
    def test_opening_second_connection_does_not_interrupt_running_job(self):
        j=self.a.create_job('ftp','download');self.a.update_job(j,'running')
        other=ArchiveV17(self.root)
        self.assertEqual(other.jobs()[0]['state'],'running');other.close()
    def test_requeue(self):
        j=self.a.create_job('ftp','download');self.a.update_job(j,'running');self.a.update_job(j,'failed');self.a.update_job(j,'queued')
        self.assertEqual(self.a.jobs()[0]['state'],'queued')
    def test_thread_worker(self):
        finished=threading.Event();runner=JobRunner(self.root)
        j=runner.submit('verify','health',lambda a,c:len(a.jobs()),lambda _:finished.set())
        self.assertTrue(finished.wait(5));self.assertEqual(self.a.jobs()[0]['state'],'completed')
    def test_thread_failure(self):
        finished=threading.Event();runner=JobRunner(self.root)
        def fail(db,c):raise RuntimeError('bad')
        runner.submit('verify','fail',fail,lambda _:finished.set());self.assertTrue(finished.wait(5));self.assertEqual(self.a.jobs()[0]['state'],'failed')
    def test_job_validation(self):
        with self.assertRaises(ValueError):self.a.create_job('unknown','task')
        with self.assertRaises(ValueError):self.a.create_job('backup','')
    def test_settings_persist(self):
        self.a.set_ui_setting('notification_filter','error');self.a.close();self.a=ArchiveV17(self.root)
        self.assertEqual(self.a.ui_setting('notification_filter'),'error')
if __name__=='__main__':unittest.main()
