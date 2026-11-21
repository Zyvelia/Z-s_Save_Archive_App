"""v1.6 usability layer: command palette, activity center, dashboard controls and fast search."""
from __future__ import annotations
import os,sys,json
from pathlib import Path
from PySide6.QtCore import Qt,QByteArray,QTimer
from PySide6.QtGui import QKeySequence,QShortcut
from PySide6.QtWidgets import (QApplication,QDialog,QVBoxLayout,QHBoxLayout,QLineEdit,QListWidget,
 QListWidgetItem,QPushButton,QMessageBox,QInputDialog,QCheckBox,QLabel,QWidget,QComboBox,QFormLayout)
from .ui_v15 import Window as BaseWindow
from .ui_v04 import STYLE

class CommandPalette(QDialog):
    def __init__(self,commands,parent=None):
        super().__init__(parent);self.setWindowTitle('Quick actions  ·  Ctrl+K');self.resize(590,430)
        self.commands=commands
        layout=QVBoxLayout(self)
        self.query=QLineEdit();self.query.setPlaceholderText('Search actions...');layout.addWidget(self.query)
        self.results=QListWidget();layout.addWidget(self.results)
        self.query.textChanged.connect(self.refresh)
        self.results.itemActivated.connect(self.run_item)
        self.refresh();self.query.setFocus()
    def refresh(self):
        self.results.clear()
        needle=self.query.text().lower().strip()
        for name in self.commands:
            if needle in name.lower():self.results.addItem(name)
        if self.results.count():self.results.setCurrentRow(0)
    def run_item(self,item):
        fn=self.commands.get(item.text())
        if fn:self.accept();QTimer.singleShot(0,fn)
    def keyPressEvent(self,event):
        if event.key()==Qt.Key.Key_Return and self.results.currentItem():
            self.run_item(self.results.currentItem());return
        super().keyPressEvent(event)

class ActivityDialog(QDialog):
    def __init__(self,archive,parent=None):
        super().__init__(parent);self.setWindowTitle('Activity and tasks');self.resize(760,560)
        box=QVBoxLayout(self)
        box.addWidget(QLabel('Recent tasks, crashes/interrupted operations, and notifications. Tasks are NOT replayed automatically.'))
        self.items=QListWidget();box.addWidget(self.items)
        btn=QPushButton('Refresh');btn.clicked.connect(self.refresh);box.addWidget(btn)
        self.archive=archive;self.refresh()
    def refresh(self):
        self.items.clear()
        for x in self.archive.tasks(120):
            self.items.addItem(f"TASK  {x['state'].upper()}  •  {x['kind']}  •  {x['label']}\n{x['updated_at']}  {x['detail'][:140]}")
        for x in self.archive.notifications(120):
            self.items.addItem(f"{x['kind'].upper()}  •  {x['message']}\n{x['created_at']}")

class SearchDialog(QDialog):
    def __init__(self,archive,parent=None):
        super().__init__(parent);self.archive=archive;self.offset=0;self.page_size=80
        self.setWindowTitle('Fast archive search');self.resize(850,630)
        layout=QVBoxLayout(self);top=QHBoxLayout();layout.addLayout(top)
        self.query=QLineEdit();self.query.setPlaceholderText('Search games, save labels, title IDs, notes, tags...');top.addWidget(self.query)
        self.platform=QComboBox();self.platform.addItems(['All','PS3','PC','PS4']);top.addWidget(self.platform)
        self.category=QComboBox();self.category.addItems(['All','Legit','Modded','Unsorted']);top.addWidget(self.category)
        self.list=QListWidget();layout.addWidget(self.list)
        bottom=QHBoxLayout();layout.addLayout(bottom)
        self.prev=QPushButton('Previous');self.next=QPushButton('Next');self.info=QLabel('')
        bottom.addWidget(self.prev);bottom.addWidget(self.info);bottom.addStretch();bottom.addWidget(self.next)
        self.prev.clicked.connect(lambda:self.page(-1));self.next.clicked.connect(lambda:self.page(1))
        self.query.textChanged.connect(self.reset);self.platform.currentTextChanged.connect(self.reset);self.category.currentTextChanged.connect(self.reset)
        self.refresh()
    def reset(self,*_):self.offset=0;self.refresh()
    def page(self,direction):self.offset=max(0,self.offset+direction*self.page_size);self.refresh()
    def refresh(self):
        result=self.archive.search_page(self.query.text(),self.platform.currentText(),self.category.currentText(),self.page_size,self.offset)
        self.list.clear()
        for r in result['items']:
            self.list.addItem(f"{r['game']}  ·  {r['label']}\n{r['platform']} / {r['category']} / {r['title_id']}  •  {', '.join(r['tags'][:5])}")
        self.info.setText(f"{result['offset']+1 if result['total'] else 0}–{min(result['total'],result['offset']+len(result['items']))} of {result['total']}")
        self.prev.setEnabled(self.offset>0);self.next.setEnabled(self.offset+len(result['items'])<result['total'])

