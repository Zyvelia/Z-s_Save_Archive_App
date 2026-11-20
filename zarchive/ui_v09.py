"""v0.9 responsive read-only PS3 browsing, recovery view, bounded PC candidate validation."""
from __future__ import annotations
import os,sys
from pathlib import Path
from PySide6.QtCore import Qt,QObject,QThread,Signal
from PySide6.QtWidgets import (QApplication,QMessageBox,QLabel,QPushButton,QListWidget,
    QListWidgetItem,QVBoxLayout,QDialog,QHBoxLayout,QProgressBar,QInputDialog)
from .ui_v08 import Window as PreviousWindow,FTPBrowser as BaseFTPBrowser
from .ui_v04 import STYLE
from .transfer_v06 import ROOT,SAVE_RE,child_path
from .reliability_v09 import inspect_pc_candidate,recoverable_jobs,retry_failed
from . import ui_v06
from .ui_ps3_live_stats import LiveTemperatures

class ListingWorker(QObject):
    result=Signal(str,object,str)
    finished=Signal()
    def __init__(self,api,path):
        super().__init__();self.api=api;self.path=path
    def run(self):
        try:self.result.emit(self.path,self.api.list(self.path),'')
        except Exception as exc:self.result.emit(self.path,[],str(exc))
        finally:self.finished.emit()

