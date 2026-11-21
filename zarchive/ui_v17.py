"""v1.7 additive interface. Long-running maintenance jobs get independent DB connections."""
from __future__ import annotations
import os,sys
from pathlib import Path
from PySide6.QtCore import Qt,QTimer,QAbstractTableModel,QModelIndex,Signal,Slot
from PySide6.QtGui import QKeySequence,QShortcut
from PySide6.QtWidgets import (QInputDialog,QApplication,QDialog,QVBoxLayout,QHBoxLayout,QLineEdit,QLabel,
    QPushButton,QTableView,QComboBox,QListWidget,QAbstractItemView,QMessageBox,QFileDialog,
    QFormLayout,QTabWidget,QCheckBox)
from .ui_v16 import Window as BaseWindow
from .ui_v15 import PublisherDialog as BasePublisherDialog
from .ui_v04 import STYLE
from .upgrade_v17 import ArchiveV17,JobRunner

class PagedSaveModel(QAbstractTableModel):
    HEADERS=('Game','Save','Platform','Category','Title ID')
    def __init__(self,archive,parent=None):
        super().__init__(parent);self.archive=archive;self.query='';self.platform='All';self.category='All';self.offset=0
        self.limit=archive.ui_setting('library_page_size',100);self.total=0;self.rows=[];self.reload()
    def rowCount(self,parent=QModelIndex()):return 0 if parent.isValid() else len(self.rows)
    def columnCount(self,parent=QModelIndex()):return 0 if parent.isValid() else len(self.HEADERS)
    def data(self,index,role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or not 0<=index.row()<len(self.rows):return None
        if role==Qt.ItemDataRole.DisplayRole:
            r=self.rows[index.row()];return (r['game'],r['label'],r['platform'],r['category'],r['title_id'])[index.column()]
        if role==Qt.ItemDataRole.UserRole:return self.rows[index.row()]['id']
        return None
    def headerData(self,section,orientation,role=Qt.ItemDataRole.DisplayRole):
        if role==Qt.ItemDataRole.DisplayRole and orientation==Qt.Orientation.Horizontal:return self.HEADERS[section]
        return None
    def reload(self,reset=False):
        if reset:self.offset=0
        result=self.archive.search_page(self.query,self.platform,self.category,self.limit,self.offset)
        self.beginResetModel();self.rows=result['items'];self.total=result['total'];self.endResetModel()
    def page(self,direction):
        self.offset=max(0,min(max(0,self.total-1)//self.limit*self.limit,self.offset+direction*self.limit));self.reload()

class LargeLibraryDialog(QDialog):
    def __init__(self,archive,parent=None):
        super().__init__(parent);self.setWindowTitle('Large Library · paged save list');self.resize(1040,700)
        self.model=PagedSaveModel(archive,self);box=QVBoxLayout(self);bar=QHBoxLayout();box.addLayout(bar)
        self.query=QLineEdit();self.query.setPlaceholderText('Search games, tags, notes and save names');bar.addWidget(self.query)
        self.platform=QComboBox();self.platform.addItems(['All','PS3','PC','PS4']);bar.addWidget(self.platform)
        self.category=QComboBox();self.category.addItems(['All','Legit','Modded','Unsorted']);bar.addWidget(self.category)
        self.table=QTableView();self.table.setModel(self.model);self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSortingEnabled(False);self.table.horizontalHeader().setStretchLastSection(True);box.addWidget(self.table)
        nav=QHBoxLayout();box.addLayout(nav);self.info=QLabel();nav.addWidget(self.info);nav.addStretch()
        self.previous=QPushButton('Previous');self.next=QPushButton('Next');nav.addWidget(self.previous);nav.addWidget(self.next)
        self.previous.clicked.connect(lambda:self.page(-1));self.next.clicked.connect(lambda:self.page(1))
        self.delay=QTimer(self);self.delay.setSingleShot(True);self.delay.setInterval(220);self.delay.timeout.connect(self.filter_changed)
        self.query.textChanged.connect(lambda:self.delay.start())
        self.platform.currentTextChanged.connect(self.filter_changed);self.category.currentTextChanged.connect(self.filter_changed)
        self.display_status()
    def filter_changed(self,*_):
        self.model.query=self.query.text();self.model.platform=self.platform.currentText();self.model.category=self.category.currentText()
        self.model.reload(True);self.display_status()
    def page(self,n):self.model.page(n);self.display_status()
    def display_status(self):
        m=self.model;self.info.setText(f'{m.offset+1 if m.total else 0}–{m.offset+len(m.rows)} of {m.total} saves')
        self.previous.setEnabled(m.offset>0);self.next.setEnabled(m.offset+len(m.rows)<m.total)

class JobCenter(QDialog):
    def __init__(self,archive,runner,parent=None):
        super().__init__(parent);self.archive=archive;self.runner=runner
        self.setWindowTitle('Background Jobs & Recovery');self.resize(850,610)
        box=QVBoxLayout(self);box.addWidget(QLabel('Operations use isolated database connections. Interrupted jobs never restart automatically.'))
        bar=QHBoxLayout();box.addLayout(bar)
        for title,callback in [('Run archive verification',self.verify),('Export public catalog',self.export_site),('Refresh',self.refresh)]:
            b=QPushButton(title);b.clicked.connect(callback);bar.addWidget(b)
        self.list=QListWidget();box.addWidget(self.list)
        self.timer=QTimer(self);self.timer.timeout.connect(self.refresh);self.timer.start(1300);self.refresh()
    def verify(self):
        self.runner.submit('verify','Archive integrity',lambda a,c:{'issues':a.audit()})
        self.refresh()
    def export_site(self):
        path=QFileDialog.getExistingDirectory(self,'Parent directory for a new public catalog')
        if not path:return
        dest=Path(path)/'Z_Save_Public_Catalog'
        self.runner.submit('export','Public catalog export',lambda a,c:a.export_public_site(dest))
        self.refresh()
    def refresh(self):
        self.list.clear()
        for j in self.archive.jobs(100):
            progress=f"  {j['progress_current']}/{j['progress_total']}" if j['progress_total'] else ''
            self.list.addItem(f"{j['state'].upper()} · {j['kind']} · {j['label']}{progress}\n{j['updated_at']} · {j['detail'][:160]}")

class SettingsHub(QDialog):
    def __init__(self,archive,parent=None):
        super().__init__(parent);self.archive=archive;self.setWindowTitle('Archive Settings');self.resize(680,520)
        layout=QVBoxLayout(self);self.search=QLineEdit();self.search.setPlaceholderText('Search settings...');layout.addWidget(self.search)
        self.labels=[]
        form=QFormLayout();layout.addLayout(form)
        self.page=QComboBox();self.page.addItems(['50','100','200']);self.page.setCurrentText(str(archive.ui_setting('library_page_size',100)))
        self.density=QComboBox();self.density.addItems(['compact','standard','comfortable']);self.density.setCurrentText(archive.get_pref('density','standard'))
        self.notifications=QComboBox();self.notifications.addItems(['all','error','warning','success','info']);self.notifications.setCurrentText(archive.ui_setting('notification_filter','all'))
        for name,control in [('Library page size',self.page),('Interface density',self.density),('Notification filter',self.notifications)]:
            label=QLabel(name);form.addRow(label,control);self.labels.append((name,label,control))
        self.search.textChanged.connect(self.search_settings)
        save=QPushButton('Save settings');save.clicked.connect(self.commit);layout.addWidget(save);layout.addStretch()
    def search_settings(self,q):
        for name,label,control in self.labels:
            visible=q.casefold().strip() in name.casefold();label.setVisible(visible);control.setVisible(visible)
    def commit(self):
        self.archive.set_ui_setting('library_page_size',int(self.page.currentText()))
        self.archive.set_pref('density',self.density.currentText())
        self.archive.set_ui_setting('notification_filter',self.notifications.currentText());self.accept()

class BackgroundPublisherDialog(BasePublisherDialog):
    """Uploading uses an isolated worker connection after explicit approval."""
    def __init__(self,archive,runner,parent=None):
        super().__init__(archive,parent);self.runner=runner
        self.setWindowTitle('GitHub Publishing · background uploads')
    def upload(self):
        def schedule():
            sid=getattr(self.parent(),'_sid')()
            if not sid:raise ValueError('Select a save in All Saves first')
            owner,repo=self.owner_repo();rid=int(self.release.text().strip())
            tag=self.tag.text().strip()
            report=self.archive.publication_preflight(sid,privacy_reviewed=self.approved.isChecked())
            if not report['ready']:raise ValueError('; '.join(report['errors']))
            if QMessageBox.question(self,'Confirm GitHub upload',
                 f"Upload {report['game']} / {report['label']} to {owner}/{repo} release {rid}?\n"
                 'This sends save contents to GitHub. The release may be public depending on its settings.')!=QMessageBox.StandardButton.Yes:
                return {'cancelled':True}
            jid=self.runner.submit('publish','GitHub asset: '+report['game'],
                 lambda a,c:a.upload_publisher_save(owner,repo,rid,sid,tag=tag,privacy_reviewed=True))
            return {'queued_job':jid,'note':'See Background Jobs for result; no automatic retry'}
        return self.run_safe(schedule)

class Window(BaseWindow):
    local_import_finished = Signal(str)

    def __init__(self,root):
        super().__init__(root);self.setWindowTitle("Z's Save Archive  •  PS3 + PC  v1.7")
        self.archive.recover_interrupted_jobs()
        self.runner=JobRunner(root)
        self.local_import_finished.connect(self.finish_local_import)
        menu=self.tools_btn.menu();menu.addSeparator()
        menu.addAction('Large Library (paged model)',self.large_library)
        menu.addAction('Background Jobs & Recovery',self.jobs_ui)
        menu.addAction('Searchable Settings',self.settings_hub)
        menu.addAction('Reorder dashboard widgets',self.reorder_widgets)
        self._shortcut_jobs=QShortcut(QKeySequence('Ctrl+Shift+J'),self);self._shortcut_jobs.activated.connect(self.jobs_ui)
    def large_library(self):LargeLibraryDialog(self.archive,self).exec()
    def publisher_ui(self):BackgroundPublisherDialog(self.archive,self.runner,self).exec()
    def backup_selected(self):
        r=getattr(self,'current',None)
        if not r:return QMessageBox.information(self,'Choose a save','Select a save first')
        path=QFileDialog.getSaveFileName(self,'Backup to ZIP',str(Path.home()/'Downloads'/(r['platform']+'_'+r['id']+'.zip')),'ZIP (*.zip)')[0]
        if not path:return
        jid=self.runner.submit('backup','Backup: '+r['game'],lambda a,c:a.backup_zip(r['id'],Path(path)))
        self.statusBar().showMessage('Backup queued: '+jid[:8]+' · see Background Jobs')
    def archive_local_save(self, path, platform, game, importer):
        method = importer.__name__
        label = f'Import {platform}: {game}'
        job = self.runner.submit('import', label, lambda archive, cancel: getattr(archive, method)(path, game),
                                 on_done=self.local_import_finished.emit)
        self.statusBar().showMessage(f'{platform} save import queued: {job[:8]}')

    @Slot(str)
    def finish_local_import(self, job_id):
        self.refresh()
        row = self.archive.conn.execute('SELECT state,detail FROM jobs_v17 WHERE id=?', (job_id,)).fetchone()
        if row is None:
            return
        if row['state'] == 'failed':
            self.statusBar().showMessage(f"Save import failed: {row['detail']}")
        elif row['state'] == 'completed':
            self.statusBar().showMessage('Save imported into your library.')

    def jobs_ui(self):JobCenter(self.archive,self.runner,self).exec()
    def settings_hub(self):
        if SettingsHub(self.archive,self).exec()==QDialog.DialogCode.Accepted:self._apply_density()
    def reorder_widgets(self):
        dlg=QDialog(self);dlg.setWindowTitle('Dashboard widget order');dlg.resize(400,350)
        l=QVBoxLayout(dlg);l.addWidget(QLabel('Change widget priority (saved for dashboard layouts).'))
        items=QListWidget();l.addWidget(items)
        for n in self.archive.dashboard_order():items.addItem(n)
        row=QHBoxLayout();l.addLayout(row)
        def move(d):
            i=items.currentRow();j=i+d
            if 0<=i<items.count() and 0<=j<items.count():
                item=items.takeItem(i);items.insertItem(j,item);items.setCurrentRow(j)
        for name,d in [('Move up',-1),('Move down',1)]:
            b=QPushButton(name);b.clicked.connect(lambda checked=False,k=d:move(k));row.addWidget(b)
        b=QPushButton('Save order');b.clicked.connect(dlg.accept);l.addWidget(b)
        if dlg.exec()==QDialog.DialogCode.Accepted:self.archive.set_dashboard_order([items.item(i).text() for i in range(items.count())])

def main():
    from . import ui
    ui.Archive=ArchiveV17
    app=QApplication(sys.argv);app.setStyle('Fusion');app.setStyleSheet(STYLE)
    home=os.environ.get('Z_ARCHIVE_HOME')
    if home:root=Path(home)
    elif (Path(sys.argv[0]).resolve().parent/'portable.flag').is_file():root=Path(sys.argv[0]).resolve().parent/'ArchiveData'
    else:root=Path.home()/'Documents'/'Z PlayStation Save Archive'
    window=Window(root);window.show();sys.exit(app.exec())
