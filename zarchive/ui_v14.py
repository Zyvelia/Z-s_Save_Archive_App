"""v1.4 PS3 read-only console dashboard and batch backup UI."""
from __future__ import annotations
import json, os, sys
from pathlib import Path
from PySide6.QtCore import QObject,QThread,Signal,Slot
from PySide6.QtWidgets import QApplication,QDialog,QVBoxLayout,QHBoxLayout,QLabel,QPushButton,QComboBox,QTextEdit,QFileDialog,QInputDialog,QMessageBox
from .ui_v13 import Window as BaseWindow
from .ui_v04 import STYLE

class BackupWorker(QObject):
    progress=Signal(int,int,str)
    finished=Signal(object,str)
    def __init__(self,archive,connection,user):
        super().__init__();self.archive=archive;self.connection=connection;self.user=user;self.cancelled=False
    @Slot()
    def run(self):
        try:
            result=self.archive.profile_backup(self.connection,self.user,progress=lambda i,n,p:self.progress.emit(i,n,p),cancel=lambda:self.cancelled)
            self.finished.emit(result,'')
        except Exception as exc:self.finished.emit(None,str(exc))

class ConsoleDialog(QDialog):
    def __init__(self,archive,parent=None):
        super().__init__(parent);self.archive=archive;self.setWindowTitle('PS3 Console Center — Read-only');self.resize(760,570)
        v=QVBoxLayout(self);v.addWidget(QLabel('PS3 Console Center  ·  Downloads only — No console files changed'))
        self.conn=QComboBox();v.addWidget(self.conn)
        bar=QHBoxLayout();v.addLayout(bar)
        for name,cb in [('Refresh profiles',self.refresh_profiles),('Check connection',self.health),('List PS3 users',self.users),('Compare saves',self.compare),('Backup entire profile',self.backup),('Browse save folders',self.browse)]:
            b=QPushButton(name);b.clicked.connect(cb);bar.addWidget(b)
        self.output=QTextEdit();self.output.setReadOnly(True);v.addWidget(self.output)
        self.cancel_btn=QPushButton('Cancel active backup');self.cancel_btn.setEnabled(False);self.cancel_btn.clicked.connect(self.request_cancel);v.addWidget(self.cancel_btn)
        self.thread=None;self.worker=None;self.refresh_profiles()
    def show_data(self,obj):self.output.setPlainText(json.dumps(obj,indent=2,ensure_ascii=False,default=str)[:30000])
    def error(self,exc):QMessageBox.warning(self,'PS3 operation failed',str(exc))
    def wrap(self,func):
        try:func()
        except Exception as exc:self.error(exc)
    def refresh_profiles(self):
        self.conn.clear()
        for row in self.archive.connections():self.conn.addItem(f"{row['name']} — {row['host']}:{row['port']}",row['id'])
    def current(self):
        cid=self.conn.currentData()
        if not cid:raise ValueError('Register a PS3 in Tools → PS3 connection profiles first')
        return cid
    def pick_user(self):
        users=self.archive.ps3_users(self.current())
        if not users:raise ValueError('No PS3 user directories detected')
        name,ok=QInputDialog.getItem(self,'PS3 user profile','Profile ID:',users,0,False)
        return name if ok else None
    def health(self):self.wrap(lambda:self.show_data(self.archive.ps3_dashboard(self.current())))
    def users(self):self.wrap(lambda:self.show_data(self.archive.ps3_users(self.current())))
    def compare(self):
        def go():
            user=self.pick_user()
            if user:self.show_data(self.archive.ps3_sync_preview(self.current(),user))
        self.wrap(go)
    def browse(self):
        def go():
            user=self.pick_user()
            if not user:return
            rows=self.archive.ps3_readonly_folder(self.current(),user)
            self.show_data(rows)
            saves=[r['name'] for r in rows['entries'] if r['is_dir']]
            if not saves:return
            name,ok=QInputDialog.getItem(self,'Save folder','Browse files in:',saves,0,False)
            if ok:self.show_data(self.archive.ps3_readonly_folder(self.current(),user,name))
        self.wrap(go)
    def backup(self):
        def go():
            if self.thread and self.thread.isRunning():raise ValueError('Backup already running')
            user=self.pick_user()
            if not user:return
            if QMessageBox.question(self,'Back up complete PS3 profile',f'Download all accessible saves in user {user}?\nAlready imported identical files are reported as skipped/failed; no console writes are performed.')!=QMessageBox.StandardButton.Yes:return
            self.thread=QThread(self);self.worker=BackupWorker(self.archive,self.current(),user);self.worker.moveToThread(self.thread)
            self.thread.started.connect(self.worker.run);self.worker.progress.connect(self.on_progress);self.worker.finished.connect(self.on_finished)
            self.worker.finished.connect(self.thread.quit);self.thread.finished.connect(self.worker.deleteLater);self.thread.finished.connect(self.thread.deleteLater)
            self.cancel_btn.setEnabled(True);self.thread.start()
        self.wrap(go)
    def on_progress(self,i,n,path):self.output.setPlainText(f'{i}/{n} saves processed\n{path}')
    def on_finished(self,data,error):
        self.cancel_btn.setEnabled(False)
        if error:self.error(error)
        else:self.show_data(data)
    def request_cancel(self):
        if self.worker:self.worker.cancelled=True
    def reject(self):
        if self.thread and self.thread.isRunning():
            self.request_cancel();QMessageBox.information(self,'Backup still running','Cancellation requested. Close this window when the current download stops.');return
        super().reject()

