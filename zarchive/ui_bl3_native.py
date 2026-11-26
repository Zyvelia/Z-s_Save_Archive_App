"""Universal profile selector: Borderlands 3 PC/PS4 character and profile.

A new game can register an editor profile later; unsupported platforms stay
visible as planned rather than allowing unsafe writes.
"""
from pathlib import Path

from PySide6.QtWidgets import (
    QComboBox, QDialog, QVBoxLayout, QFormLayout, QHBoxLayout, QLabel, QLineEdit,
    QSpinBox, QPushButton, QFileDialog, QMessageBox, QPlainTextEdit,
)

from .bl3_native import load_character, load_profile, write_character_copy, write_profile_copy
from .universal_editor_profiles import PROFILES, validate_profile


class BL3NativeDialog(QDialog):
    def __init__(self, working, parent=None):
        super().__init__(parent)
        self.working = Path(working)
        self.details = None
        self.setWindowTitle('Universal Save Editor - BL3 PC / PS4')
        self.resize(680, 540)
        layout = QVBoxLayout(self)
        guide = QLabel(
            'Choose a game/platform profile. Only PC and Apollo-exported PS4 '
            'Borderlands 3 saves are currently supported. Output is a NEW file; '
            'the original and archived copies remain unchanged.'
        )
        guide.setWordWrap(True)
        layout.addWidget(guide)
        form = QFormLayout()
        layout.addLayout(form)

        # Require an explicit game -> console -> save-type selection every time.
        # No game or console is preselected, including when launched from BL3.
        self.game = QComboBox()
        self.game.addItem('Select game…', None)
        for game in dict.fromkeys(item.game for item in PROFILES):
            self.game.addItem(game, game)
        form.addRow('Game', self.game)

        self.console = QComboBox()
        form.addRow('Console / platform', self.console)
        self.save_type = QComboBox()
        form.addRow('Save type', self.save_type)
        self.selection_hint = QLabel('Choose the game, console and save type before opening a file.')
        self.selection_hint.setWordWrap(True)
        form.addRow('Profile status', self.selection_hint)
        self.game.currentIndexChanged.connect(self.game_changed)
        self.console.currentIndexChanged.connect(self.console_changed)
        self.save_type.currentIndexChanged.connect(self.profile_changed)

        self.source = QLineEdit()
        self.source.setReadOnly(True)
        row = QHBoxLayout()
        row.addWidget(self.source, 1)
        browse = QPushButton('Choose save')
        browse.clicked.connect(self.choose_save)
        self.browse = browse
        self.browse.setEnabled(False)
        row.addWidget(browse)
        form.addRow('Save file', row)

        self.character = QLineEdit()
        self.character.setMaxLength(40)
        form.addRow('Character name', self.character)
        self.level = QSpinBox()
        self.level.setRange(1, 80)
        form.addRow('Level', self.level)
        self.money = QSpinBox()
        self.money.setRange(0, 2_000_000_000)
        form.addRow('Money', self.money)
        self.eridium = QSpinBox()
        self.eridium.setRange(0, 2_000_000_000)
        form.addRow('Eridium', self.eridium)
        self.golden_keys = QSpinBox()
        self.golden_keys.setRange(0, 2_000_000_000)
        form.addRow('Golden keys', self.golden_keys)
        self.diamond_keys = QSpinBox()
        self.diamond_keys.setRange(0, 2_000_000_000)
        form.addRow('Diamond keys', self.diamond_keys)
        self.fields = [
            (self.character, form.labelForField(self.character)),
            (self.level, form.labelForField(self.level)),
            (self.money, form.labelForField(self.money)),
            (self.eridium, form.labelForField(self.eridium)),
            (self.golden_keys, form.labelForField(self.golden_keys)),
            (self.diamond_keys, form.labelForField(self.diamond_keys)),
        ]

        self.report = QPlainTextEdit()
        self.report.setReadOnly(True)
        self.report.setMaximumBlockCount(100)
        layout.addWidget(self.report, 1)
        actions = QHBoxLayout()
        self.export = QPushButton('Export verified edited copy…')
        self.export.setEnabled(False)
        self.export.clicked.connect(self.write_copy)
        actions.addWidget(self.export)
        close = QPushButton('Close')
        close.clicked.connect(self.reject)
        actions.addWidget(close)
        layout.addLayout(actions)
        self.game_changed()

    def active_profile(self):
        from .universal_editor_profiles import profile_for
        value = self.save_type.currentData()
        return validate_profile(value) if value else None

    def game_changed(self, *_):
        self.console.blockSignals(True)
        self.console.clear()
        self.console.addItem('Select console…', None)
        game = self.game.currentData()
        for platform in dict.fromkeys(p.platform for p in PROFILES if p.game == game):
            self.console.addItem(platform, platform)
        self.console.blockSignals(False)
        self.console_changed()

    def console_changed(self, *_):
        self.save_type.blockSignals(True)
        self.save_type.clear()
        self.save_type.addItem('Select save type…', None)
        game, platform = self.game.currentData(), self.console.currentData()
        for profile in PROFILES:
            if profile.game != game or profile.platform != platform:
                continue
            label = profile.file_type if profile.editable else (
                profile.file_type + ' (' + profile.status + ')')
            self.save_type.addItem(label, profile.key)
            if not profile.editable:
                self.save_type.model().item(self.save_type.count() - 1).setEnabled(False)
        self.save_type.blockSignals(False)
        self.profile_changed()

    def profile_changed(self, *_):
        self.details = None
        self.export.setEnabled(False)
        self.source.clear()
        selected = self.active_profile()
        kind = selected.file_type.casefold() if selected else None
        for widget, label in self.fields:
            show = (kind == 'character') if widget in (
                self.character, self.level, self.money, self.eridium) else (kind == 'profile')
            widget.setVisible(show)
            label.setVisible(show)
        self.browse.setEnabled(selected is not None)
        if selected:
            self.selection_hint.setText(f'{selected.game} · {selected.platform} · {selected.file_type} — supported')
            self.report.setPlainText('Profile selected. Now choose a matching save from the protected working copy.')
        else:
            self.selection_hint.setText('Select a supported game, console and save type.')
            self.report.setPlainText('Select your game, console and save type first. Nothing has been loaded.')

    def choose_save(self):
        name, _ = QFileDialog.getOpenFileName(
            self, 'Choose save file from working copy', str(self.working), 'All files (*)')
        if name:
            self.open_save(Path(name))

    def open_save(self, path):
        self.export.setEnabled(False)
        self.details = None
        try:
            if not path.resolve().is_relative_to(self.working.resolve()):
                raise ValueError('Choose a file inside the protected working copy.')
            profile = self.active_profile()
            if profile is None:
                raise ValueError('Select a game, console and save type before opening a file.')
            if profile.file_type == 'Character':
                details = load_character(path, profile.platform)
            else:
                details = load_profile(path, profile.platform)
        except (OSError, ValueError, RuntimeError) as exc:
            self.report.setPlainText('Could not open save: ' + str(exc))
            return
        self.details = details
        self.source.setText(details['path'])
        if details['kind'] == 'character':
            self.character.setText(details['character'])
            self.level.setValue(details['level'])
            self.money.setValue(details['money'])
            self.eridium.setValue(details['eridium'])
            extra = (f"Class: {details['class']}\nXP: {details['xp']}\n"
                     f"Inventory items: {details['inventory_count']}")
        else:
            self.golden_keys.setValue(details['golden_keys'])
            self.diamond_keys.setValue(details['diamond_keys'])
            extra = f"Bank items: {details['bank_count']}"
        self.report.setPlainText(
            f"Game: Borderlands 3\nPlatform: {details['platform']}\n"
            f"Build: {details['platform_build']}\n{extra}\n"
            'No original save files will be overwritten.'
        )
        self.export.setEnabled(True)

    def write_copy(self):
        if self.details is None:
            return
        source = Path(self.details['path'])
        suggested = source.with_name(source.stem + '_edited' + source.suffix)
        name, _ = QFileDialog.getSaveFileName(
            self, 'Export new Borderlands 3 save', str(suggested), 'All files (*)')
        if not name:
            return
        try:
            if self.details['kind'] == 'character':
                result = write_character_copy(
                    source, name, name=self.character.text(),
                    level=self.level.value(), money=self.money.value(),
                    eridium=self.eridium.value(), platform=self.details['platform'],
                    expected_sha256=self.details['sha256'])
            else:
                result = write_profile_copy(
                    source, name, golden_keys=self.golden_keys.value(),
                    diamond_keys=self.diamond_keys.value(),
                    platform=self.details['platform'],
                    expected_sha256=self.details['sha256'])
        except (OSError, ValueError, RuntimeError) as exc:
            QMessageBox.warning(self, 'Save export failed', str(exc))
            return
        self.report.appendPlainText(f'\nVerified edited copy: {result}')
        QMessageBox.information(
            self, 'Verified copy exported',
            'Created a separate edited copy. Keep the original backed up. '
            'Apollo restoration needs the expected original filename and folder structure.'
        )
