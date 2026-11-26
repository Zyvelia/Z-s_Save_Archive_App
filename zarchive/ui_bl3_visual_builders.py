"""Visual Borderlands 3 weapon-parts and skill-point editors.

Design is tied to BL3's decoded save schema. Only items/skills actually
present in the save are selectable; writes are queued through the existing
backup-first validated advanced editor.
"""
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox, QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLabel, QPushButton, QListWidget, QListWidgetItem, QSpinBox,
    QGroupBox, QSplitter, QWidget,
)

from .bl3_advanced import list_visual_weapons, list_skill_tree


def _short_asset(asset):
    return str(asset).split('/')[-1].split('.')[-1] or str(asset)


class WeaponBuilderDialog(QDialog):
    """Swap a part from an item with exactly the same balance/category."""
    def __init__(self, details, queue_action, parent=None):
        super().__init__(parent)
        self.details = details
        self.queue_action = queue_action
        self.setWindowTitle('BL3 — Visual Weapon Builder')
        self.resize(920, 590)
        layout = QVBoxLayout(self)
        help_text = QLabel(
            'Choose a target and a compatible donor. Parts can only be swapped '
            'between decoded items with the exact same weapon balance and part '
            'database category. Unsupported parts are locked. Changes are queued, '
            'not applied until you confirm Save + Backup.'
        )
        help_text.setWordWrap(True)
        layout.addWidget(help_text)
        self.weapons = list_visual_weapons(details['path'], details['platform'])
        split = QSplitter()
        layout.addWidget(split, 1)
        target_box = QWidget()
        target_layout = QVBoxLayout(target_box)
        target_layout.addWidget(QLabel('TARGET WEAPON'))
        self.targets = QListWidget()
        target_layout.addWidget(self.targets)
        split.addWidget(target_box)
        edit_box = QWidget()
        edit_layout = QVBoxLayout(edit_box)
        self.part_list = QListWidget()
        edit_layout.addWidget(QLabel('CURRENT PARTS'))
        edit_layout.addWidget(self.part_list)
        edit_layout.addWidget(QLabel('COMPATIBLE DONOR WEAPON'))
        self.donors = QComboBox()
        edit_layout.addWidget(self.donors)
        edit_layout.addWidget(QLabel('DONOR PART'))
        self.donor_parts = QComboBox()
        edit_layout.addWidget(self.donor_parts)
        edit_layout.addWidget(QLabel('DONOR ANOINTMENT (optional)'))
        self.donor_anointments = QComboBox()
        edit_layout.addWidget(self.donor_anointments)
        button = QPushButton('Queue selected part replacement')
        button.clicked.connect(self.add_action)
        edit_layout.addWidget(button)
        anointment_button = QPushButton('Queue donor anointment')
        anointment_button.clicked.connect(self.add_anointment)
        edit_layout.addWidget(anointment_button)
        split.addWidget(edit_box)
        split.setSizes([380, 540])
        self.message = QLabel()
        self.message.setWordWrap(True)
        layout.addWidget(self.message)
        done = QPushButton('Back to advanced editor')
        done.clicked.connect(self.accept)
        layout.addWidget(done)
        for weapon in self.weapons:
            entry = QListWidgetItem(
                f"#{weapon['item_index']}  {_short_asset(weapon['balance'])} "
                f"({len(weapon['parts'])} parts)"
            )
            entry.setData(Qt.ItemDataRole.UserRole, weapon['item_index'])
            self.targets.addItem(entry)
        self.targets.currentItemChanged.connect(self.target_changed)
        self.part_list.currentItemChanged.connect(self.donor_changed)
        self.donors.currentIndexChanged.connect(self.donor_changed)
        if self.targets.count():
            self.targets.setCurrentRow(0)
        else:
            self.message.setText('No supported part-bearing weapons were decoded.')

    def target_changed(self, *_):
        self.part_list.clear()
        self.donors.blockSignals(True)
        self.donors.clear()
        target = self.selected_target()
        if target is not None:
            for part in target['parts']:
                item = QListWidgetItem(
                    f"{part['slot']:02d}  {_short_asset(part['asset'])}"
                )
                item.setData(Qt.ItemDataRole.UserRole, part['slot'])
                self.part_list.addItem(item)
            for candidate in self.weapons:
                if candidate['item_index'] == target['item_index']:
                    continue
                if (candidate['balance'], candidate['category']) != (
                        target['balance'], target['category']):
                    continue
                self.donors.addItem(
                    f"#{candidate['item_index']}  {_short_asset(candidate['balance'])}",
                    candidate['item_index']
                )
        self.donors.blockSignals(False)
        self.donor_changed()
        if self.part_list.count():
            self.part_list.setCurrentRow(0)

    def donor_changed(self, *_):
        self.donor_parts.clear()
        self.donor_anointments.clear()
        donor = self.selected_donor()
        if donor is None:
            self.message.setText(
                'No matching-balance donor in this character save. '
                'Import a compatible weapon code first, then reopen the builder.'
            )
            return
        target_part = self.part_list.currentItem()
        position = (target_part.data(Qt.ItemDataRole.UserRole)
                    if target_part is not None else None)
        for part in donor['parts']:
            if part['slot'] != position:
                continue
            self.donor_parts.addItem(
                f"{part['slot']:02d}  {_short_asset(part['asset'])}",
                part['slot']
            )
        target = self.selected_target()
        if target is not None and target['balance'] == donor['balance']:
            for anointment in donor['anointments']:
                asset = anointment['asset']
                if asset.casefold() != 'unknown' and 'mayhem' not in asset.casefold():
                    self.donor_anointments.addItem(_short_asset(asset), asset)
        self.message.setText(
            'Only matching part positions and donor anointments are available.'
        )

    def selected_target(self):
        item = self.targets.currentItem()
        if item is None:
            return None
        index = item.data(Qt.ItemDataRole.UserRole)
        return next((w for w in self.weapons if w['item_index'] == index), None)

    def selected_donor(self):
        index = self.donors.currentData()
        return next((w for w in self.weapons if w['item_index'] == index), None)

    def add_anointment(self):
        target = self.selected_target()
        donor = self.selected_donor()
        asset = self.donor_anointments.currentData()
        if target is None or donor is None or not asset:
            self.message.setText('Choose a compatible donor containing an anointment.')
            return
        self.queue_action({
            'op': 'weapon_anointment',
            'index': target['item_index'],
            'donor_index': donor['item_index'],
            'asset': asset,
        })
        self.message.setText('Anointment transfer queued; verification runs before saving.')

    def add_action(self):
        target = self.selected_target()
        donor = self.selected_donor()
        part = self.part_list.currentItem()
        donor_slot = self.donor_parts.currentData()
        if target is None or donor is None or part is None or donor_slot is None:
            self.message.setText('Choose a target, part slot, and compatible donor with that slot.')
            return
        self.queue_action({
            'op': 'weapon_part',
            'index': target['item_index'],
            'slot': part.data(Qt.ItemDataRole.UserRole),
            'donor_index': donor['item_index'],
            'donor_slot': donor_slot,
        })
        self.message.setText('Part replacement queued. Use Apply changes + backup to save.')


