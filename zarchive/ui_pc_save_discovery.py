"""Review and import detected PC saves from the existing Tools action."""
from PySide6.QtCore import QThread, Qt, Signal
from PySide6.QtWidgets import (
    QComboBox, QDialog, QHBoxLayout, QHeaderView, QInputDialog, QLabel, QPushButton,
    QTreeWidget, QTreeWidgetItem, QVBoxLayout,
)

from .pc_save_discovery import PROVIDERS, detect_pc_saves, import_detected_saves


class DiscoveryWorker(QThread):
    done = Signal(object)
    error = Signal(str)
    progress = Signal(str)

    def __init__(self, archive, provider, selections=None):
        super().__init__()
        self.archive_class = type(archive)
        self.root = archive.root
        self.provider = provider
        self.selections = selections

    def run(self):
        try:
            archive = self.archive_class(self.root)
            try:
                if self.selections is None:
                    result = detect_pc_saves(archive, self.provider)
                else:
                    result = import_detected_saves(archive, self.selections, self.progress.emit)
            finally:
                archive.close()
        except Exception as exc:
            self.error.emit(str(exc))
        else:
            self.done.emit(result)


class PCSaveDiscoveryDialog(QDialog):
    def __init__(self, parent, archive):
        super().__init__(parent)
        self.archive = archive
        self.worker = None
        self.setWindowTitle('Discover PC saves')
        self.resize(940, 520)
        layout = QVBoxLayout(self)
        title = QLabel('Discover PC saves')
        title.setStyleSheet('font-size: 22px; font-weight: 700;')
        layout.addWidget(title)

        controls = QHBoxLayout()
        self.provider = QComboBox()
        self.provider.addItems(PROVIDERS)
        self.provider.currentIndexChanged.connect(self.start_scan)
        self.scan_button = QPushButton('Scan again')
        self.scan_button.clicked.connect(self.start_scan)
        controls.addWidget(self.provider)
        controls.addStretch()
        controls.addWidget(self.scan_button)
        layout.addLayout(controls)

        self.table = QTreeWidget()
        self.table.setRootIsDecorated(False)
        self.table.setAlternatingRowColors(True)
        self.table.setHeaderLabels(['Game', 'Source', 'Save folder', 'Status'])
        self.table.header().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.table.header().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.table.itemChanged.connect(self.update_import_button)
        self.table.itemSelectionChanged.connect(self.update_import_button)
        layout.addWidget(self.table, 1)

        self.status = QLabel()
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        buttons = QHBoxLayout()
        self.rename_button = QPushButton('Change game name…')
        self.rename_button.clicked.connect(self.rename_game)
        self.rename_button.setEnabled(False)
        buttons.addWidget(self.rename_button)
        buttons.addStretch()
        self.import_button = QPushButton('Import selected saves')
        self.import_button.clicked.connect(self.start_import)
        self.import_button.setEnabled(False)
        close = QPushButton('Close')
        close.clicked.connect(self.close)
        buttons.addWidget(self.import_button)
        buttons.addWidget(close)
        layout.addLayout(buttons)
        self.start_scan()

    def start_scan(self):
        self.table.clear()
        self.status.setText('Looking for game-specific save folders…')
        self.start_worker()

    def start_worker(self, selections=None):
        self.set_busy(True)
        self.worker = DiscoveryWorker(self.archive, self.provider.currentText(), selections)
        self.worker.done.connect(self.show_candidates if selections is None else self.show_results)
        self.worker.error.connect(self.show_error)
        self.worker.progress.connect(self.status.setText)
        self.worker.finished.connect(self.finish_worker)
        self.worker.start()

    def set_busy(self, busy):
        for widget in (self.provider, self.scan_button, self.table):
            widget.setEnabled(not busy)
        self.update_import_button()

    def finish_worker(self):
        self.set_busy(False)

    def show_error(self, message):
        self.status.setText(message)

    def show_candidates(self, rows):
        for row in rows:
            item = QTreeWidgetItem([row['game'], row['source'], row['path'], 'Ready' if row['selected'] else 'Review'])
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(0, Qt.CheckState.Checked if row['selected'] else Qt.CheckState.Unchecked)
            item.setToolTip(2, row['path'])
            self.table.addTopLevelItem(item)
        self.status.setText(
            f'{len(rows)} save folders found. Review the list, then import the checked folders.'
            if rows else 'No supported save folders found. Try All sources or register a known game save path.'
        )

    def checked_items(self):
        return [self.table.topLevelItem(index) for index in range(self.table.topLevelItemCount())
                if self.table.topLevelItem(index).checkState(0) == Qt.CheckState.Checked]

    def update_import_button(self, *_):
        self.import_button.setEnabled(self.table.isEnabled() and bool(self.checked_items()))
        self.rename_button.setEnabled(self.table.isEnabled() and bool(self.table.selectedItems()))

    def rename_game(self):
        item = self.table.currentItem()
        if item is None:
            return
        name, accepted = QInputDialog.getText(self, 'Game name', 'Archive under:', text=item.text(0))
        if accepted and name.strip():
            item.setText(0, name.strip())

    def start_import(self):
        self.import_items = self.checked_items()
        selections = [{'game': item.text(0), 'path': item.text(2)} for item in self.import_items]
        self.status.setText('Importing checked save folders…')
        self.start_worker(selections)

    def show_results(self, results):
        for item, result in zip(self.import_items, results):
            item.setText(3, result)
            item.setToolTip(3, result)
            if result in {'Imported', 'Already archived'}:
                item.setCheckState(0, Qt.CheckState.Unchecked)
        imported = results.count('Imported')
        existing = results.count('Already archived')
        skipped = len(results) - imported - existing
        self.status.setText(f'{imported} imported · {existing} already archived · {skipped} skipped')
        parent = self.parent()
        parent.refresh()
        if hasattr(parent, 'update_home'):
            parent.update_home()

    def reject(self):
        if not (self.worker and self.worker.isRunning()):
            super().reject()

    def closeEvent(self, event):
        if self.worker and self.worker.isRunning():
            event.ignore()
        else:
            super().closeEvent(event)
