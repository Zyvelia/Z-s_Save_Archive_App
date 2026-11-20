"""PS3 Homebrew Manager: official reference links, PKG library and confirmed upload."""
from __future__ import annotations
import os,sys
from pathlib import Path
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtCore import QUrl
from PySide6.QtWidgets import (QApplication,QDialog,QVBoxLayout,QHBoxLayout,QLabel,QPushButton,
    QFileDialog,QMessageBox,QLineEdit,QTableWidget,QTableWidgetItem,QHeaderView,QPlainTextEdit,QTabWidget,
    QWidget,QFormLayout,QAbstractItemView)
from .ui_v21 import Window as V21Window
from .ui_v04 import STYLE
from .editor_v18 import ArchiveV18
from .homebrew_v22 import CATALOG,inspect_homebrew_pkg,upload_homebrew_pkg,record_history,read_history

class UploadWorker(QThread):
    done=Signal(object);error=Signal(str);progress=Signal(int,int)
    def __init__(self,path,host,user,password):
        super().__init__();self.path=path;self.host=host;self.user=user;self.password=password
    def run(self):
        try:
            self.done.emit(upload_homebrew_pkg(self.path,self.host,username=self.user,password=self.password,
                progress=lambda sent,total:self.progress.emit(sent,total)))
        except Exception as exc:self.error.emit(str(exc))

