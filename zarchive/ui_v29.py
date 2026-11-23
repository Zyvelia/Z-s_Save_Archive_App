"""v2.9 concept dashboard: live archive data, existing features preserved in workspace."""
from __future__ import annotations
import os,re,sys
from pathlib import Path
from PySide6.QtCore import Qt, QSize, QTimer
from PySide6.QtGui import QIcon, QKeySequence, QPixmap, QShortcut
from PySide6.QtWidgets import (QApplication,QMainWindow,QWidget,QFrame,QLabel,QVBoxLayout,QHBoxLayout,
 QPushButton,QScrollArea,QStackedWidget,QLineEdit,QComboBox,QListWidget,QListWidgetItem,QGridLayout,QMessageBox,QCheckBox,QDialog,QFileDialog,
 QDialogButtonBox,QFormLayout,QInputDialog,QMenu)
from .ui_v28 import Window as ExistingWindow
from .ui_v04 import STYLE
from .app_assets import asset_path
from .appdata_v34 import AppPaths
from .ui_ps4_fpkg import FpkgPanel
from .removable_drives import remembered_drive, removable_drives
from .storage import CHECKPOINT_KINDS
from .editor_v18 import numbered_save_name
from .ui_artwork import ArtworkPicker, GameArtwork
from .ui_preferences import InterfaceTextSize, choose_sort, edit_shortcuts, sorted_by, valid_sort
from .ui_v16 import CommandPalette
from .navigation_v30 import classify_action, collect_legacy_actions, DEFAULT_ACTIONS, is_advanced_action

SAVE_SORT_FIELDS = {'Game': 'game', 'Platform': 'platform', 'Save label': 'label',
                    'Checkpoint': 'checkpoint_label', 'Imported': 'imported_at',
                    'Size': 'size_bytes', 'Category': 'category', 'Status': 'status'}