class Window(BaseWindow):
    def __init__(self,root):
        super().__init__(root);self.setWindowTitle("Z's Save Archive  •  PS3 + PC  v1.4")
        menu=self.tools_btn.menu();menu.addSeparator()
        for name,fn in [('PS3 Console Center',self.ps3_center),('Apollo export for selected save',self.apollo_ui),('Record PS3 compatibility test',self.compat_ui),('PS3 compatibility history',self.compat_history_ui)]:menu.addAction(name,fn)
    def ps3_center(self):self._safe(lambda:ConsoleDialog(self.archive,self).exec())
    def apollo_ui(self):
        sid=self._sid()
        if not sid:return QMessageBox.information(self,'Select save','Select a PS3 save first')
        def go():
            path,_=QFileDialog.getSaveFileName(self,'Prepare Apollo save export','','ZIP (*.zip)')
            if path:
                if not path.lower().endswith('.zip'):path+='.zip'
                self._report('Apollo export',self.archive.apollo_export(sid,path))
        self._safe(go)
    def compat_ui(self):
        sid=self._sid()
        if not sid:return QMessageBox.information(self,'Select save','Select a PS3 save first')
        def go():
            current=self.archive._save(sid)
            title,ok=QInputDialog.getText(self,'Compatibility','PS3 title ID:',text=current['title_id'])
            if not ok:return
            result,ok=QInputDialog.getItem(self,'Compatibility test','Result:',['Unknown','Confirmed','Incompatible','Needs testing'],0,False)
            if not ok:return
            notes,ok=QInputDialog.getMultiLineText(self,'Compatibility notes','Game version, DLC, region and test notes:')
            if ok:self.archive.add_ps3_compatibility(sid,title,current['region'],result=result,notes=notes)
        self._safe(go)
    def compat_history_ui(self):
        sid=self._sid()
        if sid:self._safe(lambda:self._report('PS3 compatibility tests',self.archive.ps3_compatibility_history(sid)))

def main():
    app=QApplication(sys.argv);app.setStyle('Fusion');app.setStyleSheet(STYLE)
    home=os.environ.get('Z_ARCHIVE_HOME')
    if home:root=Path(home)
    elif (Path(sys.argv[0]).resolve().parent/'portable.flag').is_file():root=Path(sys.argv[0]).resolve().parent/'ArchiveData'
    else:root=Path.home()/'Documents'/'Z PlayStation Save Archive'
    win=Window(root);win.show();sys.exit(app.exec())
