"""Explicit GitHub publishing and recovery operations for Save Archive."""
from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
from tempfile import TemporaryDirectory
from uuid import uuid4
from zipfile import is_zipfile


SOURCE_FILES = {
    '.gitignore', 'main.py', 'update_archive.py', 'requirements.txt',
    'ZSaveArchive.iss', 'README.txt', 'UI_Preview.html', 'Build_All.bat',
    'Build_Installer.bat', 'Build_Windows.bat', 'Find_Inno_Setup.bat',
    'Start_Archive.bat', 'Update_Archive.bat',
}
SOURCE_TREES = {
    'zarchive': {'.py'}, 'tests': {'.py'}, 'assets': {'.png', '.ico', '.bat'},
    'editor_definitions': {'.json'}, 'ps3-stats': {'.c', '.h', '.png', '.xml'},
    'ps3-controller-tester': {'.c', '.h', '.png', '.xml'},
}
DOWNLOAD_NAME = re.compile(r'(?:SHA256SUMS\.txt|Controller_Tester\.pkg|PS3_Stats\.pkg|'
                           r'Z_Save_Archive_v\d+\.\d+\.\d+_Source\.zip)')


def repository_name(value: str) -> str:
    value = value.strip()
    if value.startswith('https://github.com/'):
        value = value[len('https://github.com/'):].rstrip('/').removesuffix('.git')
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9-]{0,38}/[A-Za-z0-9_.-]{1,100}', value):
        raise ValueError('Enter a GitHub repository as owner/name or its github.com URL.')
    if value.split('/', 1)[1] in {'.', '..'}:
        raise ValueError('Enter a valid GitHub repository name.')
    return value


def _linked(path: Path) -> bool:
    info = path.lstat()
    return stat.S_ISLNK(info.st_mode) or bool(
        getattr(info, 'st_file_attributes', 0) & getattr(stat, 'FILE_ATTRIBUTE_REPARSE_POINT', 0x400)
    )


def _source_files(root: Path):
    required = (root / 'main.py', root / 'ZSaveArchive.iss', root / 'zarchive' / '__init__.py')
    if not all(path.is_file() for path in required):
        raise ValueError('Choose a Git checkout, a .bundle, or an extracted Save Archive source folder.')

    for directory, folders, files in os.walk(root, followlinks=False):
        parent = Path(directory)
        relative = parent.relative_to(root)
        if parent == root:
            folders[:] = [name for name in folders if name in SOURCE_TREES or name == 'downloads']
        elif relative.parts[0] == 'downloads':
            folders.clear()
        folders[:] = [name for name in folders if not name.startswith('.') and name != '__pycache__']
        for name in folders:
            if _linked(parent / name):
                raise ValueError(f'Source contains a linked directory: {parent / name}')
        for name in files:
            path = parent / name
            if parent == root:
                allowed = name in SOURCE_FILES
            elif relative.parts[0] == 'downloads':
                allowed = DOWNLOAD_NAME.fullmatch(name)
            else:
                allowed = not name.startswith('.') and (
                    path.suffix.lower() in SOURCE_TREES[relative.parts[0]] or name == 'Makefile'
                )
            if allowed:
                if _linked(path) or not path.is_file():
                    raise ValueError(f'Expected a regular source file: {path}')
                yield path.relative_to(root)


@dataclass(frozen=True)
class Destination:
    name: str
    private: bool
    default_branch: str | None

    @property
    def url(self) -> str:
        return f'https://github.com/{self.name}'


