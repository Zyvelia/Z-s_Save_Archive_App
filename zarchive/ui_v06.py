"""v0.6 non-destructive PS3 FTP browse/queue and PC save discovery."""
from __future__ import annotations
import os,sys
from pathlib import Path
from PySide6.QtCore import Qt,QThread,Signal,QObject
from PySide6.QtWidgets import (QApplication,QDialog,QVBoxLayout,QHBoxLayout,QLabel,QLineEdit,QSpinBox,
 QPushButton,QListWidget,QListWidgetItem,QMessageBox,QProgressBar,QInputDialog,QFileDialog,QDialogButtonBox)
from .ui_v05 import Window as PreviousWindow, main as _old_main
from .ui_v04 import STYLE
from .transfer_v06 import PS3FTP,ROOT,validate_path,child_path,SAVE_RE,pc_save_candidates
from . import ui

class TransferWorker(QObject):
    progress=Signal(str,int,str)
    complete=Signal(str,object,str)
    finished=Signal()
    def __init__(self,api,paths,archive):
        super().__init__();self.api=api;self.paths=list(paths);self.archive=archive;self.cancelled=False
    def run(self):
        try:
            for path in self.paths:
                if self.cancelled:break
                try:
                    result=self.api.download_save(path,self.archive,
                        progress=lambda size,name:self.progress.emit(path,size,name),
                        cancel=lambda:self.cancelled)
                    self.complete.emit(path,result,'')
                except Exception as exc:
                    self.complete.emit(path,None,str(exc))
        finally:self.finished.emit()

