"""Native Borderlands 3 character editing panel (optional codec dependency).

This panel is intentionally restricted to character name, level, money, and
Eridium. The original Apollo export remains untouched.
"""
from pathlib import Path

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QFormLayout, QHBoxLayout, QLabel, QLineEdit,
    QSpinBox, QPushButton, QFileDialog, QMessageBox, QPlainTextEdit,
)

from .bl3_native import load_character, write_character_copy


class BL3NativeDialog(QDialog):
    def __init__(self, working, parent=None):
        super().__init__(parent)
        self.working = Path(working)
        self.details = None
        self.setWindowTitle('Borderlands 3 - Character Editor (Safe Copy)')
        self.resize(640, 440)
        layout = QVBoxLayout(self)
        guide = QLabel(
            'For Apollo-exported BL3 character saves. The original is never '
            'overwritten. A supported bl3-cli-saveedit codec is required; '
            'if it cannot decode your PS4 save, use the existing external editor.'
        )
        guide.setWordWrap(True)
        layout.addWidget(guide)

        form = QFormLayout()
        layout.addLayout(form)
        self.source = QLineEdit()
        self.source.setReadOnly(True)
        row = QHBoxLayout()
        row.addWidget(self.source, 1)
        browse = QPushButton('Choose save')
        browse.clicked.connect(self.choose_save)
        row.addWidget(browse)
        form.addRow('Apollo character file', row)
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
        candidates = [p for p in self.working.iterdir() if p.is_file() and
                      (p.name.lower().endswith('.sav') or p.name.isdigit())]
        if len(candidates) == 1:
            self.open_save(candidates[0])

    def choose_save(self):
        name, _ = QFileDialog.getOpenFileName(
            self, 'Choose Borderlands 3 character save', str(self.working),
            'All files (*)'
        )
        if name:
            self.open_save(Path(name))

    def open_save(self, path):
        self.export.setEnabled(False)
        self.details = None
        try:
            if not path.resolve().is_relative_to(self.working.resolve()):
                raise ValueError('Select a file inside the protected working copy.')
            details = load_character(path)
        except (OSError, ValueError, RuntimeError) as exc:
            self.report.setPlainText('Could not open save: ' + str(exc))
            return
        self.details = details
        self.source.setText(details['path'])
        self.character.setText(details['character'])
        self.level.setValue(details['level'])
        self.money.setValue(details['money'])
        self.eridium.setValue(details['eridium'])
        self.report.setPlainText(
            f"Class: {details['class']}\nBuild: {details['platform_build']}\n"
            f"Current XP: {details['xp']}\n"
            f"Inventory entries: {details['inventory_count']}\n"
            'Edits are always written to a new file; keep the console original.'
        )
        self.export.setEnabled(True)

    def write_copy(self):
        if self.details is None:
            return
        source = Path(self.details['path'])
        suggested = source.with_name(source.stem + '_edited' + source.suffix)
        name, _ = QFileDialog.getSaveFileName(
            self, 'Export new BL3 character save', str(suggested), 'All files (*)')
        if not name:
            return
        try:
            result = write_character_copy(
                source, name, name=self.character.text(),
                level=self.level.value(), money=self.money.value(),
                eridium=self.eridium.value(),
                expected_sha256=self.details['sha256'])
        except (OSError, ValueError, RuntimeError) as exc:
            QMessageBox.warning(self, 'BL3 export failed', str(exc))
            return
        self.report.appendPlainText(f'\nVerified edited copy: {result}')
        QMessageBox.information(
            self, 'Verified copy exported',
            'Created a new edited save. Do not restore it to the PS4 until '
            'you have backed up the original and validated it in a PS4-compatible editor. '
            'Apollo restoration requires the expected original save filename.'
        )
