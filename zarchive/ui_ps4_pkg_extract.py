"""Windows PS4 PKG extraction panel. Uses user-supplied publisher tools."""
from __future__ import annotations
import os
from pathlib import Path
from PySide6.QtCore import QProcess, Qt
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QLabel,
    QLineEdit, QPushButton, QPlainTextEdit, QFileDialog, QMessageBox, QCheckBox)
from .ps4_pkg_extract import prepare_extract, validate_executable, redact


class PkgExtractionDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("PS4 PKG Extractor · Windows")
        self.setMinimumSize(800, 560)
        self.process = None
        self.active = None
        body = QVBoxLayout(self)
        introduction = QLabel(
            "Extract supported PS4 PKGs into loose game files. Original PKGs are never changed.\n"
            "An encrypted retail package may require an unavailable key/passcode.")
        introduction.setWordWrap(True)
        body.addWidget(introduction)
        form = QFormLayout()
        body.addLayout(form)
        self.checker = QLineEdit()
        self.pkg = QLineEdit()
        self.output = QLineEdit()
        self.cmd = QLineEdit()
        self.passcode = QLineEdit()
        self.passcode.setEchoMode(QLineEdit.EchoMode.Password)
        self.passcode.setPlaceholderText("Optional: 32 hexadecimal digits")
        for title, field, mode in (
            ("orbis-pub-chk.exe (manual viewer)", self.checker, "checker"),
            ("PKG file", self.pkg, "pkg"),
            ("Extract to parent folder", self.output, "folder"),
            ("orbis-pub-cmd.exe (automatic extraction)", self.cmd, "cmd")):
            row = QHBoxLayout()
            row.addWidget(field)
            button = QPushButton("Browse")
            button.clicked.connect(lambda _, f=field, m=mode: self.browse(f, m))
            row.addWidget(button)
            form.addRow(title, row)
        form.addRow("Known package passcode", self.passcode)
        self.confirm = QCheckBox("I have rights to inspect and extract this package")
        body.addWidget(self.confirm)
        actions = QHBoxLayout()
        body.addLayout(actions)
        self.open_viewer = QPushButton("Open PKG in Image Checker")
        self.open_viewer.clicked.connect(self.launch_checker)
        actions.addWidget(self.open_viewer)
        self.extract = QPushButton("Extract loose game files")
        self.extract.clicked.connect(self.start_extract)
        actions.addWidget(self.extract)
        self.stop = QPushButton("Cancel extraction")
        self.stop.setEnabled(False)
        self.stop.clicked.connect(self.cancel)
        actions.addWidget(self.stop)
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumBlockCount(1200)
        body.addWidget(self.log)
        body.addWidget(QLabel(
            "Supports local FPKGs or authorized packages with valid decryption information. "
            "Extraction is not a bypass for retail PKG encryption. "
            "Inspect output before using it for mods or emulator testing."))

    def browse(self, field, mode):
        if mode == "folder":
            path = QFileDialog.getExistingDirectory(self, "Select existing output parent", field.text())
        else:
            filters = ("PS4 PKG (*.pkg)" if mode == "pkg" else "Windows executable (*.exe)")
            path, _ = QFileDialog.getOpenFileName(self, "Select file", field.text(), filters)
        if path:
            field.setText(path)

    def append(self, message):
        text = redact(message, self.active["passcode"] if self.active else self.passcode.text().strip())
        self.log.appendPlainText(text.rstrip()[:6000])

    def launch_checker(self):
        if not self.confirm.isChecked():
            QMessageBox.warning(self, "Confirm permission", "Confirm that you have rights to extract the PKG.")
            return
        try:
            tool = validate_executable(self.checker.text(), "orbis-pub-chk.exe")
            pkg = Path(self.pkg.text())
            if pkg.is_symlink() or not pkg.is_file() or pkg.suffix.lower() != ".pkg":
                raise ValueError("Select an existing .pkg file")
            if not QProcess.startDetached(str(tool), [str(pkg.resolve(strict=True))], str(tool.parent)):
                raise RuntimeError("Failed to launch Image Checker")
            self.append("Opened Image Checker. Use the tool's own extract command.")
        except Exception as error:
            QMessageBox.warning(self, "Viewer error", str(error))

    def start_extract(self):
        if not self.confirm.isChecked():
            QMessageBox.warning(self, "Confirm permission", "Confirm that you have rights to extract the PKG.")
            return
        if self.process is not None:
            return
        try:
            info = prepare_extract(self.pkg.text(), self.output.text(), self.cmd.text(),
                                   self.passcode.text().strip())
            target = Path(info["target"])
            target.mkdir()
        except Exception as error:
            QMessageBox.warning(self, "Invalid extraction settings", str(error))
            return
        self.active = info
        self.log.clear()
        self.append("Starting extraction into: " + info["target"])
        self.append("Original PKG is read-only.")
        self.process = QProcess(self)
        self.process.setProgram(info["program"])
        self.process.setArguments(info["args"])
        self.process.setWorkingDirectory(str(Path(info["program"]).parent))
        self.process.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        self.process.readyReadStandardOutput.connect(self.read_output)
        self.process.errorOccurred.connect(self.process_error)
        self.process.finished.connect(self.finished)
        self.extract.setEnabled(False)
        self.stop.setEnabled(True)
        self.process.start()

    def read_output(self):
        if self.process is not None:
            self.append(bytes(self.process.readAllStandardOutput()).decode("utf-8", "replace"))

    def process_error(self, error):
        self.append("Process error: " + str(error))

    def finished(self, code, status):
        self.read_output()
        target = Path(self.active["target"])
        files = sum(1 for path in target.rglob("*") if path.is_file() and not path.is_symlink())
        success = code == 0 and status == QProcess.ExitStatus.NormalExit and files > 0
        self.append(("Extraction finished. " if success else "Extraction failed or incomplete. ") +
                    str(files) + " files; exit code " + str(code))
        if not success:
            self.append("Partial files may remain in the output folder. No originals were modified.")
        self.process.deleteLater()
        self.process = None
        self.active = None
        self.extract.setEnabled(True)
        self.stop.setEnabled(False)

    def cancel(self):
        if self.process is not None:
            self.append("Cancellation requested; partial output may remain.")
            self.process.terminate()

    def closeEvent(self, event):
        if self.process is not None:
            QMessageBox.warning(self, "Extraction running",
                "Cancel or complete extraction before closing this window.")
            event.ignore()
            return
        super().closeEvent(event)