class FTPBrowser(QDialog):
    def __init__(self,archive,parent=None):
        super().__init__(parent)
        self.archive=archive;self.api=None;self.path=ROOT;self.queue=[];self.thread=None;self.worker=None
        self.setWindowTitle('PS3 FTP · Read-only Browser & Download Queue');self.resize(760,640)
        outer=QVBoxLayout(self)
        form=QHBoxLayout();self.host=QLineEdit();self.host.setPlaceholderText('PS3 IP address')
        self.host.setText('');self.user=QLineEdit('anonymous');self.user.setMaximumWidth(110)
        self.password=QLineEdit();self.password.setEchoMode(QLineEdit.EchoMode.Password);self.password.setPlaceholderText('Password');self.password.setMaximumWidth(150)
        self.port=QSpinBox();self.port.setRange(1,65535);self.port.setValue(21);self.port.setMaximumWidth(75)
        for w in (self.host,self.user,self.password,self.port):form.addWidget(w)
        outer.addLayout(form)
        bar=QHBoxLayout();self.connect_btn=QPushButton('Connect / Refresh');self.connect_btn.clicked.connect(self.connect_ps3)
        self.back_btn=QPushButton('Up Folder');self.back_btn.clicked.connect(self.go_up)
        self.add_btn=QPushButton('Queue Selected Save');self.add_btn.clicked.connect(self.add_selected)
        for w in (self.connect_btn,self.back_btn,self.add_btn):bar.addWidget(w)
        outer.addLayout(bar)
        self.location=QLabel(ROOT);outer.addWidget(self.location)
        self.files=QListWidget();self.files.itemDoubleClicked.connect(self.open_entry);outer.addWidget(self.files,3)
        outer.addWidget(QLabel('Transfer queue · Only selected save folders are downloaded; no console writes.'))
        self.items=QListWidget();outer.addWidget(self.items,2)
        buttons=QHBoxLayout();self.start_btn=QPushButton('Start Downloads');self.start_btn.clicked.connect(self.start_queue)
        self.cancel_btn=QPushButton('Cancel Transfers');self.cancel_btn.clicked.connect(self.cancel_queue)
        self.clear_btn=QPushButton('Clear Pending');self.clear_btn.clicked.connect(self.clear_pending)
        for w in (self.start_btn,self.cancel_btn,self.clear_btn):buttons.addWidget(w)
        outer.addLayout(buttons)
        self.progress=QProgressBar();self.progress.setRange(0,1);self.progress.setValue(0);outer.addWidget(self.progress)
        self.status=QLabel('Not connected.');outer.addWidget(self.status)

    def config(self):
        return PS3FTP(self.host.text(),self.user.text(),self.password.text(),self.port.value())
    def connect_ps3(self):
        if self.thread is not None:return
        try:
            api=self.config();rows=api.list(ROOT)
            self.api=api;self.path=ROOT;self.populate(rows)
            self.status.setText('Connected; showing PS3 profile directories')
        except Exception as exc:QMessageBox.warning(self,'PS3 connection',str(exc))
    def populate(self,rows):
        self.files.clear();self.location.setText(self.path)
        for row in rows:
            item=QListWidgetItem(('📁  ' if row.is_dir else '    ')+row.name)
            item.setData(Qt.ItemDataRole.UserRole,(row.name,row.is_dir))
            self.files.addItem(item)
    def open_entry(self,item):
        if self.thread is not None or not self.api:return
        name,is_dir=item.data(Qt.ItemDataRole.UserRole)
        if not is_dir:return
        try:
            nextpath=child_path(self.path,name)
            if SAVE_RE.fullmatch(nextpath):
                self.queue_save(nextpath);return
            rows=self.api.list(nextpath)
            self.path=nextpath;self.populate(rows)
        except Exception as exc:QMessageBox.warning(self,'Browse failed',str(exc))
    def go_up(self):
        if self.thread is not None or not self.api or self.path==ROOT:return
        try:
            parent=self.path.rsplit('/',1)[0]
            if not parent.startswith(ROOT):parent=ROOT
            rows=self.api.list(parent);self.path=parent;self.populate(rows)
        except Exception as exc:QMessageBox.warning(self,'Browse failed',str(exc))
    def queue_save(self,path):
        if not SAVE_RE.fullmatch(path):return
        if path not in self.queue:
            self.queue.append(path);self.items.addItem('Pending · '+path.rsplit('/',1)[-1])
    def add_selected(self):
        if self.thread is not None:return
        item=self.files.currentItem()
        if not item:return
        name,is_dir=item.data(Qt.ItemDataRole.UserRole)
        if not is_dir:return
        try:self.queue_save(child_path(self.path,name))
        except ValueError:pass
    def clear_pending(self):
        if self.thread is None:self.queue.clear();self.items.clear()
    def start_queue(self):
        if self.thread is not None or not self.queue:return
        try:api=self.config()
        except ValueError as exc:QMessageBox.warning(self,'Invalid connection',str(exc));return
        if QMessageBox.question(self,'Download selected saves',f'Download {len(self.queue)} save folder(s) from your PS3 into the local archive?\nOriginal PS3 files are never modified.')!=QMessageBox.StandardButton.Yes:return
        self.api=api;self.progress.setRange(0,0)
        self.thread=QThread(self);self.worker=TransferWorker(api,self.queue,self.archive);self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)
        self.worker.progress.connect(self.on_progress);self.worker.complete.connect(self.on_complete)
        self.worker.finished.connect(self.thread.quit);self.worker.finished.connect(self.worker.deleteLater)
        self.thread.finished.connect(self.done_queue);self.thread.start()
        self.start_btn.setEnabled(False);self.connect_btn.setEnabled(False)
    def on_progress(self,path,size,name):self.status.setText(f'{path.rsplit("/",1)[-1]} · {name} · {size:,} bytes received')
    def on_complete(self,path,record,error):
        for i in range(self.items.count()):
            if path.rsplit('/',1)[-1] in self.items.item(i).text() and 'Pending' in self.items.item(i).text():
                self.items.item(i).setText(('Failed · ' if error else 'Imported · ')+path.rsplit('/',1)[-1]+(' · '+error[:90] if error else ''));break
        if not error and self.parent():self.parent().refresh()
    def done_queue(self):
        self.thread.wait();self.thread.deleteLater();self.thread=None;self.worker=None;self.queue=[]
        self.progress.setRange(0,1);self.progress.setValue(1)
        self.start_btn.setEnabled(True);self.connect_btn.setEnabled(True)
        self.status.setText('Queue finished (check each item above for success or failure)')
    def cancel_queue(self):
        if self.worker:self.worker.cancelled=True;self.status.setText('Cancellation requested; current FTP read will stop on next data block')
    def closeEvent(self,event):
        if self.thread is not None:
            QMessageBox.information(self,'Transfer active','Cancel the transfer and wait until it stops before closing this window.')
            event.ignore();return
        super().closeEvent(event)

