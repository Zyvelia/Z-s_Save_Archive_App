"""Use local game art, then fetch exact Steam matches without blocking the interface."""
from pathlib import Path
import re

from PySide6.QtCore import QObject, QSaveFile, QSize, QUrl, Signal
from PySide6.QtGui import QImage
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest

from .integrations import steam_games
from .library_v05 import canonical_name
from .ui_v04 import cover_icon

# Store IDs for games whose PC saves may be imported from a different storefront.
KNOWN_STEAM_TITLES = {'borderlands 4': '1285190', 'borderlands r 4': '1285190'}
MAX_ART_BYTES = 2_000_000
STEAM_ART = (
    'https://shared.fastly.steamstatic.com/store_item_assets/steam/apps/{appid}/library_hero.jpg',
    'https://cdn.akamai.steamstatic.com/steam/apps/{appid}/header.jpg',
)


class GameArtwork(QObject):
    ready = Signal()

    def __init__(self, archive, parent):
        super().__init__(parent)
        self.archive = archive
        self.network = QNetworkAccessManager(self)
        self.network.setTransferTimeout(8000)
        self.attempted = set()
        self.app_ids = None

    def path(self, game, platform):
        local = self.archive.cover_for(platform, game)
        if local:
            return local
        if platform != 'PC':
            return None
        name = canonical_name(game)
        appid = KNOWN_STEAM_TITLES.get(name)
        if not appid:
            if self.app_ids is None:
                self.app_ids = {}
                for row in steam_games():
                    self.app_ids.setdefault(canonical_name(row['name']), set()).add(row['appid'])
            matches = self.app_ids.get(name, set())
            if len(matches) == 1:
                appid = next(iter(matches))
        if not appid or not re.fullmatch(r'[0-9]{1,12}', appid):
            return None
        hero = self.art_path(appid, 0)
        if hero.is_file():
            return hero
        if appid not in self.attempted:
            self.attempted.add(appid)
            self.fetch(appid, 0)
        header = self.art_path(appid, 1)
        return header if header.is_file() else None

    def art_path(self, appid, index):
        filename = f'steam_{appid}_hero.jpg' if index == 0 else f'steam_{appid}.jpg'
        return self.archive.covers_dir / filename

    def fetch(self, appid, index):
        url = QUrl(STEAM_ART[index].format(appid=appid))
        reply = self.network.get(QNetworkRequest(url))
        reply.downloadProgress.connect(
            lambda received, _: reply.abort() if received > MAX_ART_BYTES else None)
        reply.finished.connect(lambda: self.finished(reply, appid, index))

    def finished(self, reply, appid, index):
        cached = False
        try:
            if reply.error() == QNetworkReply.NetworkError.NoError and reply.bytesAvailable() <= MAX_ART_BYTES:
                data = reply.readAll()
                if bytes(data).startswith(b'\xff\xd8') and not QImage.fromData(data).isNull():
                    file = QSaveFile(str(self.art_path(appid, index)))
                    if file.open(QSaveFile.OpenModeFlag.WriteOnly):
                        if file.write(data) == data.size():
                            cached = file.commit()
                        else:
                            file.cancelWriting()
        finally:
            reply.deleteLater()
        if cached:
            self.ready.emit()
        elif index == 0 and not self.art_path(appid, 1).is_file():
            self.fetch(appid, 1)

    def icon(self, game, platform, size):
        path = self.path(game, platform)
        focus = .7 if path and re.fullmatch(r'steam_[0-9]+_hero\.jpg', path.name) else .5
        return cover_icon(game, platform, path, QSize(size), horizontal_focus=focus)

    def assign(self, game, platform, path):
        if QImage(str(path)).isNull():
            raise ValueError('Choose a readable PNG, JPEG, or WebP image.')
        self.archive.add_cover(platform, game, Path(path))
        self.ready.emit()
