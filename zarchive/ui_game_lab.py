"""PS4-first Game Lab UI, integrated from the existing Save Editor page."""
from __future__ import annotations
import json
from pathlib import Path
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QWidget, QTabWidget, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLineEdit, QComboBox, QTextEdit, QPushButton, QTableWidget, QTableWidgetItem,
    QHeaderView, QFileDialog, QMessageBox, QLabel, QAbstractItemView)
from .game_lab import (GameLabStore, PLATFORMS, STAGES, BUILTIN_GAME_PLUGINS,
                       inspect_file, compare_files, package_save, atomic_write)

class GameLabDialog(QDialog):
    def __init__(self, archive_root, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Game Development Lab · PS4 First")
        self.resize(1050, 740)
        self.setMinimumSize(800, 560)
        self.store = GameLabStore(archive_root)
        self.record_id = None
        self.last_analysis = None
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Research, track, and package game saves without modifying archived originals."))
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs)
        self._tracker_tab()
        self._inspection_tab()
        self._plugins_tab()
        self._package_tab()

    def closeEvent(self, event):
        self.store.close()
        super().closeEvent(event)

    def _tracker_tab(self):
        page = QWidget()
        self.tabs.addTab(page, "Development Tracker")
        outer = QVBoxLayout(page)
        filters = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search games, IDs, notes, and values...")
        self.search.textChanged.connect(self.reload)
        filters.addWidget(self.search, 1)
        self.platform_filter = QComboBox()
        self.platform_filter.addItems(("All",) + PLATFORMS)
        self.platform_filter.currentTextChanged.connect(self.reload)
        filters.addWidget(self.platform_filter)
        self.status_filter = QComboBox()
        self.status_filter.addItems(("All",) + STAGES)
        self.status_filter.currentTextChanged.connect(self.reload)
        filters.addWidget(self.status_filter)
        outer.addLayout(filters)
        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(("Game", "Platform", "Status", "Title ID", "Updated"))
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.itemSelectionChanged.connect(self.select_record)
        outer.addWidget(self.table, 2)
        form = QFormLayout()
        outer.addLayout(form)
        self.game = QLineEdit()
        form.addRow("Game name", self.game)
        self.platform = QComboBox()
        self.platform.addItems(PLATFORMS)
        form.addRow("Platform", self.platform)
        self.status = QComboBox()
        self.status.addItems(STAGES)
        form.addRow("Development status", self.status)
        self.title_id = QLineEdit()
        self.title_id.setPlaceholderText("CUSA12345 (optional)")
        form.addRow("Title ID", self.title_id)
        self.version = QLineEdit()
        form.addRow("Game version", self.version)
        self.values = QTextEdit()
        self.values.setMaximumHeight(65)
        form.addRow("Editable values discovered", self.values)
        self.notes = QTextEdit()
        self.notes.setMaximumHeight(75)
        form.addRow("Research / testing notes", self.notes)
        buttons = QHBoxLayout()
        outer.addLayout(buttons)
        for title, callback in (("New", self.clear_form), ("Save record", self.save_record),
                                ("Delete", self.delete_record), ("Export JSON", self.export_records)):
            button = QPushButton(title)
            button.clicked.connect(callback)
            buttons.addWidget(button)
        self.reload()

    def reload(self, *_):
        rows = self.store.list(self.search.text(),
                               self.platform_filter.currentText(),
                               self.status_filter.currentText())
        self.table.blockSignals(True)
        self.table.setRowCount(len(rows))
        for index, record in enumerate(rows):
            for column, field in enumerate(("game", "platform", "status", "title_id", "updated_at")):
                item = QTableWidgetItem(str(record[field]))
                item.setData(Qt.ItemDataRole.UserRole, record["id"])
                self.table.setItem(index, column, item)
        self.table.blockSignals(False)
        for index, record in enumerate(rows):
            if record["id"] == self.record_id:
                self.table.selectRow(index)
                break

    def select_record(self):
        selected = self.table.selectedItems()
        if not selected:
            return
        record_id = selected[0].data(Qt.ItemDataRole.UserRole)
        record = next((r for r in self.store.list() if r["id"] == record_id), None)
        if record is None:
            return
        self.record_id = record_id
        self.game.setText(record["game"])
        self.platform.setCurrentText(record["platform"])
        self.status.setCurrentText(record["status"])
        self.title_id.setText(record["title_id"])
        self.version.setText(record["game_version"])
        self.values.setPlainText(record["editable_values"])
        self.notes.setPlainText(record["notes"])

    def clear_form(self):
        self.record_id = None
        self.table.clearSelection()
        self.game.clear()
        self.platform.setCurrentText("PS4")
        self.status.setCurrentText("Not started")
        self.title_id.clear()
        self.version.clear()
        self.values.clear()
        self.notes.clear()

    def save_record(self):
        try:
            self.record_id = self.store.save(
                game=self.game.text(), platform=self.platform.currentText(),
                status=self.status.currentText(), title_id=self.title_id.text(),
                game_version=self.version.text(), editable_values=self.values.toPlainText(),
                notes=self.notes.toPlainText(), record_id=self.record_id)
            self.reload()
        except Exception as error:
            QMessageBox.warning(self, "Cannot save record", str(error))

    def delete_record(self):
        if self.record_id is None:
            return
        if QMessageBox.question(self, "Delete record",
                "Delete this research record? No game saves are deleted.") != QMessageBox.StandardButton.Yes:
            return
        self.store.delete(self.record_id)
        self.clear_form()
        self.reload()

    def export_records(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "Export projects", str(Path.home() / "Downloads" / "game_development.json"),
            "JSON (*.json)")
        if path:
            try:
                self.store.export_json(path)
                QMessageBox.information(self, "Exported", "Development records exported.")
            except Exception as error:
                QMessageBox.warning(self, "Export failed", str(error))

    def _pick_file(self, entry):
        path, _ = QFileDialog.getOpenFileName(self, "Choose decrypted save", entry.text())
        if path:
            entry.setText(path)

    def _inspection_tab(self):
        page = QWidget()
        self.tabs.addTab(page, "Save Inspector / Compare")
        layout = QVBoxLayout(page)
        layout.addWidget(QLabel("Read-only, maximum 64 MiB per file. Compare two saves from the same game version."))
        form = QFormLayout()
        layout.addLayout(form)
        self.before = QLineEdit()
        self.after = QLineEdit()
        for caption, entry in (("Original decrypted save", self.before),
                               ("Changed decrypted save", self.after)):
            controls = QHBoxLayout()
            controls.addWidget(entry, 1)
            browse = QPushButton("Browse")
            browse.clicked.connect(lambda _, e=entry: self._pick_file(e))
            controls.addWidget(browse)
            form.addRow(caption, controls)
        actions = QHBoxLayout()
        layout.addLayout(actions)
        for caption, callback in (("Inspect", self.inspect), ("Compare", self.compare),
                                  ("Export analysis JSON", self.export_analysis)):
            button = QPushButton(caption)
            button.clicked.connect(callback)
            actions.addWidget(button)
        self.analysis = QTextEdit()
        self.analysis.setReadOnly(True)
        layout.addWidget(self.analysis)

    def inspect(self):
        try:
            self.last_analysis = {"inspection": inspect_file(self.before.text())}
            self.analysis.setPlainText(json.dumps(self.last_analysis, indent=2))
        except Exception as error:
            QMessageBox.warning(self, "Inspection failed", str(error))

    def compare(self):
        try:
            self.last_analysis = compare_files(self.before.text(), self.after.text())
            self.analysis.setPlainText(json.dumps(self.last_analysis, indent=2))
        except Exception as error:
            QMessageBox.warning(self, "Comparison failed", str(error))

    def export_analysis(self):
        if self.last_analysis is None:
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Export comparison", str(Path.home() / "Downloads" / "comparison.json"),
            "JSON (*.json)")
        if path:
            try:
                atomic_write(path, json.dumps(self.last_analysis, indent=2).encode("utf-8"))
                QMessageBox.information(self, "Exported", "Research results exported.")
            except Exception as error:
                QMessageBox.warning(self, "Export failed", str(error))

    def _plugins_tab(self):
        page = QWidget()
        self.tabs.addTab(page, "Game Plugin Catalog")
        layout = QVBoxLayout(page)
        layout.addWidget(QLabel("Informational capability registry. No untrusted plugin code is executed."))
        table = QTableWidget(len(BUILTIN_GAME_PLUGINS), 3)
        table.setHorizontalHeaderLabels(("Game", "Platform", "Available support"))
        table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        for row, descriptor in enumerate(BUILTIN_GAME_PLUGINS):
            for col, key in enumerate(("game", "platform", "support")):
                table.setItem(row, col, QTableWidgetItem(descriptor[key]))
        layout.addWidget(table)
        details = QTextEdit()
        details.setReadOnly(True)
        layout.addWidget(details)
        def selection():
            index = table.currentRow()
            if 0 <= index < len(BUILTIN_GAME_PLUGINS):
                details.setPlainText(BUILTIN_GAME_PLUGINS[index]["notes"])
        table.itemSelectionChanged.connect(selection)

    def _package_tab(self):
        page = QWidget()
        self.tabs.addTab(page, "Community Package Builder")
        layout = QVBoxLayout(page)
        layout.addWidget(QLabel("Local ZIP only. Review your saves for account identifiers before distributing."))
        form = QFormLayout()
        layout.addLayout(form)
        row = QHBoxLayout()
        self.folder = QLineEdit()
        row.addWidget(self.folder)
        browse = QPushButton("Browse")
        browse.clicked.connect(self.pick_folder)
        row.addWidget(browse)
        form.addRow("Save folder", row)
        self.package_game = QLineEdit()
        form.addRow("Game", self.package_game)
        self.package_platform = QComboBox()
        self.package_platform.addItems(PLATFORMS)
        form.addRow("Platform", self.package_platform)
        self.package_title_id = QLineEdit()
        form.addRow("Title ID", self.package_title_id)
        self.package_version = QLineEdit()
        form.addRow("Game version", self.package_version)
        self.package_variant = QLineEdit("Starter Boost")
        form.addRow("Save variant", self.package_variant)
        self.package_notes = QTextEdit()
        form.addRow("Notes", self.package_notes)
        button = QPushButton("Create verified local ZIP")
        button.clicked.connect(self.build_package)
        layout.addWidget(button)
        layout.addStretch()

    def pick_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Choose save folder", self.folder.text())
        if folder:
            self.folder.setText(folder)

    def build_package(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "Save community ZIP", str(Path.home() / "Downloads" / "Z_Save_Package.zip"),
            "ZIP archive (*.zip)")
        if not path:
            return
        if QMessageBox.question(self, "Privacy confirmation",
              "Have you checked the save for private IDs, account data and tokens?") != QMessageBox.StandardButton.Yes:
            return
        metadata = {"game": self.package_game.text(), "platform": self.package_platform.currentText(),
                    "title_id": self.package_title_id.text(), "game_version": self.package_version.text(),
                    "variant": self.package_variant.text(), "notes": self.package_notes.toPlainText()}
        try:
            package_save(self.folder.text(), path, metadata)
            QMessageBox.information(self, "Package complete",
                                    "ZIP integrity checked. Nothing was uploaded.\\n" + path)
        except Exception as error:
            QMessageBox.warning(self, "Package failed", str(error))
