"""Read-only mission-definition browser for BL3 PS4/PC Unreal asset dumps."""
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox, QDialog, QFileDialog, QHBoxLayout, QLabel, QLineEdit,
    QListWidget, QListWidgetItem, QMessageBox, QPlainTextEdit, QPushButton,
    QSplitter, QVBoxLayout, QWidget,
)

from .bl3_missions_catalog import parse_missions_zip, mission_status_lookup
from .bl3_native import _read_codec


class BL3MissionExplorer(QDialog):
    def __init__(self, character_details=None, parent=None):
        super().__init__(parent)
        self.character_details = character_details
        self.missions = ()
        self.states = {}
        self.setWindowTitle('Borderlands 3 — Mission Explorer')
        self.resize(1050, 700)
        self.setMinimumSize(720, 480)
        self.setStyleSheet('''
            QDialog { background:#171320; color:#eee7f5; }
            QLabel {color:#ebe0f5;}
            QLineEdit, QComboBox, QListWidget, QPlainTextEdit {
                color:#f3eaff; background:#251e33;
                border:1px solid #654a86; border-radius:7px; padding:7px;
            }
            QPushButton {color:#f7ecff; background:#503271;
                border:1px solid #805ba4; border-radius:7px; padding:9px;}
            QPushButton:hover:enabled {background:#65418b;}
            QListWidget::item {padding:7px 9px;}
            QListWidget::item:selected {background:#72519b;}
        ''')
        root = QVBoxLayout(self)
        root.setSpacing(9)
        title = QLabel('MISSION EXPLORER')
        title.setStyleSheet('font-size:21px; font-weight:800; color:#ffd432;')
        root.addWidget(title)
        instructions = QLabel(
            'Read-only: import your own extracted Missions.zip to browse mission '
            'asset identifiers and possible references. Progress is read from '
            'the loaded character save, not inferred from files.'
        )
        instructions.setWordWrap(True)
        root.addWidget(instructions)
        tools = QHBoxLayout()
        self.load_zip = QPushButton('Load Mission ZIP…')
        self.load_zip.clicked.connect(self.choose_zip)
        tools.addWidget(self.load_zip)
        self.search = QLineEdit()
        self.search.setPlaceholderText('Search mission names or internal asset IDs…')
        self.search.textChanged.connect(self.refresh_list)
        tools.addWidget(self.search, 1)
        self.category = QComboBox()
        self.category.addItem('All categories')
        self.category.currentIndexChanged.connect(self.refresh_list)
        tools.addWidget(self.category)
        root.addLayout(tools)
        progress = QHBoxLayout()
        self.source_label = QLabel('No mission archive loaded')
        progress.addWidget(self.source_label, 1)
        progress.addWidget(QLabel('Playthrough'))
        self.playthrough = QComboBox()
        self.playthrough.addItem('Normal', 0)
        self.playthrough.addItem('TVHM', 1)
        self.playthrough.currentIndexChanged.connect(self.refresh_list)
        progress.addWidget(self.playthrough)
        self.status_filter = QComboBox()
        for status in ('All statuses', 'Active', 'Completed', 'Not recorded', 'Other state'):
            self.status_filter.addItem(status)
        self.status_filter.currentIndexChanged.connect(self.refresh_list)
        progress.addWidget(self.status_filter)
        root.addLayout(progress)
        split = QSplitter(Qt.Orientation.Horizontal)
        split.setChildrenCollapsible(False)
        root.addWidget(split, 1)
        self.item_list = QListWidget()
        self.item_list.currentItemChanged.connect(self.show_details)
        split.addWidget(self.item_list)
        self.details = QPlainTextEdit()
        self.details.setReadOnly(True)
        self.details.setPlaceholderText('Select a mission to inspect its references.')
        split.addWidget(self.details)
        split.setSizes([430, 610])
        self.counter = QLabel('No game mission definitions loaded')
        root.addWidget(self.counter)
        if character_details:
            try:
                decoded = _read_codec(
                    character_details['path'], character_details['platform'],
                    'character')
                self.states = mission_status_lookup(decoded)
            except (OSError, ValueError, RuntimeError, IndexError, KeyError, AttributeError) as exc:
                self.counter.setText('Progress unavailable: ' + str(exc))

    def choose_zip(self):
        path, _ = QFileDialog.getOpenFileName(
            self, 'Select extracted BL3 Missions ZIP', '',
            'ZIP archives (*.zip);;All files (*)'
        )
        if path:
            self.load_archive(path)

    def load_archive(self, path):
        try:
            result = parse_missions_zip(path)
        except (OSError, ValueError, RuntimeError) as exc:
            QMessageBox.warning(self, 'Mission import failed', str(exc))
            return False
        self.missions = result
        self.source_label.setText(Path(path).name)
        self.category.blockSignals(True)
        self.category.clear()
        self.category.addItem('All categories')
        for group in sorted(set(m.category for m in result)):
            self.category.addItem(group)
        self.category.blockSignals(False)
        self.refresh_list()
        return True

    def _status(self, mission):
        return self.states.get(
            (self.playthrough.currentData(), mission.asset_id), 'Not recorded'
        )

    def refresh_list(self, *_):
        self.item_list.blockSignals(True)
        self.item_list.clear()
        query = self.search.text().casefold().strip()
        category = self.category.currentText()
        status_filter = self.status_filter.currentText()
        for idx, mission in enumerate(self.missions):
            if category != 'All categories' and mission.category != category:
                continue
            if query and query not in (
                    mission.name + ' ' + mission.asset_path).casefold():
                continue
            status = self._status(mission)
            if status_filter == 'Other state':
                if not status.startswith('State '):
                    continue
            elif status_filter != 'All statuses' and status != status_filter:
                continue
            item = QListWidgetItem(f"{mission.name}  ·  {status}")
            item.setData(Qt.ItemDataRole.UserRole, idx)
            self.item_list.addItem(item)
        self.item_list.blockSignals(False)
        self.details.clear()
        self.counter.setText(
            f"{self.item_list.count()} missions shown / {len(self.missions)} indexed"
            + (' • No character save loaded' if not self.character_details else '')
        )
        if self.item_list.count():
            self.item_list.setCurrentRow(0)

    def show_details(self, item, previous=None):
        if item is None:
            self.details.clear()
            return
        mission = self.missions[item.data(Qt.ItemDataRole.UserRole)]
        lines = [
            mission.name,
            '',
            'CATEGORY: ' + mission.category,
            'SAVE STATUS: ' + self._status(mission),
            'MISSION ASSET: ' + mission.asset_path,
            '',
            'POSSIBLE ASSET REFERENCES (not verified dependencies/rewards):',
        ]
        lines.extend(mission.references or ('No readable references found.',))
        lines.extend((
            '',
            'MISSION STATUS LIMITS:',
            '“Not recorded” means absent from the selected playthrough list, '
            'not necessarily that the mission was never started.',
            'This explorer never edits the save or game files.',
        ))
        self.details.setPlainText('\\n'.join(lines))
