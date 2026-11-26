"""Compact Borderlands 3 weapon workshop embedded in the Universal Save Editor.

Displays decoded inventory and supported weapon parts without inventing game
assets or claiming a rendered weapon preview. Queued modifications use the
existing validated backup-first save engine.
"""
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFormLayout, QFrame, QSplitter,
    QLabel, QLineEdit, QListWidget, QListWidgetItem, QComboBox, QSpinBox,
    QPushButton, QPlainTextEdit, QMessageBox, QApplication,
)

from .bl3_advanced import list_inventory, list_visual_weapons
from .bl3_inplace import save_advanced_with_backup


class WeaponWorkshop(QWidget):
    saveCompleted = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.details = None
        self.records = []
        self.weapon_parts = {}
        self.queue = []
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)
        title_row = QHBoxLayout()
        title = QLabel('WEAPON WORKSHOP')
        title.setObjectName('workshopTitle')
        title_row.addWidget(title)
        title_row.addStretch()
        self.summary = QLabel('Load a character save to browse inventory')
        title_row.addWidget(self.summary)
        layout.addLayout(title_row)
        split = QSplitter(Qt.Orientation.Horizontal)
        split.setChildrenCollapsible(False)
        layout.addWidget(split, 1)

        inventory = QFrame()
        inventory.setObjectName('workshopPanel')
        left = QVBoxLayout(inventory)
        self.search = QLineEdit()
        self.search.setPlaceholderText('Search inventory by name, level or balance…')
        self.search.textChanged.connect(self.filter_items)
        left.addWidget(self.search)
        self.item_list = QListWidget()
        self.item_list.currentItemChanged.connect(self.select_item)
        left.addWidget(self.item_list, 1)
        self.import_code = QLineEdit()
        self.import_code.setPlaceholderText('Paste BL3(...) item code to import')
        left.addWidget(self.import_code)
        row = QHBoxLayout()
        add = QPushButton('Import code')
        add.clicked.connect(self.add_item)
        row.addWidget(add)
        duplicate = QPushButton('Duplicate')
        duplicate.clicked.connect(self.duplicate_item)
        row.addWidget(duplicate)
        left.addLayout(row)
        split.addWidget(inventory)

        details = QFrame()
        details.setObjectName('workshopPanel')
        right = QVBoxLayout(details)
        self.item_name = QLabel('Select an inventory item')
        self.item_name.setObjectName('workshopTitle')
        right.addWidget(self.item_name)
        self.asset_info = QLabel('Weapon art is not bundled; decoded item data appears below.')
        self.asset_info.setWordWrap(True)
        right.addWidget(self.asset_info)
        form = QFormLayout()
        self.level = QSpinBox()
        self.level.setRange(1, 100)
        form.addRow('Item level', self.level)
        self.mayhem = QSpinBox()
        self.mayhem.setRange(0, 10)
        form.addRow('Mayhem level', self.mayhem)
        right.addLayout(form)
        level_row = QHBoxLayout()
        level_action = QPushButton('Queue level')
        level_action.clicked.connect(self.queue_level)
        level_row.addWidget(level_action)
        mayhem_action = QPushButton('Queue Mayhem')
        mayhem_action.clicked.connect(self.queue_mayhem)
        level_row.addWidget(mayhem_action)
        right.addLayout(level_row)
        right.addWidget(QLabel('Decoded weapon parts'))
        self.parts = QPlainTextEdit()
        self.parts.setReadOnly(True)
        self.parts.setMaximumHeight(125)
        right.addWidget(self.parts)
        right.addWidget(QLabel('COMPATIBLE PART / ANOINTMENT DONOR'))
        donor_row = QHBoxLayout()
        self.donor = QComboBox()
        donor_row.addWidget(self.donor, 1)
        self.part_slot = QComboBox()
        donor_row.addWidget(self.part_slot, 1)
        right.addLayout(donor_row)
        swap = QPushButton('Queue compatible part swap')
        swap.clicked.connect(self.queue_part)
        right.addWidget(swap)
        self.anointment = QComboBox()
        self.anointment.setToolTip('Known donor anointments only; unavailable for unsupported weapon serials.')
        right.addWidget(self.anointment)
        add_anoint = QPushButton('Queue donor anointment')
        add_anoint.clicked.connect(self.queue_anointment)
        right.addWidget(add_anoint)
        self.donor.currentIndexChanged.connect(self.update_donor_anointments)
        self.serial = QLineEdit()
        self.serial.setReadOnly(True)
        right.addWidget(self.serial)
        copy_code = QPushButton('Copy BL3 item code')
        copy_code.clicked.connect(lambda: QApplication.clipboard().setText(self.serial.text()))
        right.addWidget(copy_code)
        self.queue_info = QLabel('0 pending changes')
        right.addWidget(self.queue_info)
        right.addStretch(1)
        split.addWidget(details)
        split.setSizes([370, 590])
        self.editor_buttons = (add, duplicate, level_action, mayhem_action, swap, add_anoint, copy_code)
        self.clear()

    def clear(self):
        self.details = None
        self.records = []
        self.weapon_parts = {}
        self.queue = []
        self.item_list.clear()
        self.donor.clear()
        self.part_slot.clear()
        self.anointment.clear()
        self.parts.clear()
        self.serial.clear()
        self.item_name.setText('Select an inventory item')
        self.asset_info.setText('Weapon art is not bundled; decoded item data appears below.')
        self.summary.setText('Character save not loaded')
        self.queue_info.setText('0 pending changes')
        self.refresh_actions()

    def refresh_actions(self):
        allowed = self.details is not None
        for button in self.editor_buttons:
            button.setEnabled(allowed)
        self.search.setEnabled(allowed)
        self.import_code.setEnabled(allowed)
        self.level.setEnabled(allowed)
        self.mayhem.setEnabled(allowed)
        self.donor.setEnabled(allowed)
        self.part_slot.setEnabled(allowed)
        self.anointment.setEnabled(allowed)

    def load_character(self, details):
        self.clear()
        self.details = dict(details)
        try:
            self.records = list_inventory(details['path'], details['platform'], 'character')
            self.weapon_parts = {
                entry['item_index']: entry
                for entry in list_visual_weapons(details['path'], details['platform'])
            }
        except (OSError, ValueError, RuntimeError) as exc:
            self.clear()
            self.summary.setText('Inventory unavailable: ' + str(exc))
            return
        self.summary.setText(f"{len(self.records)} items • {details['platform']}")
        self.refresh_actions()
        self.filter_items('')

    def filter_items(self, query):
        self.item_list.clear()
        query = query.strip().casefold()
        for record in self.records:
            label = f"#{record['index']}  {record['name']}  Lv {record['level']}"
            search_text = label + ' ' + str(record['balance'])
            if query and query not in search_text.casefold():
                continue
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, record['index'])
            self.item_list.addItem(item)

    def selected_index(self):
        selected = self.item_list.currentItem()
        return selected.data(Qt.ItemDataRole.UserRole) if selected else None

    def selected_record(self):
        index = self.selected_index()
        return next((record for record in self.records if record['index'] == index), None)

    def select_item(self, *_):
        record = self.selected_record()
        self.parts.clear()
        self.serial.clear()
        self.donor.clear()
        self.part_slot.clear()
        self.anointment.clear()
        if record is None:
            self.item_name.setText('Select an inventory item')
            return
        self.item_name.setText(str(record['name']))
        self.level.setValue(record['level'] if isinstance(record['level'], int) else 1)
        self.mayhem.setValue(record['mayhem'] if isinstance(record['mayhem'], int) else 0)
        self.serial.setText(record.get('code') or '')
        self.asset_info.setText('Decoded item: ' + str(record.get('balance') or 'Unknown balance'))
        current = self.weapon_parts.get(record['index'])
        if not current:
            self.parts.setPlainText('Part editing is unavailable for this item serial.')
            return
        self.parts.setPlainText('\n'.join(
            f"{entry['slot']}: {entry['asset']}" for entry in current['parts']
        ))
        for entry in self.weapon_parts.values():
            if entry['item_index'] == record['index']:
                continue
            if (entry['balance'], entry['category']) != (current['balance'], current['category']):
                continue
            self.donor.addItem(f"Donor #{entry['item_index']}", entry['item_index'])
        for part in current['parts']:
            self.part_slot.addItem(f"Slot {part['slot']}", part['slot'])
        self.update_donor_anointments()

    def update_donor_anointments(self, *_):
        self.anointment.clear()
        donor = self.weapon_parts.get(self.donor.currentData())
        if donor is None:
            return
        for entry in donor.get('anointments', ()):
            asset = str(entry['asset'])
            if 'mayhem' in asset.casefold() or 'unknown' in asset.casefold():
                continue
            self.anointment.addItem(asset.rsplit('/', 1)[-1], asset)

    def queue_anointment(self):
        index = self.selected_index()
        donor = self.donor.currentData()
        asset = self.anointment.currentData()
        if index is None or donor is None or not asset:
            QMessageBox.information(self, 'No compatible anointment',
                'Choose a same-balance donor with a decoded anointment.')
            return
        self.enqueue({'op': 'weapon_anointment', 'index': index,
                      'donor_index': donor, 'asset': asset})

    def enqueue(self, action):
        if self.details is None:
            return
        if len(self.queue) >= 40:
            QMessageBox.warning(self, 'Queue full', 'Maximum 40 actions per save.')
            return
        self.queue.append(action)
        self.queue_info.setText(f'{len(self.queue)} pending changes')

    def add_item(self):
        code = self.import_code.text().strip()
        if not (code.startswith('BL3(') and code.endswith(')')):
            QMessageBox.warning(self, 'Invalid code', 'Supply a compatible BL3(...) serial.')
            return
        self.enqueue({'op': 'item_add', 'code': code})

    def duplicate_item(self):
        index = self.selected_index()
        if index is not None:
            self.enqueue({'op': 'item_duplicate', 'index': index})

    def queue_level(self):
        index = self.selected_index()
        if index is not None:
            self.enqueue({'op': 'item_level', 'index': index, 'level': self.level.value()})

    def queue_mayhem(self):
        index = self.selected_index()
        if index is not None:
            self.enqueue({'op': 'item_mayhem', 'index': index, 'level': self.mayhem.value()})

    def queue_part(self):
        index, donor, slot = self.selected_index(), self.donor.currentData(), self.part_slot.currentData()
        if None not in (index, donor, slot):
            self.enqueue({'op': 'weapon_part', 'index': index, 'slot': slot,
                          'donor_index': donor, 'donor_slot': slot})

    def save_pending(self):
        if not self.queue or self.details is None:
            return False
        source = Path(self.details['path'])
        if QMessageBox.question(
                self, 'Save changes with backup',
                f'Apply {len(self.queue)} weapon edits to {source}?\n'
                'The source file will be backed up and SHA-256 verified first.',
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No) != QMessageBox.StandardButton.Yes:
            return False
        try:
            output, backup = save_advanced_with_backup(
                source, kind='character',
                expected_sha256=self.details['sha256'],
                platform=self.details['platform'], actions=list(self.queue))
        except (OSError, ValueError, RuntimeError, KeyError, IndexError, AttributeError) as exc:
            QMessageBox.warning(self, 'Save failed', str(exc))
            return False
        self.saveCompleted.emit(str(output))
        QMessageBox.information(self, 'Saved with backup', f'Updated: {output}\nBackup: {backup}')
        return True