class Window(PreviousWindow):
    def __init__(self,root):
        super().__init__(root)
        self.setWindowTitle("Z's Save Archive  •  PS3 + PC  v0.6")
        self.statusBar().showMessage('v0.6 · PS3 transfer browser and PC save discovery')
        self.ftp_btn.setText('PS3 FTP Browser')
        self.steam_btn.setText('Discover PC Saves')
    def show_ftp(self):
        dialog=FTPBrowser(self.archive,self);dialog.exec()
    def show_pc_discovery(self):
        from .integrations import steam_games
        candidates=pc_save_candidates();games=steam_games()
        dialog=QDialog(self);dialog.resize(740,500);dialog.setWindowTitle('Discover PC save locations')
        lay=QVBoxLayout(dialog);lay.addWidget(QLabel('Candidate folders only — verify the game and save contents before importing.'))
        rows=QListWidget();lay.addWidget(rows)
        for entry in candidates:
            item=QListWidgetItem(f"{entry['name']}  ·  {entry['path']}")
            item.setData(Qt.ItemDataRole.UserRole,entry['path']);rows.addItem(item)
        lay.addWidget(QLabel(f'Installed Steam manifests found: {len(games)} (game installation does not confirm a save folder).'))
        btns=QHBoxLayout();openbtn=QPushButton('Open Selected Folder');importbtn=QPushButton('Import Selected Folder as PC Save');closebtn=QPushButton('Close')
        for b in (openbtn,importbtn,closebtn):btns.addWidget(b)
        lay.addLayout(btns)
        def selected():
            item=rows.currentItem();return Path(item.data(Qt.ItemDataRole.UserRole)) if item else None
        def open_folder():
            p=selected()
            if p:
                from PySide6.QtGui import QDesktopServices
                from PySide6.QtCore import QUrl
                QDesktopServices.openUrl(QUrl.fromLocalFile(str(p)))
        def import_folder():
            p=selected()
            if not p:return
            game,ok=QInputDialog.getText(dialog,'PC game title','Name of game for this selected folder:')
            if not ok or not game.strip():return
            if QMessageBox.question(dialog,'Import folder?',f'Import all supported files under {p} as ONE save for {game}?\nThis may contain unrelated game data. Prefer selecting an individual game save directory.')!=QMessageBox.StandardButton.Yes:return
            try:self.archive.import_pc_save(p,game.strip());self.refresh();QMessageBox.information(dialog,'Imported','PC save copied into archive')
            except Exception as exc:QMessageBox.warning(dialog,'Import failed',str(exc))
        openbtn.clicked.connect(open_folder);importbtn.clicked.connect(import_folder);closebtn.clicked.connect(dialog.accept)
        dialog.exec()

def main():
    app=QApplication(sys.argv);app.setStyle('Fusion');app.setStyleSheet(STYLE)
    home=os.environ.get('Z_ARCHIVE_HOME')
    if home:root=Path(home)
    elif (Path(sys.argv[0]).resolve().parent/'portable.flag').is_file():root=Path(sys.argv[0]).resolve().parent/'ArchiveData'
    else:root=Path.home()/'Documents'/'Z PlayStation Save Archive'
    win=Window(root);win.show();sys.exit(app.exec())
