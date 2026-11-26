"""Borderlands 3 game-specific editing workspace.

The universal launcher still requires an explicit game and console choice.
Character and profile are independently loaded; their tabs remain disabled
(grey) until a matching file has been validated by the platform-specific codec.
Before saving changes, verify an independent backup and then atomically replace
only the selected source file. Never save one kind as the other.
"""
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox, QDialog, QVBoxLayout, QFormLayout, QHBoxLayout, QLabel, QLineEdit,
    QSpinBox, QPushButton, QFileDialog, QMessageBox, QPlainTextEdit,
    QTabWidget, QWidget, QGroupBox, QGridLayout, QFrame, QSplitter,
    QListWidget, QListWidgetItem, QStackedWidget,
)

from .bl3_native import (
    load_character, load_profile,
)
from .universal_editor_profiles import PROFILES, validate_profile
from .game_editor_layouts import section_enabled, layout_for
from .ui_bl3_drop_zone import SaveDropZone
from .bl3_inplace import save_with_backup
from .ui_bl3_advanced import BL3AdvancedDialog
from .ui_bl3_workshop import WeaponWorkshop


def available_sections(game, platform, loaded_kinds):
    """Pure capability logic shared by the UI and regression tests."""
    return {
        kind: section_enabled(game, platform, kind, loaded_kinds, PROFILES)
        for kind in ('character', 'profile')
    }


