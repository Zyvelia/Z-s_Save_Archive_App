"""PS3 ISO-to-XMB conversion assistant (optional external CFW2OFW Helper)."""
from __future__ import annotations
import os, sys
from threading import Event
from pathlib import Path
from PySide6.QtCore import QThread, Signal, QSettings, QTimer, QElapsedTimer
from PySide6.QtWidgets import (QApplication, QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFileDialog, QMessageBox, QLineEdit, QFormLayout, QPlainTextEdit, QCheckBox, QProgressBar)
from .ui_v18 import Window as BaseWindow
from .ui_v04 import STYLE
from .editor_v18 import ArchiveV18
from .iso_converter_v20 import stage_conversion, helper_command, inspect_game, inspect_iso, find_7zip, next_workspace, StagingCancelled, check_cancelled
from .appdata_v34 import AppPaths
from .console_v27 import conversion_preflight
from .workspace_history import record_converter_status

class ConversionWorker(QThread):
    ready = Signal(object)
    error = Signal(str)
    cancelled = Signal(str)
    progress = Signal(str)
    low_space = Signal(str)

    def __init__(self, source, helper, target, extractor):
        super().__init__()
        self.args = (source, helper, target, extractor)
        self.cancel_requested = Event()
        self.space_confirmed = Event()

    def run(self):
        try:
            source, helper, target, extractor = self.args
            cancelled = self.cancel_requested.is_set
            self.progress.emit('Checking source and available disk space…')
            extractor = extractor or find_7zip()
            report = conversion_preflight(source, helper, target, extractor, cancelled=cancelled)
            estimated = report.get('conservative_estimated_bytes')
            available = report.get('work_disk_free_bytes')
            if report['errors']:
                raise ValueError('\n'.join(report['errors']))
            if estimated is not None and available is not None and estimated > available:
                self.low_space.emit(
                    f'Estimated workspace requirement is {estimated / 1024**3:.1f} GiB. '
                    f'The drive has {available / 1024**3:.1f} GiB free. Continue?'
                )
                while not self.space_confirmed.wait(0.2):
                    check_cancelled(cancelled)
            self.ready.emit(stage_conversion(source, helper, target, extractor=extractor,
                                             progress=self.progress.emit, cancelled=cancelled))
        except StagingCancelled as exc:
            self.cancelled.emit(str(exc))
        except Exception as exc:
            self.error.emit(str(exc))


