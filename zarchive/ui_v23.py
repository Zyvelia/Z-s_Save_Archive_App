"""v2.3 Homebrew Center: release lookup, persistent local download jobs, version notes."""
from __future__ import annotations
import os,sys,threading
from pathlib import Path
from PySide6.QtCore import Qt,QThread,Signal,QUrl
from PySide6.QtWidgets import (QApplication,QDialog,QVBoxLayout,QHBoxLayout,QLabel,QPushButton,
 QMessageBox,QLineEdit,QTableWidget,QTableWidgetItem,QHeaderView,QTabWidget,QWidget,QProgressBar,
 QFileDialog,QComboBox,QCheckBox,QPlainTextEdit)
from PySide6.QtGui import QDesktopServices
from .ui_v22 import Window as V22Window,HomebrewDialog as V22Dialog
from .ui_v04 import STYLE
from .ui_v04 import STYLE
from .editor_v18 import ArchiveV18
from .homebrew_v22 import inspect_homebrew_pkg
from .homebrew_v23 import (catalog_items,list_releases,select_newest,load_queue,queue_asset,
 recover_queue,download_queued_asset,update_job)

class ReleaseWorker(QThread):
    result=Signal(object); error=Signal(str)
    def __init__(self,app):super().__init__();self.app=app
    def run(self):
        try:self.result.emit(list_releases(self.app))
        except Exception as exc:self.error.emit(str(exc))

class DownloadWorker(QThread):
    progress=Signal(int,int);result=Signal(object);error=Signal(str)
    def __init__(self,queue_path,job_id,dest,bandwidth_limit=None):
        super().__init__();self.queue_path=queue_path;self.job_id=job_id;self.dest=dest;self.bandwidth_limit=bandwidth_limit;self.cancel_flag=threading.Event()
    def run(self):
        try:
            self.result.emit(download_queued_asset(self.queue_path,self.job_id,self.dest,cancel=self.cancel_flag,
                progress=lambda a,b:self.progress.emit(a,b),bandwidth_limit=self.bandwidth_limit))
        except Exception as exc:self.error.emit(str(exc))

