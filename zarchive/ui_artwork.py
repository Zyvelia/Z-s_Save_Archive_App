"""Cache official Steam artwork and let the user choose a game image."""
from pathlib import Path
import re
from urllib.parse import urlsplit

from PySide6.QtCore import QObject, QSaveFile, QSize, Qt, QUrl, Signal
from PySide6.QtGui import QIcon, QImage, QPixmap
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest
from PySide6.QtWidgets import (
    QButtonGroup, QDialog, QDialogButtonBox, QFileDialog, QGridLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QSizePolicy, QToolButton, QVBoxLayout,
)

from .integrations import steam_games
from .library_v05 import canonical_name
from .ui_v04 import cover_icon

# Store IDs for games whose PC saves may be imported from a different storefront.
KNOWN_STEAM_TITLES = {'borderlands 4': '1285190', 'borderlands r 4': '1285190'}
MAX_ART_BYTES = 2_000_000
STEAM_ART = {
    'hero': ('Library banner', 'https://shared.fastly.steamstatic.com/store_item_assets/steam/apps/{appid}/library_hero.jpg'),
    'header': ('Store header', 'https://cdn.akamai.steamstatic.com/steam/apps/{appid}/header.jpg'),
    'capsule': ('Store capsule', 'https://cdn.akamai.steamstatic.com/steam/apps/{appid}/capsule_616x353.jpg'),
    'portrait': ('Library portrait', 'https://shared.fastly.steamstatic.com/store_item_assets/steam/apps/{appid}/library_600x900.jpg'),
}


def steam_app_id(value):
    value = value.strip()
    if re.fullmatch(r'[0-9]{1,12}', value):
        return value
    try:
        url = urlsplit(value)
    except ValueError:
        return None
    if url.scheme != 'https' or url.netloc.casefold() != 'store.steampowered.com':
        return None
    match = re.match(r'^/app/([0-9]{1,12})(?:/|$)', url.path)
    return match[1] if match else None


class GameArtwork(QObject):
    ready = Signal()
    preview_ready = Signal(str, str)

    def __init__(self, archive, parent):
        super().__init__(parent)
        self.archive = archive
        self.network = QNetworkAccessManager(self)
        self.network.setTransferTimeout(8000)
        self.pending = set()
        self.attempted = set()
        self.app_ids = None

    def app_id_for(self, game, platform):
        if platform != 'PC':
            return None
        name = canonical_name(game)
        if name in KNOWN_STEAM_TITLES:
            return KNOWN_STEAM_TITLES[name]
        if self.app_ids is None:
            self.app_ids = {}
            for row in steam_games():
                self.app_ids.setdefault(canonical_name(row['name']), set()).add(row['appid'])
        matches = self.app_ids.get(name, set())
        if len(matches) == 1:
            return steam_app_id(next(iter(matches)))
        return None

    def path(self, game, platform):
        local = self.archive.cover_for(platform, game)
        if local:
            return local
        appid = self.app_id_for(game, platform)
        if not appid:
            return None
        hero = self.art_path(appid, 'hero')
        if hero.is_file():
            return hero
        self.fetch(appid, 'hero')
        header = self.art_path(appid, 'header')
        return header if header.is_file() else None

    def art_path(self, appid, variant):
        suffix = '' if variant == 'header' else '_' + variant
        return self.archive.covers_dir / f'steam_{appid}{suffix}.jpg'

    def fetch(self, appid, variant, *, retry=False):
        key = (appid, variant)
        if (key in self.pending or (key in self.attempted and not retry)
                or self.art_path(appid, variant).is_file()):
            return
        self.pending.add(key)
        self.attempted.add(key)
        url = QUrl(STEAM_ART[variant][1].format(appid=appid))
        reply = self.network.get(QNetworkRequest(url))
        reply.downloadProgress.connect(
            lambda received, _: reply.abort() if received > MAX_ART_BYTES else None)
        reply.finished.connect(lambda: self.finished(reply, appid, variant))

    def finished(self, reply, appid, variant):
        cached = False
        try:
            if reply.error() == QNetworkReply.NetworkError.NoError and reply.bytesAvailable() <= MAX_ART_BYTES:
                data = reply.readAll()
                if bytes(data).startswith(b'\xff\xd8') and not QImage.fromData(data).isNull():
                    file = QSaveFile(str(self.art_path(appid, variant)))
                    if file.open(QSaveFile.OpenModeFlag.WriteOnly):
                        if file.write(data) == data.size():
                            cached = file.commit()
                        else:
                            file.cancelWriting()
        finally:
            self.pending.discard((appid, variant))
            reply.deleteLater()
        self.preview_ready.emit(appid, variant)
        if cached and variant in ('hero', 'header'):
            self.ready.emit()
        elif not cached and variant == 'hero':
            self.fetch(appid, 'header')

    def icon(self, game, platform, size):
        path = self.path(game, platform)
        focus = .7 if path and re.fullmatch(r'steam_[0-9]+_hero\.jpg', path.name) else .5
        return cover_icon(game, platform, path, QSize(size), horizontal_focus=focus)

    def assign(self, game, platform, path):
        if QImage(str(path)).isNull():
            raise ValueError('Choose a readable PNG, JPEG, or WebP image.')
        self.archive.add_cover(platform, game, Path(path))
        self.ready.emit()