class BL3NativeDialog(QDialog):
    def __init__(self, working, parent=None, *, embedded=False):
        super().__init__(parent)
        self.embedded = bool(embedded)
        if self.embedded:
            self.setWindowFlags(Qt.WindowType.Widget)
        self.working = Path(working).resolve()
        self.loaded = {}
        self.setWindowTitle('Universal Save Editor | Borderlands 3')
        self.resize(1250, 810)
        self.setMinimumSize(900, 620)
        self.setStyleSheet('''
            QDialog { background: #14121c; color: #e8e4f6; }
            QLabel { color: #ddd8ef; }
            QGroupBox {
                border: 1px solid #423657; border-radius: 10px;
                margin-top: 12px; padding: 12px; font-weight: 600;
            }
            QGroupBox::title { subcontrol-origin: margin; left: 12px; }
            QComboBox, QLineEdit, QSpinBox, QPlainTextEdit {
                background: #211b2c; color: #f1ecff;
                border: 1px solid #53456b; border-radius: 7px; padding: 6px;
            }
            QPushButton {
                background: #493166; color: #f5f0ff;
                border: 1px solid #725593; border-radius: 7px;
                padding: 8px 11px;
            }
            QPushButton:hover:enabled { background: #624185; }
            QPushButton:disabled { color: #77727f; background: #26232d;
                border-color: #393540; }
            QFrame#bl3FileCard { background:#241d30; border:1px solid #624579;
                border-radius:10px; }
            QListWidget#bl3Nav { background:#1b1625; color:#e3d5f0;
                border:1px solid #57416c; border-radius:10px;
                font-size:13px; padding:7px; }
            QListWidget#bl3Nav::item { padding:12px 10px; border-radius:7px; }
            QListWidget#bl3Nav::item:selected { background:#65408c;
                color:#ffffff; border-left:3px solid #ffd126; }
            QListWidget#bl3Nav::item:disabled { color:#736b7f; }
            QPushButton#bl3SaveMain { background:#ffd229; color:#19101c;
                border:1px solid #ffe47a; border-radius:10px;
                font-weight:850; padding:13px 22px; font-size:15px; }
            QPushButton#bl3SaveMain:hover:enabled { background:#ffe475; }
            QPushButton#bl3SaveMain:disabled { background:#49404a; color:#8e8790;
                border-color:#5b5260; }
            QTabWidget::pane { border: 1px solid #514364; border-radius: 8px; }
            QTabBar::tab { background: #272235; color: #ded5f0; padding: 11px 18px;
                border: 1px solid #4b3f5e; border-radius: 6px; margin-right: 4px; }
            QTabBar::tab:selected { background: #5e3b83; color: #ffffff; }
            QTabBar::tab:disabled { background: #25232b; color: #77737e;
                border: 1px solid #36313d; }
        ''')
        # Compact fixed header and save cards leave room for the actual editor.
        root = QVBoxLayout(self)
        root.setContentsMargins(10, 8, 10, 8)
        root.setSpacing(8)
        header = QHBoxLayout()
        root.addLayout(header)
        heading = QLabel('BORDERLANDS 3  /  SAVE EDITOR')
        heading.setStyleSheet('font-size:20px; font-weight:800; color:#f8d02a;')
        header.addWidget(heading, 1)

        self.game = QComboBox()
        self.game.addItem('Select game…', None)
        for game in dict.fromkeys(p.game for p in PROFILES):
            self.game.addItem(game, game)
            if layout_for(game) is None:
                self.game.model().item(self.game.count()-1).setEnabled(False)
        self.game_label = QLabel('Game')
        header.addWidget(self.game_label)
        header.addWidget(self.game)
        self.game_label.setVisible(not self.embedded)
        self.game.setVisible(not self.embedded)
        header.addWidget(QLabel('Console'))
        self.console = QComboBox()
        self.console.setMinimumWidth(135)
        header.addWidget(self.console)
        self.game.currentIndexChanged.connect(self.game_changed)
        self.console.currentIndexChanged.connect(self.console_changed)

        files = QHBoxLayout()
        files.setSpacing(10)
        root.addLayout(files)
        self.source_labels = {}
        self.load_buttons = {}
        self.clear_buttons = {}
        self.drop_zones = {}
        self.file_cards = {}
        for kind, label in (('character', 'CHARACTER SAVE'), ('profile', 'PROFILE DATA')):
            card = QFrame(self)
            card.setObjectName('bl3FileCard')
            self.file_cards[kind] = card
            file_layout = QVBoxLayout(card)
            file_layout.setContentsMargins(10, 8, 10, 8)
            file_layout.setSpacing(5)
            top = QHBoxLayout()
            top.addWidget(QLabel(label))
            field = QLineEdit()
            field.setReadOnly(True)
            field.setPlaceholderText('Not loaded')
            self.source_labels[kind] = field
            top.addWidget(field, 1)
            load = QPushButton('Load…')
            load.clicked.connect(lambda checked=False, k=kind: self.choose_file(k))
            self.load_buttons[kind] = load
            top.addWidget(load)
            clear = QPushButton('Unload')
            clear.clicked.connect(lambda checked=False, k=kind: self.unload(k))
            self.clear_buttons[kind] = clear
            top.addWidget(clear)
            file_layout.addLayout(top)
            drop = SaveDropZone(kind)
            drop.setMinimumHeight(36)
            drop.setMaximumHeight(42)
            drop.setText('Drop ' + kind + ' save here')
            drop.fileDropped.connect(lambda path, k=kind: self.import_dropped(path, k))
            self.drop_zones[kind] = drop
            file_layout.addWidget(drop)
            files.addWidget(card, 1)

        self.workspace_split = QSplitter(Qt.Orientation.Horizontal)
        self.workspace_split.setChildrenCollapsible(False)
        root.addWidget(self.workspace_split, 1)
        self.navigation = QListWidget(self)
        self.navigation.setObjectName('bl3Nav')
        self.navigation.setMinimumWidth(175)
        self.navigation.setMaximumWidth(235)
        self.workspace_split.addWidget(self.navigation)
        content = QWidget(self)
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(4)
        self.tabs = QTabWidget()
        self.tabs.tabBar().hide()
        content_layout.addWidget(self.tabs, 1)
        self.empty_hint = QLabel(
            'Select PC or PS4, then drag in a character save and/or profile file. '
            'The corresponding editing pages unlock after successful validation.'
        )
        self.empty_hint.setWordWrap(True)
        self.empty_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_hint.setStyleSheet(
            'background:#211b2c; border:1px dashed #53456b; '
            'border-radius:9px; color:#c0b6d1; padding:28px;'
        )
        content_layout.addWidget(self.empty_hint, 1)
        self.workspace_split.addWidget(content)
        self.workspace_split.setStretchFactor(1, 1)
        self.workspace_split.setSizes([210, 880])

        self.character_tab = QWidget()
        self.profile_tab = QWidget()
        self.character_tab_index = self.tabs.addTab(self.character_tab, 'Character Overview')
        self.profile_tab_index = self.tabs.addTab(self.profile_tab, 'Profile Overview')
        self._create_character_design()
        self._create_profile_design()
        self._create_extra_tabs()
        self.workshop = WeaponWorkshop(self.tabs)
        self.workshop_index = self.tabs.addTab(self.workshop, 'Weapon Workshop')
        self.workshop.saveCompleted.connect(
            lambda output: self.open_save(Path(output), 'character')
        )
        self.page_kinds = {
            self.character_tab_index: 'character',
            self.profile_tab_index: 'profile',
            self.workshop_index: 'character',
        }
        for index, kind, view in self.extra_tabs.values():
            self.page_kinds[index] = kind
        self.navigation.addItem('CHARACTER')
        for index in (self.character_tab_index,
                      next(x[0] for name,x in self.extra_tabs.items() if name=='Inventory & Weapons'),
                      self.workshop_index,
                      next(x[0] for name,x in self.extra_tabs.items() if name=='Skills & Progression')):
            item = QListWidgetItem(self.tabs.tabText(index))
            item.setData(Qt.ItemDataRole.UserRole, index)
            self.navigation.addItem(item)
        self.navigation.addItem('PROFILE')
        for index in (self.profile_tab_index,
                      next(x[0] for name,x in self.extra_tabs.items() if name=='Guardian & Vault'),
                      next(x[0] for name,x in self.extra_tabs.items() if name=='Cosmetics & Bank')):
            item = QListWidgetItem(self.tabs.tabText(index))
            item.setData(Qt.ItemDataRole.UserRole, index)
            self.navigation.addItem(item)
        self.navigation.currentItemChanged.connect(self._navigate)
        self.tabs.currentChanged.connect(self._sync_nav)

        self.status = QPlainTextEdit()
        self.status.setReadOnly(True)
        self.status.setMaximumHeight(44)
        root.addWidget(self.status)
        actions = QHBoxLayout()
        self.pending_label = QLabel('Loaded saves: 0')
        actions.addWidget(self.pending_label, 1)
        self.export_character_button = QPushButton('Save + Backup')
        self.export_character_button.setObjectName('bl3SaveMain')
        self.export_character_button.clicked.connect(self.save_character_page)
        actions.addWidget(self.export_character_button)
        self.export_profile_button = QPushButton('Save Profile + Backup')
        self.export_profile_button.clicked.connect(lambda: self.write_copy('profile'))
        actions.addWidget(self.export_profile_button)
        if not self.embedded:
            close = QPushButton('Close')
            close.clicked.connect(self.reject)
            actions.addWidget(close)
        root.addLayout(actions)
        self.game_changed()

    def _navigate(self, current, previous=None):
        if current is None:
            return
        index = current.data(Qt.ItemDataRole.UserRole)
        if type(index) is int and self.tabs.isTabEnabled(index):
            self.tabs.setCurrentIndex(index)

    def _sync_nav(self, index):
        for row in range(self.navigation.count()):
            item = self.navigation.item(row)
            if item.data(Qt.ItemDataRole.UserRole) == index and bool(item.flags() & Qt.ItemFlag.ItemIsEnabled):
                self.navigation.blockSignals(True)
                self.navigation.setCurrentRow(row)
                self.navigation.blockSignals(False)
                break

    def save_character_page(self):
        page = self.tabs.currentIndex()
        if self.page_kinds.get(page) == 'profile':
            self.write_copy('profile')
        elif page == self.workshop_index and self.workshop.queue:
            self.workshop.save_pending()
        elif 'character' in self.loaded:
            self.write_copy('character')
        elif 'profile' in self.loaded:
            self.write_copy('profile')

    def set_target(self, game, platform=None):
        """Select the game without locking the console dropdown.

        The main universal selector owns game selection; each game's custom
        editor independently selects an available console. Switching either
        value unloads character/profile files and locks their tabs.
        """
        game_index = self.game.findData(game)
        if game_index < 0:
            raise ValueError('No custom editor layout is installed for this game.')
        self.game.setCurrentIndex(game_index)
        console_index = self.console.findData(platform) if platform else 0
        self.console.setCurrentIndex(max(0, console_index))
        self.console_changed()
        self.game.setEnabled(not self.embedded)
        self.console.setEnabled(True)

    def _spin(self, low=0, high=2_000_000_000):
        box = QSpinBox()
        box.setRange(low, high)
        return box

    def _info(self, text):
        label = QLabel(text)
        label.setWordWrap(True)
        label.setStyleSheet('color: #ada4bd;')
        return label

    def _create_character_design(self):
        """Large overview with a side portrait placeholder and editable stat cards."""
        outer = QVBoxLayout(self.character_tab)
        outer.setContentsMargins(10, 10, 10, 10)
        outer.setSpacing(10)
        heading = QLabel('CHARACTER OVERVIEW')
        heading.setStyleSheet('font-size:22px; font-weight:800; color:#f2e8ff;')
        outer.addWidget(heading)
        area = QHBoxLayout()
        area.setSpacing(14)
        outer.addLayout(area, 1)

        portrait = QFrame()
        portrait.setObjectName('bl3Portrait')
        portrait.setMinimumWidth(190)
        portrait.setMaximumWidth(320)
        portrait.setStyleSheet(
            'QFrame#bl3Portrait {background:#352342; border:1px solid #845ba4;'
            'border-radius:14px;}'
        )
        pl = QVBoxLayout(portrait)
        pl.setContentsMargins(14, 24, 14, 18)
        pl.addStretch()
        portrait_title = QLabel('VAULT HUNTER')
        portrait_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        portrait_title.setStyleSheet('font-size:23px; color:#f8d22b; font-weight:800;')
        pl.addWidget(portrait_title)
        self.class_portrait = QLabel('CHARACTER PREVIEW')
        self.class_portrait.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.class_portrait.setWordWrap(True)
        self.class_portrait.setStyleSheet('font-size:15px; color:#e4d1fa;')
        pl.addWidget(self.class_portrait)
        self.character_info = QLabel('Load a character save to view stats.')
        self.character_info.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.character_info.setWordWrap(True)
        pl.addWidget(self.character_info)
        pl.addStretch()
        area.addWidget(portrait, 1)

        right = QVBoxLayout()
        right.setSpacing(11)
        area.addLayout(right, 3)
        hero = QFrame()
        hero.setStyleSheet('background:#2c2038; border:1px solid #795397; border-radius:12px;')
        hero_layout = QVBoxLayout(hero)
        self.hero_character = QLabel('NO CHARACTER LOADED')
        self.hero_character.setStyleSheet(
            'font-size:26px; font-weight:750; color:#ffffff; border:0;'
        )
        hero_layout.addWidget(self.hero_character)
        self.hero_subtitle = QLabel('Select PC or PS4 and load a matching character file')
        self.hero_subtitle.setStyleSheet('color:#c2add8; border:0;')
        hero_layout.addWidget(self.hero_subtitle)
        right.addWidget(hero)

        stats = QFrame()
        stats.setStyleSheet('background:#241b30; border:1px solid #674b83; border-radius:12px;')
        stats_layout = QFormLayout(stats)
        stats_layout.setContentsMargins(15, 15, 15, 15)
        stats_layout.setSpacing(12)
        self.character = QLineEdit()
        self.character.setMaxLength(40)
        stats_layout.addRow('Character Name', self.character)
        self.level = self._spin(1, 80)
        stats_layout.addRow('Level', self.level)
        self.money = self._spin()
        stats_layout.addRow('Money', self.money)
        self.eridium = self._spin()
        stats_layout.addRow('Eridium', self.eridium)
        right.addWidget(stats)

        panel = QFrame()
        panel.setStyleSheet('background:#241b30; border:1px solid #674b83; border-radius:12px;')
        pane_layout = QVBoxLayout(panel)
        pane_layout.addWidget(QLabel('INVENTORY / QUICK ACTIONS'))
        self.inventory_info = self._info('Load a character to inspect inventory.')
        pane_layout.addWidget(self.inventory_info)
        action_row = QHBoxLayout()
        open_weapons = QPushButton('Weapon Workshop')
        open_weapons.clicked.connect(
            lambda: self.tabs.setCurrentIndex(self.workshop_index))
        action_row.addWidget(open_weapons)
        open_skills = QPushButton('Skills & Progression')
        open_skills.clicked.connect(
            lambda: self.tabs.setCurrentIndex(
                self.extra_tabs['Skills & Progression'][0]))
        action_row.addWidget(open_skills)
        pane_layout.addLayout(action_row)
        right.addWidget(panel)
        right.addStretch(1)

    def _create_profile_design(self):
        root = QVBoxLayout(self.profile_tab)
        self.profile_info = self._info('Load a compatible profile file to unlock profile editing.')
        root.addWidget(self.profile_info)
        keys = QGroupBox('PROFILE / SHARED KEYS')
        form = QFormLayout(keys)
        self.golden_keys = self._spin()
        form.addRow('Golden Keys', self.golden_keys)
        self.diamond_keys = self._spin()
        form.addRow('Diamond Keys', self.diamond_keys)
        root.addWidget(keys)
        bank = QGroupBox('PROFILE / BANK')
        bank_layout = QVBoxLayout(bank)
        self.bank_info = self._info(
            'Bank item count is available. Bank item modifications are planned.'
        )
        bank_layout.addWidget(self.bank_info)
        root.addWidget(bank)
        root.addStretch(1)

    def _create_extra_tabs(self):
        """BL3-specific read-only pages with independent source prerequisites."""
        self.extra_tabs = {}
        specs = (
            ('Inventory & Weapons', 'character', 'INVENTORY / WEAPONS',
             'Open Advanced to search, duplicate, import/replace BL3 codes, and edit item level or Mayhem. Direct part editing is not available.'),
            ('Skills & Progression', 'character', 'SKILLS / MISSIONS / MAYHEM / SDUs',
             'View progress below, or open Advanced for Mayhem, known SDUs and skill-tree unlock. Individual skill points remain read-only.'),
            ('Guardian & Vault', 'profile', 'GUARDIAN / VAULT CARDS',
             'View totals below, or open Advanced for Guardian tokens, Vault Card keys and unopened chests.'),
            ('Cosmetics & Bank', 'profile', 'COSMETICS / SHARED BANK',
             'View totals below, or open Advanced to unlock supported cosmetic groups and import compatible bank items.'),
        )
        for title, kind, header, note in specs:
            page = QWidget()
            layout = QVBoxLayout(page)
            group = QGroupBox(header)
            content = QVBoxLayout(group)
            content.addWidget(self._info(note))
            view = QPlainTextEdit()
            view.setReadOnly(True)
            view.setPlainText('Load the matching save file to view decoded data.')
            content.addWidget(view)
            edit = QPushButton('Open advanced ' + title + ' editor…')
            edit.clicked.connect(lambda checked=False, k=kind: self.open_advanced(k))
            layout.addWidget(group)
            layout.addWidget(edit)
            layout.addStretch()
            index = self.tabs.addTab(page, title)
            self.extra_tabs[title] = (index, kind, view)

    def _update_previews(self):
        for title, (index, kind, view) in self.extra_tabs.items():
            details = self.loaded.get(kind)
            if details is None:
                view.setPlainText('This tab is locked until its file is loaded.')
                continue
            preview = details.get('preview', {})
            if title == 'Inventory & Weapons':
                fields = {'Inventory entries': details['inventory_count']}
            elif title == 'Skills & Progression':
                fields = {key.replace('_', ' ').title(): preview.get(key)
                          for key in ('mayhem_levels', 'completed_missions',
                                      'guardian_rank', 'sdus')}
            elif title == 'Guardian & Vault':
                fields = {key.replace('_', ' ').title(): preview.get(key)
                          for key in ('guardian_rank', 'guardian_tokens',
                                      'vault_card_1_keys', 'vault_card_2_keys',
                                      'vault_card_3_keys')}
            else:
                fields = {
                    'Bank entries': details['bank_count'],
                    'Heads unlocked': preview.get('heads_unlocked'),
                    'Skins unlocked': preview.get('skins_unlocked'),
                    'SDUs': preview.get('sdus'),
                }
            view.setPlainText('\\n'.join(
                f'{key}: {value if value is not None else "Unavailable"}'
                for key, value in fields.items()
            ))

    def open_advanced(self, kind):
        """Open a game-specific module without unlocking unrelated save tabs."""
        details = self.loaded.get(kind)
        if details is None or not available_sections(
                self.game.currentData(), self.console.currentData(), self.loaded)[kind]:
            self.status.setPlainText('Load the corresponding game data file first.')
            return
        dialog = BL3AdvancedDialog(details, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.open_save(Path(details['path']), kind)

    def _selected_profile(self, kind):
        game, platform = self.game.currentData(), self.console.currentData()
        key = next((p.key for p in PROFILES if p.game == game and
                    p.platform == platform and p.file_type.casefold() == kind), None)
        if key is None:
            return None
        try:
            return validate_profile(key)
        except ValueError:
            return None

    def game_changed(self, *_):
        self.console.blockSignals(True)
        self.console.clear()
        self.console.addItem('Select console…', None)
        for platform in dict.fromkeys(
                p.platform for p in PROFILES if p.game == self.game.currentData()):
            supported = any(
                p.editable for p in PROFILES
                if p.game == self.game.currentData() and p.platform == platform
            )
            self.console.addItem(
                platform if supported else platform + ' (planned)', platform
            )
            if not supported:
                self.console.model().item(self.console.count() - 1).setEnabled(False)
        self.console.blockSignals(False)
        self.console_changed()

    def console_changed(self, *_):
        self.loaded.clear()
        self.workshop.clear()
        self.refresh_state()

    def refresh_state(self):
        states = available_sections(
            self.game.currentData(), self.console.currentData(), self.loaded)
        self.tabs.setTabEnabled(self.character_tab_index, states['character'])
        self.tabs.setTabEnabled(self.profile_tab_index, states['profile'])
        for index, kind, view in self.extra_tabs.values():
            self.tabs.setTabEnabled(index, states[kind])
        self.tabs.setTabEnabled(self.workshop_index, states['character'])
        self._update_previews()
        for row in range(self.navigation.count()):
            item = self.navigation.item(row)
            index = item.data(Qt.ItemDataRole.UserRole)
            enabled = type(index) is int and self.tabs.isTabEnabled(index)
            flags = item.flags()
            item.setFlags(
                (flags | Qt.ItemFlag.ItemIsEnabled) if enabled
                else (flags & ~Qt.ItemFlag.ItemIsEnabled)
            )
        self.pending_label.setText(
            f"Loaded saves: {len(self.loaded)}  •  "
            f"Queued weapon edits: {len(self.workshop.queue)}"
        )
        self.export_profile_button.hide()
        for kind, index in (('character', self.character_tab_index),
                            ('profile', self.profile_tab_index)):
            loaded = self.loaded.get(kind)
            if loaded is None:
                self.source_labels[kind].clear()
            else:
                self.source_labels[kind].setText(loaded['path'])
            self.clear_buttons[kind].setEnabled(loaded is not None)
            self.file_cards[kind].setProperty('loaded', loaded is not None)
            supported = self._selected_profile(kind) is not None
            self.load_buttons[kind].setEnabled(supported)
            self.drop_zones[kind].setEnabled(supported)
        any_loaded=states['character'] or states['profile']
        self.tabs.setVisible(any_loaded)
        self.empty_hint.setVisible(not any_loaded)
        self.export_character_button.setEnabled(any_loaded)
        self.export_profile_button.setEnabled(states['profile'])
        for kind, widgets in (
            ('character', (self.character, self.level, self.money, self.eridium)),
            ('profile', (self.golden_keys, self.diamond_keys)),
        ):
            for widget in widgets:
                widget.setEnabled(states[kind])
        if any_loaded and not self.tabs.isTabEnabled(self.tabs.currentIndex()):
            if states['character']:
                self.tabs.setCurrentIndex(self.character_tab_index)
            elif states['profile']:
                self.tabs.setCurrentIndex(self.profile_tab_index)
        elif not any_loaded:
            self.status.setPlainText(
                'Choose a supported console and load a save or profile. '
                'Matching editing pages unlock after validation.'
            )
        self._sync_nav(self.tabs.currentIndex())
        self.character_info.setText(
            'Character save loaded — editing enabled.' if states['character']
            else 'Character save missing: tab locked.')
        self.profile_info.setText(
            'Profile data loaded — editing enabled.' if states['profile']
            else 'Profile file missing: tab locked.')

    def import_dropped(self, path, kind):
        """A dropped external source is edited directly only after backup."""
        self.open_save(Path(path), kind)

    def choose_file(self, kind):
        try:
            profile = self._selected_profile(kind)
        except ValueError as exc:
            self.status.setPlainText(str(exc))
            return
        if profile is None:
            return
        name, _ = QFileDialog.getOpenFileName(
            self, 'Load ' + kind + ' save (backup created before editing)',
            str(self.working), 'All files (*)')
        if name:
            self.open_save(Path(name), kind)

    def open_save(self, path, kind):
        """Load only the requested kind, preserving the other independent file."""
        self.loaded.pop(kind, None)
        self.refresh_state()
        try:
            profile = self._selected_profile(kind)
            if profile is None:
                raise ValueError('Choose a supported game and console first.')
            resolved = path.resolve(strict=True)
            if path.is_symlink() or not resolved.is_file():
                raise ValueError('Choose a regular save file, not a link or folder.')
            details = (load_character(resolved, profile.platform) if kind == 'character'
                       else load_profile(resolved, profile.platform))
            if details['kind'] != kind or details['platform'] != profile.platform:
                raise ValueError('Save kind or platform does not match the selected profile.')
        except (OSError, ValueError, RuntimeError) as exc:
            self.status.setPlainText('Cannot load ' + kind + ': ' + str(exc))
            return False

        self.loaded[kind] = details
        if kind == 'character':
            self.workshop.load_character(details)
            self.hero_character.setText(
                f"{details['character']}  /  {details['class']}"
            )
            self.hero_subtitle.setText(
                f"Level {details['level']}  •  {details['platform']}"
            )
            self.class_portrait.setText(details['class'])
            self.character.setText(details['character'])
            self.level.setValue(details['level'])
            self.money.setValue(details['money'])
            self.eridium.setValue(details['eridium'])
            self.inventory_info.setText(
                f"Inventory: {details['inventory_count']} items · "
                f"Class: {details['class']} · XP: {details['xp']}"
            )
        else:
            self.golden_keys.setValue(details['golden_keys'])
            self.diamond_keys.setValue(details['diamond_keys'])
            self.bank_info.setText(f"Bank inventory: {details['bank_count']} items")
        self.refresh_state()
        self.tabs.setCurrentIndex(
            self.character_tab_index if kind == 'character' else self.profile_tab_index)
        self.status.setPlainText(
            f"{kind.title()} loaded ({details['platform']}). "
            'Other tabs remain locked until their files are loaded independently.'
        )
        return True

    def unload(self, kind):
        self.loaded.pop(kind, None)
        if kind == 'character':
            self.workshop.clear()
            self.hero_character.setText('NO CHARACTER LOADED')
            self.hero_subtitle.setText('Load a character save to begin editing.')
            self.class_portrait.setText('CHARACTER PREVIEW')
        self.refresh_state()

    def write_copy(self, kind):
        details = self.loaded.get(kind)
        if details is None or not available_sections(
                self.game.currentData(), self.console.currentData(), self.loaded)[kind]:
            return
        source = Path(details['path'])
        confirmation = QMessageBox.question(
            self, 'Save and back up original',
            f'This will modify the selected {kind} file in place:\n{source}\n\n'
            'An independent verified copy will be created first in '
            'ZSaveArchive_Backups beside the file. Continue?',
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        if confirmation != QMessageBox.StandardButton.Yes:
            return
        try:
            values = (
                {'name': self.character.text(), 'level': self.level.value(),
                 'money': self.money.value(), 'eridium': self.eridium.value()}
                if kind == 'character' else
                {'golden_keys': self.golden_keys.value(),
                 'diamond_keys': self.diamond_keys.value()}
            )
            written, backup = save_with_backup(
                source, kind=kind, platform=details['platform'],
                expected_sha256=details['sha256'], **values)
        except (OSError, ValueError, RuntimeError) as exc:
            QMessageBox.warning(self, 'Save failed; review backup', str(exc))
            return
        # Reload from disk to refresh the expected SHA and all displayed values.
        self.open_save(written, kind)
        self.status.setPlainText(
            f'Updated {kind} source: {written}\nVerified backup: {backup}')
        QMessageBox.information(
            self, 'Save updated and backed up',
            f'Source edited: {written}\nBackup: {backup}\n'
            'For PS4, Apollo must still restore the edited export '
            'to the console save container.'
        )
