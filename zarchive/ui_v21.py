"""Opt-in post-conversion PKG inspection, external builder, and PS3 upload UI."""
from __future__ import annotations
import os, sys
from time import monotonic
from pathlib import Path
from PySide6.QtCore import QThread, Signal, QUrl, Qt
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (QApplication,QDialog,QVBoxLayout,QHBoxLayout,QLabel,QLineEdit,
    QPushButton,QFileDialog,QMessageBox,QFormLayout,QPlainTextEdit,QInputDialog,QTreeWidget,QTreeWidgetItem,QProgressBar)
from .ui_v20 import Window as V20Window, ConverterDialog as V20Dialog
from .ui_v04 import STYLE
from .editor_v18 import ArchiveV18
from .converter_output_v21 import (inspect_conversion_output,run_builder,upload_pkg_ftp,validate_pkg)
from .trueancestor_v25 import prepare_trueancestor
from .workspace_history import workspace_history
from .console_v27 import summarize_transfer
from .retail2pkg_v31 import inspect_retail2pkg_folder, prepare_retail2pkg_handoff, build_pkgs_locally, prepare_local_batch

class TaskWorker(QThread):
    done=Signal(object)
    error=Signal(str)
    progress=Signal(object,object)
    message=Signal(str)
    def __init__(self,fn,*args,**kwargs):
        super().__init__();self.fn=fn;self.args=args;self.kwargs=kwargs
    def run(self):
        try:self.done.emit(self.fn(*self.args,**self.kwargs))
        except Exception as e:self.error.emit(str(e))