class HomebrewDialog(QDialog):
    def __init__(self,parent=None,root=None):
        super().__init__(parent)
        self.setWindowTitle('PS3 Homebrew Manager • v2.2');self.resize(880,650)
        self.root=Path(root or Path.home()/'Documents'/'Z PlayStation Save Archive')
        self.history_file=self.root/'homebrew'/'upload_history.json'
        self.packages=[];self.worker=None
        layout=QVBoxLayout(self)
        heading=QLabel('PS3 Homebrew Manager');heading.setStyleSheet('font-size:20px;font-weight:700');layout.addWidget(heading)
        note=QLabel('Browse trusted project pages, add locally downloaded homebrew PKGs, and send them to your CFW PS3. Uploading never installs or runs a package. Installation is manual on the console.');note.setWordWrap(True);layout.addWidget(note)
        self.tabs=QTabWidget();layout.addWidget(self.tabs,1)
        catalog_page=QWidget();cl=QVBoxLayout(catalog_page)
        cat=QTableWidget(len(CATALOG),3);cat.setHorizontalHeaderLabels(['App','Type','Description']);cat.horizontalHeader().setSectionResizeMode(2,QHeaderView.ResizeMode.Stretch)
        cat.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows);cat.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        for i,app in enumerate(CATALOG):
            for j,key in enumerate(('name','group','description')):cat.setItem(i,j,QTableWidgetItem(app[key]))
        cl.addWidget(cat)
        source_button=QPushButton('Open selected project page');source_button.clicked.connect(lambda:self.open_project(cat.currentRow()));cl.addWidget(source_button)
        cl.addWidget(QLabel('Catalog contains reference links, not bundled applications. Verify each release and your firmware compatibility before installing.'))
        self.tabs.addTab(catalog_page,'Homebrew Catalog')
        pkg_page=QWidget();pl=QVBoxLayout(pkg_page)
        self.table=QTableWidget(0,3);self.table.setHorizontalHeaderLabels(['PKG filename','Size','SHA-256 (short)']);self.table.horizontalHeader().setSectionResizeMode(0,QHeaderView.ResizeMode.Stretch)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows);self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        pl.addWidget(self.table)
        row=QHBoxLayout();pl.addLayout(row)
        add=QPushButton('Add local PKG files');add.clicked.connect(self.add_packages);row.addWidget(add)
        remove=QPushButton('Remove from list');remove.clicked.connect(self.remove_package);row.addWidget(remove)
        form=QFormLayout();pl.addLayout(form)
        self.host=QLineEdit();self.host.setPlaceholderText('e.g. 192.168.1.50')
        self.user=QLineEdit('anonymous');self.password=QLineEdit();self.password.setEchoMode(QLineEdit.EchoMode.Password)
        form.addRow('PS3 IP / hostname',self.host);form.addRow('FTP username',self.user);form.addRow('FTP password (not saved)',self.password)
        self.send=QPushButton('Upload selected PKG to PS3 (requires confirmation)');self.send.clicked.connect(self.upload);pl.addWidget(self.send)
        self.log=QPlainTextEdit();self.log.setReadOnly(True);pl.addWidget(self.log,1)
        self.tabs.addTab(pkg_page,'PKG Upload')
        history_page=QWidget();hl=QVBoxLayout(history_page)
        self.history_box=QPlainTextEdit();self.history_box.setReadOnly(True);hl.addWidget(self.history_box)
        refresh=QPushButton('Refresh history');refresh.clicked.connect(self.refresh_history);hl.addWidget(refresh)
        self.tabs.addTab(history_page,'Upload History')
        self.refresh_history()
    def open_project(self,index):
        if index<0 or index>=len(CATALOG):return
        QDesktopServices.openUrl(QUrl(CATALOG[index]['url']))
    def add_packages(self):
        paths=QFileDialog.getOpenFileNames(self,'Select trusted PS3 homebrew PKGs','','PS3 packages (*.pkg)')[0]
        for path in paths:
            try:info=inspect_homebrew_pkg(path)
            except Exception as exc:
                QMessageBox.warning(self,'Invalid PKG',f'{Path(path).name}: {exc}');continue
            if any(x['path']==info['path'] for x in self.packages):continue
            self.packages.append(info)
            row=self.table.rowCount();self.table.insertRow(row)
            for col,value in enumerate((info['filename'],f"{info['bytes']:,} bytes",info['sha256'][:16])):
                self.table.setItem(row,col,QTableWidgetItem(value))
        if self.packages and self.table.currentRow()<0:self.table.selectRow(0)
    def remove_package(self):
        i=self.table.currentRow()
        if i<0 or i>=len(self.packages):return
        self.packages.pop(i);self.table.removeRow(i)
    def upload(self):
        row=self.table.currentRow()
        if row<0 or row>=len(self.packages):return QMessageBox.information(self,'Select PKG','Select a package first.')
        if self.worker and self.worker.isRunning():return QMessageBox.information(self,'Transfer running','Finish the active transfer first.')
        selected=self.packages[row]
        try:
            fresh=inspect_homebrew_pkg(selected['path'])
            if fresh['sha256']!=selected['sha256']:raise ValueError('File changed since it was added. Remove and re-add it.')
        except Exception as exc:return QMessageBox.warning(self,'Validation failed',str(exc))
        host=self.host.text().strip()
        if not host:return QMessageBox.warning(self,'Missing PS3 address','Enter your PS3 FTP address.')
        message=(f"Upload {selected['filename']} ({selected['bytes']:,} bytes) to {host}:/dev_hdd0/packages/?\n\n"
                 'This does NOT install the app. Existing remote files will not be overwritten.\n'
                 'Only use packages from sources you trust. Continue?')
        if QMessageBox.question(self,'Confirm homebrew upload',message)!=QMessageBox.StandardButton.Yes:return
        self.send.setEnabled(False)
        self.log.appendPlainText('Uploading '+selected['filename']+'...')
        self.worker=UploadWorker(selected['path'],host,self.user.text().strip() or 'anonymous',self.password.text())
        self.worker.progress.connect(lambda sent,total:self.log_progress(sent,total))
        self.worker.done.connect(lambda result:self.on_success(selected,result))
        self.worker.error.connect(lambda error:self.on_error(selected,error))
        self.worker.finished.connect(lambda:self.send.setEnabled(True))
        self.worker.start()
    def log_progress(self,sent,total):
        self.setWindowTitle(f'PS3 Homebrew Manager • Upload {sent*100//max(total,1)}%')
    def on_success(self,info,result):
        record_history(self.history_file,filename=info['filename'],status='uploaded',sha256=info['sha256'],details=result['remote_path'])
        self.log.appendPlainText('Uploaded: '+result['remote_path']+' (FTP size checked, not remote SHA-256).\nInstall on PS3: Game → Package Manager → Install Package Files → PS3 System Storage.')
        self.refresh_history();self.setWindowTitle('PS3 Homebrew Manager • v2.2')
    def on_error(self,info,error):
        record_history(self.history_file,filename=info['filename'],status='failed',sha256=info['sha256'],details=error)
        self.log.appendPlainText('Upload failed: '+error);self.refresh_history();QMessageBox.warning(self,'Upload failed',error)
        self.setWindowTitle('PS3 Homebrew Manager • v2.2')
    def refresh_history(self):
        entries=read_history(self.history_file)
        self.history_box.setPlainText('\n'.join(f"{e.get('timestamp','')} | {e.get('status','')} | {e.get('filename','')} | {e.get('details','')}" for e in reversed(entries)) or 'No uploads recorded yet.')
    def closeEvent(self,event):
        if self.worker and self.worker.isRunning():
            QMessageBox.information(self,'Upload running','Finish the current upload before closing.');event.ignore();return
        self.password.clear();super().closeEvent(event)

class Window(V21Window):
    def __init__(self,root):
        super().__init__(root)
        self.setWindowTitle("Z's Save Archive • PS3 + PC v2.2")
        self.tools_btn.menu().addSeparator()
        self.tools_btn.menu().addAction('PS3 Homebrew Manager',lambda:HomebrewDialog(self,root).exec())

def main():
    from . import ui
    ui.Archive=ArchiveV18
    app=QApplication(sys.argv);app.setStyle('Fusion');app.setStyleSheet(STYLE)
    home=os.environ.get('Z_ARCHIVE_HOME')
    if home:root=Path(home)
    elif (Path(sys.argv[0]).resolve().parent/'portable.flag').is_file():root=Path(sys.argv[0]).resolve().parent/'ArchiveData'
    else:root=Path.home()/'Documents'/'Z PlayStation Save Archive'
    win=Window(root);win.show();sys.exit(app.exec())

from .ui_v04 import STYLE
