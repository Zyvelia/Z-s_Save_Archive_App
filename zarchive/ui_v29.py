"""v2.9 concept dashboard: live archive data, existing features preserved in workspace."""
from __future__ import annotations
import os,sys
from pathlib import Path
from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QIcon,QPixmap
from PySide6.QtWidgets import (QApplication,QMainWindow,QWidget,QFrame,QLabel,QVBoxLayout,QHBoxLayout,
 QPushButton,QScrollArea,QStackedWidget,QLineEdit,QComboBox,QListWidget,QListWidgetItem,QGridLayout,QMessageBox,QCheckBox,QDialog,QFileDialog)
from .ui_v28 import Window as ExistingWindow
from .ui_v04 import STYLE,cover_icon
from .app_assets import asset_path
from .appdata_v34 import AppPaths
from .navigation_v30 import classify_action, collect_legacy_actions, DEFAULT_ACTIONS, is_advanced_action

DESIGN='''
QFrame#newSidebar {background:#151021;border-right:1px solid #51316d;}
QFrame#newCard {background:#221b32;border:1px solid #59416f;border-radius:15px;}
QFrame#newHero {background:#251735;border:1px solid #8744b5;border-radius:16px;}
QPushButton#newNav {background:transparent;border:none;text-align:left;padding:12px 15px;border-radius:9px;color:#d9cdeb;font-size:13px;}
QPushButton#newNav:hover {background:#352447;border:1px solid #8753c4;}
QPushButton#newNav:checked {background:#6a2b9b;border:1px solid #a65af2;color:white;}
QPushButton#newAction {background:#49266c;border:1px solid #a35de2;text-align:center;padding:13px;border-radius:10px;}
QPushButton#newAction:hover {background:#683595;}
QListWidget#newList::item {background:#241b35;border:1px solid #53436a;border-radius:10px;padding:11px;margin:4px;}
QListWidget#newList::item:selected {background:#503074;border:1px solid #bc6eff;}
QLabel#newNumber {font-size:27px;font-weight:750;color:#f6e9ff;}
QLabel#newTitle {font-size:22px;font-weight:750;color:#fff;}
QLabel#newMuted {color:#b8a9cc;}
'''

def txt(value,size=None,muted=False):
    w=QLabel(str(value));w.setWordWrap(True)
    if muted:w.setObjectName('newMuted')
    if size:w.setStyleSheet(f'font-size:{size}px;'+('font-weight:650;' if size>=15 else ''))
    return w

def pane(title):
    frame=QFrame();frame.setObjectName('newCard');lay=QVBoxLayout(frame)
    lay.setContentsMargins(17,15,17,16);lay.setSpacing(10);lay.addWidget(txt(title,16))
    return frame,lay

class AppDataDialog(QDialog):
    def __init__(self,parent=None):
        super().__init__(parent);self.setWindowTitle('AppData Storage Manager');self.resize(650,420)
        self.paths=AppPaths.discover().initialize()
        layout=QVBoxLayout(self)
        layout.addWidget(txt('AppData Storage Manager',20))
        layout.addWidget(txt('Settings are stored in Roaming. Regenerable caches and logs are in Local. Save backups, ISOs and PKGs remain in your chosen folders.',12,True))
        self.info=QLabel();self.info.setWordWrap(True);layout.addWidget(self.info)
        buttons=QHBoxLayout();layout.addLayout(buttons)
        for label,path in [('Open Roaming',self.paths.roaming),('Open Local',self.paths.local)]:
            b=QPushButton(label);b.clicked.connect(lambda _,p=path:self._open_dir(p));buttons.addWidget(b)
        refresh=QPushButton('Refresh usage');refresh.clicked.connect(self.refresh);buttons.addWidget(refresh)
        clear=QPushButton('Clear cache');clear.clicked.connect(self.clear_cache);layout.addWidget(clear)
        archive=QPushButton('Choose default archive folder (future new installs)');archive.clicked.connect(self.choose_archive);layout.addWidget(archive)
        self.archive_label=QLabel();self.archive_label.setWordWrap(True);layout.addWidget(self.archive_label)
        layout.addWidget(txt('Existing archives are never automatically migrated, moved, or removed. Override with Z_ARCHIVE_HOME or portable.flag when needed.',11,True))
        layout.addStretch();self.refresh()

    def _open_dir(self,path):
        from PySide6.QtGui import QDesktopServices
        from PySide6.QtCore import QUrl
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

    def refresh(self):
        data=self.paths.folder_sizes()
        self.info.setText('Roaming: '+str(self.paths.roaming)+'\nLocal: '+str(self.paths.local)+'\n'+
            '   |   '.join(f'{k}: {v/1048576:.2f} MiB' for k,v in data.items()))
        self.archive_label.setText('Default archive: '+(self.paths.path('archive_root') or 'Documents\\Z PlayStation Save Archive (legacy default)'))

    def clear_cache(self):
        if QMessageBox.question(self,'Clear generated cache?', 'Remove regenerable cached art and metadata only?')!=QMessageBox.StandardButton.Yes:return
        try:
            size=self.paths.clear_cache();self.refresh()
            QMessageBox.information(self,'Cache cleared',f'Cleared {size/1048576:.2f} MiB; archives, settings and logs were not changed.')
        except Exception as exc: QMessageBox.warning(self,'Cache cleanup failed',str(exc))

    def choose_archive(self):
        folder=QFileDialog.getExistingDirectory(self,'Choose existing or new archive location')
        if folder:
            self.paths.remember_path('archive_root',folder)
            QMessageBox.information(self,'Saved', 'Archive location preference saved. Restart to apply. Existing archive files are NOT moved or copied.')
            self.refresh()

