"""v0.5 library enhancements. Additive migration; no save-content mutations."""
from __future__ import annotations
import hashlib, os, re, shutil, uuid
from pathlib import Path
from .enhanced import EnhancedArchive
from .integrations import steam_games, download_steam_cover

VALID_IMAGE_EXT={'.png','.jpg','.jpeg','.webp'}

def canonical_name(name):
    return ' '.join(re.findall(r'[a-z0-9]+',str(name).casefold()))

class LibraryArchive(EnhancedArchive):
    def __init__(self,root):
        super().__init__(root)
        self.conn.executescript('''
        CREATE TABLE IF NOT EXISTS game_covers(
          platform TEXT NOT NULL, game TEXT NOT NULL, filename TEXT NOT NULL,
          source TEXT NOT NULL, PRIMARY KEY(platform,game));
        ''')
        self.covers_dir=self.root/'covers';self.covers_dir.mkdir(exist_ok=True)

    def add_cover(self,platform,game,source):
        if platform not in ('PS3','PC','PS4'):raise ValueError('Invalid platform')
        if not self.conn.execute('SELECT 1 FROM saves WHERE platform=? AND game=?',(platform,game)).fetchone():
            raise ValueError('Game not in archive')
        source=Path(source)
        if source.is_symlink() or not source.is_file() or source.suffix.lower() not in VALID_IMAGE_EXT:
            raise ValueError('Choose a PNG, JPEG or WebP image')
        if source.stat().st_size>5_000_000:raise ValueError('Cover image is over 5 MB')
        with source.open('rb') as stream:
            header=stream.read(16)
        if not (header.startswith(b'\x89PNG\r\n\x1a\n') or header.startswith(b'\xff\xd8') or header.startswith(b'RIFF') and header[8:12]==b'WEBP'):
            raise ValueError('Unsupported image format')
        digest=hashlib.sha256(f'{platform}\0{game}'.encode()).hexdigest()[:24]
        name=f'cover_{digest}{source.suffix.lower()}'
        dest=self.covers_dir/name
        tmp=self.covers_dir/f'.{uuid.uuid4().hex}.tmp'
        try:
            shutil.copyfile(source,tmp)
            tmp.replace(dest)
            self.conn.execute('INSERT INTO game_covers(platform,game,filename,source) VALUES(?,?,?,?) ON CONFLICT(platform,game) DO UPDATE SET filename=excluded.filename,source=excluded.source',(platform,game,name,'local'))
            self.conn.commit()
        finally:tmp.unlink(missing_ok=True)
        return dest

    def cover_for(self,platform,game):
        row=self.conn.execute('SELECT filename FROM game_covers WHERE platform=? AND game=?',(platform,game)).fetchone()
        if row:
            path=self.covers_dir/row['filename']
            if path.is_file():return path
        # Backwards compatibility with v0.3/v0.4 manually cached Steam covers
        legacy=re.sub(r'[^A-Za-z0-9_-]','_',game)[:80]
        for path in sorted(self.covers_dir.glob(legacy+'_*')):
            if path.is_file() and path.suffix.lower() in VALID_IMAGE_EXT:return path
        return None

    def steam_matches(self,game):
        wanted=canonical_name(game)
        return [row for row in steam_games() if canonical_name(row['name'])==wanted]

    def steam_cover(self,platform,game,appid):
        if platform!='PC':raise ValueError('Steam automatic covers are for PC entries only; choose a local image for console games')
        allowed={row['appid'] for row in self.steam_matches(game)}
        if str(appid) not in allowed:raise ValueError('Steam App ID does not match a detected installed game')
        path=download_steam_cover(str(appid),self.covers_dir)
        return self.add_cover(platform,game,path)

    def remove_from_collection(self,cid,platform,game):
        self.conn.execute('DELETE FROM collection_games WHERE collection_id=? AND platform=? AND game=?',(cid,platform,game))
        self.conn.commit()

    def rename_collection(self,cid,name):
        name=' '.join(name.split())[:90]
        if not name:raise ValueError('Collection name required')
        if not self.conn.execute('UPDATE collections SET name=? WHERE id=?',(name,cid)).rowcount:
            raise ValueError('Collection not found')
        self.conn.commit()

    def delete_collection(self,cid):
        # Delete membership and collection, not games or saves.
        self.conn.execute('DELETE FROM collection_games WHERE collection_id=?',(cid,))
        self.conn.execute('DELETE FROM collections WHERE id=?',(cid,));self.conn.commit()
