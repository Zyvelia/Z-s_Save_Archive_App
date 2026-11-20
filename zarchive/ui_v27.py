"""v2.7 opt-in diagnostics UI, preserving v2.6 converter and homebrew screens."""
from __future__ import annotations
import json,os,sys
from pathlib import Path
from PySide6.QtCore import QThread,Signal
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication,QDialog,QVBoxLayout,QHBoxLayout,QLabel,QLineEdit,QPushButton,QPlainTextEdit,QFileDialog,QMessageBox,QFormLayout
from .ui_v24 import Window as BaseWindow
from .ui_v04 import STYLE
from .app_assets import asset_path
from .console_v27 import check_ftp, discover_ps3_hosts, conversion_preflight, save_diagnostic_report

class NetworkWorker(QThread):
    result=Signal(object); failed=Signal(str)
    def __init__(self,kind,value):super().__init__();self.kind=kind;self.value=value
    def run(self):
        try:self.result.emit(check_ftp(self.value) if self.kind=='check' else discover_ps3_hosts(self.value))
        except Exception as exc:self.failed.emit(str(exc))

class ConsoleDiagnostics(QDialog):
    def __init__(self,parent=None):
        super().__init__(parent);self.setWindowTitle('PS3 Diagnostics • read-only v2.7');self.resize(700,520)
        self.worker=None;self.last={}
        root=QVBoxLayout(self)
        root.addWidget(QLabel('Opt-in LAN diagnostics. FTP port checks cannot verify firmware, temperature, uptime or free HDD space.'))
        form=QFormLayout();root.addLayout(form)
        self.host=QLineEdit('192.168.1.50');form.addRow('PS3 IPv4 address:',self.host)
        self.subnet=QLineEdit('192.168.1.0/27');form.addRow('Small private LAN subnet (up to 32 hosts):',self.subnet)
        row=QHBoxLayout();root.addLayout(row)
        self.check=QPushButton('Check FTP port');self.check.clicked.connect(lambda:self.start('check'));row.addWidget(self.check)
        self.scan=QPushButton('Discover FTP endpoints');self.scan.clicked.connect(lambda:self.start('discover'));row.addWidget(self.scan)
        self.export=QPushButton('Export privacy-safe report');self.export.clicked.connect(self.save_report);row.addWidget(self.export)
        self.output=QPlainTextEdit();self.output.setReadOnly(True);root.addWidget(self.output)
        root.addWidget(QLabel('LAN discovery checks for reachable FTP services, not confirmed PS3 consoles.'))
    def start(self,kind):
        if self.worker and self.worker.isRunning():return
        val=(self.host if kind=='check' else self.subnet).text().strip()
        self.worker=NetworkWorker(kind,val);self.worker.result.connect(self.show_result);self.worker.failed.connect(self.show_error)
        self.check.setEnabled(False);self.scan.setEnabled(False)
        self.worker.finished.connect(lambda:(self.check.setEnabled(True),self.scan.setEnabled(True)))
        self.output.setPlainText('Checking…');self.worker.start()
    def show_result(self,result):
        self.last=result;self.output.setPlainText(json.dumps(result,indent=2))
    def show_error(self,message):
        self.output.setPlainText('Diagnostic failed: '+message)
    def save_report(self):
        if not self.last:return QMessageBox.information(self,'No report','Run a diagnostic first.')
        path,_=QFileDialog.getSaveFileName(self,'Export report','','JSON (*.json)')
        if path:
            try:save_diagnostic_report(path,self.last)
            except Exception as exc:QMessageBox.warning(self,'Export failed',str(exc))
    def reject(self):
        if self.worker and self.worker.isRunning():
            return QMessageBox.information(self,'Scan in progress','Close after the current bounded LAN scan completes.')
        super().reject()

class ConversionPreflight(QDialog):
    def __init__(self,parent=None):
        super().__init__(parent);self.setWindowTitle('ISO Conversion Preflight v2.7');self.resize(740,560)
        root=QVBoxLayout(self)
        root.addWidget(QLabel('Read-only conversion check: validates source, tools, new workspace and estimated staging space.'))
        form=QFormLayout();root.addLayout(form)
        self.entries={}
        for key,label in [('source','ISO or PS3_GAME'),('helper','CFW2OFW Helper.exe'),('extractor','7z.exe (ISO only)'),('target','New work directory')]:
            row=QHBoxLayout();edit=QLineEdit();self.entries[key]=edit;row.addWidget(edit)
            b=QPushButton('Browse…');b.clicked.connect(lambda _,k=key:self.browse(k));row.addWidget(b)
            form.addRow(label,row)
        button=QPushButton('Run Preflight');button.clicked.connect(self.inspect);root.addWidget(button)
        self.out=QPlainTextEdit();self.out.setReadOnly(True);root.addWidget(self.out)
    def browse(self,key):
        if key=='target':
            folder=QFileDialog.getExistingDirectory(self,'Select work parent')
            if folder:self.entries[key].setText(str(Path(folder)/'PS3_Conversion_New'))
        elif key=='source':
            file,_=QFileDialog.getOpenFileName(self,'Choose ISO','','ISO (*.iso)')
            if not file:file=QFileDialog.getExistingDirectory(self,'Or select extracted game folder')
            if file:self.entries[key].setText(file)
        else:
            file,_=QFileDialog.getOpenFileName(self,'Choose executable','','Executables (*.exe)')
            if file:self.entries[key].setText(file)
    def inspect(self):
        try:
            data=conversion_preflight(**{k:v.text().strip() for k,v in self.entries.items()})
            self.out.setPlainText(json.dumps(data,indent=2,default=str))
        except Exception as exc:self.out.setPlainText('Preflight error: '+str(exc))

class Window(BaseWindow):
    def __init__(self,root):
        super().__init__(root)
        self.setWindowTitle("Z's Save Archive • PS3 + PC v2.7")
        # Place additions in existing grouped submenus, not a new giant Tools list.
        menu=self.tools_btn.menu()
        def find_section(name):
            for action in menu.actions():
                if action.menu() and action.text()==name:return action.menu()
            return menu
        find_section('PS3 & Connections').addAction('PS3 LAN Diagnostics (read-only)',lambda:ConsoleDiagnostics(self).exec())
        find_section('Homebrew, ISO & Packages').addAction('ISO Conversion Preflight',lambda:ConversionPreflight(self).exec())

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