class SkillTreeDialog(QDialog):
    """Edit only existing BL3 protobuf skill entries, conserving total points."""
    def __init__(self, details, queue_action, parent=None):
        super().__init__(parent)
        self.queue_action = queue_action
        self.setWindowTitle('BL3 — Individual Skill Tree Points')
        self.resize(780, 560)
        data = list_skill_tree(details['path'], details['platform'])
        self.rows = data['rows']
        self.budget = data['budget']
        layout = QVBoxLayout(self)
        info = QLabel(
            'Only skills present in this character save can be edited. '
            'Changes preserve the total spent + unspent points. '
            'Queue decreases before increases when reallocating points.'
        )
        info.setWordWrap(True)
        layout.addWidget(info)
        self.budget_label = QLabel(
            f"Current spent: {self.budget['spent']}    "
            f"Unspent: {self.budget['remaining']}    "
            f"Total: {self.budget['total']}"
        )
        layout.addWidget(self.budget_label)
        self.skills = QListWidget()
        layout.addWidget(self.skills, 1)
        for row in self.rows:
            entry = QListWidgetItem(
                f"Tree {row['tree']} | {_short_asset(row['asset'])} | "
                f"{row['points']} / {row['max_points']}"
            )
            entry.setData(Qt.ItemDataRole.UserRole, row['index'])
            self.skills.addItem(entry)
        form = QFormLayout()
        self.points = QSpinBox()
        self.points.setRange(0, 0)
        form.addRow('Invested points', self.points)
        layout.addLayout(form)
        self.message = QLabel()
        layout.addWidget(self.message)
        buttons = QHBoxLayout()
        queue = QPushButton('Queue skill-point edit')
        queue.clicked.connect(self.add_action)
        buttons.addWidget(queue)
        close = QPushButton('Back to advanced editor')
        close.clicked.connect(self.accept)
        buttons.addWidget(close)
        layout.addLayout(buttons)
        self.skills.currentItemChanged.connect(self.selection_changed)
        if self.skills.count():
            self.skills.setCurrentRow(0)
        else:
            self.message.setText(
                'No editable skill entries exist in this save yet. '
                'The editor will not fabricate unknown skill paths.'
            )

    def selection_changed(self, *_):
        current = self.skills.currentItem()
        if current is None:
            self.points.setRange(0, 0)
            return
        idx = current.data(Qt.ItemDataRole.UserRole)
        row = next((r for r in self.rows if r['index'] == idx), None)
        if row is not None:
            self.points.setRange(0, max(0, row['max_points']))
            self.points.setValue(row['points'])

    def add_action(self):
        current = self.skills.currentItem()
        if current is None:
            return
        idx = current.data(Qt.ItemDataRole.UserRole)
        self.queue_action({
            'op': 'skill_points',
            'index': idx,
            'points': self.points.value(),
        })
        self.message.setText(
            'Skill change queued. The point budget is rechecked when all edits apply.'
        )
