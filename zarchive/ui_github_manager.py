"""GitHub source publishing, repository migration and backup uploads."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QThread, Signal, Slot, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QCheckBox, QDialog, QFileDialog, QFormLayout, QHBoxLayout, QLabel, QLineEdit,
    QMessageBox, QPlainTextEdit, QPushButton, QVBoxLayout,
)

from .github_manager import GitHubManager, repository_name


class GitHubTask(QThread):
    message = Signal(str)
    done = Signal(object)
    failed = Signal(str)

    def __init__(self, operation, *args, **kwargs):
        super().__init__()
        self.operation = operation
        self.args = args
        self.kwargs = kwargs

    def run(self):
        try:
            manager = GitHubManager(self.message.emit)
            self.done.emit(getattr(manager, self.operation)(*self.args, **self.kwargs))
        except Exception as exc:
            self.failed.emit(str(exc))


class GitHubManagerDialog(QDialog):
    def __init__(self, archive, parent=None):
        super().__init__(parent)
        self.archive = archive
        self.worker = None
        self.repository_url = ''
        self.setWindowTitle('GitHub Manager')
        self.resize(840, 530)
        layout = QVBoxLayout(self)
        note = QLabel('Use GitHub CLI to sign in. Source publishing and Git bundles also require Git.')
        note.setWordWrap(True)
        layout.addWidget(note)

        form = QFormLayout()
        layout.addLayout(form)
        self.repo = QLineEdit(archive.publishing_repo())
        self.repo.setPlaceholderText('owner/repository or GitHub URL')
        form.addRow('Repository', self.repo)
        self.create = QCheckBox('Create a new repository when publishing or uploading')
        self.public = QCheckBox('Make the new source repository public')
        self.public.setEnabled(False)
        self.create.toggled.connect(self.public.setEnabled)
        form.addRow('', self.create)
        form.addRow('', self.public)

        source_root = Path(__file__).resolve().parent.parent
        self.source = QLineEdit(str(source_root) if (source_root / 'main.py').is_file() else '')
        self.source.setPlaceholderText('Git checkout, Git bundle, or extracted Save Archive source')
        source_row = QHBoxLayout()
        source_row.addWidget(self.source, 1)
        folder = QPushButton('Folder…')
        folder.clicked.connect(self.pick_folder)
        source_row.addWidget(folder)
        bundle = QPushButton('Bundle…')
        bundle.clicked.connect(self.pick_bundle)
        source_row.addWidget(bundle)
        form.addRow('Source', source_row)

        self.branch = QLineEdit('main')
        form.addRow('Destination branch', self.branch)
        self.all_refs = QCheckBox('Publish all local branches and tags from a Git checkout or bundle')
        self.all_refs.toggled.connect(self.branch.setDisabled)
        form.addRow('', self.all_refs)
        self.snapshot = QCheckBox('Publish the current app files as a snapshot, including local edits')
        self.snapshot.toggled.connect(self.all_refs.setDisabled)
        self.all_refs.toggled.connect(self.snapshot.setDisabled)
        form.addRow('', self.snapshot)

        self.buttons = []
        for actions in (
            (('Sign in…', self.sign_in), ('Check sign-in', self.check_account),
             ('Remember repository', self.remember)),
            (('Publish source', self.publish), ('Save Git bundle…', self.save_bundle),
             ('Download repository bundle…', self.download_bundle),
             ('Upload backup ZIP…', self.upload_backup)),
        ):
            row = QHBoxLayout()
            for label, callback in actions:
                button = QPushButton(label)
                button.clicked.connect(callback)
                self.buttons.append(button)
                row.addWidget(button)
            layout.addLayout(row)

        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumBlockCount(1000)
        layout.addWidget(self.log, 1)
        footer = QHBoxLayout()
        self.open_repo = QPushButton('Open repository')
        self.open_repo.setEnabled(False)
        self.open_repo.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(self.repository_url)))
        footer.addWidget(self.open_repo)
        footer.addStretch(1)
        close = QPushButton('Close')
        close.clicked.connect(self.reject)
        footer.addWidget(close)
        layout.addLayout(footer)

    def pick_folder(self):
        selected = QFileDialog.getExistingDirectory(self, 'Choose source folder')
        if selected:
            self.source.setText(selected)

    def pick_bundle(self):
        path, _ = QFileDialog.getOpenFileName(self, 'Choose a local Git bundle', '', 'Git bundles (*.bundle)')
        if path:
            self.source.setText(path)

    def _repository(self):
        try:
            return repository_name(self.repo.text())
        except ValueError as exc:
            QMessageBox.warning(self, 'GitHub repository', str(exc))
            return None

    def remember(self):
        name = self._repository()
        if name:
            try:
                self.archive.set_publishing_repo(*name.split('/', 1))
            except (OSError, ValueError) as exc:
                QMessageBox.warning(self, 'GitHub repository', str(exc))
                return
            self.log.appendPlainText(f'Remembered {name} for GitHub publishing.')

    def sign_in(self):
        try:
            GitHubManager().sign_in()
            self.log.appendPlainText('Finish signing in in the GitHub CLI window, then select Check sign-in.')
        except (OSError, ValueError) as exc:
            self.log.appendPlainText(str(exc))

    def check_account(self):
        self._start('account', on_success=lambda login: self.log.appendPlainText(f'Signed in as {login}.'))

    def publish(self):
        name = self._repository()
        source = self.source.text().strip()
        branch = self.branch.text().strip()
        all_refs = self.all_refs.isChecked()
        snapshot = self.snapshot.isChecked()
        if not name:
            return
        if not source or not (all_refs or branch):
            QMessageBox.warning(self, 'Publish source', 'Choose a source and a destination branch.')
            return
        create = self.create.isChecked()
        private = not self.public.isChecked()
        ref = 'all local branches and tags' if all_refs else f'branch {branch}'
        action = (f'Create a {"private" if private else "public"} repository and publish to'
                  if create else 'Publish to')
        message = (
            f'{action} {name}, {ref}?\n\nSource: {source}\n\n'
            'Git checkouts and bundles include committed history. Extracted source folders upload the app files. '
            'An existing destination may be public. Review the source before publishing.'
        )
        if self._confirmed('Publish source', message):
            self._start('publish', source, name, branch, create=create, private=private,
                        all_refs=all_refs, snapshot=snapshot, on_success=self._show_repo)

    def save_bundle(self):
        source = self.source.text().strip()
        if not source:
            QMessageBox.warning(self, 'Save Git bundle', 'Choose a local Git checkout first.')
            return
        path, _ = QFileDialog.getSaveFileName(
            self, 'Save local Git bundle', 'SaveArchive.bundle', 'Git bundles (*.bundle)')
        if path:
            self._start('save_bundle', source, path, on_success=self._show_bundle)

    def download_bundle(self):
        name = self._repository()
        if not name:
            return
        path, _ = QFileDialog.getSaveFileName(self, 'Download repository bundle',
                                             f"{name.split('/', 1)[1]}.bundle", 'Git bundles (*.bundle)')
        if path:
            self._start('download_bundle', name, path, on_success=self._show_bundle)

    def _show_bundle(self, path):
        self.log.appendPlainText(f'Saved {path}. This includes committed Git history.')

    def upload_backup(self):
        name = self._repository()
        if not name:
            return
        path, _ = QFileDialog.getOpenFileName(self, 'Choose a backup ZIP', '', 'ZIP files (*.zip)')
        if not path:
            return
        create = self.create.isChecked()
        action = 'Create a private repo and upload' if create else 'Upload'
        if self._confirmed('Upload backup ZIP',
                           f'{action} {Path(path).name} to a draft release in private repository {name}?'):
            self._start('upload_backup', path, name, create=create, on_success=self._show_backup)

    def _confirmed(self, title, message):
        return QMessageBox.question(
            self, title, message, QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        ) == QMessageBox.StandardButton.Yes

    def _start(self, operation, *args, on_success, **kwargs):
        self.log.clear()
        self.open_repo.setEnabled(False)
        for button in self.buttons:
            button.setEnabled(False)
        self.on_success = on_success
        self.worker = GitHubTask(operation, *args, **kwargs)
        self.worker.message.connect(self.log.appendPlainText)
        self.worker.done.connect(self._show_success)
        self.worker.failed.connect(self._show_error)
        self.worker.finished.connect(self._finish)
        self.worker.start()

    def _show_error(self, error):
        self.log.appendPlainText(f'Operation stopped: {error}')

    @Slot(object)
    def _show_success(self, result):
        self.on_success(result)

    def _show_repo(self, destination):
        self.repository_url = destination.url
        self.repo.setText(destination.name)
        self.create.setChecked(False)
        self.open_repo.setEnabled(True)
        self.log.appendPlainText(f'Finished. {destination.url}')

    def _show_backup(self, result):
        destination, release_url = result
        self._show_repo(destination)
        self.log.appendPlainText(f'Draft release: {release_url}')

    def _finish(self):
        for button in self.buttons:
            button.setEnabled(True)

    def reject(self):
        if not (self.worker and self.worker.isRunning()):
            super().reject()

    def closeEvent(self, event):
        if self.worker and self.worker.isRunning():
            event.ignore()
        else:
            super().closeEvent(event)
