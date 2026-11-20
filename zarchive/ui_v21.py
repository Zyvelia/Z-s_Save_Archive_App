"""Opt-in post-conversion PKG inspection, and PS3 upload UI."""
from __future__ import annotations
import os, sys
from time import monotonic
from pathlib import Path
from PySide6.QtCore import QThread, Signal, QUrl, Qt
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (QApplication,QDialog,QVBoxLayout,QHBoxLayout,QLabel,QLineEdit,
    QPushButton,QFileDialog,QMessageBox,QFormLayout,QPlainTextEdit,QTreeWidget,QTreeWidgetItem,QProgressBar)
from .ui_v20 import Window as V20Window, ConverterDialog as V20Dialog
from .ui_v04 import STYLE
from .editor_v18 import ArchiveV18
from .converter_output_v21 import (inspect_conversion_output,upload_pkg_ftp,validate_pkg)
from .workspace_history import workspace_history
from .console_v27 import summarize_transfer

class TaskWorker(QThread):
    done=Signal(object)
    error=Signal(str)
    progress=Signal(object,object)
    def __init__(self,fn,*args,**kwargs):
        super().__init__();self.fn=fn;self.args=args;self.kwargs=kwargs
    def run(self):
        try:self.done.emit(self.fn(*self.args,**self.kwargs))
        except Exception as e:self.error.emit(str(e))