class Window(ExistingWindow):
    def __init__(self,root):
        super().__init__(root)
        self.setWindowTitle("Z's Save Archive • v3.6.8")
        self.resize(1540,930);self.setMinimumSize(1060,720)
        self.classic_content=self.takeCentralWidget()
        # All existing tools retain their QAction callbacks, even though the menu is hidden.
        self.legacy_actions=collect_legacy_actions(self.tools_btn.menu())
        self.tools_btn.hide()
        # Hide the duplicate internal sidebar when the classic workspace is embedded.
        self.sidebar.hide()
        # Existing application, pages, dialogs, menus, and signals remain available.
        shell=QWidget();self.setCentralWidget(shell)
        row=QHBoxLayout(shell);row.setContentsMargins(0,0,0,0);row.setSpacing(0)
        side=QFrame();side.setObjectName('newSidebar');side.setFixedWidth(224)
        sl=QVBoxLayout(side);sl.setContentsMargins(13,18,13,18);sl.setSpacing(5)
        brand=QLabel();brand.setAlignment(Qt.AlignmentFlag.AlignCenter)
        pix=QPixmap(str(asset_path('ZSaveArchive.png')))
        brand.setPixmap(pix.scaled(105,105,Qt.AspectRatioMode.KeepAspectRatio,Qt.TransformationMode.SmoothTransformation))
        sl.addWidget(brand)
        name=txt("Z's Save Archive",18);name.setAlignment(Qt.AlignmentFlag.AlignCenter);sl.addWidget(name)
        sub=txt('PS3 & PC Save Manager',11,True);sub.setAlignment(Qt.AlignmentFlag.AlignCenter);sl.addWidget(sub)
        sl.addSpacing(22)
        self.navbuttons={}
        routes=[('Dashboard',self.open_home),('Game Library',lambda:self.open_classic('games')),
                ('Saves & Backups',lambda:self.open_section('Saves & Backups')),
                ('PS3 Console',lambda:self.open_classic('ftp')),
                ('Save Editor',lambda:self.open_section('Save Editor')),
                ('PS3 Tools',lambda:self.open_section('PS3 Tools')),
                ('Releases',lambda:self.open_section('Releases')),
                ('Settings',lambda:self.open_section('Settings'))]
        for index,(text,handler) in enumerate(routes):
            b=QPushButton(text);b.setObjectName('newNav');b.setCheckable(True)
            b.clicked.connect(lambda _,f=handler:f());sl.addWidget(b);self.navbuttons[text]=b
        sl.addStretch();sl.addWidget(txt('Local-first · No demo save data',10,True))
        row.addWidget(side)
        self.shell_stack=QStackedWidget();row.addWidget(self.shell_stack,1)
        self.home=QScrollArea();self.home.setWidgetResizable(True);self.home.setObjectName('newHome')
        self.shell_stack.addWidget(self.home);self.shell_stack.addWidget(self.classic_content)
        self.section_pages={}
        for section in ('Saves & Backups','Save Editor','PS3 Tools','Releases','Settings'):
            self.section_pages[section]=self._make_section(section)
            self.shell_stack.addWidget(self.section_pages[section])
        self.make_home();self.open_home()

    def make_home(self):
        body=QWidget();self.home.setWidget(body)
        vertical=QVBoxLayout(body);vertical.setContentsMargins(20,18,20,24);vertical.setSpacing(14)
        header=QHBoxLayout();titles=QVBoxLayout()
        title=txt("Welcome to Z's Save Archive",24);title.setObjectName('newTitle')
        titles.addWidget(title);titles.addWidget(txt('Organize, inspect and back up your actual PS3 and PC saves.',12,True))
        header.addLayout(titles,1)
        self.home_search=QLineEdit();self.home_search.setPlaceholderText('Search games and saves…');self.home_search.setMinimumWidth(230)
        self.home_search.textChanged.connect(self.update_home)
        header.addWidget(self.home_search)
        self.platform_filter=QComboBox();self.platform_filter.addItems(['All Platforms','PS3','PC']);self.platform_filter.currentIndexChanged.connect(self.update_home)
        header.addWidget(self.platform_filter);vertical.addLayout(header)
        hero=QFrame();hero.setObjectName('newHero');hl=QHBoxLayout(hero)
        hl.addWidget(txt('ARCHIVE OVERVIEW',15))
        self.counts={}
        for key in ('Games','Saves','Verified','Backups'):
            group=QVBoxLayout();num=txt('—');num.setObjectName('newNumber');num.setAlignment(Qt.AlignmentFlag.AlignCenter)
            group.addWidget(num);lab=txt(key,11,True);lab.setAlignment(Qt.AlignmentFlag.AlignCenter);group.addWidget(lab)
            hl.addLayout(group);self.counts[key]=num
        vertical.addWidget(hero)
        info=QHBoxLayout();info.setSpacing(12)
        self.ps3_card,self.ps3_content=pane('PS3 SAVES')
        self.pc_card,self.pc_content=pane('PC SAVES')
        self.backup_card,self.backup_content=pane('BACKUP STATUS')
        self.ps3_summary=txt('—',19);self.pc_summary=txt('—',19);self.backup_summary=txt('—',16)
        self.ps3_content.addWidget(self.ps3_summary);self.pc_content.addWidget(self.pc_summary);self.backup_content.addWidget(self.backup_summary)
        info.addWidget(self.ps3_card);info.addWidget(self.pc_card);info.addWidget(self.backup_card);vertical.addLayout(info)
        content=QHBoxLayout();content.setSpacing(12)
        left,left_layout=pane('GAME & SAVE LIBRARY')
        bar=QHBoxLayout();bar.addWidget(txt('Games in your archive',11,True));bar.addStretch()
        browse=QPushButton('Open full library');browse.clicked.connect(lambda:self.open_classic('games'));bar.addWidget(browse)
        organize=QPushButton('Organize');organize.clicked.connect(lambda:self.open_section('Game Library'));bar.addWidget(organize)
        left_layout.addLayout(bar)
        self.game_list=QListWidget();self.game_list.setObjectName('newList');self.game_list.setMinimumHeight(350)
        self.game_list.itemActivated.connect(self.choose_game);self.game_list.itemClicked.connect(self.choose_game)
        left_layout.addWidget(self.game_list)
        hint=txt('Select a game to open and inspect its saves.',11,True);left_layout.addWidget(hint)
        content.addWidget(left,3)
        right=QVBoxLayout();right.setSpacing(12)
        console,console_layout=pane('PS3 CONSOLE')
        console_layout.addWidget(txt('Connection status is not inferred automatically.',11,True))
        cb=QPushButton('Open PS3 connection tools');cb.clicked.connect(lambda:self.open_classic('ftp'));console_layout.addWidget(cb)
        right.addWidget(console)
        recent,recent_layout=pane('RECENT ARCHIVED SAVES')
        self.recent_list=QListWidget();self.recent_list.setObjectName('newList');self.recent_list.setMinimumHeight(140)
        self.recent_list.itemClicked.connect(self.choose_recent)
        recent_layout.addWidget(self.recent_list);right.addWidget(recent)
        actions,action_layout=pane('QUICK TOOLS')
        grid=QGridLayout();grid.setSpacing(7)
        quick=[('Import PS3',self.import_folder),('Import PC',self.import_pc),('Backups',lambda:self.open_section('Saves & Backups')),
               ('Edit Save',self.editor_ui),('PS3 Transfer',lambda:self.open_classic('ftp')),('PS3 Tools',lambda:self.open_section('PS3 Tools'))]
        for i,(label,handler) in enumerate(quick):
            b=QPushButton(label);b.setObjectName('newAction');b.clicked.connect(handler);grid.addWidget(b,i//3,i%3)
        action_layout.addLayout(grid);right.addWidget(actions)
        content.addLayout(right,2);vertical.addLayout(content)
        vertical.addWidget(txt('This preview uses real local archive data. PS3 status is available through the existing connection tools; no fictitious connected console, storage, or backup health is displayed.',11,True))
        vertical.addStretch()

    def _set_nav(self,name):
        for key,b in self.navbuttons.items():b.setChecked(key==name)

    def open_home(self):
        self.shell_stack.setCurrentIndex(0);self._set_nav('Dashboard');self.update_home()

    def open_classic(self,which):
        self.shell_stack.setCurrentIndex(1)
        mapping={'games':('Game Library',self.show_games),'saves':('Saves & Backups',self.show_saves),
                 'settings':('Settings',self.show_settings),'history':('Saves & Backups',self.show_history),
                 'ftp':('PS3 Console',self.show_ftp)}
        if which in mapping:
            label,handler=mapping[which];self._set_nav(label);handler()
        elif which=='releases':
            self.open_section('Releases')

    def homebrew(self):
        from .ui_v24 import HomebrewCenter
        HomebrewCenter(self,root=self.archive.root).exec()

    def _make_section(self, section):
        """Build action panels from existing wired QAction objects (no detached tool copies)."""
        page=QScrollArea();page.setWidgetResizable(True)
        body=QWidget();page.setWidget(body)
        outer=QVBoxLayout(body);outer.setContentsMargins(25,23,25,23);outer.setSpacing(14)
        captions={
            'Saves & Backups':'Restore, snapshot, compare and protect your archived saves.',
            'Save Editor':'Edit supported saves and inspect metadata safely.',
            'PS3 Tools':'Homebrew, PKG management and ISO conversion in one place.',
            'Releases':'GitHub publishing, release preparation and public catalogs.',
            'Settings':'Appearance, maintenance and advanced diagnostics.',
            'Game Library':'Optional organization tools; normal browsing stays in Game Library.',
        }
        outer.addWidget(txt(section,24));outer.addWidget(txt(captions[section],12,True))
        if section=='Saves & Backups':
            row=QHBoxLayout()
            for label,fn in [('Browse Saves',lambda:self.open_classic('saves')),
                             ('Backup History',lambda:self.open_classic('history')),
                             ('Import PC Save',self.import_pc)]:
                b=QPushButton(label);b.setObjectName('newAction');b.clicked.connect(fn);row.addWidget(b)
            outer.addLayout(row)
        elif section=='Save Editor':
            b=QPushButton('Open Universal Save Editor');b.setObjectName('newAction');b.clicked.connect(self.editor_ui);outer.addWidget(b)
            outer.addWidget(txt('Unsupported or experimental game-specific editing stays hidden until validated.',11,True))
        elif section=='PS3 Tools':
            row=QHBoxLayout()
            for label,fn in [('Homebrew Manager',self.homebrew),('Browse PS3 FTP',lambda:self.open_classic('ftp'))]:
                b=QPushButton(label);b.setObjectName('newAction');b.clicked.connect(fn);row.addWidget(b)
            outer.addLayout(row)
        elif section=='Game Library':
            b=QPushButton('Back to Game Library');b.clicked.connect(lambda:self.open_classic('games'));outer.addWidget(b)
        elif section=='Settings':
            b=QPushButton('Open Archive Settings');b.clicked.connect(lambda:self.open_classic('settings'));outer.addWidget(b)
            manager=QPushButton('AppData Storage Manager');manager.setObjectName('newAction');manager.clicked.connect(lambda:AppDataDialog(self).exec());outer.addWidget(manager)
        self._add_action_panel(section,outer)
        outer.addStretch(1)
        return page

    def _add_action_panel(self,section,outer):
        panel,layout=pane('AVAILABLE ACTIONS')
        advanced=[];primary=[];seen=set()
        for action in self.legacy_actions:
            name=action.text().replace('&','').strip()
            if name in seen or not action.isEnabled():continue
            seen.add(name)
            if classify_action(name)!=section:continue
            (advanced if is_advanced_action(name) else primary).append((name,action))
        # Each button triggers the original action and its original callback.
        def add_buttons(items,target):
            for name,action in items:
                btn=QPushButton(name);btn.setObjectName('newAction')
                btn.setToolTip('Existing tool; uses the original application callback')
                btn.clicked.connect(lambda _=False,a=action:a.trigger())
                target.addWidget(btn)
        add_buttons(primary,layout)
        if advanced:
            toggle=QCheckBox('Show advanced / experimental actions')
            layout.addWidget(toggle)
            advanced_panel=QWidget();advanced_layout=QVBoxLayout(advanced_panel)
            advanced_layout.setContentsMargins(0,0,0,0)
            add_buttons(advanced,advanced_layout)
            advanced_panel.setVisible(False)
            toggle.toggled.connect(advanced_panel.setVisible)
            layout.addWidget(advanced_panel)
        if not primary and not advanced:layout.addWidget(txt('No additional utilities in this section.',11,True))
        outer.addWidget(panel)

    def open_section(self,section):
        if section not in self.section_pages:
            self.section_pages[section]=self._make_section(section)
            self.shell_stack.addWidget(self.section_pages[section])
        self.shell_stack.setCurrentWidget(self.section_pages[section])
        self._set_nav(section if section in self.navbuttons else 'Game Library')

    def choose_game(self,item):
        data=item.data(Qt.ItemDataRole.UserRole)
        if not data:return
        self.open_classic('games')
        self.search.setText(data['game'])
        self.platform.setCurrentText(data['platform'])

    def choose_recent(self,item):
        row=item.data(Qt.ItemDataRole.UserRole)
        if row:self.shell_stack.setCurrentIndex(1);self._set_nav('Saves & Backups');self.show_saves();self.search.setText(row['game'])

    def update_home(self,*_):
        try:
            stats=self.archive.dashboard()
            for key,col in [('Games','games'),('Saves','saves'),('Verified','verified'),('Backups','backups')]:
                self.counts[key].setText(f"{stats.get(col,0):,}")
            all_saves=self.archive.list_saves()
            nps3=sum(1 for r in all_saves if r.get('platform')=='PS3')
            npc=sum(1 for r in all_saves if r.get('platform')=='PC')
            self.ps3_summary.setText(f'{nps3:,} archived saves')
            self.pc_summary.setText(f'{npc:,} archived saves')
            self.backup_summary.setText(f"{stats.get('backups',0):,} recorded backups\nVerification not automated")
            platform=self.platform_filter.currentText();platform='All' if platform=='All Platforms' else platform
            query=self.home_search.text().strip()
            games=self.archive.games(query,platform)
            self.game_list.clear()
            for game in games[:100]:
                row=QListWidgetItem(f"{game['game']}   ·   {game['platform']}\n{game['saves']} archived saves  ·  {game['title_id']}")
                row.setData(Qt.ItemDataRole.UserRole,game)
                row.setIcon(cover_icon(game['game'],game['platform'],size=QSize(100,70)))
                self.game_list.addItem(row)
            if not games:
                item=QListWidgetItem('No games match your search. Import saves to populate the library.')
                item.setFlags(Qt.ItemFlag.NoItemFlags);self.game_list.addItem(item)
            self.recent_list.clear()
            for save in all_saves[:6]:
                item=QListWidgetItem(f"{save['game']}  ·  {save['platform']}\n{save['label']}")
                item.setData(Qt.ItemDataRole.UserRole,save);self.recent_list.addItem(item)
            if not all_saves:self.recent_list.addItem('No archived saves yet')
        except Exception as exc:
            self.statusBar().showMessage('Dashboard refresh error: '+str(exc)[:180])

def main():
    from . import ui
    from .editor_v18 import ArchiveV18
    ui.Archive=ArchiveV18
    app=QApplication(sys.argv);app.setStyle('Fusion');app.setStyleSheet(STYLE+DESIGN)
    app.setWindowIcon(QIcon(str(asset_path('ZSaveArchive.png'))))
    home=os.environ.get('Z_ARCHIVE_HOME')
    if home:root=Path(home)
    elif (Path(sys.argv[0]).resolve().parent/'portable.flag').is_file():root=Path(sys.argv[0]).resolve().parent/'ArchiveData'
    else:
        locations=AppPaths.discover().initialize()
        root=Path(locations.path('archive_root') or Path.home()/'Documents'/'Z PlayStation Save Archive')
    win=Window(root);win.setWindowIcon(app.windowIcon());win.show();sys.exit(app.exec())
