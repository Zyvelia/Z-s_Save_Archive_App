"""v0.8 persistent FTP queue and resumable read-only transfers."""
from __future__ import annotations
import os,sys
from pathlib import Path
from PySide6.QtWidgets import QApplication,QDialog,QMessageBox
from .ui_v07 import Window as PreviousWindow
from .ui_v06 import FTPBrowser as PreviousFTPBrowser, TransferWorker as BaseWorker
from .ui_v04 import STYLE
from .transfers_v08 import ResumablePS3FTP,TransferQueue
from .workflows_v07 import download_with_retry
from .transfer_v06 import pc_save_candidates
from . import ui_v06

class TransferWorker(BaseWorker):
    def run(self):
        try:
            for path in self.paths:
                if self.cancelled:break
                try:
                    result=download_with_retry(self.api,path,self.archive,
                        progress=lambda size,name:self.progress.emit(path,size,name),
                        cancel=lambda:self.cancelled,max_attempts=3,
                        notify=lambda n,reason:self.progress.emit(path,0,'Retry '+str(n)+' · '+reason[:55]))
                    self.complete.emit(path,result,'')
                except Exception as exc:self.complete.emit(path,None,str(exc))
        finally:self.finished.emit()

ui_v06.TransferWorker=TransferWorker

class FTPBrowser(PreviousFTPBrowser):
    def __init__(self,archive,parent=None):
        super().__init__(archive,parent)
        self.queue_store=TransferQueue(Path(archive.root)/'transfer_queue_v08.json')
        self.setWindowTitle('PS3 FTP · Persistent Queue & Safe Resume')
        self.status.setText('Queue stored locally. Passwords are never saved. Enter PS3 IP and connect to recover pending jobs.')

    def config(self):
        return ResumablePS3FTP(self.host.text(),self.user.text(),self.password.text(),self.port.value(),
                               staging_root=Path(self.archive.root)/'transfer_staging_v08')

    def connect_ps3(self):
        super().connect_ps3()
        if self.api:
            self.queue.clear();self.items.clear()
            for j in self.queue_store.jobs:
                if (j['host'],j['port'])==(self.api.host,self.api.port) and j['status']=='pending':
                    self.queue.append(j['path']);self.items.addItem('Pending · '+j['path'].rsplit('/',1)[-1])
            self.status.setText(f'Connected. {len(self.queue)} pending transfers recovered.')

    def queue_save(self,path):
        if not self.api:return
        if self.queue_store.add(self.api.host,self.api.port,path):super().queue_save(path)

    def clear_pending(self):
        if self.thread is not None:return
        if self.api:
            for path in self.queue:self.queue_store.update(self.api.host,self.api.port,path,'failed','Removed from pending queue')
        super().clear_pending()

    def on_complete(self,path,record,error):
        if self.api:
            status='pending' if 'cancel' in error.lower() else ('failed' if error else 'completed')
            if status!='pending':self.queue_store.update(self.api.host,self.api.port,path,status,error)
        super().on_complete(path,record,error)

    def cancel_queue(self):
        super().cancel_queue()
        self.status.setText('Cancelling; remaining pending saves are retained for the next session.')

class Window(PreviousWindow):
    def __init__(self,root):
        super().__init__(root)
        self.setWindowTitle("Z's Save Archive  •  PS3 + PC  v0.8")
        self.statusBar().showMessage('v0.8 · durable PS3 transfer queue · guarded per-file resume')

    def show_ftp(self):
        dialog=FTPBrowser(self.archive,self);dialog.exec()

def main():
    app=QApplication(sys.argv);app.setStyle('Fusion');app.setStyleSheet(STYLE)
    home=os.environ.get('Z_ARCHIVE_HOME')
    if home:root=Path(home)
    elif (Path(sys.argv[0]).resolve().parent/'portable.flag').is_file():root=Path(sys.argv[0]).resolve().parent/'ArchiveData'
    else:root=Path.home()/'Documents'/'Z PlayStation Save Archive'
    win=Window(root);win.show();sys.exit(app.exec())