class PackageDialog(QDialog):
    def __init__(self, parent=None, workspace=''):
        super().__init__(parent)
        self.setWindowTitle('PS3 PKG Inspect and Upload')
        self.resize(790, 475)
        self.worker = None
        self.workspace = workspace
        self.upload_active = False
        outer = QVBoxLayout(self)
        form = QFormLayout()
        outer.addLayout(form)

        self.pkg = QLineEdit()
        browse = QPushButton('Browse…')
        browse.clicked.connect(lambda: self.pick_file(self.pkg, 'PS3 packages (*.pkg)'))
        row = QHBoxLayout()
        row.addWidget(self.pkg, 1)
        row.addWidget(browse)
        form.addRow('Existing PKG', row)
        self.host = QLineEdit()
        self.user = QLineEdit('anonymous')
        self.password = QLineEdit()
        self.password.setEchoMode(QLineEdit.EchoMode.Password)
        form.addRow('PS3 IP / hostname', self.host)
        form.addRow('FTP username', self.user)
        form.addRow('FTP password', self.password)

        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        outer.addWidget(self.log, 1)
        self.transfer_progress = QProgressBar()
        self.transfer_progress.setRange(0, 100)
        self.transfer_progress.hide()
        outer.addWidget(self.transfer_progress)
        self.transfer_status = QLabel()
        outer.addWidget(self.transfer_status)

        buttons = QHBoxLayout()
        outer.addLayout(buttons)
        self.inspect_btn = QPushButton('Inspect workspace' if workspace else 'Inspect PKG')
        self.inspect_btn.clicked.connect(self.inspect)
        self.upload_btn = QPushButton('Upload PKG to PS3')
        self.upload_btn.clicked.connect(self.upload)
        close = QPushButton('Close')
        close.clicked.connect(self.close)
        for button in (self.inspect_btn, self.upload_btn, close):
            buttons.addWidget(button)

    def package_root(self, package):
        return self.workspace or Path(package).absolute().parent

    def pick_file(self,field,filter):
        p=QFileDialog.getOpenFileName(self,'Select file','',filter)[0]
        if p:field.setText(p)
    def inspect(self):
        try:
            if self.workspace:
                report = inspect_conversion_output(self.workspace)
                folders = ', '.join(item['relative_path'] for item in report['folders'])
                packages = ', '.join(item['relative_path'] for item in report['packages'])
                self.log.appendPlainText(f"Game folders: {folders or 'none'}\nPackages: {packages or 'none'}")
                if report['packages'] and not self.pkg.text().strip():
                    self.pkg.setText(str(Path(self.workspace) / report['packages'][0]['relative_path']))
            else:
                package = self.pkg.text().strip()
                info = validate_pkg(self.package_root(package), package)
                self.log.appendPlainText(f"{info['filename']} · {info['bytes']:,} bytes · PS3 PKG header found")
        except (OSError, ValueError) as exc:
            QMessageBox.warning(self, 'Inspection failed', str(exc))

    def begin(self, worker):
        self.worker = worker
        self.inspect_btn.setEnabled(False)
        self.upload_btn.setEnabled(False)
        worker.done.connect(self.finished)
        worker.error.connect(self.failed)
        worker.finished.connect(self.enable_controls)
        worker.start()

    def enable_controls(self):
        self.inspect_btn.setEnabled(True)
        self.upload_btn.setEnabled(True)

    def finished(self, result):
        self.upload_active = False
        self.transfer_status.setText('Upload complete. Remote size verified.')
        self.log.appendPlainText(
            f"Uploaded {result['remote_path']} ({result['bytes']:,} bytes; remote size checked).\n"
            + result['instruction']
        )

    def show_progress(self, sent, total):
        if not self.upload_active:
            return
        if sent >= total:
            self.transfer_progress.setValue(100)
            self.transfer_status.setText('Checking remote package size…')
            return
        self.transfer_progress.setValue(sent * 100 // total)
        now = monotonic()
        if not self.transfer_samples:
            self.transfer_samples.append({'time': now, 'bytes': sent, 'total': total})
            return
        if now - self.transfer_samples[-1]['time'] < 0.5:
            return
        self.transfer_samples.append({'time': now, 'bytes': sent, 'total': total})
        self.transfer_samples = self.transfer_samples[-8:]
        estimate = summarize_transfer(self.transfer_samples)
        rate = estimate['rate_bytes_per_second'] / 1024**2
        eta = estimate['eta_seconds']
        remaining = f'{eta:.0f} s' if eta is not None else 'Estimating…'
        self.transfer_status.setText(
            f'{sent / 1024**2:,.1f} / {total / 1024**2:,.1f} MiB · {rate:.2f} MiB/s · ETA {remaining}'
        )

    def failed(self, message):
        if self.upload_active:
            self.upload_active = False
            self.transfer_status.setText('Upload failed. See the log.')
        self.log.appendPlainText('Operation failed: ' + message)
        QMessageBox.warning(self, 'Operation failed', message)

    def upload(self):
        package = self.pkg.text().strip()
        root = self.package_root(package)
        try:info=validate_pkg(root,package)
        except Exception as e:return QMessageBox.warning(self,'Invalid package',str(e))
        host=self.host.text().strip()
        if not host:return QMessageBox.warning(self,'Missing PS3 address','Enter the console IP address.')
        if QMessageBox.question(self,'Confirm PS3 FTP upload',f"Upload {info['filename']} ({info['bytes']:,} bytes) to {host}:/dev_hdd0/packages/?\n\nThis does not install the PKG, and will refuse to overwrite existing files.")!=QMessageBox.StandardButton.Yes:return
        self.upload_active = True
        self.transfer_samples = []
        self.transfer_progress.setValue(0)
        self.transfer_progress.show()
        self.transfer_status.setText('Connecting to PS3…')
        self.log.appendPlainText('Uploading package in background...')
        worker=TaskWorker(upload_pkg_ftp,root,info['path'],host,
            username=self.user.text().strip() or 'anonymous',password=self.password.text())
        last_update = 0.0

        def report_progress(sent, total):
            nonlocal last_update
            now = monotonic()
            if sent >= total or now - last_update >= 0.5:
                last_update = now
                worker.progress.emit(sent, total)

        worker.kwargs['progress'] = report_progress
        worker.progress.connect(self.show_progress)
        self.begin(worker)
    def closeEvent(self,event):
        if self.worker and self.worker.isRunning():
            QMessageBox.information(self,'Operation running','Finish the current operation before closing.');event.ignore();return
        self.password.clear();super().closeEvent(event)

class WorkspaceHistoryDialog(QDialog):
    def __init__(self, parent, folder):
        super().__init__(parent)
        self.setWindowTitle('Conversion workspace history')
        self.resize(880, 420)
        layout = QVBoxLayout(self)
        self.status = QLabel('Reading workspace history…')
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.table = QTreeWidget()
        self.table.setHeaderLabels(['Game', 'Date', 'Size', 'Recorded status'])
        self.table.setRootIsDecorated(False)
        layout.addWidget(self.table)

        buttons = QHBoxLayout()
        layout.addLayout(buttons)
        self.open_button = QPushButton('Open folder')
        self.inspect_button = QPushButton('Inspect output')
        for button in (self.open_button, self.inspect_button):
            buttons.addWidget(button)
        close = QPushButton('Close')
        close.clicked.connect(self.reject)
        buttons.addWidget(close)
        self.open_button.clicked.connect(self.open_folder)
        self.inspect_button.clicked.connect(self.open_package)
        self.table.itemSelectionChanged.connect(self.update_actions)
        self.update_actions()

        self.worker = TaskWorker(workspace_history, folder)
        self.worker.done.connect(self.show_runs)
        self.worker.error.connect(self.status.setText)
        self.worker.start()

    def reject(self):
        if not self.worker.isRunning():
            super().reject()

    def selected_run(self):
        selected = self.table.selectedItems()
        return selected[0].data(0, Qt.ItemDataRole.UserRole) if selected else None

    def update_actions(self):
        run = self.selected_run()
        self.open_button.setEnabled(run is not None)
        self.inspect_button.setEnabled(bool(run and run['can_inspect']))

    def show_runs(self, runs):
        self.status.setText('Choose a conversion run.' if runs else 'No conversion runs found in this parent folder.')
        for run in runs:
            game = f"{run['title']} [{run['title_id']}]" if run['title_id'] else str(run['title'])
            size = run['bytes']
            item = QTreeWidgetItem([
                game, run['date'].astimezone().strftime('%Y-%m-%d %H:%M'),
                f'{size / 1024**3:.2f} GiB' if size >= 1024**3 else f'{size / 1024**2:.1f} MiB',
                run['status'],
            ])
            item.setToolTip(0, str(run['folder']))
            item.setData(0, Qt.ItemDataRole.UserRole, run)
            self.table.addTopLevelItem(item)
        for column in range(self.table.columnCount()):
            self.table.resizeColumnToContents(column)

    def open_folder(self):
        run = self.selected_run()
        if run and not QDesktopServices.openUrl(QUrl.fromLocalFile(str(run['folder']))):
            QMessageBox.warning(self, 'Folder unavailable', str(run['folder']))

    def open_package(self):
        run = self.selected_run()
        if not run or not run['can_inspect']:
            return
        dialog = PackageDialog(self, str(run['folder']))
        dialog.inspect()
        dialog.exec()


class ConverterDialog(V20Dialog):
    def __init__(self,parent=None):
        super().__init__(parent)
        actions = QHBoxLayout()
        self.package_button = QPushButton('Inspect conversion output')
        self.package_button.clicked.connect(self.open_workspace_package)
        self.history_button = QPushButton('Workspace history…')
        self.history_button.clicked.connect(self.open_workspace_history)
        actions.addWidget(self.package_button)
        actions.addWidget(self.history_button)
        self.layout().insertLayout(self.layout().count() - 1, actions)

    def set_conversion_actions_enabled(self, enabled):
        super().set_conversion_actions_enabled(enabled)
        self.package_button.setEnabled(enabled)
        self.history_button.setEnabled(enabled)

    def open_workspace_package(self):
        if self.conversion_busy():
            return
        if self.prepared:
            dialog = PackageDialog(self, self.prepared['workspace'])
            dialog.inspect()
            dialog.exec()
        else:
            self.open_workspace_history()

    def open_workspace_history(self):
        if self.conversion_busy():
            return
        folder = self.output.text().strip()
        if not folder:
            QMessageBox.information(self, 'Workspace parent required', 'Choose a workspace parent folder first.')
            return
        WorkspaceHistoryDialog(self, folder).exec()


class Window(V20Window):
    def __init__(self,root):
        super().__init__(root);self.setWindowTitle("Z's Save Archive • PS3 + PC v2.1")
        menu=self.tools_btn.menu()
        for action in menu.actions():
            if action.text() == 'PS3 ISO → XMB Conversion Assistant':
                action.setText('PS3 ISO → XMB Assistant v2.1')
                action.triggered.disconnect()
                action.triggered.connect(lambda:ConverterDialog(self).exec())
        menu.addSeparator()
        menu.addAction('PS3 PKG Inspect and Upload',lambda:PackageDialog(self).exec())

def main():
    from . import ui
    ui.Archive=ArchiveV18
    app=QApplication(sys.argv);app.setStyle('Fusion');app.setStyleSheet(STYLE)
    home=os.environ.get('Z_ARCHIVE_HOME')
    if home:root=Path(home)
    elif (Path(sys.argv[0]).resolve().parent/'portable.flag').is_file():root=Path(sys.argv[0]).resolve().parent/'ArchiveData'
    else:root=Path.home()/'Documents'/'Z PlayStation Save Archive'
    win=Window(root);win.show();sys.exit(app.exec())