class GitHubManager:
    def __init__(self, progress=None):
        self.progress = progress or (lambda message: None)

    @staticmethod
    def _program(name):
        path = shutil.which(name)
        if not path:
            raise ValueError(f'Install {"GitHub CLI (gh)" if name == "gh" else "Git"}, then reopen Save Archive.')
        return path

    def _run(self, program, *args, cwd=None, input_text=None):
        env = dict(os.environ, GH_HOST='github.com', GH_PROMPT_DISABLED='1', GIT_TERMINAL_PROMPT='0')
        for name in ('GIT_DIR', 'GIT_WORK_TREE', 'GIT_INDEX_FILE', 'GIT_COMMON_DIR', 'GIT_NAMESPACE'):
            env.pop(name, None)
        result = subprocess.run(
            [self._program(program), *args], cwd=cwd, env=env, input=input_text,
            stdin=subprocess.DEVNULL if input_text is None else None, capture_output=True,
            encoding='utf-8', errors='replace', timeout=900, check=False,
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0),
        )
        if result.returncode:
            detail = (result.stderr.strip() or result.stdout.strip())[-3500:]
            raise RuntimeError(f'{program} {args[0]} failed. {detail}')
        return result.stdout.strip()

    def _git(self, *args, cwd=None):
        return self._run('git', *args, cwd=cwd)

    def _remote_git(self, *args, cwd=None):
        return self._git('-c', 'credential.helper=', '-c',
                         'credential.helper=!gh auth git-credential', *args, cwd=cwd)

    def sign_in(self):
        """Start the interactive GitHub CLI login in its own Windows console."""
        if os.name != 'nt':
            raise ValueError('Run gh auth login --hostname github.com in a terminal, then check sign-in here.')
        subprocess.Popen(
            [self._program('gh'), 'auth', 'login', '--hostname', 'github.com', '--git-protocol', 'https', '--web'],
            creationflags=subprocess.CREATE_NEW_CONSOLE,
        )

    def account(self) -> str:
        return self._run('gh', 'api', '--hostname', 'github.com', 'user', '--jq', '.login')

    def destination(self, name: str) -> Destination:
        name = repository_name(name)
        info = json.loads(self._run('gh', 'repo', 'view', name, '--json',
                                    'nameWithOwner,isPrivate,defaultBranchRef,viewerPermission'))
        if info['viewerPermission'] not in {'ADMIN', 'MAINTAIN', 'WRITE'}:
            raise ValueError(f'Your GitHub account does not have write access to {name}.')
        canonical = repository_name(info['nameWithOwner'])
        if canonical.casefold() != name.casefold():
            raise ValueError(f'GitHub resolved that repository to {canonical}. Enter that name explicitly.')
        return Destination(canonical, info['isPrivate'], (info['defaultBranchRef'] or {}).get('name'))

    def create(self, name: str, *, private=True, initialize=False) -> Destination:
        name = repository_name(name)
        args = ['repo', 'create', name, '--private' if private else '--public']
        if initialize:
            args.append('--add-readme')
        self._run('gh', *args)
        self.progress(f'Created https://github.com/{name}. If any later step fails, use this existing repository on retry.')
        return self.destination(name)

    def _checkout(self, root: Path):
        if not root.is_dir() or not (root / '.git').exists():
            raise ValueError('Select the root of a local Git checkout.')
        self._git('rev-parse', '--verify', 'HEAD', cwd=root)

    def save_bundle(self, source: str, filename: str) -> Path:
        root = Path(source).expanduser().resolve(strict=True)
        self._checkout(root)
        return self._write_bundle(root, filename)

    def download_bundle(self, name: str, filename: str) -> Path:
        name = repository_name(name)
        with TemporaryDirectory(prefix='zarchive-github-') as temporary:
            stage = Path(temporary)
            self.progress(f'Downloading Git history from {name}…')
            self._remote_git('clone', '--bare', f'https://github.com/{name}.git', '.', cwd=stage)
            return self._write_bundle(stage, filename)

    def _write_bundle(self, root: Path, filename: str) -> Path:
        output = Path(filename).expanduser().absolute()
        if output.suffix.lower() != '.bundle':
            raise ValueError('Save Git backups with the .bundle extension.')
        if output.exists():
            raise FileExistsError(f'Choose a new backup filename: {output}')
        with TemporaryDirectory(prefix='zarchive-bundle-', dir=output.parent) as stage:
            bundle = Path(stage) / 'backup.bundle'
            self._git('bundle', 'create', str(bundle), '--all', cwd=root)
            self._git('bundle', 'verify', str(bundle), cwd=root)
            with bundle.open('rb') as source, output.open('xb') as sink:
                try:
                    shutil.copyfileobj(source, sink)
                    sink.flush()
                except BaseException:
                    sink.close()
                    output.unlink()
                    raise
        return output

    def _snapshot(self, root: Path, files, target: Destination, branch: str, stage: Path):
        self._git('init', '-q', cwd=stage)
        ref = f'refs/heads/{branch}'
        remote = target.url + '.git'
        if self._remote_git('ls-remote', '--heads', remote, ref, cwd=stage):
            self._remote_git('fetch', '--no-tags', remote, ref, cwd=stage)
            self._git('checkout', '--detach', 'FETCH_HEAD', cwd=stage)
        for relative in files:
            destination = stage / relative
            if any(_linked(path) for path in (destination, *destination.parents)
                   if path != stage and path.is_relative_to(stage) and (path.exists() or path.is_symlink())):
                raise ValueError(f'The destination contains a linked source path: {relative}')
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(root / relative, destination)

        # Stage only the selected source files. Git does not touch the original folder.
        self._run('git', '--literal-pathspecs', 'add', '-f', '--pathspec-from-file=-', '--pathspec-file-nul',
                  cwd=stage, input_text=''.join(f'{path.as_posix()}\0' for path in files))
        if self._git('diff', '--cached', '--name-only', cwd=stage):
            account = self.account()
            self._git('-c', f'user.name={account}', '-c', f'user.email={account}@users.noreply.github.com',
                      'commit', '--no-gpg-sign', '-m', 'Publish Save Archive source', cwd=stage)
        else:
            self.progress('The selected source files already match the destination branch.')

    def publish(self, source: str, name: str, branch: str, *, create=False,
                private=True, all_refs=False, snapshot=False) -> Destination:
        root = Path(source).expanduser().resolve(strict=True)
        bundle = root.is_file() and root.suffix.lower() == '.bundle'
        if snapshot and (all_refs or not root.is_dir()):
            raise ValueError('Source snapshots require an app source folder and one destination branch.')
        checkout = not snapshot and root.is_dir() and (root / '.git').exists()
        if not all_refs:
            self._git('check-ref-format', f'refs/heads/{branch}')
        with TemporaryDirectory(prefix='zarchive-github-') as temporary:
            stage = Path(temporary)
            if bundle:
                self._git('clone', '--bare', str(root), '.', cwd=stage)
            elif checkout:
                self._checkout(root)
                stage = root
                if self._git('status', '--porcelain', cwd=root):
                    self.progress('Local changes are present. Git will upload committed history only.')
            elif root.is_dir() and not all_refs:
                files = list(_source_files(root))
            elif all_refs:
                raise ValueError('Publishing all branches and tags requires a Git checkout or .bundle backup.')
            else:
                raise ValueError('Choose a Git checkout, a .bundle, or an extracted Save Archive source folder.')
            if checkout or bundle:
                self._git('rev-parse', '--verify', 'HEAD', cwd=stage)

            target = self.create(name, private=private) if create else self.destination(name)
            self.progress(f'Destination: {target.url} ({"private" if target.private else "public"})')
            if not (checkout or bundle):
                self._snapshot(root, files, target, branch, stage)
            self.progress('Pushing local commits to GitHub…')
            refs = ('--atomic', '--tags', 'refs/heads/*:refs/heads/*') if all_refs else (f'HEAD:refs/heads/{branch}',)
            self._remote_git('push', target.url + '.git', *refs, cwd=stage)
        return target

    def upload_backup(self, filename: str, name: str, *, create=False):
        path = Path(filename).expanduser().resolve(strict=True)
        if path.suffix.lower() != '.zip' or not path.is_file() or not is_zipfile(path) or '#' in str(path):
            raise ValueError('Choose a valid backup .zip with no # character in its path.')
        if path.stat().st_size >= 2 * 1024**3:
            raise ValueError('GitHub release assets must be smaller than 2 GiB.')
        target = self.create(name, initialize=True) if create else self.destination(name)
        if not target.private:
            raise ValueError('Backup uploads require a private GitHub repository.')
        if not target.default_branch:
            raise ValueError('Publish source or initialize the empty repository before uploading a backup.')
        tag = f'save-archive-backup-{uuid4().hex[:12]}'
        self.progress(f'Uploading {path.name} as a draft release asset in {target.name}. Draft tag: {tag}')
        url = self._run('gh', 'release', 'create', tag, str(path), '--repo', target.name,
                        '--draft', '--title', f'Save Archive backup {tag[-12:]}', '--notes', 'Save Archive backup ZIP.')
        return target, url
