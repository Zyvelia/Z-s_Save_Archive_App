"""Windows AppData layout and safe, explicit legacy preference import.

Large game files and archives are never moved into AppData automatically.
"""
from __future__ import annotations
import json
import os
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path

APP_NAME = 'ZSaveArchive'

@dataclass(frozen=True)
class AppPaths:
    roaming: Path
    local: Path

    @classmethod
    def discover(cls, env=None, home=None):
        env = os.environ if env is None else env
        home = Path.home() if home is None else Path(home)
        roaming = Path(env.get('APPDATA') or home/'AppData'/'Roaming')/APP_NAME
        local = Path(env.get('LOCALAPPDATA') or home/'AppData'/'Local')/APP_NAME
        return cls(roaming, local)

    @property
    def settings(self): return self.roaming/'settings.json'

    def initialize(self):
        for path in (self.roaming, self.local, self.roaming/'presets',
                     self.local/'cache'/'covers', self.local/'cache'/'metadata',
                     self.local/'logs', self.local/'temp', self.local/'crash_reports'):
            path.mkdir(parents=True, exist_ok=True)
        return self

    def load_settings(self):
        try:
            if not self.settings.exists(): return {}
            if self.settings.stat().st_size > 1024*1024: raise ValueError('Settings file is too large')
            data=json.loads(self.settings.read_text(encoding='utf-8'))
            if not isinstance(data,dict): raise ValueError('Settings must be a JSON object')
            return data
        except (OSError,UnicodeError,json.JSONDecodeError,ValueError):
            # Never overwrite invalid settings until the user explicitly saves.
            return {}

    def save_settings(self, values):
        if not isinstance(values,dict): raise ValueError('Expected a dictionary')
        self.initialize()
        serialized=json.dumps(values,indent=2,ensure_ascii=False)
        if len(serialized.encode('utf-8'))>1024*1024:raise ValueError('Settings file too large')
        name=None
        try:
            with tempfile.NamedTemporaryFile(mode='w',encoding='utf-8',dir=self.roaming,
                                             prefix='.settings-',suffix='.tmp',delete=False) as f:
                name=f.name
                f.write(serialized)
            os.replace(name,self.settings)
        finally:
            if name and os.path.exists(name):os.unlink(name)

    def remember_path(self,key,value):
        if key not in {'helper','extractor','source','workspace','ftp_downloads','archive_root','orbis_pub_cmd'}:
            raise ValueError('Unsupported path key')
        settings=self.load_settings()
        settings.setdefault('paths',{})[key]=str(value)
        self.save_settings(settings)

    def path(self,key,default=''):
        return str(self.load_settings().get('paths',{}).get(key,default))

    def folder_sizes(self):
        def size(folder):
            total=0
            if not folder.exists():return 0
            for root,dirs,files in os.walk(folder,followlinks=False):
                dirs[:]=[d for d in dirs if not (Path(root)/d).is_symlink()]
                for file in files:
                    p=Path(root)/file
                    if not p.is_symlink():
                        try:total+=p.stat().st_size
                        except OSError:pass
            return total
        return {key:size(self.local/key) for key in ('cache','logs','temp','crash_reports')}

    def clear_cache(self):
        """Delete only known regenerate-able cache content, never saves, DB or logs."""
        cache=self.local/'cache'
        if cache.is_symlink():raise ValueError('Cache folder cannot be a symlink')
        removed=0
        if cache.exists():
            # Preflight entire cache before deletion so a symlink causes no partial cleanup.
            for root, dirs, files in os.walk(cache, followlinks=False):
                if any((Path(root)/name).is_symlink() for name in dirs+files):
                    raise ValueError('Refusing to delete symlinked cache contents')
            for child in cache.iterdir():
                if child.is_symlink():raise ValueError('Refusing to delete symlinked cache entries')
                if child.is_file():
                    removed+=child.stat().st_size;child.unlink()
                elif child.is_dir():
                    for root,dirs,files in os.walk(child,followlinks=False):
                        if any((Path(root)/n).is_symlink() for n in dirs+files):
                            raise ValueError('Refusing to delete symlinked cache contents')
                    removed+=sum(p.stat().st_size for p in child.rglob('*') if p.is_file())
                    shutil.rmtree(child)
        self.initialize()
        return removed

    def import_legacy_json(self, source):
        """Import an existing JSON settings file ONLY if no current config exists.
        Original stays untouched; return False when there is nothing safe to import.
        """
        source=Path(source)
        if self.settings.exists() or source.is_symlink() or not source.is_file() or source.stat().st_size>1024*1024:
            return False
        value=json.loads(source.read_text(encoding='utf-8'))
        if not isinstance(value,dict):raise ValueError('Legacy settings must be an object')
        self.save_settings(value)
        return True