class FTPBrowser(BaseFTPBrowser):
    def __init__(self,archive,parent=None):
        super().__init__(archive,parent)
        self.setWindowTitle('PS3 FTP · Browse, Recover & Download')
        self.resize(880,710)
        self.browse_thread=None;self.browse_worker=None;self.browse_new_connection=False
        self.completed_count=0;self.transfer_total=0
        self.recover_btn=QPushButton('Recover Failed Transfers')
        self.recover_btn.clicked.connect(self.show_recovery)
        self.recovery_status=QLabel('No remote changes are made. Failed downloads can be requeued manually.')
        self.layout().insertWidget(self.layout().count()-2,self.recover_btn)
        self.layout().insertWidget(self.layout().count()-2,self.recovery_status)
        self.progress.setFormat('%v / %m saves processed')
        live = QPushButton('Live Temperatures')
        live.clicked.connect(lambda: LiveTemperatures(self.host.text().strip(), self).exec())
        self.layout().insertWidget(1, live)

    def _browse(self,path,new_connection=False):
        if self.browse_thread is not None or self.thread is not None:return
        try:api=self.config() if new_connection else self.api
        except Exception as exc:QMessageBox.warning(self,'Connection settings',str(exc));return
        if api is None:return
        self.browse_new_connection=new_connection
        self.pending_api=api
        self.connect_btn.setEnabled(False);self.back_btn.setEnabled(False)
        self.add_btn.setEnabled(False);self.files.setEnabled(False)
        self.status.setText('Loading '+path+' in background…')
        self.browse_thread=QThread(self)
        self.browse_worker=ListingWorker(api,path)
        self.browse_worker.moveToThread(self.browse_thread)
        self.browse_thread.started.connect(self.browse_worker.run)
        self.browse_worker.result.connect(self._listed)
        self.browse_worker.finished.connect(self.browse_thread.quit)
        self.browse_worker.finished.connect(self.browse_worker.deleteLater)
        self.browse_thread.finished.connect(self._listing_done)
        self.browse_thread.start()

    def _listed(self,path,rows,error):
        if error:
            self.status.setText('Browse failed: '+error[:180]);return
        if self.browse_new_connection:
            self.api=self.pending_api
            self.queue.clear();self.items.clear()
            for job in self.queue_store.jobs:
                if (job['host'],job['port'])==(self.api.host,self.api.port) and job['status']=='pending':
                    self.queue.append(job['path'])
                    self.items.addItem('Pending · '+job['path'].rsplit('/',1)[-1])
        self.path=path;self.populate(rows)
        self.status.setText(f'{len(rows)} entries · {len(self.queue)} queued saves · FTP read-only')
        self._update_recovery_count()

    def _listing_done(self):
        self.browse_thread.wait()
        self.browse_thread.deleteLater();self.browse_thread=None;self.browse_worker=None
        self.connect_btn.setEnabled(True);self.back_btn.setEnabled(True)
        self.add_btn.setEnabled(True);self.files.setEnabled(True)

    def connect_ps3(self):self._browse(ROOT,True)
    def open_entry(self,item):
        if self.browse_thread is not None or self.thread is not None or not self.api:return
        name,is_dir=item.data(Qt.ItemDataRole.UserRole)
        if not is_dir:return
        try:
            path=child_path(self.path,name)
            if SAVE_RE.fullmatch(path):self.queue_save(path)
            else:self._browse(path)
        except ValueError as exc:QMessageBox.warning(self,'Invalid path',str(exc))
    def go_up(self):
        if self.browse_thread is not None or self.thread is not None or not self.api or self.path==ROOT:return
        parent=self.path.rsplit('/',1)[0]
        if not parent.startswith(ROOT):parent=ROOT
        self._browse(parent)

    def _update_recovery_count(self):
        if self.api is None:return
        jobs=recoverable_jobs(self.queue_store,self.api.host,self.api.port)
        failed=sum(j['status']=='failed' for j in jobs)
        self.recovery_status.setText(f'{failed} failed and {len(jobs)-failed} pending jobs · passwords never saved')

    def show_recovery(self):
        if self.api is None:
            QMessageBox.information(self,'Connect first','Connect to the PS3 to review its stored jobs.');return
        if self.thread is not None or self.browse_thread is not None:return
        jobs=recoverable_jobs(self.queue_store,self.api.host,self.api.port)
        dialog=QDialog(self);dialog.resize(690,410);dialog.setWindowTitle('Transfer Recovery')
        lay=QVBoxLayout(dialog)
        lay.addWidget(QLabel('Choose failed save folders to retry. Pending saves stay queued.'))
        rows=QListWidget();rows.setSelectionMode(QListWidget.SelectionMode.MultiSelection)
        lay.addWidget(rows)
        for job in jobs:
            item=QListWidgetItem(f"{job['status'].title()} · {job['path']} · {job['detail'][:65]}")
            item.setData(Qt.ItemDataRole.UserRole,(job['path'],job['status']))
            rows.addItem(item)
        bar=QHBoxLayout();retry=QPushButton('Requeue Selected Failed');close=QPushButton('Close')
        bar.addWidget(retry);bar.addWidget(close);lay.addLayout(bar)
        def requeue():
            paths=[item.data(Qt.ItemDataRole.UserRole)[0] for item in rows.selectedItems()
                   if item.data(Qt.ItemDataRole.UserRole)[1]=='failed']
            if not paths:return
            n=retry_failed(self.queue_store,self.api.host,self.api.port,paths)
            for path in paths:
                if path not in self.queue and any(j['path']==path and j['status']=='pending' for j in self.queue_store.jobs):
                    self.queue.append(path);self.items.addItem('Pending · '+path.rsplit('/',1)[-1])
            self._update_recovery_count()
            QMessageBox.information(dialog,'Recovery',f'{n} failed transfer(s) requeued. Start downloads to retry.')
            dialog.accept()
        retry.clicked.connect(requeue);close.clicked.connect(dialog.accept);dialog.exec()

    def start_queue(self):
        if self.browse_thread is not None:return
        self.completed_count=0;self.transfer_total=len(self.queue)
        super().start_queue()
        if self.thread is not None:
            self.progress.setRange(0,self.transfer_total)
            self.progress.setValue(0)
    def on_progress(self,path,size,name):
        self.status.setText(f'{self.completed_count}/{self.transfer_total} saves · {path.rsplit("/",1)[-1]} · {name} · {size:,} bytes')
    def on_complete(self,path,record,error):
        super().on_complete(path,record,error)
        self.completed_count+=1
        self.progress.setValue(min(self.completed_count,self.transfer_total))
        self._update_recovery_count()
    def done_queue(self):
        super().done_queue()
        self.progress.setRange(0,max(1,self.transfer_total))
        self.progress.setValue(self.completed_count)
        self.status.setText(f'{self.completed_count}/{self.transfer_total} attempted · inspect failed jobs in Recovery')
        self._update_recovery_count()
    def closeEvent(self,event):
        if self.browse_thread is not None:
            QMessageBox.information(self,'Browse active','Directory listing is still running. Close after it finishes.')
            event.ignore();return
        super().closeEvent(event)