class HomebrewCenter(V22Dialog):
    def __init__(self,parent=None,root=None):
        super().__init__(parent,root)
        self.setWindowTitle('PS3 Homebrew Manager • v2.3');self.resize(1000,730)
        self.queue_file=self.root/'homebrew'/'downloads.json'
        self.download_dir=self.root/'homebrew'/'downloads'
        recover_queue(self.queue_file)
        self.releases=[];self.worker_lookup=None;self.worker_download=None
        self._add_release_page();self._add_queue_page();self._refresh_catalog()
        self._add_catalog_filters()

    def _refresh_catalog(self):
        tab=self.tabs.widget(0)
        table=tab.findChild(QTableWidget)
        if table is None:return
        items=catalog_items()
        table.setColumnCount(4);table.setHorizontalHeaderLabels(['App','Category','Description','Release checking'])
        table.setRowCount(len(items))
        for i,item in enumerate(items):
            for j,value in enumerate((item['name'],item['group'],item['description'],
                                      'GitHub releases' if item['auto_release'] else 'Manual project page')):
                table.setItem(i,j,QTableWidgetItem(value))
        table.horizontalHeader().setSectionResizeMode(2,QHeaderView.ResizeMode.Stretch)

    def _add_catalog_filters(self):
        tab=self.tabs.widget(0)
        layout=tab.layout()
        bar=QHBoxLayout()
        self.catalog_search=QLineEdit();self.catalog_search.setPlaceholderText('Search homebrew apps, categories and descriptions…')
        self.catalog_search.textChanged.connect(self.filter_catalog);bar.addWidget(self.catalog_search)
        self.catalog_category=QComboBox()
        self.catalog_category.addItems(['All categories']+sorted({x['group'] for x in catalog_items()}))
        self.catalog_category.currentTextChanged.connect(self.filter_catalog)
        bar.addWidget(self.catalog_category)
        layout.insertLayout(1,bar)

    def filter_catalog(self):
        table=self.tabs.widget(0).findChild(QTableWidget)
        term=self.catalog_search.text().lower().strip(); group=self.catalog_category.currentText()
        for i,item in enumerate(catalog_items()):
            table.setRowHidden(i,(group!='All categories' and item['group']!=group) or
                               (bool(term) and term not in (' '.join((item['name'],item['description'],item['group']))).lower()))

    def _add_release_page(self):
        tab=QWidget();layout=QVBoxLayout(tab)
        layout.addWidget(QLabel('Official GitHub releases • only public PS3 .pkg assets appear. Check compatibility before use.'))
        row=QHBoxLayout();layout.addLayout(row)
        self.app_combo=QComboBox();self.app_combo.addItems([x['name'] for x in catalog_items() if x['auto_release']]);row.addWidget(self.app_combo)
        self.check_btn=QPushButton('Check releases');self.check_btn.clicked.connect(self.check_releases);row.addWidget(self.check_btn)
        self.allow_pre=QCheckBox('Include pre-releases');self.allow_pre.stateChanged.connect(self.update_releases);row.addWidget(self.allow_pre)
        self.release_table=QTableWidget(0,4);self.release_table.setHorizontalHeaderLabels(['Version','PKG','Size','Release date']);layout.addWidget(self.release_table)
        self.release_table.horizontalHeader().setSectionResizeMode(1,QHeaderView.ResizeMode.Stretch)
        add=QPushButton('Queue selected PKG download');add.clicked.connect(self.enqueue_selected);layout.addWidget(add)
        self.release_note=QLabel('Catalog version refers to GitHub release tags; installed PS3 versions cannot be detected remotely.')
        self.release_note.setWordWrap(True);layout.addWidget(self.release_note)
        self.tabs.insertTab(1,tab,'Find Releases')

    def check_releases(self):
        if self.worker_lookup and self.worker_lookup.isRunning():return
        self.check_btn.setEnabled(False);self.release_note.setText('Checking published GitHub releases…')
        self.worker_lookup=ReleaseWorker(self.app_combo.currentText())
        self.worker_lookup.result.connect(self.on_releases)
        self.worker_lookup.error.connect(lambda e:self.release_note.setText('Release lookup failed: '+e))
        self.worker_lookup.finished.connect(lambda:self.check_btn.setEnabled(True))
        self.worker_lookup.start()

    def on_releases(self,releases):
        self.releases=releases;self.update_releases()
        current=select_newest(releases,include_prerelease=self.allow_pre.isChecked())
        self.release_note.setText('Newest listed compatible PKG release: '+(current['tag'] if current else 'none found')+'. Check the release page for firmware requirements.')

    def update_releases(self):
        self.rows=[]
        for release in self.releases:
            if release['prerelease'] and not self.allow_pre.isChecked():continue
            for asset in release['assets']:self.rows.append((release,asset))
        self.release_table.setRowCount(len(self.rows))
        for i,(release,asset) in enumerate(self.rows):
            for j,text in enumerate((release['tag'],asset['name'],f"{asset['size']/1048576:.1f} MiB",str(release['published_at'] or '')[:10])):
                self.release_table.setItem(i,j,QTableWidgetItem(text))
        if self.rows:self.release_table.selectRow(0)

    def enqueue_selected(self):
        idx=self.release_table.currentRow()
        if idx<0 or idx>=len(self.rows):return
        release,asset=self.rows[idx]
        if QMessageBox.question(self,'Queue PS3 PKG',f"Queue {asset['name']} from {release['repo']} ({release['tag']})?\n\nDownload will not start or install automatically.")!=QMessageBox.StandardButton.Yes:return
        try:queue_asset(self.queue_file,release['app'],release['tag'],asset)
        except Exception as exc:return QMessageBox.warning(self,'Cannot queue package',str(exc))
        self.refresh_queue();self.tabs.setCurrentWidget(self.queue_tab)

    def _add_queue_page(self):
        self.queue_tab=QWidget();layout=QVBoxLayout(self.queue_tab)
        layout.addWidget(QLabel('Downloads are local only. Choose Start; after validation, select the PKG in the Upload tab to send it to your PS3.'))
        self.download_table=QTableWidget(0,4);self.download_table.setHorizontalHeaderLabels(['App','File','Release','Status'])
        self.download_table.horizontalHeader().setSectionResizeMode(1,QHeaderView.ResizeMode.Stretch);layout.addWidget(self.download_table)
        row=QHBoxLayout();layout.addLayout(row)
        start=QPushButton('Start selected download');start.clicked.connect(self.start_download);row.addWidget(start)
        cancel=QPushButton('Cancel active');cancel.clicked.connect(self.cancel_download);row.addWidget(cancel)
        refresh=QPushButton('Refresh');refresh.clicked.connect(self.refresh_queue);row.addWidget(refresh)
        open_dir=QPushButton('Open download folder');open_dir.clicked.connect(lambda:QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.download_dir))));row.addWidget(open_dir)
        self.progress=QProgressBar();self.progress.setRange(0,100);layout.addWidget(self.progress)
        self.queue_log=QPlainTextEdit();self.queue_log.setReadOnly(True);layout.addWidget(self.queue_log)
        self.tabs.insertTab(2,self.queue_tab,'Download Queue');self.refresh_queue()

    def refresh_queue(self):
        self.jobs=load_queue(self.queue_file);self.download_table.setRowCount(len(self.jobs))
        for i,item in enumerate(self.jobs):
            for j,value in enumerate((item.get('app',''),item.get('name',''),item.get('tag',''),item.get('status',''))):
                self.download_table.setItem(i,j,QTableWidgetItem(str(value)))
        if self.jobs and self.download_table.currentRow()<0:self.download_table.selectRow(0)

    def start_download(self):
        i=self.download_table.currentRow()
        if i<0 or i>=len(self.jobs):return
        job=self.jobs[i]
        if self.worker_download and self.worker_download.isRunning():return QMessageBox.information(self,'Busy','One download at a time.')
        if QMessageBox.question(self,'Approve download',f"Download {job['name']} to {self.download_dir}?\n\nThe PKG remains uninstalled. Inspect the project and release notes first.")!=QMessageBox.StandardButton.Yes:return
        self.worker_download=DownloadWorker(self.queue_file,job['id'],self.download_dir,
            bandwidth_limit=(int(self.bandwidth_kib.text())*1024 if hasattr(self,"bandwidth_kib") and self.bandwidth_kib.text().strip().isdigit() and int(self.bandwidth_kib.text())>0 else None))
        self.worker_download.progress.connect(lambda received,total:self.progress.setValue(int(received*100/max(total,1))))
        self.worker_download.result.connect(self.on_download_done)
        self.worker_download.error.connect(lambda msg:(self.queue_log.appendPlainText('Download error: '+msg),self.refresh_queue()))
        self.worker_download.start()

    def on_download_done(self,job):
        self.queue_log.appendPlainText('Downloaded and checked '+job['name']+'; added to local PKG upload list. PS3 upload still requires approval.')
        try:
            info=inspect_homebrew_pkg(job['local_path'])
            if not any(x['path']==info['path'] for x in self.packages):
                self.packages.append(info)
                row=self.table.rowCount();self.table.insertRow(row)
                for col,value in enumerate((info['filename'],f"{info['bytes']:,} bytes",info['sha256'][:16])):
                    self.table.setItem(row,col,QTableWidgetItem(str(value)))
                self.table.selectRow(row)
        except Exception as exc:
            self.queue_log.appendPlainText('Download completed but PKG import needs review: '+str(exc))
        self.progress.setValue(100);self.refresh_queue()

    def cancel_download(self):
        if self.worker_download and self.worker_download.isRunning():self.worker_download.cancel_flag.set()

    def closeEvent(self,event):
        if ((self.worker_lookup and self.worker_lookup.isRunning()) or (self.worker_download and self.worker_download.isRunning())):
            QMessageBox.information(self,'Busy','Finish or cancel the active lookup/download before closing.');event.ignore();return
        super().closeEvent(event)

class Window(V22Window):
    def __init__(self,root):
        super().__init__(root)
        self.setWindowTitle("Z's Save Archive • PS3 + PC v2.3")
        # Existing v2.2 menu entry stays valid; replace its action without changing the rest of the UI.
        for action in self.tools_btn.menu().actions():
            if action.text()=='PS3 Homebrew Manager':
                action.triggered.disconnect()
                action.triggered.connect(lambda:HomebrewCenter(self,root).exec())

def main():
    from . import ui
    ui.Archive=ArchiveV18
    app=QApplication(sys.argv);app.setStyle('Fusion');app.setStyleSheet(STYLE)
    home=os.environ.get('Z_ARCHIVE_HOME')
    if home:root=Path(home)
    elif (Path(sys.argv[0]).resolve().parent/'portable.flag').is_file():root=Path(sys.argv[0]).resolve().parent/'ArchiveData'
    else:root=Path.home()/'Documents'/'Z PlayStation Save Archive'
    win=Window(root);win.show();sys.exit(app.exec())
