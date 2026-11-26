"""Drag/drop target for a single character or profile save.

Only local files are accepted. The editor stages every drop into its protected
workspace and runs full decoding before enabling the corresponding tabs.
"""
from pathlib import Path

from PySide6.QtCore import Signal, Qt
from PySide6.QtWidgets import QLabel


class SaveDropZone(QLabel):
    fileDropped = Signal(str)

    def __init__(self, kind, parent=None):
        super().__init__(parent)
        self.kind = kind
        self.setAcceptDrops(True)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setWordWrap(True)
        self.setText(f'Drop {kind} file here\n(or use Load…)')
        self.setMinimumHeight(62)
        self.setStyleSheet('''
            QLabel {
                background: #24202f; border: 2px dashed #74618d;
                border-radius: 9px; color: #c8b8df; padding: 8px;
            }
        ''')

    @staticmethod
    def local_file(mime):
        """Reject URL lists, remote URLs and folder drops."""
        if not mime.hasUrls() or len(mime.urls()) != 1:
            return None
        url = mime.urls()[0]
        if not url.isLocalFile():
            return None
        path = Path(url.toLocalFile())
        if path.is_symlink() or not path.is_file():
            return None
        return str(path)

    def dragEnterEvent(self, event):
        if self.isEnabled() and self.local_file(event.mimeData()):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        if self.isEnabled() and self.local_file(event.mimeData()):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event):
        path = self.local_file(event.mimeData()) if self.isEnabled() else None
        if not path:
            event.ignore()
            return
        event.acceptProposedAction()
        self.fileDropped.emit(path)
