"""PySide6 UI for the PS3 local save archive."""
from __future__ import annotations
import os
import sys
from pathlib import Path
from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (QApplication,QMainWindow,QWidget,QVBoxLayout,QHBoxLayout,QLabel,
 QFrame,QPushButton,QLineEdit,QListWidget,QListWidgetItem,QComboBox,QTextEdit,QFileDialog,
 QMessageBox,QSplitter,QStackedWidget,QScrollArea,QGridLayout,QDialog,QDialogButtonBox,
 QFormLayout,QAbstractItemView,QInputDialog)
from .upgrade_v15 import ArchiveV15 as Archive
from .storage import discover_saves, CATEGORIES

BG='#111019'; PANEL='#1b1927'; PANEL2='#252237'; EDGE='#393449'; TEXT='#f2efff'; MUTE='#ada6bf'; PURPLE='#b393ff'
QSS=f'''
 QWidget {{background:{BG};color:{TEXT};font-family:'Segoe UI';font-size:13px}}
 QMainWindow {{background:{BG}}}
 QLabel {{background:transparent}}
 QFrame#sidebar {{background:#171522;border-right:1px solid {EDGE}}}
 QFrame#card, QFrame#stat {{background:{PANEL};border:1px solid {EDGE};border-radius:13px}}
 QLabel#muted {{color:{MUTE}}}
 QLabel#heading {{font-size:25px;font-weight:700}}
 QLabel#large {{font-size:24px;font-weight:700;color:{PURPLE}}}
 QPushButton {{background:{PANEL2};border:1px solid {EDGE};padding:10px 14px;border-radius:9px;text-align:left}}
 QPushButton:hover {{background:#343047;border:1px solid {PURPLE}}}
 QPushButton#primary {{background:#7653cb;border:1px solid #9676e7;font-weight:600;text-align:center}}
 QPushButton#primary:hover {{background:#8966e2}}
 QPushButton#nav {{background:transparent;border:0;text-align:left;padding:14px 16px;font-weight:600}}
 QPushButton#nav:checked {{background:#302841;border-left:3px solid {PURPLE};border-radius:6px}}
 QPushButton#nav:hover {{background:#292437}}
 QLineEdit, QComboBox, QTextEdit {{background:{PANEL2};border:1px solid {EDGE};border-radius:9px;padding:9px;selection-background-color:#7653cb}}
 QLineEdit:focus, QComboBox:focus, QTextEdit:focus {{border:1px solid {PURPLE}}}
 QListWidget {{background:transparent;border:0;outline:0}}
 QListWidget::item {{background:{PANEL};margin:5px 0;padding:15px;border:1px solid {EDGE};border-radius:9px}}
 QListWidget::item:selected {{background:#38304c;border:1px solid {PURPLE}}}
 QScrollArea {{border:0}}
 QSplitter::handle {{background:{EDGE};width:1px}}
 QScrollBar:vertical {{background:transparent;width:9px}}
 QScrollBar::handle:vertical {{background:#4d455c;border-radius:4px}}
'''

def label(text, size=13, muted=False):
    l=QLabel(str(text));l.setWordWrap(True)
    if muted:l.setObjectName('muted')
    if size != 13:l.setStyleSheet(f'font-size:{size}px;'+(f'color:{MUTE};' if muted else ''))
    return l

def panel(layout=None):
    w=QFrame();w.setObjectName('card')
    if layout:w.setLayout(layout)
    return w

class ImportDialog(QDialog):
    def __init__(self, folders, parent=None):
        super().__init__(parent);self.setWindowTitle('Import PS3 Saves');self.resize(530,340)
        v=QVBoxLayout(self);v.setSpacing(12)
        v.addWidget(label(f'{len(folders)} PS3 save folder(s) detected',19))
        v.addWidget(label('Imported saves are copied into the archive. Source files remain untouched.',muted=True))
        self.list=QListWidget();self.list.addItems([str(p) for p in folders]);v.addWidget(self.list)
        form=QFormLayout();self.category=QComboBox();self.category.addItems(CATEGORIES);self.category.setCurrentText('Unsorted')
        form.addRow('Category',self.category);v.addLayout(form)
        buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Ok|QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept);buttons.rejected.connect(self.reject);v.addWidget(buttons)

