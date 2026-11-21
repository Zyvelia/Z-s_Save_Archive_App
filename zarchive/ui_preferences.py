"""Shared sorting controls, keyboard settings, and interface spacing preferences."""
import re
from collections import Counter

from PySide6.QtCore import QEvent, QObject
from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import (
    QComboBox, QDialog, QDialogButtonBox, QFormLayout, QHBoxLayout,
    QKeySequenceEdit, QMessageBox, QScrollArea, QVBoxLayout, QWidget,
)

FONT_SIZE = re.compile(r'(font-size\s*:\s*)(\d+(?:\.\d+)?)px', re.I)


def sorted_by(rows, order, key):
    result = list(rows)
    for field, descending in reversed(order):
        result.sort(key=lambda row: key(row, field), reverse=descending)
    return result


def valid_sort(value, fields, default):
    if (isinstance(value, list) and 1 <= len(value) <= 3
            and all(isinstance(row, (tuple, list)) and len(row) == 2
                    and isinstance(row[0], str) and row[0] in fields and isinstance(row[1], bool)
                    for row in value)
            and len({row[0] for row in value}) == len(value)):
        return value
    return default


def choose_sort(parent, fields, current):
    dialog = QDialog(parent)
    dialog.setWindowTitle('Sort by multiple columns')
    layout = QFormLayout(dialog)
    controls = []
    for index, label in enumerate(('Sort by', 'Then by', 'Then by')):
        row = QHBoxLayout()
        column, direction = QComboBox(), QComboBox()
        if index:
            column.addItem('None', None)
        for field in fields:
            column.addItem(field, field)
        direction.addItems(['Ascending', 'Descending'])
        if index < len(current):
            column.setCurrentIndex(max(0, column.findData(current[index][0])))
            direction.setCurrentIndex(int(bool(current[index][1])))
        row.addWidget(column, 1)
        row.addWidget(direction)
        layout.addRow(label, row)
        controls.append((column, direction))
    buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
    buttons.accepted.connect(dialog.accept)
    buttons.rejected.connect(dialog.reject)
    layout.addRow(buttons)
    while dialog.exec() == QDialog.DialogCode.Accepted:
        order = [(column.currentData(), bool(direction.currentIndex())) for column, direction in controls
                 if column.currentData() is not None]
        if len({field for field, _ in order}) == len(order):
            return order
        QMessageBox.warning(parent, 'Duplicate sort column', 'Choose each sort column once.')
    return None


def edit_shortcuts(parent, labels, defaults, current):
    dialog = QDialog(parent)
    dialog.setWindowTitle('Keyboard shortcuts')
    dialog.resize(570, 580)
    layout = QVBoxLayout(dialog)
    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    body = QWidget()
    form = QFormLayout(body)
    editors = {}
    portable = QKeySequence.SequenceFormat.PortableText
    for name, label in labels.items():
        edit = QKeySequenceEdit(QKeySequence.fromString(current[name], portable))
        edit.setClearButtonEnabled(True)
        edit.setMaximumSequenceLength(1)
        form.addRow(label, edit)
        editors[name] = edit
    scroll.setWidget(body)
    layout.addWidget(scroll, 1)
    buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
                               | QDialogButtonBox.StandardButton.RestoreDefaults)
    buttons.accepted.connect(dialog.accept)
    buttons.rejected.connect(dialog.reject)

    def reset():
        for name, edit in editors.items():
            edit.setKeySequence(QKeySequence.fromString(defaults[name], portable))

    buttons.button(QDialogButtonBox.StandardButton.RestoreDefaults).clicked.connect(reset)
    layout.addWidget(buttons)
    while dialog.exec() == QDialog.DialogCode.Accepted:
        keys = {name: edit.keySequence().toString(portable) for name, edit in editors.items()}
        assigned = [key for key in keys.values() if key]
        duplicates = [key for key, count in Counter(assigned).items() if count > 1]
        invalid = [key for key in assigned if key in {'Ctrl+A', 'Ctrl+C', 'Ctrl+V', 'Ctrl+X', 'Ctrl+Y', 'Ctrl+Z'}
                   or ('+' not in key and not re.fullmatch(r'F(?:[1-9]|1[0-9]|2[0-4])', key))]
        if not duplicates and not invalid:
            return keys
        details = sorted(set(duplicates + invalid))
        QMessageBox.warning(parent, 'Shortcut conflict', 'Choose unique shortcuts that use a modifier or function key. '
                            'Keep standard editing shortcuts available. Review ' + ', '.join(details) + '.')
    return None


class InterfaceTextSize(QObject):
    def __init__(self, app, parent):
        super().__init__(parent)
        self.app = app
        original = app.property('archiveOriginalAppStyle')
        self.app_style = app.styleSheet() if original is None else original
        self.percent = 100
        self.app.installEventFilter(self)

    def scaled(self, style):
        return FONT_SIZE.sub(lambda match: f'{match[1]}{float(match[2]) * self.percent / 100:.2f}px', style)

    def apply_widget(self, widget):
        current = widget.styleSheet()
        last_scaled = widget.property('archiveScaledStyle')
        if current != last_scaled:
            widget.setProperty('archiveOriginalStyle', current)
        original = widget.property('archiveOriginalStyle')
        if original and FONT_SIZE.search(original):
            scaled = self.scaled(original)
            widget.setProperty('archiveScaledStyle', scaled)
            if current != scaled:
                widget.setStyleSheet(scaled)

    def set_percent(self, percent):
        self.percent = percent
        self.app.setProperty('archiveOriginalAppStyle', self.app_style)
        self.app.setStyleSheet(self.scaled(self.app_style))
        for widget in self.app.allWidgets():
            self.apply_widget(widget)

    def eventFilter(self, widget, event):
        if event.type() == QEvent.Type.Polish and isinstance(widget, QWidget):
            self.apply_widget(widget)
        return False