class ConverterDialog(QDialog):
    def __init__(self,parent=None):
        super().__init__(parent);self.setWindowTitle('PS3 ISO → XMB Conversion Assistant');self.resize(790,570)
        self.worker=None;self.process=None;self.prepared=None;self.auto_run=False
        self.stage_cancel_pending = False
        self.prefs=QSettings('ZsSaveArchive','ZSaveArchive')
        self.app_paths=AppPaths.discover().initialize()
        self.elapsed=QElapsedTimer()
        self.pulse=QTimer(self);self.pulse.setInterval(1000);self.pulse.timeout.connect(self.update_elapsed)
        self.report_step = "Idle"
        self.report_exit_code = None
        self.stage_name='Idle'
        layout=QVBoxLayout(self)
        headline=QLabel('Convert compatible PS3 disc games for direct XMB launching')
        headline.setStyleSheet('font-size:17px;font-weight:600');layout.addWidget(headline)
        subtitle=QLabel('Requires separately installed CFW2OFW Helper. This utility stages a COPY and never modifies your original ISO. Conversion does not guarantee compatibility or create a PKG by itself.')
        subtitle.setWordWrap(True);layout.addWidget(subtitle)
        form=QFormLayout();layout.addLayout(form)
        self.source=QLineEdit();self.helper=QLineEdit();self.extractor=QLineEdit();self.output=QLineEdit()
        for field in (self.source,self.helper,self.extractor,self.output):
            field.setMinimumWidth(100)
            field.textChanged.connect(lambda value,widget=field:widget.setToolTip(value))
        def line(name,edit,buttons):
            row=QHBoxLayout();row.addWidget(edit,1)
            for label,cb in buttons:
                btn=QPushButton(label);btn.clicked.connect(cb);row.addWidget(btn)
            form.addRow(name,row)
        line('PS3 ISO / PS3_GAME',self.source,[('ISO…',self.pick_iso),('Folder…',self.pick_game)])
        line('CFW2OFW Helper EXE',self.helper,[('Browse…',lambda:self.pick_file(self.helper,'Executable (*.exe)'))])
        line('7z.exe for ISO input',self.extractor,[('Auto-find',self.auto_find_7zip),('Browse…',lambda:self.pick_file(self.extractor,'Executable (*.exe)'))])
        line('Workspace parent folder',self.output,[('Choose parent…',self.pick_dest)])
        # Persist chosen paths per Windows user; never store passwords or game content.
        for key,field in (('source',self.source),('helper',self.helper),('extractor',self.extractor),('workspace',self.output)):
            saved = self.app_paths.path(key)
            if not saved and key == 'workspace':
                saved = self.app_paths.path('output')
            if not saved:
                legacy_key = 'output' if key == 'workspace' else key
                saved = self.prefs.value('conversion/' + legacy_key, '', type=str)
            if saved: field.setText(saved)
            field.textChanged.connect(lambda text,k=key:self._save_conversion_path(k,text))
        if not self.extractor.text().strip():
            found=find_7zip()
            if found: self.extractor.setText(str(found))
        self.ack=QCheckBox('I understand this stages a separate copy and runs an external converter only with my approval.')
        layout.addWidget(self.ack)
        self.status=QLabel('Step 1 of 3: Choose ISO or extracted PS3_GAME, helper, and work folder.')
        self.status.setWordWrap(True);self.status.setStyleSheet('font-weight:600;color:#ba9cf8')
        layout.addWidget(self.status)
        self.progress_bar=QProgressBar();self.progress_bar.setRange(0,1);self.progress_bar.setValue(0)
        self.progress_bar.setFormat('Ready');layout.addWidget(self.progress_bar)
        self.elapsed_label=QLabel('Idle — no conversion running');layout.addWidget(self.elapsed_label)
        self.log=QPlainTextEdit();self.log.setReadOnly(True);layout.addWidget(self.log,1)
        report_actions = QHBoxLayout()
        self.hide_report_paths = QCheckBox('Hide paths in report')
        self.hide_report_paths.setChecked(True)
        report_actions.addWidget(self.hide_report_paths)
        copy_report = QPushButton('Copy troubleshooting report')
        copy_report.clicked.connect(self.copy_troubleshooting_report)
        report_actions.addWidget(copy_report)
        self.report_feedback = QLabel()
        report_actions.addWidget(self.report_feedback, 1)
        layout.addLayout(report_actions)
        btns=QHBoxLayout();layout.addLayout(btns)
        inspect=QPushButton('Inspect source');inspect.clicked.connect(self.inspect);btns.addWidget(inspect)
        self.stage=QPushButton('Stage only');self.stage.clicked.connect(self.begin_stage);btns.addWidget(self.stage)
        self.convert=QPushButton('Stage && Convert');self.convert.setToolTip('Stages a separate copy, then runs CFW2OFW Helper after approval.');self.convert.clicked.connect(self.begin_auto_convert);btns.addWidget(self.convert)
        self.runbtn=QPushButton('Run staged converter');self.runbtn.setEnabled(False);self.runbtn.setToolTip('Enabled once staging succeeds. Use Stage & Convert to perform both steps.');self.runbtn.clicked.connect(self.run_converter);btns.addWidget(self.runbtn)
        self.cancel_stage = QPushButton('Cancel staging')
        self.cancel_stage.setEnabled(False)
        self.cancel_stage.clicked.connect(self.request_stage_cancel)
        btns.addWidget(self.cancel_stage)
        end=QPushButton('Close');end.clicked.connect(self.close);btns.addWidget(end)
        self.log.appendPlainText('Choose a workspace parent folder once; every conversion automatically gets its own safe subfolder.\nUse Stage & Convert to prepare the game folders. Open the PKG builder afterward to package compatible output. Run staged converter is disabled until staging finishes. Encrypted PS3 ISOs cannot be decrypted by 7-Zip; provide an extractable disc image or a PS3_GAME folder from your own backup.')
    def copy_troubleshooting_report(self):
        lines = self.log.toPlainText()[-12000:].splitlines()[-40:]
        if self.hide_report_paths.isChecked():
            # Cover paths from external tool output as well as the configured inputs.
            lines = ['[Line with a possible path omitted]' if '/' in line or chr(92) in line
                     else line for line in lines]
        code = self.report_exit_code if self.report_exit_code is not None else 'Unavailable'
        report = ['PS3 ISO → XMB troubleshooting report', f'Step: {self.report_step}',
                  f'Converter exit code: {code}', '', 'Recent log', *lines]
        QApplication.clipboard().setText('\n'.join(report))
        self.report_feedback.setText('Copied')

    def _save_conversion_path(self,key,value):
        try: self.app_paths.remember_path(key,value)
        except OSError as e: self.log.appendPlainText('Could not save path: '+str(e))

    def auto_find_7zip(self):
        found=find_7zip()
        if found:
            self.extractor.setText(str(found))
            self.log.appendPlainText('7-Zip detected: '+str(found))
        else:
            self.log.appendPlainText('7z.exe not found in PATH, Program Files, AppData, or registry. Select it manually.')
            QMessageBox.information(self,'7-Zip not found','Auto-detection could not find 7z.exe. Select its location using Browse.')

    def start_activity(self,label):
        self.stage_name=label;self.elapsed.start();self.pulse.start()
        self.progress_bar.setRange(0,0)  # indeterminate: no fabricated percentage
        self.progress_bar.setFormat(label)
        self.update_elapsed()
        self.log.appendPlainText('--- '+label+' started ---')

    def stop_activity(self,success):
        self.pulse.stop();self.progress_bar.setRange(0,1)
        self.progress_bar.setValue(1 if success else 0)
        self.progress_bar.setFormat('Completed' if success else 'Failed')
        self.update_elapsed()

    def update_elapsed(self):
        secs=max(0,self.elapsed.elapsed()//1000) if self.elapsed.isValid() else 0
        self.elapsed_label.setText(f'{self.stage_name} — elapsed {secs//60:02d}:{secs%60:02d}')

    def pick_file(self,field,types):
        p=QFileDialog.getOpenFileName(self,'Choose file','',types)[0]
        if p:field.setText(p)
    def pick_iso(self):self.pick_file(self.source,'ISO (*.iso)')
    def pick_game(self):
        p=QFileDialog.getExistingDirectory(self,'Select PS3_GAME directory or parent')
        if p:self.source.setText(p)
    def pick_dest(self):
        p=QFileDialog.getExistingDirectory(self,'Choose parent folder for work directory')
        if p:self.output.setText(str(Path(p)))
    def inspect(self):
        try:
            src=Path(self.source.text().strip())
            data=inspect_iso(src) if src.suffix.lower()=='.iso' else inspect_game(src)
            self.log.appendPlainText(str(data))
        except Exception as e:QMessageBox.warning(self,'Inspection failed',str(e))
    def conversion_busy(self):
        return (self.cancel_stage.isEnabled() or self.stage_cancel_pending
                or (self.process is not None and self.process.state() != self.process.ProcessState.NotRunning))

    def request_stage_cancel(self):
        self.stage_cancel_pending = True
        self.worker.cancel_requested.set()
        self.cancel_stage.setEnabled(False)
        self.status.setText('Cancelling staging…')

    def confirm_low_space(self, message):
        if self.worker.cancel_requested.is_set():
            return
        if QMessageBox.question(self, 'Low workspace disk space', message) == QMessageBox.StandardButton.Yes:
            self.worker.space_confirmed.set()
        else:
            self.request_stage_cancel()

    def begin_auto_convert(self):
        self.auto_run=True
        self.begin_stage()

    def begin_stage(self):
        if self.conversion_busy() or (self.worker and self.worker.isRunning()):
            self.auto_run = False
            return
        if not self.ack.isChecked():
            self.auto_run=False
            return QMessageBox.information(self,'Confirmation required','Check the safety acknowledgement first.')
        if not all(x.text().strip() for x in (self.source,self.helper,self.output)):
            self.auto_run=False
            return QMessageBox.warning(self,'Missing information','Choose source, helper and a workspace parent folder. 7z.exe is also required for ISO input.')
        try:
            workspace=next_workspace(self.output.text().strip(),self.source.text().strip())
        except (OSError, ValueError) as e:
            self.auto_run=False
            return QMessageBox.warning(self,'Invalid workspace location',str(e))
        if QMessageBox.question(self,'Prepare copy',
                'Create a fresh conversion subfolder here?\n'+str(workspace)+
                '\n\nPrevious workspaces will be kept. This may use many gigabytes of disk space.')!=QMessageBox.StandardButton.Yes:
            self.auto_run=False
            return
        self.prepared = None
        self.report_exit_code = None
        self.report_step = 'Staging'
        self.report_feedback.clear()
        self.runbtn.setEnabled(False)
        self.set_conversion_actions_enabled(False)
        self.cancel_stage.setEnabled(True)
        self.status.setText('Step 2 of 3. Preparing a separate working copy…')
        self.start_activity('Staging')
        self.log.appendPlainText('Using fresh workspace: '+str(workspace))
        self.worker = ConversionWorker(self.source.text().strip(), self.helper.text().strip(),
                                       str(workspace), self.extractor.text().strip())
        self.worker.ready.connect(self.stage_ready)
        self.worker.error.connect(self.stage_failed)
        self.worker.cancelled.connect(self.stage_cancelled)
        self.worker.low_space.connect(self.confirm_low_space)
        self.worker.progress.connect(self.on_stage_progress)
        self.worker.start()

    def end_staging(self):
        self.cancel_stage.setEnabled(False)
        self.stage_cancel_pending = False
        self.set_conversion_actions_enabled(True)

    def set_conversion_actions_enabled(self, enabled):
        self.stage.setEnabled(enabled)
        self.convert.setEnabled(enabled)

    def stage_cancelled(self, message):
        self.auto_run = False
        self.end_staging()
        self.stop_activity(False)
        self.progress_bar.setFormat('Cancelled')
        self.report_step = 'Staging cancelled'
        self.status.setText('Staging cancelled.')
        self.log.appendPlainText(message)

    def on_stage_progress(self,message):
        self.stage_name=message
        self.report_step = message
        self.progress_bar.setFormat(message)
        self.log.appendPlainText(message)
        self.update_elapsed()

    def stage_ready(self,info):
        cancelled = self.stage_cancel_pending
        self.end_staging()
        self.stop_activity(True)
        self.prepared = info
        self.report_step = 'Staging completed'
        self.runbtn.setEnabled(True)
        self.status.setText(f"Staged {info['title']} [{info['title_id']}]. Ready to run the converter.")
        self.log.appendPlainText('Staged '+info['title']+' ['+info['title_id']+'] at '+info['workspace'])
        auto_run = self.auto_run
        self.auto_run = False
        if auto_run and not cancelled:
            self.run_converter()
    def stage_failed(self,message):
        self.stop_activity(False)
        self.auto_run = False
        self.end_staging()
        self.status.setText('Staging failed — check the log; conversion has NOT started.')
        self.report_step = 'Staging failed during ' + self.stage_name
        self.log.appendPlainText('Staging failed: '+message)
        if '7-Zip extraction failed' in message or 'PS3_GAME' in message:
            self.log.appendPlainText('Troubleshooting: 7-Zip cannot decrypt encrypted PS3 disc ISOs. Use a decrypted/extractable backup or choose an existing PS3_GAME folder. Retry using the same parent folder; a fresh subfolder will be generated.')
        QMessageBox.warning(self,'Staging failed',message)
    def run_converter(self):
        from PySide6.QtCore import QProcess
        if not self.prepared or self.conversion_busy():
            return
        work = Path(self.prepared['workspace'])
        game = f"{self.prepared['title']} [{self.prepared['title_id']}]"
        message = (f'Run CFW2OFW Helper for {game}?\n\nWorkspace: {work}\n\n'
                   'The helper may remove the staged input.')
        if QMessageBox.question(self, 'Confirm external tool', message) != QMessageBox.StandardButton.Yes:
            return
        self.report_step = 'Starting converter'
        self.report_exit_code = None
        self.report_feedback.clear()
        try:
            command = helper_command(work, Path(self.prepared['helper']).name)
        except (OSError, ValueError) as exc:
            self.converter_start_failed(work, str(exc))
            return
        self.process = QProcess(self)
        self.process.setWorkingDirectory(str(work))
        self.process.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        self.process.readyReadStandardOutput.connect(self.read_converter_output)
        self.process.started.connect(lambda: self.converter_started(work))
        self.process.errorOccurred.connect(
            lambda error: self.converter_start_failed(work, self.process.errorString())
            if error == QProcess.ProcessError.FailedToStart else None
        )
        self.process.finished.connect(lambda code, status: self.converter_finished(code, status, work))
        self.runbtn.setEnabled(False)
        self.set_conversion_actions_enabled(False)
        self.status.setText('Step 3 of 3. Converter running on the staged copy…')
        self.start_activity('Running converter')
        self.log.appendPlainText('Launching staged converter: ' + command[0])
        self.process.start(command[0], [])

    def converter_started(self, work):
        self.report_step = 'Running converter'
        self.save_converter_status(work, 'Converter started')

    def converter_start_failed(self, work, message):
        self.save_converter_status(work, 'Converter failed')
        self.runbtn.setEnabled(True)
        self.set_conversion_actions_enabled(True)
        self.stop_activity(False)
        self.report_step = 'Converter could not start'
        self.log.appendPlainText('Converter could not start: ' + message)
        self.status.setText('Converter could not start.')
        QMessageBox.warning(self, 'Converter could not start', message)

    def read_converter_output(self):
        output=bytes(self.process.readAllStandardOutput()).decode('utf-8',errors='replace')
        if output.strip(): self.log.appendPlainText(output.rstrip())

    def save_converter_status(self, work, status):
        try:
            record_converter_status(work, status)
        except OSError as exc:
            self.log.appendPlainText(f'Could not save converter status: {exc}')

    def converter_finished(self,code,status,work):
        self.read_converter_output()
        success = code == 0 and status == self.process.ExitStatus.NormalExit
        self.report_step = 'Converter finished' if success else 'Converter failed'
        self.report_exit_code = code
        self.save_converter_status(work, self.report_step)
        self.stop_activity(success)
        self.log.appendPlainText(f'Converter exit code: {code}; inspect output in {work}. An exit code alone does not prove game compatibility.')
        self.status.setText('Converter finished. Open the PKG builder to inspect or package the output.' if success else f'Converter failed (exit {code}); review the log.')
        self.runbtn.setEnabled(True)
        self.set_conversion_actions_enabled(True)

    def reject(self):
        if not self.conversion_busy() and not (self.worker and self.worker.isRunning()):
            super().reject()

    def closeEvent(self,event):
        if self.process is not None and self.process.state()!=self.process.ProcessState.NotRunning:
            QMessageBox.information(self,'Converter running','Close after the converter has finished; it will not be terminated automatically.')
            event.ignore();return
        if self.worker is not None and self.worker.isRunning():
            QMessageBox.information(self,'Staging running','Close after staging finishes.')
            event.ignore();return
        super().closeEvent(event)

class Window(BaseWindow):
    def __init__(self,root):
        super().__init__(root);self.setWindowTitle("Z's Save Archive • PS3 + PC  v2.0")
        self.tools_btn.menu().addSeparator()
        self.tools_btn.menu().addAction('PS3 ISO → XMB Conversion Assistant',lambda:ConverterDialog(self).exec())

def main():
    from . import ui
    ui.Archive=ArchiveV18
    app=QApplication(sys.argv);app.setStyle('Fusion');app.setStyleSheet(STYLE)
    home=os.environ.get('Z_ARCHIVE_HOME')
    if home:root=Path(home)
    elif (Path(sys.argv[0]).resolve().parent/'portable.flag').is_file():root=Path(sys.argv[0]).resolve().parent/'ArchiveData'
    else:root=Path.home()/'Documents'/'Z PlayStation Save Archive'
    window=Window(root);window.show();sys.exit(app.exec())