class Window(PreviousWindow):
    def __init__(self,root):
        super().__init__(root)
        self.setWindowTitle("Z's Save Archive  •  PS3 + PC  v0.9")
        self.statusBar().showMessage('v0.9 · background FTP browse · transfer recovery · PC candidate validation')
    def show_ftp(self):
        FTPBrowser(self.archive,self).exec()
    def show_pc_discovery(self):
        # Preserve existing discovery UI, but validate candidate contents before import
        from .transfer_v06 import pc_save_candidates
        from .workflows_v07 import discover_game_locations
        from .integrations import steam_games
        from PySide6.QtWidgets import QFileDialog
        candidates=pc_save_candidates()+discover_game_locations(games=steam_games())
        dialog=QDialog(self);dialog.resize(850,520);dialog.setWindowTitle('Discover PC Saves · Inspect Before Import')
        lay=QVBoxLayout(dialog)
        lay.addWidget(QLabel('Location hints only. Scan file names/size before importing; no files are changed.'))
        rows=QListWidget();lay.addWidget(rows)
        seen=set()
        for entry in candidates:
            p=entry['path']
            if p.casefold() in seen:continue
            seen.add(p.casefold())
            item=QListWidgetItem(f"{entry['name']}  ·  {p}")
            item.setData(Qt.ItemDataRole.UserRole,p)
            rows.addItem(item)
        report=QLabel('Select a folder, then Inspect. Scans are bounded to 350 files / 3 levels.')
        report.setWordWrap(True);lay.addWidget(report)
        bar=QHBoxLayout();inspect=QPushButton('Inspect Selected');imp=QPushButton('Import Reviewed Folder');close=QPushButton('Close')
        for button in (inspect,imp,close):bar.addWidget(button)
        lay.addLayout(bar)
        inspected=set()
        def selected():
            item=rows.currentItem()
            return Path(item.data(Qt.ItemDataRole.UserRole)) if item else None
        def inspect_path():
            path=selected()
            if path is None:return
            try:
                info=inspect_pc_candidate(path)
                inspected.add(str(path))
                report.setText(f"{info['status']} · {info['file_count']} files · {info['bytes']:,} bytes"
                    +(' · scan capped' if info['truncated'] else '')
                    +'\nHints: '+(', '.join(info['samples'][:4]) or 'none'))
            except Exception as exc:QMessageBox.warning(dialog,'Scan error',str(exc))
        def import_path():
            path=selected()
            if path is None:return
            if str(path) not in inspected:
                QMessageBox.warning(dialog,'Inspect first','Inspect this folder before importing.');return
            name,ok=QInputDialog.getText(dialog,'PC game title','Game name for the selected folder:')
            if not ok or not name.strip():return
            if QMessageBox.question(dialog,'Confirm PC import',f'Import {path} as a save for {name}? Confirm the folder contains only the intended save data.')!=QMessageBox.StandardButton.Yes:return
            try:self.archive.import_pc_save(path,name.strip());self.refresh();QMessageBox.information(dialog,'Imported','PC save imported')
            except Exception as exc:QMessageBox.warning(dialog,'Import failed',str(exc))
        inspect.clicked.connect(inspect_path);imp.clicked.connect(import_path);close.clicked.connect(dialog.accept)
        dialog.exec()

def main():
    app=QApplication(sys.argv);app.setStyle('Fusion');app.setStyleSheet(STYLE)
    home=os.environ.get('Z_ARCHIVE_HOME')
    if home:root=Path(home)
    elif (Path(sys.argv[0]).resolve().parent/'portable.flag').is_file():root=Path(sys.argv[0]).resolve().parent/'ArchiveData'
    else:root=Path.home()/'Documents'/'Z PlayStation Save Archive'
    win=Window(root);win.show();sys.exit(app.exec())