TEXT_SIZES = (90, 100, 110, 125, 140)
SHORTCUT_DEFAULTS = {
    'Command palette': 'Ctrl+K', 'Dashboard': 'Ctrl+1', 'Game Library': 'Ctrl+2',
    'All Saves': 'Ctrl+3', 'Settings': 'Ctrl+4', 'Focus search': 'Ctrl+F',
    'Search archive': 'Ctrl+Shift+F', 'Import PC save': 'Ctrl+I',
    'Import PC save (alternate)': 'Ctrl+Shift+I',
    'Import PS3 save': '', 'Import PS4 save': '', 'Create versioned backup': 'Ctrl+B',
    'Archive health check': 'Ctrl+Shift+H', 'Pin selected save': 'Ctrl+Shift+P',
    'Jobs': 'Ctrl+Shift+J', 'Recently Removed': '', 'Dump to FPKG Builder': '',
}

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
        self.setWindowTitle("Z's Save Archive • v3.6.28")
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
        self.shell_sidebar = side
        sl=QVBoxLayout(side);sl.setContentsMargins(13,18,13,18);sl.setSpacing(5)
        brand=QLabel();brand.setAlignment(Qt.AlignmentFlag.AlignCenter)
        pix=QPixmap(str(asset_path('ZSaveArchive.png')))
        brand.setPixmap(pix.scaled(105,105,Qt.AspectRatioMode.KeepAspectRatio,Qt.TransformationMode.SmoothTransformation))
        sl.addWidget(brand)
        name=txt("Z's Save Archive",18);name.setAlignment(Qt.AlignmentFlag.AlignCenter);sl.addWidget(name)
        sub=txt('PlayStation & PC Saves',11,True);sub.setAlignment(Qt.AlignmentFlag.AlignCenter);sl.addWidget(sub)
        sl.addSpacing(22)
        self.ui_settings = AppPaths.discover()
        self.hide_ps3 = self.ui_settings.load_settings().get('hide_ps3_tools') is True
        self.ps3_widgets = []
        self.navbuttons={}
        routes=[('Dashboard',self.open_home),('Game Library',lambda:self.open_classic('games')),
                ('Saves & Backups',lambda:self.open_section('Saves & Backups')),
                ('PS3 Console',lambda:self.open_classic('ftp')),
                ('Save Editor',lambda:self.open_section('Save Editor')),
                ('PS3 Tools',lambda:self.open_section('PS3 Tools')),
                ('Dump to FPKG Builder',lambda:self.open_section('Dump to FPKG Builder')),
                ('Releases',lambda:self.open_section('Releases')),
                ('Settings',lambda:self.open_section('Settings'))]
        for index,(text,handler) in enumerate(routes):
            b=QPushButton(text.replace('&', '&&'));b.setObjectName('newNav');b.setCheckable(True)
            b.clicked.connect(lambda _,f=handler:f());sl.addWidget(b);self.navbuttons[text]=b
        sl.addStretch()
        palette = QPushButton('Command Palette')
        palette.clicked.connect(self.open_palette)
        sl.addWidget(palette)
        row.addWidget(side)
        self.shell_stack=QStackedWidget();row.addWidget(self.shell_stack,1)
        self.home=QScrollArea();self.home.setWidgetResizable(True);self.home.setObjectName('newHome')
        self.shell_stack.addWidget(self.home);self.shell_stack.addWidget(self.classic_content)
        self.section_pages={}
        self.artwork = GameArtwork(self.archive, self)
        self.artwork.ready.connect(self.refresh_artwork)
        self.save_sort = valid_sort(self.ui_settings.load_settings().get('save_sort'),
                                    SAVE_SORT_FIELDS, [('Imported', True)])
        self.install_save_controls()
        for section in ('Saves & Backups','Save Editor','PS3 Tools','Releases','Settings'):
            self.section_pages[section]=self._make_section(section)
            self.shell_stack.addWidget(self.section_pages[section])
        self.make_home()
        self.setup_shortcuts()
        self.text_size = InterfaceTextSize(QApplication.instance(), self)
        percent = self.ui_settings.load_settings().get('text_size', 100)
        self.set_text_size(percent if percent in TEXT_SIZES else 100)
        self.usb_timer = QTimer(self)
        self.usb_timer.setInterval(5000)
        self.usb_timer.timeout.connect(self.refresh_usb_status)
        self.usb_timer.start()
        self.refresh_usb_status()
        self.apply_ps3_visibility()
        self.open_home()

    def closeEvent(self, event):
        panel = self.section_pages.get('Dump to FPKG Builder')
        if panel is not None and panel.worker is not None:
            panel.cancel()
            self.open_section('Dump to FPKG Builder')
            event.ignore()
            return
        super().closeEvent(event)

    def make_home(self):
        body=QWidget();self.home.setWidget(body)
        vertical=QVBoxLayout(body);vertical.setContentsMargins(20,18,20,24);vertical.setSpacing(14)
        header=QHBoxLayout();titles=QVBoxLayout()
        title=txt("Welcome to Z's Save Archive",24);title.setObjectName('newTitle')
        titles.addWidget(title);titles.addWidget(txt('Organize, inspect and back up PS3, PS4 and PC saves.',12,True))
        header.addLayout(titles,1)
        self.home_search=QLineEdit();self.home_search.setPlaceholderText('Search games and saves…');self.home_search.setMinimumWidth(230)
        self.home_search.textChanged.connect(self.update_home)
        header.addWidget(self.home_search)
        self.platform_filter=QComboBox();self.platform_filter.addItems(['All Platforms','PS3','PC','PS4']);self.platform_filter.currentIndexChanged.connect(self.update_home)
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
        self.ps4_card,ps4_content=pane('PS4 SAVES')
        self.ps4_summary=txt('—',19)
        ps4_content.addWidget(self.ps4_summary)
        self.ps3_widgets.append(self.ps3_card)
        self.backup_card,self.backup_content=pane('BACKUP STATUS')
        self.ps3_summary=txt('—',19);self.pc_summary=txt('—',19);self.backup_summary=txt('—',16)
        self.ps3_content.addWidget(self.ps3_summary);self.pc_content.addWidget(self.pc_summary);self.backup_content.addWidget(self.backup_summary)
        info.addWidget(self.ps3_card);info.addWidget(self.ps4_card);info.addWidget(self.pc_card);info.addWidget(self.backup_card);vertical.addLayout(info)
        content=QHBoxLayout();content.setSpacing(12)
        left,left_layout=pane('GAME & SAVE LIBRARY')
        bar=QHBoxLayout();bar.addStretch()
        browse=QPushButton('Open full library');browse.clicked.connect(lambda:self.open_classic('games'));bar.addWidget(browse)
        organize=QPushButton('Organize');organize.clicked.connect(lambda:self.open_section('Game Library'));bar.addWidget(organize)
        left_layout.addLayout(bar)
        self.home_game_list=QListWidget();self.home_game_list.setObjectName('newList');self.home_game_list.setMinimumHeight(350)
        self.home_game_list.setIconSize(QSize(150, 76))
        self.home_game_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.home_game_list.customContextMenuRequested.connect(self.home_artwork_menu)
        self.home_game_list.itemActivated.connect(self.choose_game);self.home_game_list.itemClicked.connect(self.choose_game)
        left_layout.addWidget(self.home_game_list)
        content.addWidget(left,3)
        right_panel = QWidget()
        right=QVBoxLayout(right_panel);right.setContentsMargins(0,0,0,0);right.setSpacing(12)
        console,console_layout=pane('PS3 CONSOLE')
        console_layout.addWidget(txt('Connection status is not inferred automatically.',11,True))
        cb=QPushButton('Open PS3 connection tools');cb.clicked.connect(lambda:self.open_classic('ftp'));console_layout.addWidget(cb)
        right.addWidget(console)
        self.ps3_widgets.append(console)
        recent,recent_layout=pane('RECENT ARCHIVED SAVES')
        self.home_recent_list=QListWidget();self.home_recent_list.setObjectName('newList');self.home_recent_list.setMinimumHeight(140)
        self.home_recent_list.itemClicked.connect(self.choose_recent)
        recent_layout.addWidget(self.home_recent_list);right.addWidget(recent)
        actions,action_layout=pane('QUICK TOOLS')
        grid=QGridLayout();grid.setSpacing(7)
        quick=[('Import PS3',self.import_folder),('Import PC',self.import_pc),('Import PS4',self.import_ps4),('Backups',lambda:self.open_section('Saves & Backups')),
               ('Edit Save',self.editor_ui),('PS3 Transfer',lambda:self.open_classic('ftp')),('PS3 Tools',lambda:self.open_section('PS3 Tools'))]
        for i,(label,handler) in enumerate(quick):
            b=QPushButton(label);b.setObjectName('newAction');b.clicked.connect(handler);grid.addWidget(b,i//3,i%3)
            if 'PS3' in label:self.ps3_widgets.append(b)
        action_layout.addLayout(grid);right.addWidget(actions)
        content.addWidget(right_panel,2);vertical.addLayout(content)
        self.dashboard_cards = {
            'Overview statistics': hero, 'PS3 saves': self.ps3_card, 'PS4 saves': self.ps4_card,
            'PC saves': self.pc_card, 'Backup status': self.backup_card, 'Game and save library': left,
            'PS3 console': console, 'Recent archived saves': recent, 'Quick tools': actions,
        }
        self.dashboard_right = right_panel
        vertical.addStretch()

    def set_ps3_visibility(self, hidden):
        settings = self.ui_settings.load_settings()
        settings['hide_ps3_tools'] = hidden
        try:
            self.ui_settings.save_settings(settings)
        except OSError as exc:
            QMessageBox.warning(self, 'Could not save settings', str(exc))
            checkbox = self.sender()
            if isinstance(checkbox, QCheckBox):
                checkbox.blockSignals(True)
                checkbox.setChecked(self.hide_ps3)
                checkbox.blockSignals(False)
            return
        self.hide_ps3 = hidden
        self.apply_ps3_visibility()

    def apply_ps3_visibility(self):
        for name in ('PS3 Console', 'PS3 Tools'):
            self.navbuttons[name].setVisible(not self.hide_ps3)
        for widget in self.ps3_widgets:
            widget.setVisible(not self.hide_ps3)
        self.apply_dashboard_cards()

    def _set_nav(self,name):
        for key,b in self.navbuttons.items():b.setChecked(key==name)

    def open_home(self):
        self.shell_stack.setCurrentIndex(0);self._set_nav('Dashboard');self.update_home()

    def open_classic(self,which):
        if which == 'ftp' and self.hide_ps3:
            return
        self.shell_stack.setCurrentIndex(1)
        mapping={'games':('Game Library',self.show_games),'saves':('Saves & Backups',self.show_saves),
                 'settings':('Settings',self.show_settings),
                 'ftp':('PS3 Console',self.show_ftp)}
        if which in mapping:
            label,handler=mapping[which];self._set_nav(label);handler()
        elif which=='releases':
            self.open_section('Releases')

    def refresh(self, *args):
        super().refresh(*args)
        if hasattr(self, 'save_banner') and self.mode == 'saves':
            self.render_save_rows()
            self.update_save_header()
        if hasattr(self, 'home_recent_list') and self.shell_stack.currentIndex() == 0:
            self.update_home()

    def homebrew(self):
        from .ui_v24 import HomebrewCenter
        HomebrewCenter(self,root=self.archive.root).exec()

    def open_borderlands_editor(self):
        from .ui_borderlands_edit import BorderlandsWorkspace

        BorderlandsWorkspace(self.archive, self.ui_settings, self).exec()

    def open_game_lab(self):
        from .ui_game_lab import GameLabDialog
        GameLabDialog(self.archive.root, self).exec()

    def _make_section(self, section):
        """Build action panels from existing wired QAction objects (no detached tool copies)."""
        if section == 'Dump to FPKG Builder':
            return FpkgPanel(self.archive, self.ui_settings)
        page=QScrollArea();page.setWidgetResizable(True)
        body=QWidget();page.setWidget(body)
        outer=QVBoxLayout(body);outer.setContentsMargins(25,23,25,23);outer.setSpacing(14)
        captions={
            'Saves & Backups':'Restore, snapshot, compare and protect your archived saves.',
            'Save Editor':'Edit supported saves and inspect metadata safely.',
            'PS3 Tools':'Homebrew, existing PKGs, and ISO conversion.',
            'Releases':'GitHub publishing, release preparation and public catalogs.',
            'Settings':'Appearance, maintenance and advanced diagnostics.',
            'Game Library':'Optional organization tools; normal browsing stays in Game Library.',
        }
        outer.addWidget(txt(section,24));outer.addWidget(txt(captions[section],12,True))
        if section=='Saves & Backups':
            self.usb_status = QLabel()
            outer.addWidget(self.usb_status)
            row=QHBoxLayout()
            for label,fn in [('Browse Saves',lambda:self.open_classic('saves')),
                             ('Recently Removed',self.show_recently_removed),
                             ('Remember Save USB',self.choose_save_usb),
                             ('Import PS4 Save',self.import_ps4),('Import PC Save',self.import_pc)]:
                b=QPushButton(label);b.setObjectName('newAction');b.clicked.connect(fn);row.addWidget(b)
            outer.addLayout(row)
        elif section=='Save Editor':
            b=QPushButton('Open Universal Save Editor');b.setObjectName('newAction');b.clicked.connect(self.editor_ui);outer.addWidget(b)
            borderlands = QPushButton('Open Borderlands Save Editor')
            borderlands.setObjectName('newAction')
            borderlands.clicked.connect(self.open_borderlands_editor)
            outer.addWidget(borderlands)
            lab = QPushButton('Open Game Development Lab')
            lab.setObjectName('newAction')
            lab.clicked.connect(self.open_game_lab)
            outer.addWidget(lab)
        elif section=='PS3 Tools':
            row=QHBoxLayout()
            for label,fn in [('Homebrew Manager',self.homebrew),('Browse PS3 FTP',lambda:self.open_classic('ftp'))]:
                b=QPushButton(label);b.setObjectName('newAction');b.clicked.connect(fn);row.addWidget(b)
            outer.addLayout(row)
        elif section=='Game Library':
            b=QPushButton('Back to Game Library');b.clicked.connect(lambda:self.open_classic('games'));outer.addWidget(b)
        elif section=='Settings':
            hide_ps3 = QCheckBox('Hide PS3 tools and dashboard shortcuts')
            hide_ps3.setChecked(self.hide_ps3)
            hide_ps3.toggled.connect(self.set_ps3_visibility)
            outer.addWidget(hide_ps3)
            for label, callback in (
                ('Interface Text Size', self.choose_text_size),
                ('Keyboard Shortcuts', self.configure_shortcuts),
                ('Dashboard Cards', self.dashboard_preferences),
                ('Remember Save USB', self.choose_save_usb),
            ):
                button = QPushButton(label)
                button.clicked.connect(callback)
                outer.addWidget(button)
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
                if 'ps3' in name.casefold():self.ps3_widgets.append(btn)
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
        if section == 'PS3 Tools' and self.hide_ps3:
            return
        if section not in self.section_pages:
            self.section_pages[section]=self._make_section(section)
            self.shell_stack.addWidget(self.section_pages[section])
        self.shell_stack.setCurrentWidget(self.section_pages[section])
        self._set_nav(section if section in self.navbuttons else 'Game Library')

    def save_preference(self, key, value):
        settings = self.ui_settings.load_settings()
        settings[key] = value
        try:
            self.ui_settings.save_settings(settings)
        except (OSError, ValueError) as error:
            QMessageBox.warning(self, 'Could not save settings', str(error))
            return False
        return True

    def _commands(self):
        commands = super()._commands()
        commands.update({
            'Command palette': self.open_palette, 'Dashboard': self.open_home,
            'Game Library': lambda: self.open_classic('games'),
            'All Saves': lambda: self.open_classic('saves'),
            'Settings': lambda: self.open_section('Settings'),
            'Saves & Backups': lambda: self.open_section('Saves & Backups'),
            'Focus search': self.focus_visible_search, 'Import PS4 save': self.import_ps4,
            'Import PC save (alternate)': self.import_pc,
            'Create versioned backup': self.backup_version, 'Pin selected save': self.pin_current,
            'Jobs': self.jobs_ui, 'Recently Removed': self.show_recently_removed,
            'Dump to FPKG Builder': lambda: self.open_section('Dump to FPKG Builder'),
            'Keyboard shortcuts': self.configure_shortcuts, 'Interface text size': self.choose_text_size,
            'Remember save USB': self.choose_save_usb,
        })
        hidden = getattr(self, 'hide_ps3', False)
        for action in getattr(self, 'legacy_actions', ()):
            text = action.text().replace('&', '').strip()
            section = classify_action(text)
            if text and action.isEnabled() and not (hidden and section == 'PS3 Tools'):
                commands.setdefault(re.sub(r' \(Ctrl\+[^)]+\)$', '', text), action.trigger)
        if hidden:
            commands = {name: fn for name, fn in commands.items() if 'ps3' not in name.casefold()}
        return commands

    def open_palette(self):
        commands = self._commands()
        defaults = getattr(self, 'command_shortcuts', {})
        commands.pop('Command palette', None)
        commands.pop('Import PC save (alternate)', None)
        keys = {name: shortcut.key().toString() for name, shortcut in defaults.items()}
        CommandPalette(commands, self, shortcuts=keys).exec()

    def setup_shortcuts(self):
        for shortcut in self.findChildren(QShortcut):
            shortcut.setEnabled(False)
        self.command_shortcuts = {}
        keys = self.ui_settings.load_settings().get('keyboard_shortcuts', {})
        keys = keys if isinstance(keys, dict) else {}
        for name, default in SHORTCUT_DEFAULTS.items():
            shortcut = QShortcut(self)
            configured = keys.get(name, default)
            shortcut.setKey(QKeySequence.fromString(configured if isinstance(configured, str) else default,
                                                    QKeySequence.SequenceFormat.PortableText))
            shortcut.activated.connect(lambda command=name: self.run_command(command))
            self.command_shortcuts[name] = shortcut

    def run_command(self, name):
        command = self._commands().get(name)
        if command is not None:
            command()

    def focus_visible_search(self):
        if self.shell_stack.currentWidget() == self.home:
            self.home_search.setFocus()
        elif self.shell_stack.currentWidget() == self.classic_content:
            self.focus_search()
        else:
            self.fast_search()

    def configure_shortcuts(self):
        labels = {name: name for name in SHORTCUT_DEFAULTS}
        portable = QKeySequence.SequenceFormat.PortableText
        current = {name: shortcut.key().toString(portable) for name, shortcut in self.command_shortcuts.items()}
        keys = edit_shortcuts(self, labels, SHORTCUT_DEFAULTS, current)
        if keys is not None and self.save_preference('keyboard_shortcuts', keys):
            for name, key in keys.items():
                self.command_shortcuts[name].setKey(QKeySequence.fromString(key, portable))

    def apply_dashboard_cards(self):
        cards = self.ui_settings.load_settings().get('home_dashboard_cards', list(self.dashboard_cards))
        if not isinstance(cards, list):
            cards = list(self.dashboard_cards)
        for title, widget in self.dashboard_cards.items():
            widget.setVisible(title in cards and not (self.hide_ps3 and title.startswith('PS3')))
        self.dashboard_right.setVisible(any(not self.dashboard_cards[name].isHidden()
                                            for name in ('PS3 console', 'Recent archived saves', 'Quick tools')))

    def dashboard_preferences(self):
        if not hasattr(self, 'dashboard_cards'):
            return super().dashboard_preferences()
        dialog = QDialog(self)
        dialog.setWindowTitle('Dashboard Cards')
        layout = QVBoxLayout(dialog)
        selected = self.ui_settings.load_settings().get('home_dashboard_cards', list(self.dashboard_cards))
        if not isinstance(selected, list):
            selected = list(self.dashboard_cards)
        options = {}
        for title in self.dashboard_cards:
            checkbox = QCheckBox(title)
            checkbox.setChecked(title in selected)
            layout.addWidget(checkbox)
            options[title] = checkbox
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            cards = [title for title, checkbox in options.items() if checkbox.isChecked()]
            if self.save_preference('home_dashboard_cards', cards):
                self.apply_dashboard_cards()

    def set_text_size(self, percent):
        self.text_size.set_percent(percent)
        self.shell_sidebar.setFixedWidth(max(224, round(224 * percent / 100)))

    def choose_text_size(self):
        current = TEXT_SIZES.index(self.text_size.percent)
        value, accepted = QInputDialog.getItem(self, 'Interface Text Size', 'Scale',
                                               [f'{size}%' for size in TEXT_SIZES], current, False)
        if accepted:
            percent = int(value.rstrip('%'))
            if self.save_preference('text_size', percent):
                self.set_text_size(percent)

    def _apply_density(self):
        super()._apply_density()
        if hasattr(self, 'text_size'):
            self.text_size.apply_widget(self)

    def choose_theme(self):
        app = QApplication.instance()
        previous = app.styleSheet()
        super().choose_theme()
        if hasattr(self, 'text_size') and app.styleSheet() != previous:
            self.text_size.app_style = app.styleSheet() + DESIGN
            self.set_text_size(self.text_size.percent)

    def refresh_usb_status(self):
        preference = self.ui_settings.load_settings().get('save_usb', {})
        if not isinstance(preference, dict) or not preference.get('serial'):
            self.usb_status.setText('Save USB · No drive remembered')
            return
        drive = remembered_drive(preference, removable_drives())
        location = f'Connected at {drive.root}' if drive else 'Disconnected'
        self.usb_status.setText(f"Save USB · {preference.get('label') or 'Remembered drive'} · {location}")

    def choose_save_usb(self):
        drives = removable_drives()
        dialog = QDialog(self)
        dialog.setWindowTitle('Remember Save USB')
        layout = QVBoxLayout(dialog)
        layout.addWidget(QLabel('Save import dialogs open on the remembered drive when it is connected.'))
        options = QComboBox()
        for drive in drives:
            options.addItem(f'{drive.label} ({drive.root})', drive.serial)
        layout.addWidget(options)
        remembered = self.ui_settings.load_settings().get('save_usb', {})
        if isinstance(remembered, dict) and remembered:
            options.setCurrentIndex(max(0, options.findData(remembered.get('serial'))))
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel)
        buttons.rejected.connect(dialog.reject)
        remember = buttons.addButton('Remember selected drive', QDialogButtonBox.ButtonRole.AcceptRole)
        remember.setEnabled(bool(drives))
        forget = buttons.addButton('Forget remembered drive', QDialogButtonBox.ButtonRole.DestructiveRole)
        forget.setEnabled(bool(remembered))
        remember.clicked.connect(dialog.accept)
        forget.clicked.connect(lambda: dialog.done(2))
        if not drives:
            layout.addWidget(QLabel('No Windows removable drive is connected.'))
        layout.addWidget(buttons)
        result = dialog.exec()
        if result not in (QDialog.DialogCode.Accepted, 2):
            return
        drive = drives[options.currentIndex()] if result == QDialog.DialogCode.Accepted else None
        if self.save_preference('save_usb', {'serial': drive.serial, 'label': drive.label} if drive else {}):
            self.refresh_usb_status()

    def save_source_directory(self, platform):
        preference = self.ui_settings.load_settings().get('save_usb', {})
        drive = remembered_drive(preference, removable_drives()) if isinstance(preference, dict) and preference else None
        if drive is None:
            return super().save_source_directory(platform)
        folder = drive.root / platform / 'SAVEDATA'
        return str(folder if platform in ('PS3', 'PS4') and folder.is_dir() else drive.root)

    def install_save_controls(self):
        splitter = self.stack.widget(1)
        panel = QWidget(splitter)
        panel.setMinimumWidth(300)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        sort = QPushButton('Sort Saves…')
        sort.clicked.connect(self.sort_saves)
        layout.addWidget(sort, 0, Qt.AlignmentFlag.AlignLeft)
        layout.addWidget(self.save_list, 1)
        splitter.insertWidget(0, panel)
        self.save_list.show()
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)

        detail = self.detail_title.parentWidget().layout()
        self.save_banner = QLabel()
        self.save_banner.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.save_banner.setFixedHeight(151)
        self.save_banner.hide()
        detail.insertWidget(detail.indexOf(self.detail_title) + 1, self.save_banner)
        self.checkpoint_summary = QLabel()
        self.checkpoint_summary.setWordWrap(True)
        detail.insertWidget(detail.indexOf(self.detail_meta) + 1, self.checkpoint_summary)
        tools = QHBoxLayout()
        self.checkpoint_button = QPushButton('Set Checkpoint…')
        self.checkpoint_button.clicked.connect(self.edit_checkpoint)
        self.art_button = QPushButton('Choose Game Art…')
        self.art_button.clicked.connect(self.choose_save_art)
        tools.addWidget(self.checkpoint_button)
        tools.addWidget(self.art_button)
        detail.insertLayout(detail.indexOf(self.checkpoint_summary) + 1, tools)
        self.sav_number_button = QPushButton('Change .sav Number…')
        self.sav_number_button.clicked.connect(self.change_sav_number)
        detail.insertWidget(detail.indexOf(self.checkpoint_summary) + 2, self.sav_number_button)
        self.update_save_header()

    def sort_saves(self):
        choice = choose_sort(self, SAVE_SORT_FIELDS, self.save_sort)
        if choice is not None and self.save_preference('save_sort', choice):
            selected = set(self.selected_ids())
            current = self.current['id'] if self.current else None
            self.save_sort = choice
            self.refresh()
            for index in range(self.save_list.count()):
                item = self.save_list.item(index)
                record_id = item.data(Qt.ItemDataRole.UserRole)['id']
                item.setSelected(record_id in selected)
                if record_id == current:
                    self.select_save(item)

    def render_save_rows(self):
        rows = []
        while self.save_list.count():
            rows.append(self.save_list.takeItem(self.save_list.count()-1))
        rows.reverse()

        def key(item, field):
            value = item.data(Qt.ItemDataRole.UserRole).get(SAVE_SORT_FIELDS[field], '')
            return value.casefold() if isinstance(value, str) else value

        for item in sorted_by(rows, self.save_sort, key):
            row = item.data(Qt.ItemDataRole.UserRole)
            if row['checkpoint_label']:
                item.setText(item.text() + f"\n{row['checkpoint_kind']} · {row['checkpoint_label']}")
            self.save_list.addItem(item)

    def select_save(self, item):
        super().select_save(item)
        if hasattr(self, 'save_banner'):
            self.update_save_header()

    def update_save_header(self):
        save = self.current if self.mode == 'saves' else None
        self.save_banner.setVisible(bool(save))
        self.checkpoint_button.setEnabled(bool(save))
        self.art_button.setEnabled(bool(save))
        self.sav_number_button.setEnabled(bool(save))
        if save:
            size = QSize(324, 151)
            self.save_banner.setPixmap(self.artwork.icon(save['game'], save['platform'], size).pixmap(size))
            self.save_banner.setAccessibleName(f"Game art for {save['game']}")
        self.checkpoint_summary.setVisible(bool(save and save['checkpoint_label']))
        if save and save['checkpoint_label']:
            self.checkpoint_summary.setText(f"{save['checkpoint_kind']} · {save['checkpoint_label']}")

    def edit_checkpoint(self):
        save = self.current
        if not save:
            return
        dialog = QDialog(self)
        dialog.setWindowTitle('Checkpoint')
        layout = QFormLayout(dialog)
        kind = QComboBox()
        kind.addItems(CHECKPOINT_KINDS)
        kind.setCurrentText(save['checkpoint_kind'] or CHECKPOINT_KINDS[0])
        label = QLineEdit(save['checkpoint_label'])
        label.setMaxLength(100)
        label.setPlaceholderText('Leave blank to clear')
        layout.addRow('Type', kind)
        layout.addRow('Label', label)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addRow(buttons)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            try:
                self.archive.set_checkpoint(save['id'], kind.currentText(), label.text())
            except Exception as error:
                QMessageBox.warning(self, 'Could not save checkpoint', str(error))
                return
            self.refresh()
            for index in range(self.save_list.count()):
                item = self.save_list.item(index)
                if item.data(Qt.ItemDataRole.UserRole)['id'] == save['id']:
                    self.save_list.setCurrentItem(item)
                    self.select_save(item)
                    break

    def change_sav_number(self):
        save = self.current
        if not save:
            return
        try:
            candidates = self.archive.numbered_saves(save['id'])
        except (OSError, ValueError) as error:
            QMessageBox.warning(self, 'Could not open archived save', str(error))
            return
        if not candidates:
            QMessageBox.information(self, 'Change .sav Number',
                                    'This entry has no numbered .sav files to export.')
            return

        dialog = QDialog(self)
        dialog.setWindowTitle('Change .sav Number')
        form = QFormLayout(dialog)
        source = QComboBox()
        source.addItems([path.as_posix() for path in candidates])
        number = QLineEdit()
        number.setPlaceholderText('Example: 7')
        preview = QLabel()
        preview.setWordWrap(True)
        form.addRow('Archived file', source)
        form.addRow('New slot', number)
        form.addRow('Export filename', preview)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        export = buttons.button(QDialogButtonBox.StandardButton.Save)
        export.setText('Export copy…')
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        form.addRow(buttons)

        def update_preview():
            try:
                name = numbered_save_name(candidates[source.currentIndex()].name, number.text())
            except ValueError as error:
                preview.setText(str(error) if number.text().strip() else 'Enter a new slot number.')
                export.setEnabled(False)
            else:
                preview.setText(name)
                export.setEnabled(True)

        source.currentIndexChanged.connect(update_preview)
        number.textChanged.connect(update_preview)
        update_preview()
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        output = QFileDialog.getExistingDirectory(self, 'Choose a folder for the renamed copy')
        if not output:
            return
        try:
            target = self.archive.export_numbered_save(
                save['id'], candidates[source.currentIndex()], number.text(), output,
            )
        except FileExistsError:
            QMessageBox.warning(self, 'Filename already in use', 'Choose another slot number or output folder.')
        except (OSError, ValueError) as error:
            QMessageBox.warning(self, 'Could not export save', str(error))
        else:
            self.statusBar().showMessage(f'Exported {target}')
            QMessageBox.information(self, 'Renamed copy exported', str(target))

    def set_game_row_art(self, item, game):
        item.setIcon(self.artwork.icon(game['game'], game['platform'], self.home_game_list.iconSize()))

    def refresh_artwork(self):
        self.update_save_header()
        for index in range(self.home_game_list.count()):
            row = self.home_game_list.item(index)
            data = row.data(Qt.ItemDataRole.UserRole)
            if data:
                self.set_game_row_art(row, data)

    def choose_save_art(self):
        if self.current:
            self.choose_game_art(self.current)

    def home_artwork_menu(self, position):
        row = self.home_game_list.itemAt(position)
        if row is None or not row.data(Qt.ItemDataRole.UserRole):
            return
        menu = QMenu(self)
        menu.addAction('Choose Game Art…', lambda: self.choose_game_art(row.data(Qt.ItemDataRole.UserRole)))
        menu.exec(self.home_game_list.viewport().mapToGlobal(position))

    def choose_game_art(self, game):
        picker = ArtworkPicker(self.artwork, game['game'], game['platform'], self)
        result = picker.exec()
        chosen = picker.chosen
        picker.deleteLater()
        if result == QDialog.DialogCode.Accepted and chosen:
            try:
                self.artwork.assign(game['game'], game['platform'], chosen)
            except (OSError, ValueError) as error:
                QMessageBox.warning(self, 'Could not save game art', str(error))

    def choose_game(self, item):
        data = item.data(Qt.ItemDataRole.UserRole)
        if data:
            self.shell_stack.setCurrentIndex(1)
            self._set_nav('Saves & Backups')
            self.show_game_saves(data['game'], data['platform'], data['title_id'])

    def choose_recent(self, item):
        if item.data(Qt.ItemDataRole.UserRole):
            self.shell_stack.setCurrentIndex(1)
            self._set_nav('Saves & Backups')
            self.open_recent(item)

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
            nps4=sum(1 for r in all_saves if r.get('platform')=='PS4')
            self.ps4_summary.setText(f'{nps4:,} archived saves')
            self.backup_summary.setText(f"{stats.get('backups',0):,} recorded backups\nVerification not automated")
            platform=self.platform_filter.currentText();platform='All' if platform=='All Platforms' else platform
            query=self.home_search.text().strip()
            games=self.archive.games(query,platform)
            self.home_game_list.clear()
            for game in games[:100]:
                count = f"{game['saves']} archived {'save' if game['saves'] == 1 else 'saves'}"
                title_id = game['title_id']
                if title_id != game['platform']:
                    count += f'  ·  {title_id}'
                row=QListWidgetItem(f"{game['game']}   ·   {game['platform']}\n{count}")
                row.setData(Qt.ItemDataRole.UserRole,game)
                row.setSizeHint(QSize(0, 106))
                self.set_game_row_art(row, game)
                self.home_game_list.addItem(row)
            if not games:
                item=QListWidgetItem('No games match your search. Import saves to populate the library.')
                item.setFlags(Qt.ItemFlag.NoItemFlags);self.home_game_list.addItem(item)
            self.home_recent_list.clear()
            for save in all_saves[:6]:
                item=QListWidgetItem(f"{save['game']}  ·  {save['platform']}\n{save['label']}")
                if save['checkpoint_label']:
                    item.setText(item.text() + f" · {save['checkpoint_label']}")
                item.setData(Qt.ItemDataRole.UserRole,save);self.home_recent_list.addItem(item)
            if not all_saves:self.home_recent_list.addItem('No archived saves yet')
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