class ArtworkPicker(QDialog):
    def __init__(self, artwork, game, platform, parent):
        super().__init__(parent)
        self.artwork = artwork
        self.appid = None
        self.preview_buttons = {}
        self.chosen = None
        self.setWindowTitle('Choose Game Art — ' + game)
        self.resize(610, 500)
        layout = QVBoxLayout(self)
        lookup = QHBoxLayout()
        self.steam_link = QLineEdit(artwork.app_id_for(game, platform) or '')
        self.steam_link.setPlaceholderText('Steam App ID or store link')
        self.steam_link.returnPressed.connect(self.load_art)
        lookup.addWidget(self.steam_link, 1)
        load = QPushButton('Load Steam artwork')
        load.clicked.connect(self.load_art)
        load.setAutoDefault(False)
        lookup.addWidget(load)
        layout.addLayout(lookup)

        previews = QGridLayout()
        self.group = QButtonGroup(self)
        self.group.buttonToggled.connect(self.update_selection)
        for index, (variant, (label, _)) in enumerate(STEAM_ART.items()):
            button = QToolButton()
            button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
            button.setText(label)
            button.setCheckable(True)
            button.setEnabled(False)
            button.setIconSize(QSize(232, 126))
            button.setMinimumHeight(166)
            button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
            button.setStyleSheet(
                'QToolButton { padding: 8px; background: #1b1927; border: 1px solid #393449; border-radius: 9px; }'
                'QToolButton:hover, QToolButton:checked { border: 1px solid #b393ff; background: #38304c; }'
            )
            self.group.addButton(button)
            self.preview_buttons[variant] = button
            previews.addWidget(button, index // 2, index % 2)
        layout.addLayout(previews, 1)
        self.status = QLabel('Enter a Steam App ID or choose a local image.')
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel)
        buttons.rejected.connect(self.reject)
        local = buttons.addButton('Choose local image…', QDialogButtonBox.ButtonRole.ActionRole)
        local.clicked.connect(self.choose_local)
        self.use_button = buttons.addButton('Use selected artwork', QDialogButtonBox.ButtonRole.AcceptRole)
        self.use_button.setEnabled(False)
        self.use_button.setAutoDefault(False)
        self.use_button.clicked.connect(self.use_current)
        layout.addWidget(buttons)
        artwork.preview_ready.connect(self.update_preview)
        if self.steam_link.text():
            self.load_art()

    def load_art(self):
        appid = steam_app_id(self.steam_link.text())
        if appid is None:
            self.status.setText('Enter a numeric Steam App ID or a store.steampowered.com game link.')
            return
        self.appid = appid
        checked = self.group.checkedButton()
        if checked:
            self.group.setExclusive(False)
            checked.setChecked(False)
            self.group.setExclusive(True)
        for variant in self.preview_buttons:
            self.artwork.fetch(appid, variant, retry=True)
            self.update_preview(appid, variant)
        self.status.setText('Select an image to use in the dashboard and save inspector.')

    def update_preview(self, appid, variant):
        if appid != self.appid:
            return
        button = self.preview_buttons[variant]
        title = STEAM_ART[variant][0]
        path = self.artwork.art_path(appid, variant)
        pixmap = QPixmap(str(path)) if path.is_file() else QPixmap()
        if pixmap.isNull():
            status = 'Loading…' if (appid, variant) in self.artwork.pending else 'Unavailable'
            button.setText(f'{title} · {status}')
            button.setIcon(QIcon())
            button.setEnabled(False)
        else:
            image = pixmap.scaled(button.iconSize(), Qt.AspectRatioMode.KeepAspectRatio,
                                  Qt.TransformationMode.SmoothTransformation)
            button.setIcon(QIcon(image))
            button.setText(title)
            button.setEnabled(True)
        self.update_selection()

    def update_selection(self, *_):
        checked = self.group.checkedButton()
        self.use_button.setEnabled(bool(checked and checked.isEnabled()))

    def use_current(self):
        checked = self.group.checkedButton()
        if checked and checked.isEnabled():
            variant = next(name for name, button in self.preview_buttons.items() if button is checked)
            self.chosen = self.artwork.art_path(self.appid, variant)
            self.accept()

    def choose_local(self):
        path, _ = QFileDialog.getOpenFileName(self, 'Choose game art', '', 'Images (*.png *.jpg *.jpeg *.webp)')
        if path:
            self.chosen = Path(path)
            self.accept()