class Window(BaseWindow):
    def __init__(self,root):
        super().__init__(root)
        self.setWindowTitle("Z's Save Archive  •  PS3 + PC  v1.6")
        self.resize(1450,900)
        self.setMinimumSize(950,640)
        # Preference state uses the same DB already opened by the older UI.
        menu=self.tools_btn.menu();menu.addSeparator()
        menu.addAction('Quick actions (Ctrl+K)',self.open_palette)
        menu.addAction('Fast archive search (Ctrl+Shift+F)',self.fast_search)
        menu.addAction('Activity & task history',self.activity)
        menu.addAction('Dashboard layout preferences',self.dashboard_preferences)
        menu.addAction('Interface density',self.density_preferences)
        for seq,cb in [('Ctrl+K',self.open_palette),('Ctrl+Shift+F',self.fast_search),('Ctrl+1',self.show_dashboard),
                       ('Ctrl+2',self.show_games),('Ctrl+3',self.show_saves),('Ctrl+4',self.show_settings),
                       ('Ctrl+Shift+I',self.import_pc),('Ctrl+Shift+P',self.import_folder)]:
            shortcut=QShortcut(QKeySequence(seq),self);shortcut.activated.connect(cb)
        self._apply_density()
        geometry=self.archive.get_pref('window_geometry')
        if geometry:
            try:self.restoreGeometry(QByteArray.fromBase64(geometry.encode('ascii')))
            except (ValueError,TypeError):pass
        self.apply_widgets()
        self.archive.notify('info','Archive v1.6 opened. Prior active jobs are marked interrupted, not replayed.')
        self._restore_last_page()
    def _commands(self):
        return {'Dashboard':self.show_dashboard,'Game Library':self.show_games,'All Saves':self.show_saves,
            'Settings':self.show_settings,'Import PS3 save':self.import_folder,'Import PC save':self.import_pc,
            'Archive health check':self.health_check,'Activity and tasks':self.activity,
            'Search archive':self.fast_search,'PS3 Console Center':self.ps3_center,
            'GitHub Publishing Center':self.publisher_ui,
            'Discover and import PC saves':self.show_pc_discovery,'Dashboard layout':self.dashboard_preferences}
    def open_palette(self):CommandPalette(self._commands(),self).exec()
    def activity(self):ActivityDialog(self.archive,self).exec()
    def fast_search(self):SearchDialog(self.archive,self).exec()
    def dashboard_preferences(self):
        available=[('stats','Overview statistics'),('recent','Recent saves'),('quick','Quick actions'),('storage','Storage summary')]
        selected=set(self.archive.get_pref('dashboard_widgets',list(x[0] for x in available)))
        dialog=QDialog(self);dialog.setWindowTitle('Dashboard widgets');layout=QVBoxLayout(dialog)
        controls=[]
        for key,title in available:
            cb=QCheckBox(title);cb.setChecked(key in selected);layout.addWidget(cb);controls.append((key,cb))
        save=QPushButton('Save layout');layout.addWidget(save);save.clicked.connect(dialog.accept)
        if dialog.exec()==QDialog.DialogCode.Accepted:
            self.archive.set_pref('dashboard_widgets',[key for key,cb in controls if cb.isChecked()]);self.apply_widgets()
    def apply_widgets(self):
        selected=set(self.archive.get_pref('dashboard_widgets',['stats','recent','quick','storage']))
        for widget,container in [('recent',self.recent_list),('storage',self.disk_label)]:container.setVisible(widget in selected)
        for i in range(self.dashboard_stats.count()):
            w=self.dashboard_stats.itemAt(i).widget()
            if w:w.setVisible('stats' in selected)
        # The existing quick-panel actions are left accessible in menus even if dashboard is minimized.
    def density_preferences(self):
        val,ok=QInputDialog.getItem(self,'Interface density','Spacing:', ['compact','standard','comfortable'],
                                    ['compact','standard','comfortable'].index(self.archive.get_pref('density','standard')),False)
        if ok:self.archive.set_pref('density',val);self._apply_density()
    def _apply_density(self):
        density=self.archive.get_pref('density','standard')
        pad={'compact':6,'standard':10,'comfortable':14}.get(density,10)
        self.setStyleSheet(STYLE+f'\nQPushButton {{padding:{pad}px {pad+3}px}}\nQListWidget::item {{padding:{pad}px}}')
    def _restore_last_page(self):
        key=self.archive.get_pref('last_page','dashboard')
        {'dashboard':self.show_dashboard,'games':self.show_games,'saves':self.show_saves,'settings':self.show_settings}.get(key,self.show_dashboard)()
    def closeEvent(self,event):
        try:
            self.archive.set_pref('window_geometry',bytes(self.saveGeometry().toBase64()).decode('ascii'))
            self.archive.set_pref('last_page',self.mode if self.mode in ('dashboard','games','saves','settings') else 'dashboard')
        except Exception:pass
        super().closeEvent(event)

def main():
    from . import ui
    # ui.Archive is the application storage constructor, shared by inherited window classes.
    from .upgrade_v16 import ArchiveV16
    ui.Archive=ArchiveV16
    app=QApplication(sys.argv);app.setStyle('Fusion');app.setStyleSheet(STYLE)
    home=os.environ.get('Z_ARCHIVE_HOME')
    if home:root=Path(home)
    elif (Path(sys.argv[0]).resolve().parent/'portable.flag').is_file():root=Path(sys.argv[0]).resolve().parent/'ArchiveData'
    else:root=Path.home()/'Documents'/'Z PlayStation Save Archive'
    window=Window(root);window.show();sys.exit(app.exec())