class PackageDialog(QDialog):
    def __init__(self,parent=None,workspace='',retail_folder='',extractor=''):
        super().__init__(parent);self.setWindowTitle('PS3 PKG Builder — Local or FTP');self.resize(950,700)
        self.worker=None;self.last_report=None
        self.extractor = QLineEdit(extractor)
        self.extractor.setPlaceholderText('Auto-detect if blank')
        self.staging = None
        outer=QVBoxLayout(self)
        title=QLabel('Create PKGs on your PC — FTP upload is optional')
        title.setStyleSheet('font-size:17px;font-weight:600');outer.addWidget(title)
        note=QLabel('Select a disc ISO, a PS3_GAME folder, or a conversion workspace, and your Retail2Pkg tools. Build PKGs into a local folder without connecting to your PS3. The optional FTP upload is a separate action and never installs packages.')
        note.setWordWrap(True);outer.addWidget(note)
        form=QFormLayout();outer.addLayout(form)
        self.workspace=QLineEdit(workspace)
        self.retail_folder=QLineEdit(retail_folder);self.local_output=QLineEdit();self.local_output.setPlaceholderText("Choose where finished .pkg files should be saved")
        self.builder=QLineEdit();self.args=QLineEdit();self.pkg=QLineEdit()
        self.host=QLineEdit();self.host.setPlaceholderText('192.168.1.50')
        self.user=QLineEdit('anonymous');self.password=QLineEdit();self.password.setEchoMode(QLineEdit.EchoMode.Password)
        def add(label,field,action=None):
            if action:
                h=QHBoxLayout();h.addWidget(field,1)
                btn=QPushButton('Browse…');btn.clicked.connect(action);h.addWidget(btn);form.addRow(label,h)
            else:form.addRow(label,field)
        add('Game input / workspace',self.workspace,self.pick_workspace)
        iso_button = QPushButton('Choose disc ISO…')
        iso_button.clicked.connect(lambda: self.pick_file(self.workspace, 'ISO (*.iso)'))
        form.addRow(iso_button)
        add('7-Zip for ISO input', self.extractor,
            lambda: self.pick_file(self.extractor, 'Executables (*.exe)'))
        add('Retail2Pkg tools folder',self.retail_folder,self.pick_retail_folder)
        add('Local PKG output folder',self.local_output,self.pick_output_folder)
        add('PKG builder (.exe)',self.builder,lambda:self.pick_file(self.builder,'Executables (*.exe)'))
        add('Builder arguments',self.args)
        add('Produced PKG',self.pkg,lambda:self.pick_file(self.pkg,'PS3 packages (*.pkg)'))
        ftp_label=QLabel('Optional — FTP upload only');ftp_label.setStyleSheet('font-weight:600');form.addRow(ftp_label)
        add('PS3 IP / hostname',self.host)
        add('FTP username',self.user)
        add('FTP password (never saved)',self.password)
        self.log=QPlainTextEdit();self.log.setReadOnly(True);outer.addWidget(self.log,1)
        self.transfer_progress = QProgressBar()
        self.transfer_progress.setRange(0, 100)
        self.transfer_progress.hide()
        outer.addWidget(self.transfer_progress)
        self.transfer_status = QLabel()
        outer.addWidget(self.transfer_status)
        self.upload_active = False
        buttons=QHBoxLayout();outer.addLayout(buttons)
        self.inspect_btn=QPushButton('Inspect output');self.inspect_btn.clicked.connect(self.inspect);buttons.addWidget(self.inspect_btn)
        self.ta_btn=QPushButton('Prepare TrueAncestor handoff');self.ta_btn.clicked.connect(self.trueancestor);buttons.addWidget(self.ta_btn)
        self.retail_btn=QPushButton('Prepare Retail2Pkg handoff');self.retail_btn.clicked.connect(self.retail_handoff);buttons.addWidget(self.retail_btn)
        self.prepare_batch_btn = QPushButton('Prepare batch folder')
        self.prepare_batch_btn.clicked.connect(lambda: self.build_local(prepare_only=True))
        buttons.addWidget(self.prepare_batch_btn)
        self.open_stage_btn = QPushButton('Open batch folder')
        self.open_stage_btn.setEnabled(False)
        self.open_stage_btn.clicked.connect(self.open_stage)
        buttons.addWidget(self.open_stage_btn)
        local_buttons=QHBoxLayout();outer.addLayout(local_buttons)
        self.local_build_btn=QPushButton('Build PKGs Locally (No FTP)');self.local_build_btn.clicked.connect(lambda: self.build_local());local_buttons.addWidget(self.local_build_btn)
        self.build_btn=QPushButton('Run custom .exe builder');self.build_btn.clicked.connect(self.build);local_buttons.addWidget(self.build_btn)
        self.upload_btn=QPushButton('Optional: Upload PKG to PS3');self.upload_btn.clicked.connect(self.upload);local_buttons.addWidget(self.upload_btn)
        close=QPushButton('Close');close.clicked.connect(self.close);local_buttons.addWidget(close)
        self.log.appendPlainText('Use Build PKGs Locally to save completed packages to your PC. FTP is not necessary.\nFor direct-XMB installable PKGs, TrueAncestor PKG Repacker may be needed after CFW2OFW. Use Prepare TrueAncestor handoff to copy output to a new directory; it does not automatically build a PKG. TrueAncestor BACKUP Retailer is a different workflow.')
    def pick_output_folder(self):
        folder=QFileDialog.getExistingDirectory(self,'Select local folder for finished PKGs')
        if folder:self.local_output.setText(folder)
    def build_local(self, *, prepare_only=False):
        workspace=self.workspace.text().strip()
        tools=self.retail_folder.text().strip()
        output=self.local_output.text().strip()
        if not workspace or not tools or not output:
            return QMessageBox.warning(self,'Missing folders','Select game input, Retail2Pkg folder and local output folder. FTP is not required.')
        if not prepare_only and QMessageBox.question(self,'Build PKGs locally',
            'This creates a NEW independent staging copy, then executes Retail2Pkg.bat inside it.\n\n'
            'The third-party batch moves and deletes files inside the staging copy and may take a long time. '
            'Watch the Windows console for prompts and close it using the batch’s final key prompt. Continue?') != QMessageBox.StandardButton.Yes:return
        self.log.appendPlainText('Preparing the Retail2Pkg batch folder…')
        task = prepare_local_batch if prepare_only else build_pkgs_locally
        worker = TaskWorker(task, workspace, tools, output,
                            extractor=self.extractor.text().strip() or None)
        worker.kwargs['progress'] = worker.message.emit
        self.begin(worker)

    def open_stage(self):
        if self.staging and not QDesktopServices.openUrl(QUrl.fromLocalFile(self.staging)):
            QMessageBox.warning(self, 'Folder unavailable', self.staging)
    def pick_retail_folder(self):
        folder=QFileDialog.getExistingDirectory(self,'Select extracted Retail2Pkg folder')
        if not folder:return
        try:info=inspect_retail2pkg_folder(folder)
        except Exception as exc:return QMessageBox.warning(self,'Invalid Retail2Pkg folder',str(exc))
        self.retail_folder.setText(info['folder'])
        self.log.appendPlainText('Retail2Pkg tools found. The converter and PKG batch will not execute without separate approval.')
    def retail_handoff(self):
        if not self.retail_folder.text().strip():return QMessageBox.warning(self,'Missing tools','Select an extracted Retail2Pkg folder first.')
        if not self.workspace.text().strip():return QMessageBox.warning(self,'Missing workspace','Select your completed conversion workspace first.')
        parent=QFileDialog.getExistingDirectory(self,'Choose destination parent for NEW Retail2Pkg handoff')
        if not parent:return
        target=str(Path(parent)/'Retail2Pkg_Handoff')
        if QMessageBox.question(self,'Prepare Retail2Pkg handoff','Copy compatible converted game files and tool executables into a NEW folder?\n\nThis may require multiple GB. The Retail2Pkg.bat script MOVES and DELETES files, so it must only run on the handoff copy.')!=QMessageBox.StandardButton.Yes:return
        self.begin(TaskWorker(prepare_retail2pkg_handoff,self.workspace.text().strip(),self.retail_folder.text().strip(),target))
    def pick_workspace(self):
        p=QFileDialog.getExistingDirectory(self,'Select PS3_GAME, its parent, or a conversion workspace')
        if p:self.workspace.setText(p)
    def pick_file(self,field,filter):
        p=QFileDialog.getOpenFileName(self,'Select file','',filter)[0]
        if p:field.setText(p)
    def inspect(self):
        try:
            report=inspect_conversion_output(self.workspace.text().strip());self.last_report=report
            if report['packages']:
                self.log.appendPlainText('PS3 PKG files found.')
            elif report['folders']:
                self.log.appendPlainText('Conversion folders found. No PKG exists yet. '
                                         'To package compatible output, select an output folder and click Build PKGs Locally (No FTP).')
            else:
                self.log.appendPlainText('No converted title folders or PKGs found. Check the CFW2OFW Helper log.')
            self.log.appendPlainText('Game folders: '+(', '.join(x['relative_path'] for x in report['folders']) or 'none'))
            self.log.appendPlainText('Packages: '+(', '.join(x['relative_path'] for x in report['packages']) or 'none'))
            if report['packages'] and not self.pkg.text().strip():
                self.pkg.setText(str(Path(self.workspace.text().strip())/report['packages'][0]['relative_path']))
            self.log.appendPlainText(report['warning'])
        except Exception as e:QMessageBox.warning(self,'Inspection failed',str(e))
    def begin(self,worker):
        if self.worker and self.worker.isRunning():return QMessageBox.information(self,'Busy','An operation is already running.')
        self.worker=worker
        for button in (self.inspect_btn,self.ta_btn,self.retail_btn,self.local_build_btn,self.build_btn,self.upload_btn,self.prepare_batch_btn):button.setEnabled(False)
        self.worker.message.connect(self.log.appendPlainText)
        self.worker.done.connect(self.finished);self.worker.error.connect(self.failed);self.worker.finished.connect(self.enable_controls)
        self.worker.start()
    def enable_controls(self):
        for button in (self.inspect_btn,self.ta_btn,self.retail_btn,self.local_build_btn,self.build_btn,self.upload_btn,self.prepare_batch_btn):button.setEnabled(True)
    def finished(self,result):
        if 'staging' in result:
            self.staging = result['staging']
            self.open_stage_btn.setEnabled(True)
        if 'staging' in result and 'packages' not in result:
            self.log.appendPlainText(f"Batch folder ready: {self.staging}\n"
                                     "Click Open batch folder and run Retail2Pkg.bat there.")
        elif 'output_folder' in result:
            self.log.appendPlainText('Local PKG build: '+('Completed' if result['success'] else 'No valid packages produced')+'\nStaging: '+result['staging']+'\nSaved to: '+result['output_folder']+'\nPackages: '+(', '.join(result['packages']) or 'none')+'\n'+result['warning']+'\nBuilder log:\n'+result['log'])
            if result['packages']:
                self.workspace.setText(result['output_folder'])
                self.pkg.setText(result['packages'][0])
            if not result['success']:
                QMessageBox.warning(self,'No local PKGs created','The builder did not produce a valid PKG. See the log and staging folder. No FTP connection was attempted.')
        elif 'destination' in result:
            self.log.appendPlainText('TrueAncestor handoff prepared: '+result['destination']+'\nConverted folders: '+', '.join(result['folders'])+'\n'+result['instructions'])
        elif 'exit_code' in result:
            self.log.appendPlainText('Builder exit code: '+str(result['exit_code'])+'\n'+result['log'])
            self.log.appendPlainText('Inspect output again; builder success does not establish game compatibility.')
        else:
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

    def trueancestor(self):
        workspace=self.workspace.text().strip()
        if not workspace:return QMessageBox.warning(self,'Missing workspace','Select a converted workspace first.')
        destination=QFileDialog.getExistingDirectory(self,'Choose parent directory for a NEW TrueAncestor staging folder')
        if not destination:return
        target=Path(destination)/'TrueAncestor_Handoff'
        if QMessageBox.question(self,'Prepare TrueAncestor files',
            f'Copy converted game folders into a NEW staging directory?\n{target}\n\nThis can use several GB. Your original ISO and conversion workspace will not be changed.')!=QMessageBox.StandardButton.Yes:return
        self.begin(TaskWorker(prepare_trueancestor,workspace,str(target)))

    def build(self):
        if not (self.workspace.text().strip() and self.builder.text().strip()):return QMessageBox.warning(self,'Missing information','Select a workspace and a trusted builder executable.')
        if QMessageBox.question(self,'Run third-party builder','This executes an external tool that may change files inside your conversion workspace. Make sure you trust it. Continue?')!=QMessageBox.StandardButton.Yes:return
        self.log.appendPlainText('Launching builder in background...')
        self.begin(TaskWorker(run_builder,self.workspace.text().strip(),self.builder.text().strip(),self.args.text().strip()))
    def upload(self):
        try:info=validate_pkg(self.workspace.text().strip(),self.pkg.text().strip())
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
        worker=TaskWorker(upload_pkg_ftp,self.workspace.text().strip(),info['path'],host,
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
    def __init__(self, parent, folder, retail_folder=''):
        super().__init__(parent)
        self.retail_folder = retail_folder
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
        self.build_button = QPushButton('Open PKG builder')
        for button in (self.open_button, self.inspect_button, self.build_button):
            buttons.addWidget(button)
        close = QPushButton('Close')
        close.clicked.connect(self.reject)
        buttons.addWidget(close)
        self.open_button.clicked.connect(self.open_folder)
        self.inspect_button.clicked.connect(lambda: self.open_package(inspect=True))
        self.build_button.clicked.connect(self.open_package)
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
        self.build_button.setEnabled(bool(run and run['can_inspect']))

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

    def open_package(self, inspect=False):
        run = self.selected_run()
        if not run or not run['can_inspect']:
            return
        dialog = PackageDialog(self, str(run['folder']), self.retail_folder)
        if inspect:
            dialog.inspect()
        dialog.exec()


class ConverterDialog(V20Dialog):
    def __init__(self,parent=None):
        super().__init__(parent)
        actions = QHBoxLayout()
        self.package_button = QPushButton('Inspect output / Build PKG / Upload to PS3')
        self.package_button.clicked.connect(self.open_workspace_package)
        self.history_button = QPushButton('Workspace history…')
        self.history_button.clicked.connect(self.open_workspace_history)
        self.disc_pkg_button = QPushButton('Build PKG from disc input…')
        self.disc_pkg_button.clicked.connect(self.open_disc_package)
        actions.addWidget(self.disc_pkg_button)
        actions.addWidget(self.package_button)
        actions.addWidget(self.history_button)
        self.layout().insertLayout(self.layout().count() - 1, actions)
        folder_row=QHBoxLayout()
        self.retail2pkg_path=QLineEdit();self.retail2pkg_path.setPlaceholderText('Select your extracted Retail2Pkg folder (optional)')
        folder_row.addWidget(self.retail2pkg_path,1)
        pick=QPushButton('Retail2Pkg Folder…');pick.clicked.connect(self.pick_retail2pkg);folder_row.addWidget(pick)
        self.layout().insertLayout(2,folder_row)

    def set_conversion_actions_enabled(self, enabled):
        super().set_conversion_actions_enabled(enabled)
        self.package_button.setEnabled(enabled)
        self.disc_pkg_button.setEnabled(enabled)
        self.history_button.setEnabled(enabled)

    def open_disc_package(self):
        if not self.conversion_busy():
            PackageDialog(self, self.source.text().strip(), self.retail2pkg_path.text().strip(),
                          self.extractor.text().strip()).exec()

    def open_workspace_package(self):
        if self.conversion_busy():
            return
        if self.prepared:
            dialog = PackageDialog(self, self.prepared['workspace'], self.retail2pkg_path.text().strip())
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
        WorkspaceHistoryDialog(self, folder, self.retail2pkg_path.text().strip()).exec()

    def pick_retail2pkg(self):
        folder=QFileDialog.getExistingDirectory(self,'Select extracted Retail2Pkg folder')
        if not folder:return
        try:info=inspect_retail2pkg_folder(folder)
        except Exception as exc:return QMessageBox.warning(self,'Invalid Retail2Pkg folder',str(exc))
        self.retail2pkg_path.setText(info['folder'])
        self.helper.setText(info['helper'])
        self.log.appendPlainText('Selected Retail2Pkg toolkit: ' + info['folder'] + '\nCFW2OFW Helper executable detected.\nChoose a workspace parent. Each new run gets its own subfolder.')

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
        menu.addAction('PS3 PKG Builder (Local / FTP)',lambda:PackageDialog(self).exec())

def main():
    from . import ui
    ui.Archive=ArchiveV18
    app=QApplication(sys.argv);app.setStyle('Fusion');app.setStyleSheet(STYLE)
    home=os.environ.get('Z_ARCHIVE_HOME')
    if home:root=Path(home)
    elif (Path(sys.argv[0]).resolve().parent/'portable.flag').is_file():root=Path(sys.argv[0]).resolve().parent/'ArchiveData'
    else:root=Path.home()/'Documents'/'Z PlayStation Save Archive'
    win=Window(root);win.show();sys.exit(app.exec())
