"""Borderlands 3 game-specific editing workspace.

The universal launcher still requires an explicit game and console choice.
Character and profile are independently loaded; their tabs remain disabled
(grey) until a matching file has been validated by the platform-specific codec.
Never save one file as the other, and never silently overwrite an existing file.
"""
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox, QDialog, QVBoxLayout, QFormLayout, QHBoxLayout, QLabel, QLineEdit,
    QSpinBox, QPushButton, QFileDialog, QMessageBox, QPlainTextEdit,
    QTabWidget, QWidget, QGroupBox, QGridLayout,
)

from .bl3_native import (
    load_character, load_profile, write_character_copy, write_profile_copy,
)
from .universal_editor_profiles import PROFILES, validate_profile


def available_sections(game, platform, loaded_kinds):
    """Pure capability logic shared by the UI and regression tests."""
    if not game or not platform:
        return {'character': False, 'profile': False}
    return {
        kind: (kind in loaded_kinds and any(
            p.game == game and p.platform == platform and
            p.file_type.casefold() == kind and p.editable for p in PROFILES))
        for kind in ('character', 'profile')
    }


class BL3NativeDialog(QDialog):
    def __init__(self, working, parent=None):
        super().__init__(parent)
        self.working = Path(working).resolve()
        self.loaded = {}
        self.setWindowTitle('Universal Save Editor | Borderlands 3')
        self.resize(940, 650)
        self.setMinimumSize(760, 540)
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
            QTabWidget::pane { border: 1px solid #514364; border-radius: 8px; }
            QTabBar::tab { background: #272235; color: #ded5f0; padding: 11px 18px;
                border: 1px solid #4b3f5e; border-radius: 6px; margin-right: 4px; }
            QTabBar::tab:selected { background: #5e3b83; color: #ffffff; }
            QTabBar::tab:disabled { background: #25232b; color: #77737e;
                border: 1px solid #36313d; }
        ''')
        root = QVBoxLayout(self)
        heading = QLabel('BORDERLANDS 3  /  SAVE ENGINEERING')
        heading.setStyleSheet('font-size: 21px; font-weight: 700; color: #c8a7ff;')
        root.addWidget(heading)
        desc = QLabel(
            'Select a game and console first. Import character and profile files '
            'independently. Missing data tabs remain gray and locked.'
        )
        desc.setWordWrap(True)
        root.addWidget(desc)
        picker = QHBoxLayout()
        root.addLayout(picker)
        self.game = QComboBox()
        self.game.addItem('Select game…', None)
        for game in dict.fromkeys(p.game for p in PROFILES):
            self.game.addItem(game, game)
        picker.addWidget(QLabel('Game'))
        picker.addWidget(self.game, 2)
        self.console = QComboBox()
        picker.addWidget(QLabel('Console'))
        picker.addWidget(self.console, 1)
        self.game.currentIndexChanged.connect(self.game_changed)
        self.console.currentIndexChanged.connect(self.console_changed)

        self.file_row = QGridLayout()
        root.addLayout(self.file_row)
        self.source_labels = {}
        self.load_buttons = {}
        self.clear_buttons = {}
        for index, kind in enumerate(('character', 'profile')):
            label = QLabel('CHARACTER SAVE' if kind == 'character' else 'PROFILE DATA')
            label.setStyleSheet('color: #c9b6e6; font-weight: 600;')
            self.file_row.addWidget(label, index, 0)
            field = QLineEdit()
            field.setReadOnly(True)
            field.setPlaceholderText('Not loaded — this section is locked')
            self.source_labels[kind] = field
            self.file_row.addWidget(field, index, 1)
            load = QPushButton('Load ' + ('save…' if kind == 'character' else 'profile…'))
            load.clicked.connect(lambda checked=False, k=kind: self.choose_file(k))
            self.load_buttons[kind] = load
            self.file_row.addWidget(load, index, 2)
            clear = QPushButton('Unload')
            clear.clicked.connect(lambda checked=False, k=kind: self.unload(k))
            self.clear_buttons[kind] = clear
            self.file_row.addWidget(clear, index, 3)

        self.tabs = QTabWidget()
        root.addWidget(self.tabs, 1)
        self.character_tab = QWidget()
        self.profile_tab = QWidget()
        self.character_tab_index = self.tabs.addTab(self.character_tab, 'Character Save')
        self.profile_tab_index = self.tabs.addTab(self.profile_tab, 'Profile Data')
        self._create_character_design()
        self._create_profile_design()

        self.status = QPlainTextEdit()
        self.status.setReadOnly(True)
        self.status.setMaximumHeight(85)
        root.addWidget(self.status)
        actions = QHBoxLayout()
        self.export_character_button = QPushButton('Export character copy…')
        self.export_character_button.clicked.connect(lambda: self.write_copy('character'))
        actions.addWidget(self.export_character_button)
        self.export_profile_button = QPushButton('Export profile copy…')
        self.export_profile_button.clicked.connect(lambda: self.write_copy('profile'))
        actions.addWidget(self.export_profile_button)
        close = QPushButton('Close')
        close.clicked.connect(self.reject)
        actions.addWidget(close)
        root.addLayout(actions)
        self.game_changed()

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
        root = QVBoxLayout(self.character_tab)
        self.character_info = self._info('Load a compatible character save to edit.')
        root.addWidget(self.character_info)
        stats = QGroupBox('CHARACTER / STATS')
        form = QFormLayout(stats)
        self.character = QLineEdit()
        self.character.setMaxLength(40)
        form.addRow('Character name', self.character)
        self.level = self._spin(1, 80)
        form.addRow('Level', self.level)
        self.money = self._spin()
        form.addRow('Money', self.money)
        self.eridium = self._spin()
        form.addRow('Eridium', self.eridium)
        root.addWidget(stats)
        equipment = QGroupBox('EQUIPMENT / INVENTORY')
        equip_layout = QVBoxLayout(equipment)
        self.inventory_info = self._info(
            'Item count is available. Weapon parts, rarity and inventory edits '
            'will be enabled in a future update after item round-trip tests.'
        )
        equip_layout.addWidget(self.inventory_info)
        root.addWidget(equipment)
        root.addStretch(1)

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
            self.console.addItem(platform, platform)
        self.console.blockSignals(False)
        self.console_changed()

    def console_changed(self, *_):
        self.loaded.clear()
        self.refresh_state()

    def refresh_state(self):
        states = available_sections(
            self.game.currentData(), self.console.currentData(), self.loaded)
        self.tabs.setTabEnabled(self.character_tab_index, states['character'])
        self.tabs.setTabEnabled(self.profile_tab_index, states['profile'])
        for kind, index in (('character', self.character_tab_index),
                            ('profile', self.profile_tab_index)):
            loaded = self.loaded.get(kind)
            if loaded is None:
                self.source_labels[kind].clear()
            else:
                self.source_labels[kind].setText(loaded['path'])
            self.clear_buttons[kind].setEnabled(loaded is not None)
            self.load_buttons[kind].setEnabled(
                self._selected_profile(kind) is not None)
        self.export_character_button.setEnabled(states['character'])
        self.export_profile_button.setEnabled(states['profile'])
        for kind, widgets in (
            ('character', (self.character, self.level, self.money, self.eridium)),
            ('profile', (self.golden_keys, self.diamond_keys)),
        ):
            for widget in widgets:
                widget.setEnabled(states[kind])
        if states['character']:
            self.tabs.setCurrentIndex(self.character_tab_index)
        elif states['profile']:
            self.tabs.setCurrentIndex(self.profile_tab_index)
        else:
            self.status.setPlainText(
                'Choose a supported game and console, then load a save. '
                'Character and profile tabs are locked until their own file is loaded.'
            )
        self.character_info.setText(
            'Character save loaded — editing enabled.' if states['character']
            else 'Character save missing: tab locked.')
        self.profile_info.setText(
            'Profile data loaded — editing enabled.' if states['profile']
            else 'Profile file missing: tab locked.')

    def choose_file(self, kind):
        try:
            profile = self._selected_profile(kind)
        except ValueError as exc:
            self.status.setPlainText(str(exc))
            return
        if profile is None:
            return
        name, _ = QFileDialog.getOpenFileName(
            self, 'Load ' + kind + ' from protected working copy',
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
            if path.is_symlink() or not resolved.is_relative_to(self.working) or not resolved.is_file():
                raise ValueError('Choose a regular file inside the protected working copy.')
            details = (load_character(resolved, profile.platform) if kind == 'character'
                       else load_profile(resolved, profile.platform))
            if details['kind'] != kind or details['platform'] != profile.platform:
                raise ValueError('Save kind or platform does not match the selected profile.')
        except (OSError, ValueError, RuntimeError) as exc:
            self.status.setPlainText('Cannot load ' + kind + ': ' + str(exc))
            return False

        self.loaded[kind] = details
        if kind == 'character':
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
        self.refresh_state()

    def write_copy(self, kind):
        details = self.loaded.get(kind)
        if details is None or not available_sections(
                self.game.currentData(), self.console.currentData(), self.loaded)[kind]:
            return
        source = Path(details['path'])
        suggested = source.with_name(source.stem + '_edited' + source.suffix)
        output, _ = QFileDialog.getSaveFileName(
            self, f'Export edited {kind} to new file', str(suggested), 'All files (*)')
        if not output:
            return
        try:
            if kind == 'character':
                written = write_character_copy(
                    source, output, name=self.character.text(),
                    level=self.level.value(), money=self.money.value(),
                    eridium=self.eridium.value(), platform=details['platform'],
                    expected_sha256=details['sha256'])
            else:
                written = write_profile_copy(
                    source, output, golden_keys=self.golden_keys.value(),
                    diamond_keys=self.diamond_keys.value(), platform=details['platform'],
                    expected_sha256=details['sha256'])
        except (OSError, ValueError, RuntimeError) as exc:
            QMessageBox.warning(self, 'Export failed', str(exc))
            return
        self.status.setPlainText(f'Verified {kind} copy saved: {written}')
        QMessageBox.information(
            self, 'New save exported',
            'Created a new edited copy. Keep the original. '
            'For PS4, Apollo restoration requires the expected original filename and folder.'
        )
