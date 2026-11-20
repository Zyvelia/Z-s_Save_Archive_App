"""v2.8 compact workflow additions over v2.7, avoiding another crowded Tools menu."""
from __future__ import annotations
import json,os,subprocess,sys
from datetime import datetime,timezone
from pathlib import Path
from PySide6.QtCore import QTimer
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication,QDialog,QVBoxLayout,QHBoxLayout,QLabel,QLineEdit,QPushButton,QPlainTextEdit,QFileDialog,QMessageBox,QComboBox
from .ui_v27 import Window as BaseWindow
from .ui_v04 import STYLE
from .app_assets import asset_path
from .workflows_v28 import compare_pkgs,firmware_compatibility,cloud_conflict_preview,ExitBackupMonitor

class PackageAndCompatibility(QDialog):
    def __init__(self,parent=None):
        super().__init__(parent);self.setWindowTitle('Packages & Compatibility • v2.8');self.resize(780,560)
        layout=QVBoxLayout(self)
        layout.addWidget(QLabel('Read-only PKG comparisons and advisory compatibility checks. No PS3 writes.'))
        row=QHBoxLayout();layout.addLayout(row)
        for label,call in [('Compare PKGs / Find Duplicates',self.compare),('Firmware Compatibility Notes',self.compat),('Cloud Restore Preview',self.cloud)]:
            b=QPushButton(label);b.clicked.connect(call);row.addWidget(b)
        self.output=QPlainTextEdit();self.output.setReadOnly(True);layout.addWidget(self.output)
    def compare(self):
        files=QFileDialog.getOpenFileNames(self,'Select packages','','PS3 Packages (*.pkg)')[0]
        if files:self.output.setPlainText(json.dumps(compare_pkgs(files),indent=2))
    def compat(self):
        self.output.setPlainText(json.dumps(firmware_compatibility(),indent=2))
    def cloud(self):
        path=QFileDialog.getExistingDirectory(self,'Select target save folder')
        if path:self.output.setPlainText(json.dumps(cloud_conflict_preview(path),indent=2))

class GameExitBackup(QDialog):
    def __init__(self,archive,parent=None):
        super().__init__(parent);self.archive=archive;self.monitor=None
        self.setWindowTitle('Backup on game exit • opt-in session');self.resize(630,410)
        layout=QVBoxLayout(self)
        layout.addWidget(QLabel('Windows only. Select a registered backup rule and enter the game executable name.\n'
                                'Monitoring runs only while this dialog is open. It never terminates the game.'))
        self.choices=QComboBox();self.rules=archive.backup_rules()
        for r in self.rules:self.choices.addItem(f"{r['game']} — {r['path']}",r['watch_id'])
        layout.addWidget(self.choices)
        self.exe=QLineEdit();self.exe.setPlaceholderText('Example: Borderlands2.exe');layout.addWidget(self.exe)
        row=QHBoxLayout();layout.addLayout(row)
        self.start=QPushButton('Start session monitoring');self.start.clicked.connect(self.enable);row.addWidget(self.start)
        self.stop=QPushButton('Stop');self.stop.clicked.connect(self.disable);row.addWidget(self.stop)
        self.output=QPlainTextEdit();self.output.setReadOnly(True);layout.addWidget(self.output)
        self.timer=QTimer(self);self.timer.setInterval(3000);self.timer.timeout.connect(self.tick)
        if sys.platform!='win32':self.start.setEnabled(False);self.output.setPlainText('Game-exit detection requires Windows.')
    def enable(self):
        if self.choices.currentIndex()<0:return QMessageBox.warning(self,'Missing rule','Register a watched PC save folder first.')
        name=self.exe.text().strip()
        if not name.lower().endswith('.exe'):return QMessageBox.warning(self,'Executable required','Enter a Windows executable basename ending in .exe.')
        selected=self.rules[self.choices.currentIndex()]
        if not selected['enabled']:return QMessageBox.warning(self,'Rule not enabled','Enable this backup rule in PC Discovery & Backups first.')
        def backup():
            try:
                label='Game exit snapshot '+datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')
                result=self.archive.import_pc_save(Path(selected['path']),selected['game'],label=label)
                self.output.appendPlainText('Game exited; snapshot imported: '+str(result))
            except ValueError as exc:
                self.output.appendPlainText('Game-exit snapshot skipped: '+str(exc)[:200])
            except Exception as exc:
                self.output.appendPlainText('Game-exit backup FAILED: '+str(exc)[:200])
        try:self.monitor=ExitBackupMonitor(name,backup,minimum_interval=60)
        except ValueError as exc:return QMessageBox.warning(self,'Invalid executable',str(exc))
        self.output.appendPlainText('Monitoring '+name+'; closes with this dialog.');self.timer.start();self.tick()
    def disable(self):self.timer.stop();self.monitor=None;self.output.appendPlainText('Monitoring stopped.')
    def tick(self):
        if not self.monitor:return
        try:
            proc=subprocess.run(['tasklist','/FO','CSV','/NH'],capture_output=True,text=True,timeout=6,check=True)
            import csv,io
            names=[r[0] for r in csv.reader(io.StringIO(proc.stdout)) if r]
            state=self.monitor.check(names)
            if state=='backup_triggered':self.output.appendPlainText('Snapshot check completed.')
        except Exception as exc:self.output.appendPlainText('Process scan error: '+str(exc)[:200]);self.disable()
    def reject(self):self.disable();super().reject()

class Window(BaseWindow):
    def __init__(self,root):
        super().__init__(root)
        self.setWindowTitle("Z's Save Archive • PS3 + PC v2.8")
        menu=self.tools_btn.menu()
        def section(name):
            for act in menu.actions():
                if act.menu() and act.text()==name:return act.menu()
            return menu
        section('Homebrew, ISO & Packages').addAction('PKG Comparison & Compatibility',lambda:PackageAndCompatibility(self).exec())
        section('PC Discovery & Backups').addAction('Backup After Game Exit (opt-in)',lambda:GameExitBackup(self.archive,self).exec())

def main():
    from . import ui
    from .editor_v18 import ArchiveV18
    ui.Archive=ArchiveV18
    app=QApplication(sys.argv);app.setStyle('Fusion');app.setStyleSheet(STYLE)
    app.setWindowIcon(QIcon(str(asset_path('ZSaveArchive.png'))))
    home=os.environ.get('Z_ARCHIVE_HOME')
    if home:root=Path(home)
    elif (Path(sys.argv[0]).resolve().parent/'portable.flag').is_file():root=Path(sys.argv[0]).resolve().parent/'ArchiveData'
    else:root=Path.home()/'Documents'/'Z PlayStation Save Archive'
    win=Window(root);win.setWindowIcon(app.windowIcon());win.show();sys.exit(app.exec())
