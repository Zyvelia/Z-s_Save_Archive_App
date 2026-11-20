"""v1.6 regression tests for additive preferences, task safety and pagination."""
import tempfile,unittest
from pathlib import Path
from zarchive.upgrade_v16 import ArchiveV16

class V16Tests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.archive=ArchiveV16(Path(self.temp.name)/'archive')
    def tearDown(self):
        self.archive.close();self.temp.cleanup()
    def test_default_preferences(self):
        self.assertEqual(self.archive.get_pref('density','standard'),'standard')
    def test_persist_preferences(self):
        self.archive.set_pref('density','compact')
        self.archive.set_pref('dashboard_widgets',['stats','recent'])
        self.archive.close()
        self.archive=ArchiveV16(Path(self.temp.name)/'archive')
        self.assertEqual(self.archive.get_pref('density'),'compact')
        self.assertEqual(self.archive.get_pref('dashboard_widgets'),['stats','recent'])
    def test_invalid_widget_rejected(self):
        with self.assertRaises(ValueError):self.archive.set_pref('dashboard_widgets',['recent','recent'])
        with self.assertRaises(ValueError):self.archive.set_pref('dashboard_widgets',['unknown'])
        with self.assertRaises(ValueError):self.archive.set_pref('last_page','../foo')
    def test_task_lifecycle(self):
        tid=self.archive.create_task('backup','Backup game')
        self.archive.task_status(tid,'running')
        self.archive.task_status(tid,'completed','ok')
        self.assertEqual(self.archive.tasks()[0]['state'],'completed')
    def test_crash_marks_running_interrupted(self):
        tid=self.archive.create_task('ftp','Transfer game')
        self.archive.task_status(tid,'running')
        self.archive.close();self.archive=ArchiveV16(Path(self.temp.name)/'archive')
        self.assertEqual(self.archive.tasks()[0]['state'],'interrupted')
    def test_no_implicit_replay(self):
        tid=self.archive.create_task('import','Import')
        self.archive.close();self.archive=ArchiveV16(Path(self.temp.name)/'archive')
        self.assertEqual(self.archive.tasks()[0]['state'],'queued')
    def test_notifications(self):
        self.archive.notify('warning','Disk nearly full')
        self.assertEqual(self.archive.notifications()[0]['message'],'Disk nearly full')
    def test_invalid_notification(self):
        with self.assertRaises(ValueError):self.archive.notify('other','bad')
    def test_search_empty(self):
        r=self.archive.search_page('anything',limit=1)
        self.assertEqual(r['total'],0)
        self.assertEqual(r['items'],[])
    def test_search_limit_clamped(self):
        self.assertEqual(self.archive.search_page(limit=999999)['limit'],250)
    def test_search_invalid_filters(self):
        with self.assertRaises(ValueError):self.archive.search_page(platform='PS5')
        with self.assertRaises(ValueError):self.archive.search_page(category='garbage')
    def test_search_metacharacters_are_literal(self):
        self.assertEqual(self.archive.search_page('%')['total'],0)
    def test_task_validation(self):
        with self.assertRaises(ValueError):self.archive.create_task('malicious','bad')
        with self.assertRaises(ValueError):self.archive.create_task('backup','')
    def test_unknown_task_rejected(self):
        with self.assertRaises(ValueError):self.archive.task_status('missing','completed')

if __name__=='__main__':unittest.main()