class MainWindow(QMainWindow):
    def __init__(self, root: Path):
        super().__init__();self.archive=Archive(root);self.setWindowTitle("Z's Save Archive  •  PS3 + PC  v0.2")
        self.resize(1320,840);self.setMinimumSize(980,650);self.current=None;self.mode='games'
        outer=QWidget();self.setCentralWidget(outer);horizontal=QHBoxLayout(outer);horizontal.setContentsMargins(0,0,0,0);horizontal.setSpacing(0)
        sidebar=QFrame();sidebar.setObjectName('sidebar');sidebar.setFixedWidth(214);sl=QVBoxLayout(sidebar);sl.setContentsMargins(16,27,16,20);sl.setSpacing(8)
        brand=label('◈  Z ARCHIVE',21);brand.setStyleSheet(f'font-size:20px;font-weight:800;color:{PURPLE}')
        sl.addWidget(brand);sl.addWidget(label('GAME SAVE LIBRARY',10,True));sl.addSpacing(29)
        self.nav=[]
        for name,fn in [('▦  Game Library',self.show_games),('▤  All Saves',self.show_saves),('⚙  Settings',self.show_settings)]:
            btn=QPushButton(name);btn.setObjectName('nav');btn.setCheckable(True);btn.clicked.connect(fn);sl.addWidget(btn);self.nav.append(btn)
        sl.addStretch();sl.addWidget(label('SUPPORTED PLATFORMS',10,True))
        ps3=label('●  PS3      ●  PC');ps3.setStyleSheet('color:#a8e3c2;font-weight:600');sl.addWidget(ps3)
        sl.addSpacing(15);sl.addWidget(label('v0.2  •  Local-first archive',10,True))
        horizontal.addWidget(sidebar)
        main=QWidget();ml=QVBoxLayout(main);ml.setContentsMargins(28,24,28,22);ml.setSpacing(17)
        top=QHBoxLayout();headers=QVBoxLayout();self.heading=QLabel('Game Library');self.heading.setObjectName('heading');headers.addWidget(self.heading)
        self.subheading=label('Manage your personal PS3 save collection.',12,True);headers.addWidget(self.subheading);top.addLayout(headers);top.addStretch()
        self.importbtn=QPushButton('＋  Import PS3');self.importbtn.setObjectName('primary');self.importbtn.clicked.connect(self.import_folder);top.addWidget(self.importbtn)
        self.pcbtn=QPushButton('＋  Import PC');self.pcbtn.clicked.connect(self.import_pc);top.addWidget(self.pcbtn);ml.addLayout(top)
        stats=QHBoxLayout();self.stat_widgets=[]
        for title in ('GAMES IN LIBRARY','TOTAL SAVES','VERIFIED SAVES'):
            lay=QVBoxLayout();lay.setContentsMargins(18,15,18,15);lay.setSpacing(4)
            lay.addWidget(label(title,10,True));value=QLabel('0');value.setObjectName('large');lay.addWidget(value)
            c=panel(lay);stats.addWidget(c);self.stat_widgets.append(value)
        ml.addLayout(stats)
        controls=QHBoxLayout();self.search=QLineEdit();self.search.setPlaceholderText('⌕  Search games, title IDs, saves...');self.search.textChanged.connect(self.refresh)
        controls.addWidget(self.search,1)
        self.platform=QComboBox();self.platform.addItems(['All','PS3','PC','PS4']);self.platform.setFixedWidth(105);self.platform.currentTextChanged.connect(self.refresh);controls.addWidget(self.platform)
        self.tagfilter=QComboBox();self.tagfilter.setFixedWidth(170);self.tagfilter.currentTextChanged.connect(self.refresh);controls.addWidget(self.tagfilter)
        self.filter=QComboBox();self.filter.addItems(('All',)+CATEGORIES);self.filter.currentTextChanged.connect(self.refresh);self.filter.setFixedWidth(140);controls.addWidget(self.filter);ml.addLayout(controls)
        self.stack=QStackedWidget();ml.addWidget(self.stack,1)
        self.game_list=QListWidget();self.game_list.itemClicked.connect(self.select_game)
        games_panel=QWidget();gp=QVBoxLayout(games_panel);gp.setContentsMargins(0,0,0,0);gp.addWidget(self.game_list)
        self.game_hint=panel();empty=QVBoxLayout(self.game_hint);empty.setContentsMargins(30,34,30,34);empty.setSpacing(12)
        headline=label('Your save collection starts here',22);headline.setAlignment(Qt.AlignmentFlag.AlignCenter);empty.addWidget(headline)
        hint=label('Import PS3 save folders or PC save files to build your library.\nEverything is copied into a local archive; your original files stay untouched.',13,True)
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter);empty.addWidget(hint)
        action=QPushButton('＋  Import a PS3 save');action.setObjectName('primary');action.clicked.connect(self.import_folder);empty.addWidget(action,0,Qt.AlignmentFlag.AlignCenter)
        gp.addWidget(self.game_hint);gp.addStretch(1)
        self.stack.addWidget(games_panel)
        savepage=QSplitter(Qt.Orientation.Horizontal)
        self.save_list=QListWidget();self.save_list.setMinimumWidth(300);self.save_list.itemClicked.connect(self.select_save)
        savepage.addWidget(self.save_list)
        detail=QWidget();dl=QVBoxLayout(detail);dl.setContentsMargins(18,8,8,8);dl.setSpacing(12)
        self.detail_title=label('Choose a save to inspect',20);dl.addWidget(self.detail_title)
        self.detail_meta=label('Save metadata and testing status will appear here.',12,True);dl.addWidget(self.detail_meta)
        self.detail_category=QComboBox();self.detail_category.addItems(CATEGORIES);dl.addWidget(label('Category',11,True));dl.addWidget(self.detail_category)
        dl.addWidget(label('Release label',11,True));self.detail_label=QLineEdit();dl.addWidget(self.detail_label)
        dl.addWidget(label('Notes / modifications',11,True));self.detail_notes=QTextEdit();self.detail_notes.setPlaceholderText('What did you unlock or modify?');self.detail_notes.setMaximumHeight(110);dl.addWidget(self.detail_notes)
        dl.addWidget(label('Tags (comma-separated; add your own)',11,True))
        self.detail_tags=QLineEdit();self.detail_tags.setPlaceholderText('Max Money, All Unlocks, Starter Boost');dl.addWidget(self.detail_tags)
        self.tag_hints=label('Suggestions: Max Money · Max Level · 100% Complete · All Unlocks · Starter Boost',11,True);dl.addWidget(self.tag_hints)
        dl.addWidget(label('Test status',11,True));self.detail_status=QComboBox();self.detail_status.addItems(['Unverified','Verified','Needs fixes']);dl.addWidget(self.detail_status)
        self.savebutton=QPushButton('Save Details');self.savebutton.setObjectName('primary');self.savebutton.clicked.connect(self.save_details);dl.addWidget(self.savebutton)
        self.backupbutton=QPushButton('⬇  Backup Save to ZIP');self.backupbutton.clicked.connect(self.backup_selected);dl.addWidget(self.backupbutton)
        self.openbutton=QPushButton('Open Archived Folder');self.openbutton.clicked.connect(self.open_selected_folder);dl.addWidget(self.openbutton)
        dl.addStretch(1)
        savepage.addWidget(detail);savepage.setStretchFactor(0,3);savepage.setStretchFactor(1,2);self.stack.addWidget(savepage)
        settings=QWidget();st=QVBoxLayout(settings);st.setContentsMargins(12,12,12,12);st.setSpacing(14)
        st.addWidget(label('Archive storage',20));st.addWidget(label(str(self.archive.root),13,True));st.addWidget(label('Each imported save is copied into a unique archive directory. Original files remain untouched. Backups are ZIP files with metadata and the original save files.'))
        st.addSpacing(20);st.addWidget(label('Supported now',20));st.addWidget(label('PS3 PARAM.SFO scanning, PC save file/folder import, tags, filters, duplicate checks, notes, verification tracking, integrity-checked ZIP backups and search.'))
        st.addWidget(label('Not included in v0.2: FTP sync, automatic PC game detection, save editing or re-signing.',muted=True));st.addStretch();self.stack.addWidget(settings)
        horizontal.addWidget(main,1)
        self.statusBar().showMessage('PS3 + PC local library ready')
        self.show_games()

    def activate_nav(self,idx):
        for i,b in enumerate(self.nav):b.setChecked(i==idx)
        self.stack.setCurrentIndex(idx)
        self.filter.setVisible(idx==1);self.tagfilter.setVisible(idx==1);self.platform.setVisible(idx!=2);self.search.setVisible(idx!=2)
    def show_games(self):
        self.activate_nav(0);self.mode='games';self.heading.setText('Game Library');self.subheading.setText('All your PS3 and PC saves, organized in one place.');self.refresh()
    def show_saves(self):
        self.activate_nav(1);self.mode='saves';self.heading.setText('All Saves');self.subheading.setText('Manage tags, test status, and secure ZIP backups.');self.refresh()
    def show_settings(self):
        self.activate_nav(2);self.mode='settings';self.heading.setText('Settings');self.subheading.setText('Local archive configuration and feature availability.');self.refresh()
    def refresh(self,*args):
        for w,value in zip(self.stat_widgets,self.archive.stats()):w.setText(str(value))
        oldtag=self.tagfilter.currentText()
        self.tagfilter.blockSignals(True);self.tagfilter.clear();self.tagfilter.addItems(['All']+self.archive.list_tags())
        self.tagfilter.setCurrentText(oldtag if oldtag in ['All']+self.archive.list_tags() else 'All')
        self.tagfilter.blockSignals(False)
        if self.mode=='games':
            self.game_list.clear();rows=self.archive.games(self.search.text(),self.platform.currentText())
            for g in rows:
                item=QListWidgetItem(f"▣  {g['game']}\n      {g['platform']}  •  {g['title_id']}  •  {g['saves']} save(s)")
                item.setData(Qt.ItemDataRole.UserRole,(g['title_id'],g['game'],g['platform']));self.game_list.addItem(item)
            self.game_hint.setVisible(not bool(rows))
        elif self.mode=='saves':
            self.save_list.clear();rows=self.archive.list_saves(self.search.text(),self.filter.currentText(),self.platform.currentText(),self.tagfilter.currentText())
            for r in rows:
                item=QListWidgetItem(f"{r['game']}  [{r['platform']}]\n{r['label']}\n{r['category']}  •  {r['status']}  •  {', '.join(r['tags'][:3])}")
                item.setData(Qt.ItemDataRole.UserRole,r);self.save_list.addItem(item)
            self.current=None;self.detail_title.setText('Choose a save to inspect')
    def select_game(self,item):
        title,game,platform=item.data(Qt.ItemDataRole.UserRole)
        self.show_game_saves(game, platform, title)

    def show_game_saves(self, game, platform, title=''):
        self.filter.setCurrentText('All')
        self.tagfilter.setCurrentText('All')
        self.platform.setCurrentText(platform)
        self.search.setText(title if platform == 'PS3' and title else game)
        self.show_saves()
    def select_save(self,item):
        r=item.data(Qt.ItemDataRole.UserRole);self.current=r
        self.detail_title.setText(r['game']);self.detail_meta.setText(f"{r['platform']}  •  {r['title_id']}  •  {r['region']}  •  {r['file_count']} files  •  {r['size_bytes']:,} bytes\nSHA-256: {r['file_hash'][:24]}…")
        self.detail_category.setCurrentText(r['category']);self.detail_label.setText(r['label']);self.detail_notes.setPlainText(r['notes']);self.detail_status.setCurrentText(r['status']);self.detail_tags.setText(', '.join(r.get('tags',[])))
    def save_details(self):
        if not self.current:return
        try:
            self.archive.update(self.current['id'],category=self.detail_category.currentText(),label=self.detail_label.text(),notes=self.detail_notes.toPlainText(),status=self.detail_status.currentText())
            self.archive.set_tags(self.current['id'],self.detail_tags.text().split(','))
            self.statusBar().showMessage('Save details and tags updated');self.refresh()
        except Exception as e:QMessageBox.warning(self,'Update failed',str(e))
    def open_selected_folder(self):
        if not self.current:return
        import subprocess
        folder=self.archive.root/self.current['stored_path']
        if sys.platform=='win32':os.startfile(str(folder))
        elif sys.platform=='darwin':subprocess.Popen(['open',str(folder)])
        else:subprocess.Popen(['xdg-open',str(folder)])
    def import_pc(self):
        self.import_local_save('PC', self.archive.import_pc_save)

    def import_ps4(self):
        self.import_local_save('PS4', self.archive.import_ps4_save)

    def import_local_save(self, platform, importer):
        choice=QMessageBox.question(self,f'{platform} save source','Import a folder? Choose Yes for a folder, No for a single file.',QMessageBox.StandardButton.Yes|QMessageBox.StandardButton.No|QMessageBox.StandardButton.Cancel)
        if choice==QMessageBox.StandardButton.Cancel:return
        path=(QFileDialog.getExistingDirectory(self,f'Choose {platform} save folder') if choice==QMessageBox.StandardButton.Yes
              else QFileDialog.getOpenFileName(self,f'Choose {platform} save file')[0])
        if not path:return
        game = self.choose_game_title(platform)
        if game:
            self.archive_local_save(Path(path), platform, game, importer)

    def choose_game_title(self, platform):
        titles = {}
        for row in self.archive.games(platform=platform):
            title = row['game']
            titles.setdefault(title.casefold(), title)
        game, accepted = QInputDialog.getItem(
            self, f'{platform} game title', 'Choose an existing game or type a new name:',
            ['', *sorted(titles.values(), key=str.casefold)], 0, True,
        )
        game = game.strip()
        return titles.get(game.casefold(), game) if accepted else ''

    def archive_local_save(self, path, platform, game, importer):
        try:
            importer(path, game)
            self.refresh()
            self.statusBar().showMessage(f'{platform} save imported')
            QMessageBox.information(self, 'Imported', f'{platform} save copied into your library.')
        except Exception as exc:
            QMessageBox.warning(self, 'Import failed', str(exc))

    def backup_selected(self):
        if not self.current:
            QMessageBox.information(self,'Select a save','Select a save first.');return
        r=self.current
        import re
        safe=lambda x:re.sub(r'[^a-zA-Z0-9._-]+','_',x).strip('_')[:55]
        filename=f"{safe(r['game'])}_{r['platform']}_{safe(r['label'])}.zip"
        path=QFileDialog.getSaveFileName(self,'Backup save as ZIP',str(Path.home()/'Downloads'/filename),'ZIP archive (*.zip)')[0]
        if not path:return
        try:
            result=self.archive.backup_zip(r['id'],Path(path))
            self.statusBar().showMessage('ZIP backup verified: '+str(result))
            QMessageBox.information(self,'Backup complete',f'ZIP created and integrity checked:\n{result}')
        except Exception as e:QMessageBox.warning(self,'Backup failed',str(e))

    def import_folder(self):
        path=QFileDialog.getExistingDirectory(self,'Select PS3 save folder or parent directory')
        if not path:return
        try:
            root=Path(path);folders=discover_saves(root)
            if not folders:QMessageBox.information(self,'No saves found','No folders containing PARAM.SFO were found.');return
            dlg=ImportDialog(folders,self)
            if dlg.exec()!=QDialog.DialogCode.Accepted:return
            success=[];failed=[]
            for folder in folders:
                try:self.archive.import_save(folder,category=dlg.category.currentText());success.append(folder.name)
                except Exception as e:failed.append(f'{folder.name}: {e}')
            self.refresh()
            text=f'Imported {len(success)} save(s).'
            if failed:text+='\n\nSkipped / errors:\n'+'\n'.join(failed[:15])
            QMessageBox.information(self,'Import results',text)
        except Exception as e:QMessageBox.warning(self,'Import failed',str(e))
    def closeEvent(self,event):
        self.archive.close();super().closeEvent(event)

def main():
    app=QApplication(sys.argv);app.setStyle('Fusion');app.setStyleSheet(QSS)
    root=Path(os.environ.get('Z_ARCHIVE_HOME',str(Path.home()/'Documents'/'Z PlayStation Save Archive')))
    window=MainWindow(root);window.show();sys.exit(app.exec())
