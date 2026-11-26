"""BL3 advanced editor: item/code operations, progression and profile features.

Every action is queued and validated by the codec. Applying actions updates
the loaded source only after ZSaveArchive_Backups receives a verified copy.
"""
from pathlib import Path

from PySide6.QtCore import Qt

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QFormLayout, QHBoxLayout, QLabel, QLineEdit,
    QSpinBox, QPushButton, QMessageBox, QTabWidget, QWidget, QComboBox,
    QPlainTextEdit, QListWidget, QListWidgetItem, QGroupBox, QApplication,
)

from .bl3_advanced import list_inventory, COSMETICS
from .bl3_inplace import save_advanced_with_backup
from .ui_bl3_visual_builders import WeaponBuilderDialog, SkillTreeDialog


class BL3AdvancedDialog(QDialog):
    def __init__(self, details, parent=None):
        super().__init__(parent)
        self.details = dict(details)
        self.actions = []
        self.setWindowTitle('Borderlands 3 — Advanced ' + details['kind'].title() + ' Editor')
        self.resize(860, 650)
        root = QVBoxLayout(self)
        self.tabs = QTabWidget()
        root.addWidget(self.tabs, 1)
        if details['kind'] == 'character':
            self._inventory_page()
            self._progression_page()
        else:
            self._bank_page()
            self._guardian_page()
            self._vault_page()
            self._cosmetics_page()
        root.addWidget(QLabel(
            'Queued changes are applied together. Original filename is preserved; '
            'a verified backup is created first.'))
        self.queue = QListWidget()
        self.queue.setMaximumHeight(135)
        root.addWidget(self.queue)
        actions = QHBoxLayout()
        remove = QPushButton('Remove selected action')
        remove.clicked.connect(self.remove_selected)
        actions.addWidget(remove)
        clear = QPushButton('Clear queue')
        clear.clicked.connect(self.clear_queue)
        actions.addWidget(clear)
        apply = QPushButton('Apply changes + backup')
        apply.clicked.connect(self.apply)
        actions.addWidget(apply)
        root.addLayout(actions)

    def _page(self, title, info):
        page = QWidget()
        layout = QVBoxLayout(page)
        label = QLabel(info)
        label.setWordWrap(True)
        layout.addWidget(label)
        self.tabs.addTab(page, title)
        return layout

    def _spin(self, minval=0, maxval=2_000_000_000):
        field = QSpinBox()
        field.setRange(minval, maxval)
        return field

    def _add_button(self, layout, label, operation):
        button = QPushButton(label)
        button.clicked.connect(operation)
        layout.addWidget(button)
        return button

    def _queue(self, action):
        if len(self.actions) >= 40:
            QMessageBox.warning(self, 'Queue full', 'Maximum 40 actions per save.')
            return
        self.actions.append(action)
        self.queue.addItem(str(len(self.actions)) + '. ' + self._description(action))

    @staticmethod
    def _description(action):
        return action['op'].replace('_', ' ').title() + ' — ' + ', '.join(
            f'{key}={str(value)[:90]}' for key, value in action.items() if key != 'op'
        )

    def remove_selected(self):
        index = self.queue.currentRow()
        if index < 0:
            return
        del self.actions[index]
        self._draw_queue()

    def clear_queue(self):
        self.actions.clear()
        self._draw_queue()

    def _draw_queue(self):
        self.queue.clear()
        for index, action in enumerate(self.actions, 1):
            self.queue.addItem(f'{index}. {self._description(action)}')

    def _inventory(self, layout, kind):
        box = QGroupBox('Inventory entries')
        inner = QVBoxLayout(box)
        self.search_items = QLineEdit()
        self.search_items.setPlaceholderText('Search inventory by name, level or balance')
        self.search_items.textChanged.connect(self._filter_inventory)
        inner.addWidget(self.search_items)
        self.item_list = QListWidget()
        inner.addWidget(self.item_list)
        self.item_level = self._spin(1, 100)
        self.item_mayhem = self._spin(0, 10)
        form = QFormLayout()
        form.addRow('Item level', self.item_level)
        if kind == 'character':
            form.addRow('Item Mayhem level', self.item_mayhem)
        inner.addLayout(form)
        self.item_code = QPlainTextEdit()
        self.item_code.setPlaceholderText('Paste BL3(...) item serial code here')
        self.item_code.setMaximumHeight(105)
        inner.addWidget(self.item_code)
        layout.addWidget(box)
        buttons = QHBoxLayout()
        layout.addLayout(buttons)
        def button(label, callback):
            b = QPushButton(label)
            b.clicked.connect(callback)
            buttons.addWidget(b)
        try:
            self.inventory_records = list_inventory(
                self.details['path'], self.details['platform'], kind)
            self._filter_inventory('')
        except (OSError, ValueError, RuntimeError) as exc:
            self.inventory_records = []
            self.item_list.addItem('Inventory preview unavailable: ' + str(exc))
        def selected():
            item = self.item_list.currentItem()
            return item.data(Qt.ItemDataRole.UserRole) if item is not None else None
        def duplicate():
            idx = selected()
            if idx is not None:
                self._queue({'op': 'item_duplicate', 'index': idx})
        def change_level():
            idx = selected()
            if idx is not None:
                self._queue({'op': 'item_level', 'index': idx,
                             'level': self.item_level.value()})
        def change_mayhem():
            idx = selected()
            if idx is not None:
                self._queue({'op': 'item_mayhem', 'index': idx,
                             'level': self.item_mayhem.value()})
        def add_code():
            code = self.item_code.toPlainText().strip()
            if not code.startswith('BL3(') or not code.endswith(')'):
                QMessageBox.warning(self, 'Invalid item code', 'Paste a BL3(...) serial first.')
                return
            self._queue({'op': 'item_add' if kind == 'character' else 'bank_add',
                         'code': code})
        button('Import BL3 code', add_code)
        def copy_code():
            idx = selected()
            if idx is None:
                return
            code = self.inventory_records[idx].get('code')
            if code:
                QApplication.clipboard().setText(code)
        button('Copy selected BL3 code', copy_code)
        if kind == 'character':
            def replace_code():
                idx = selected()
                code = self.item_code.toPlainText().strip()
                if idx is None:
                    QMessageBox.warning(self, 'Select an item', 'Choose an inventory entry to replace.')
                    return
                if not code.startswith('BL3(') or not code.endswith(')'):
                    QMessageBox.warning(self, 'Invalid item code', 'Paste a BL3(...) serial first.')
                    return
                self._queue({'op': 'item_replace', 'index': idx, 'code': code})
            button('Replace selected with BL3 code', replace_code)
            button('Duplicate selected', duplicate)
            button('Set item level', change_level)
            button('Set item Mayhem', change_mayhem)

    def _filter_inventory(self, text):
        """Maintain original indices even when searching/filtering inventory."""
        if not hasattr(self, 'inventory_records'):
            return
        query = text.strip().casefold()
        self.item_list.clear()
        for record in self.inventory_records:
            display = (f"{record['index']:04d}  {record['name']}  "
                       f"Level {record['level']}  Mayhem {record['mayhem']}")
            if query and query not in (display + ' ' + str(record['balance'])).casefold():
                continue
            item = QListWidgetItem(display)
            item.setData(Qt.ItemDataRole.UserRole, record['index'])
            self.item_list.addItem(item)

    def _inventory_page(self):
        layout = self._page('Inventory & Weapons',
            'Browse existing items, duplicate equipment, import item codes and '
            'change supported item levels/Mayhem. Arbitrary parts and '
            'anointment editing require additional compatibility validation.')
        self._inventory(layout, 'character')
        self._add_button(
            layout, 'Open Visual Weapon Parts Builder…',
            self.open_visual_weapon_builder
        )

    def _bank_page(self):
        layout = self._page('Bank & DLC Gear',
            'Inspect the profile bank and import compatible BL3(...) item codes, '
            'including DLC items when installed game assets support them. '
            'This does not grant DLC ownership or edit DLC missions.')
        self._inventory(layout, 'profile')

    def _progression_page(self):
        layout = self._page('Skills / Mayhem / SDUs',
            'Applies to character save data. Unlock skill tree availability, '
            'set Mayhem for existing playthroughs, and maximize known SDUs. '
            'Individual skill points and missions are not yet editable.')
        mayhem = self._spin(0, 11)
        form = QFormLayout()
        form.addRow('All playthroughs Mayhem', mayhem)
        layout.addLayout(form)
        self._add_button(layout, 'Queue Mayhem level',
                         lambda: self._queue({'op': 'mayhem_all', 'level': mayhem.value()}))
        self._add_button(layout, 'Queue max character SDUs',
                         lambda: self._queue({'op': 'max_sdu'}))
        self._add_button(layout, 'Queue unlock skill-tree availability',
                         lambda: self._queue({'op': 'unlock_skill_tree'}))
        self._add_button(
            layout, 'Open Individual Skill Tree Editor…',
            self.open_skill_editor
        )
        layout.addStretch()

    def open_visual_weapon_builder(self):
        try:
            WeaponBuilderDialog(self.details, self._queue, self).exec()
        except (OSError, ValueError, RuntimeError) as exc:
            QMessageBox.warning(self, 'Weapon builder unavailable', str(exc))

    def open_skill_editor(self):
        try:
            SkillTreeDialog(self.details, self._queue, self).exec()
        except (OSError, ValueError, RuntimeError) as exc:
            QMessageBox.warning(self, 'Skill editor unavailable', str(exc))

    def _guardian_page(self):
        layout = self._page('Guardian / SDUs',
            'Set unspent Guardian tokens or maximize profile SDUs. '
            'The game may independently reconcile Guardian Rank.')
        tokens = self._spin()
        form = QFormLayout()
        form.addRow('Guardian tokens', tokens)
        layout.addLayout(form)
        self._add_button(layout, 'Queue Guardian tokens',
                         lambda: self._queue({'op': 'guardian_tokens', 'value': tokens.value()}))
        self._add_button(layout, 'Queue max profile SDUs',
                         lambda: self._queue({'op': 'max_sdu'}))
        layout.addStretch()

    def _vault_page(self):
        layout = self._page('Vault Cards',
            'Edit Vault Card keys and unopened chests. DLC content must exist '
            'in your game for corresponding rewards to function.')
        card = QComboBox()
        for n in (1, 2, 3):
            card.addItem(f'Vault Card {n}', n)
        amount = self._spin()
        form = QFormLayout()
        form.addRow('Vault Card', card)
        form.addRow('Amount', amount)
        layout.addLayout(form)
        self._add_button(layout, 'Queue keys',
                         lambda: self._queue({'op': 'vault_keys', 'card': card.currentData(),
                                              'value': amount.value()}))
        self._add_button(layout, 'Queue unopened chests',
                         lambda: self._queue({'op': 'vault_chests', 'card': card.currentData(),
                                              'value': amount.value()}))
        layout.addStretch()

    def _cosmetics_page(self):
        layout = self._page('Cosmetics',
            'Unlock known heads, skins, emotes, ECHO themes, room decorations, '
            'weapon skins and trinkets. Some items may be tied to DLC.')
        category = QComboBox()
        for item in COSMETICS:
            category.addItem(item.replace('_', ' ').title(), item)
        layout.addWidget(category)
        self._add_button(layout, 'Queue unlock selected category',
                         lambda: self._queue({'op': 'unlock_cosmetic',
                                              'category': category.currentData()}))
        layout.addStretch()

    def apply(self):
        if not self.actions:
            QMessageBox.information(self, 'No edits', 'Queue at least one action.')
            return
        source = Path(self.details['path'])
        check = QMessageBox.question(
            self, 'Apply advanced changes',
            f'Apply {len(self.actions)} edits to:\n{source}\n\n'
            'Create and SHA-256 verify an original backup first?',
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        if check != QMessageBox.StandardButton.Yes:
            return
        try:
            written, backup = save_advanced_with_backup(
                source, kind=self.details['kind'],
                expected_sha256=self.details['sha256'],
                platform=self.details['platform'], actions=list(self.actions))
        except (OSError, ValueError, RuntimeError, KeyError, IndexError, AttributeError) as exc:
            QMessageBox.warning(self, 'Edit failed — original unchanged if validation failed',
                                str(exc))
            return
        QMessageBox.information(self, 'Advanced save edited',
            f'Updated: {written}\nBackup: {backup}\n'
            'Reload to inspect the result. For PS4, restore through Apollo.')
        self.accept()
