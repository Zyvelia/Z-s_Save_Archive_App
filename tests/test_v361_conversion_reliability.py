import errno
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from test_v20 import write_sfo
from zarchive.iso_converter_v20 import StagingCancelled, stage_conversion
from zarchive.workspace_history import record_converter_status, workspace_history

try:
    from PySide6.QtWidgets import QApplication, QMessageBox
except ImportError:
    QApplication = None


class ConversionReliability(unittest.TestCase):
    def setUp(self):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.source = self.root / 'Game A' / 'PS3_GAME'
        self.source.mkdir(parents=True)
        write_sfo(self.source / 'PARAM.SFO')
        self.helper = self.root / 'tools' / 'helper.exe'
        self.helper.parent.mkdir()
        self.helper.write_bytes(b'exe')
        self.parent = self.root / 'runs'

    def test_marker_failure_preserves_original_disk_error(self):
        error = OSError(errno.ENOSPC, 'Drive full')
        with patch('zarchive.iso_converter_v20.safe_copy_tree', side_effect=error):
            with patch.object(Path, 'write_text', side_effect=OSError(errno.EIO, 'Marker failed')):
                with self.assertRaises(OSError) as raised:
                    stage_conversion(self.source, self.helper, self.parent / 'failed')
        self.assertIs(raised.exception, error)

    def test_cancelled_copy_is_retained_and_history_reads_old_manifests(self):
        staged = self.parent / 'staged'
        stage_conversion(self.source, self.helper, staged)
        manifest = staged / 'conversion_manifest.json'
        before = json.loads(manifest.read_text(encoding='utf-8'))
        self.assertEqual(workspace_history(self.parent)[0]['status'], 'Staged')
        record_converter_status(staged, 'Converter finished')

        partial = self.parent / 'partial'
        with self.assertRaises(StagingCancelled):
            stage_conversion(self.source, self.helper, partial,
                             cancelled=lambda: (partial / self.helper.name).exists())
        results = {run['folder']: run for run in workspace_history(self.parent)}
        self.assertEqual(results[partial]['status'], 'Staging cancelled')
        self.assertFalse(results[partial]['can_inspect'])
        self.assertTrue(results[staged]['can_inspect'])
        self.assertEqual(results[staged]['status'], 'Converter finished')
        self.assertEqual(json.loads(manifest.read_text(encoding='utf-8')), before)
        self.assertTrue((self.source / 'PARAM.SFO').is_file())

    @unittest.skipUnless(QApplication, 'PySide6 is required to test the PKG builder handoff')
    def test_pkg_builder_inherits_the_selected_retail2pkg_folder(self):
        from zarchive.appdata_v34 import AppPaths
        from zarchive.ui_v21 import ConverterDialog

        os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
        app = QApplication.instance() or QApplication([])
        paths = AppPaths.discover(env={
            'LOCALAPPDATA': str(self.root / 'local'), 'APPDATA': str(self.root / 'roaming')
        })
        with patch.object(AppPaths, 'discover', return_value=paths):
            dialog = ConverterDialog()
        self.addCleanup(dialog.close)
        dialog.retail2pkg_path.setText(str(self.helper.parent))
        dialog.prepared = {'workspace': str(self.parent / 'finished')}

        with patch('zarchive.ui_v21.PackageDialog') as package:
            dialog.open_workspace_package()
        package.assert_called_once_with(dialog, str(self.parent / 'finished'), str(self.helper.parent))
        package.return_value.inspect.assert_called_once_with()
        package.return_value.exec.assert_called_once_with()
        app.processEvents()

    @unittest.skipUnless(QApplication, 'PySide6 is required for the converter dialog regression')
    def test_failed_new_stage_does_not_leave_previous_game_runnable(self):
        from PySide6.QtTest import QTest
        from zarchive.appdata_v34 import AppPaths
        from zarchive.ui_v21 import ConverterDialog, WorkspaceHistoryDialog

        os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
        app = QApplication.instance() or QApplication([])
        with patch.object(AppPaths, 'discover', return_value=AppPaths.discover(
            env={'LOCALAPPDATA': str(self.root / 'local'), 'APPDATA': str(self.root / 'roaming')}
        )):
            dialog = ConverterDialog()
        self.addCleanup(dialog.close)
        dialog.source.setText(str(self.source))
        dialog.helper.setText(str(self.helper))
        dialog.output.setText(str(self.parent))
        self.assertEqual(dialog.app_paths.path('workspace'), str(self.parent))
        dialog.ack.setChecked(True)

        def finish_staging():
            self.assertTrue(dialog.worker.wait(5000))
            app.processEvents()

        with patch.object(QMessageBox, 'question', return_value=QMessageBox.StandardButton.Yes):
            dialog.begin_stage()
            finish_staging()
            previous = dict(dialog.prepared)
            self.assertTrue(dialog.runbtn.isEnabled())
            dialog.source.setText(str(self.root / 'Missing Game B'))
            with patch.object(QMessageBox, 'warning'):
                dialog.begin_stage()
                self.assertFalse(dialog.runbtn.isEnabled())
                self.assertFalse(dialog.package_button.isEnabled())
                finish_staging()
            self.assertIsNone(dialog.prepared)
            self.assertFalse(dialog.runbtn.isEnabled())
            self.assertTrue(dialog.package_button.isEnabled())

            history = WorkspaceHistoryDialog(dialog, str(self.parent))
            self.assertTrue(history.worker.wait(5000))
            QTest.qWait(5)
            self.assertEqual(history.table.topLevelItemCount(), 1)
            history.table.setCurrentItem(history.table.topLevelItem(0))
            self.assertEqual(history.selected_run()['folder'], Path(previous['workspace']))
            self.assertTrue(history.build_button.isEnabled())
            history.close()
