"""Borderlands editing workspace with a protected copy of the selected save."""
from pathlib import Path
import sys

from PySide6.QtCore import Qt, QTimer, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QApplication, QComboBox, QDialog, QFileDialog, QFormLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QTabWidget, QVBoxLayout, QWidget,
)

from .borderlands_edit import EDITORS, match_editor, open_editor, stage_save, validate_editor
from .ui_bl3_native import BL3NativeDialog
from .ui_v21 import TaskWorker


class BorderlandsWorkspace(QDialog):
    def __init__(self, archive, settings, parent=None):
        super().__init__(parent)
        self.archive = archive
        self.settings = settings
        self.worker = None
        self.process = None
        self.working = None
        self.original_row = None
        self.setWindowTitle('Borderlands Save Editor')
        self.resize(820, 500)
        layout = QVBoxLayout(self)
        title = QLabel('Borderlands Save Editor')
        title.setStyleSheet('font-size: 23px; font-weight: 700')
        layout.addWidget(title)
        form = QFormLayout()
        layout.addLayout(form)

        self.game = QComboBox()
        for editor in EDITORS:
            self.game.addItem(f'{editor.game} · {editor.platform}', editor)
        form.addRow('Game and platform', self.game)
        self.archived = QComboBox()
        form.addRow('Archived save', self.archived)
        self.source = QLineEdit()
        self.source.setPlaceholderText('Optional · use a decrypted export from disk')
        source_row = QHBoxLayout()
        source_row.addWidget(self.source, 1)
        self.folder_button = QPushButton('Folder…')
        self.folder_button.clicked.connect(lambda: self.choose_source(True))
        self.file_button = QPushButton('File…')
        self.file_button.clicked.connect(lambda: self.choose_source(False))
        source_row.addWidget(self.folder_button)
        source_row.addWidget(self.file_button)
        form.addRow('Decrypted source', source_row)
        self.executable = QLineEdit()
        self.executable.setPlaceholderText('Choose the matching editor executable')
        tool_row = QHBoxLayout()
        tool_row.addWidget(self.executable, 1)
        self.tool_button = QPushButton('Browse…')
        self.tool_button.clicked.connect(self.choose_editor)
        tool_row.addWidget(self.tool_button)
        self.source_link = QPushButton('Editor project')
        self.source_link.clicked.connect(self.open_project)
        tool_row.addWidget(self.source_link)
        form.addRow('Windows editor', tool_row)

        tabs = QTabWidget()
        self.character = self.add_tab(tabs, 'Character data')
        self.weapons = self.add_tab(tabs, 'Weapons & inventory')
        layout.addWidget(tabs, 1)

        self.working_path = QLineEdit()
        self.working_path.setReadOnly(True)
        self.working_path.setPlaceholderText('Prepare an editable working copy first')
        working_row = QHBoxLayout()
        working_row.addWidget(self.working_path, 1)
        self.copy_path = QPushButton('Copy path')
        self.copy_path.clicked.connect(lambda: QApplication.clipboard().setText(self.working_path.text()))
        working_row.addWidget(self.copy_path)
        form.addRow('Working copy', working_row)

        self.status = QLabel()
        self.status.setWordWrap(True)
        self.status.setTextFormat(Qt.TextFormat.PlainText)
        layout.addWidget(self.status)
        actions = QHBoxLayout()
        self.prepare_button = QPushButton('Prepare working copy…')
        self.prepare_button.setObjectName('newAction')
        self.prepare_button.clicked.connect(self.prepare)
        self.launch_button = QPushButton('Open editor')
        self.launch_button.clicked.connect(self.launch)
        self.native_button = QPushButton('BL3 Character Editor…')
        self.native_button.setToolTip('Optional in-app name, level, money and Eridium editor. Writes a verified copy.')
        self.native_button.clicked.connect(self.open_native)
        self.open_folder = QPushButton('Open copy folder')
        self.open_folder.clicked.connect(lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.working))))
        self.import_button = QPushButton('Archive edited copy')
        self.import_button.clicked.connect(self.import_copy)
        close = QPushButton('Close')
        close.clicked.connect(self.close)
        for button in (self.prepare_button, self.launch_button, self.native_button,
                       self.open_folder, self.import_button, close):
            actions.addWidget(button)
        layout.addLayout(actions)

        self.process_timer = QTimer(self)
        self.process_timer.setInterval(500)
        self.process_timer.timeout.connect(self.check_editor)
        self.game.currentIndexChanged.connect(self.change_game)
        self.archived.currentIndexChanged.connect(self.reset_copy)
        self.source.textChanged.connect(self.reset_copy)
        self.change_game()

    def add_tab(self, tabs, name):
        page = QWidget()
        layout = QVBoxLayout(page)
        description = QLabel()
        description.setWordWrap(True)
        description.setTextFormat(Qt.TextFormat.PlainText)
        layout.addWidget(description)
        layout.addStretch()
        tabs.addTab(page, name)
        return description

    def change_game(self):
        editor = self.game.currentData()
        self.archived.blockSignals(True)
        self.archived.clear()
        self.archived.addItem('Select an archived save', None)
        for row in self.archive.list_saves(platform=editor.platform):
            if match_editor(editor, row):
                self.archived.addItem(f"{row['game']} · {row['label']} · {row['title_id']}", row)
        self.archived.blockSignals(False)
        self.source.clear()
        self.executable.setText(self.settings.path('borderlands_' + editor.key))
        self.character.setText(editor.character)
        self.weapons.setText(editor.weapons)
        self.reset_copy()
        self.status.setText(f'Edits run in {editor.editor}. Select a decrypted save for this game and platform. A PS3 folder needs PARAM.SFO to re-import.')

    def reset_copy(self):
        self.working = None
        self.original_row = None
        self.working_path.clear()
        self.update_actions()

    def update_actions(self):
        idle = self.worker is None and self.process is None
        for widget in (self.game, self.archived, self.source, self.folder_button, self.file_button,
                       self.executable, self.tool_button):
            widget.setEnabled(idle)
        self.prepare_button.setEnabled(idle and bool(self.source.text().strip() or self.archived.currentData()))
        self.launch_button.setEnabled(idle and self.working is not None)
        self.native_button.setEnabled(idle and self.working is not None and
                                      self.game.currentData().key == 'bl3_ps4')
        self.copy_path.setEnabled(self.working is not None)
        self.open_folder.setEnabled(self.working is not None)
        self.import_button.setEnabled(idle and self.working is not None)

    def choose_source(self, directory):
        path = (QFileDialog.getExistingDirectory(self, 'Choose decrypted save folder') if directory else
                QFileDialog.getOpenFileName(self, 'Choose decrypted save file')[0])
        if path:
            self.source.setText(path)

    def choose_editor(self):
        path, _ = QFileDialog.getOpenFileName(self, 'Choose editor executable', '', 'Windows executable (*.exe)')
        if path:
            try:
                executable = validate_editor(path)
                self.settings.remember_path('borderlands_' + self.game.currentData().key, executable)
                self.executable.setText(str(executable))
                self.status.setText('Editor path saved.')
            except (OSError, ValueError) as exc:
                self.status.setText(str(exc))

    def open_project(self):
        QDesktopServices.openUrl(QUrl(self.game.currentData().source_url))

    def prepare(self):
        editor = self.game.currentData()
        source = self.source.text().strip()
        row = None if source else self.archived.currentData()
        if row:
            archive_data = self.archive.data_dir.resolve()
            source = (self.archive.root / row['stored_path']).resolve()
            if archive_data not in source.parents:
                self.status.setText('The archived save path is outside the save store.')
                return
        if not source:
            return
        output = QFileDialog.getExistingDirectory(self, 'Choose a folder for the working copy')
        if not output:
            return
        self.reset_copy()
        self.original_row = row
        self.status.setText('Copying the save…')
        self.worker = TaskWorker(stage_save, source, output, self.archive.root, platform=editor.platform,
                                 title_id=row['title_id'] if row else '')
        self.worker.done.connect(self.show_copy)
        self.worker.error.connect(self.status.setText)
        self.worker.finished.connect(self.worker_finished)
        self.update_actions()
        self.worker.start()

    def worker_finished(self):
        self.worker = None
        self.update_actions()

    def show_copy(self, folder):
        self.working = folder
        self.working_path.setText(str(folder))
        self.status.setText('Working copy ready. Open the editor and load this copy to edit character data or weapons.')

    def launch(self):
        try:
            if sys.platform != 'win32':
                raise OSError('The configured desktop editors require Windows.')
            name = self.game.currentData().editor
            value = self.executable.text().strip()
            if not value:
                raise ValueError(f'Choose the {name} executable first.')
            executable = validate_editor(value)
            self.settings.remember_path('borderlands_' + self.game.currentData().key, executable)
            self.process = open_editor(executable, self.working)
        except (OSError, ValueError) as exc:
            self.status.setText(str(exc))
        else:
            self.status.setText(f'{name} is open. Load the working file and save your changes to that copy.')
            self.process_timer.start()
            self.update_actions()

    def open_native(self):
        if self.working is None or self.game.currentData().key != 'bl3_ps4':
            return
        BL3NativeDialog(self.working, self).exec()

    def check_editor(self):
        code = self.process.poll()
        if code is None:
            return
        self.process_timer.stop()
        self.process = None
        self.status.setText('Editor closed. Archive the copy if you saved changes.' if code == 0
                            else f'Editor exited with code {code}. Your working copy is still available.')
        self.update_actions()

    def import_copy(self):
        editor = self.game.currentData()
        row = self.original_row or {}
        try:
            label = f"Edited · {row.get('label', editor.game)}"
            if editor.platform == 'PS3':
                self.archive.import_save(self.working, category=row.get('category', 'Modded'), label=label)
            else:
                self.archive.import_ps4_save(self.working, row.get('game', editor.game),
                                             category=row.get('category', 'Modded'), label=label)
        except (OSError, ValueError) as exc:
            self.status.setText(str(exc))
        else:
            self.status.setText('Edited copy imported as a new save.')
            self.parent().refresh()

    def reject(self):
        if self.worker is None:
            super().reject()

    def closeEvent(self, event):
        if self.worker is not None:
            event.ignore()
        else:
            super().closeEvent(event)
