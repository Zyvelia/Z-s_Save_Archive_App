"""Synchronize an extracted Z's Save Archive source installation with GitHub."""
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import sys
from tempfile import TemporaryDirectory, mkdtemp
from urllib.request import Request, urlopen
from zipfile import ZipFile

REPOSITORY = "Zyvelia/Z-s_Save_Archive_App"
REVISION_URL = f"https://api.github.com/repos/{REPOSITORY}/commits/main"
ARCHIVE_URL = f"https://codeload.github.com/{REPOSITORY}/zip/"
REVISION = re.compile(r"[0-9a-f]{40}")
SOURCE_DIRS = {"assets", "editor_definitions", "tests", "zarchive", "ps3-controller-tester", "ps3-stats"}
ROOT_SUFFIXES = {".bat", ".html", ".iss", ".md", ".py", ".txt"}
SOURCE_SUFFIXES = {".bat", ".c", ".h", ".ico", ".json", ".png", ".py", ".xml"}
BUNDLED_LAUNCHER = PurePosixPath("assets/Retail2Pkg_ISO_Launcher_v3.zip")
STATE_FILE = Path(".archive-update-files.json")
REQUIRED = {"main.py", "ZSaveArchive.iss", "zarchive/__init__.py", "update_archive.py", "Update_Archive.bat"}
MAX_SOURCE_SIZE = 128 * 1024 * 1024
MAX_SOURCE_FILES = 4000


def latest_revision():
    request = Request(REVISION_URL, headers={"User-Agent": "Z-Save-Archive-Updater", "Accept": "application/vnd.github+json"})
    with urlopen(request, timeout=30) as response:
        data = response.read(1024 * 1024 + 1)
    if len(data) > 1024 * 1024:
        raise ValueError("The GitHub revision response is larger than expected.")
    revision = json.loads(data).get("sha", "")
    if not REVISION.fullmatch(revision):
        raise ValueError("GitHub did not return a valid main commit.")
    return revision


def download_source(revision, destination):
    with urlopen(ARCHIVE_URL + revision, timeout=30) as response, destination.open("xb") as output:
        remaining = MAX_SOURCE_SIZE
        while chunk := response.read(1024 * 1024):
            remaining -= len(chunk)
            if remaining < 0:
                raise ValueError("The GitHub source ZIP is larger than expected.")
            output.write(chunk)


def is_link(path):
    try:
        info = path.lstat()
    except FileNotFoundError:
        return False
    return stat.S_ISLNK(info.st_mode) or bool(
        getattr(info, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    )


def safe_path(value):
    path = PurePosixPath(value)
    if (not path.parts or any(not re.fullmatch(r"[A-Za-z0-9_ .-]+", part)
                              or part in {".", ".."} or part.endswith((".", " "))
                              or re.fullmatch(r"(?i:CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])", part.split(".")[0])
                              for part in path.parts)
            or path.as_posix() != value):
        raise ValueError(f"Unsafe source path: {value}")
    return path


def is_source(path):
    if len(path.parts) == 1:
        return path.name == ".gitignore" or path.suffix.lower() in ROOT_SUFFIXES
    return (path == BUNDLED_LAUNCHER or
            (path.parts[0] in SOURCE_DIRS and not any(
                part.startswith(".") or part == "__pycache__" for part in path.parts[1:]
            ) and (path.suffix.lower() in SOURCE_SUFFIXES or path.name == "Makefile")))


def stage_source(archive, revision, staged):
    paths = {}
    size = 0
    prefix = f"{REPOSITORY.split('/')[1]}-{revision}"
    for member in archive.infolist():
        if member.is_dir():
            continue
        path = safe_path(member.filename)
        if path.parts[0] != prefix or len(path.parts) < 2:
            raise ValueError(f"Unexpected GitHub ZIP entry: {member.filename}")
        relative = PurePosixPath(*path.parts[1:])
        if not is_source(relative):
            continue
        key = relative.as_posix().casefold()
        if key in paths or stat.S_ISLNK(member.external_attr >> 16):
            raise ValueError(f"Linked or duplicate source ZIP entry: {member.filename}")
        paths[key] = Path(*relative.parts)
        size += member.file_size
        if size > MAX_SOURCE_SIZE or len(paths) > MAX_SOURCE_FILES:
            raise ValueError("The extracted source is larger than expected.")
        target = staged / paths[key]
        target.parent.mkdir(parents=True, exist_ok=True)
        with archive.open(member) as source, target.open("xb") as output:
            shutil.copyfileobj(source, output)
    if not REQUIRED <= {path.as_posix() for path in paths.values()}:
        raise ValueError("The GitHub ZIP is missing required app source files.")
    return list(paths.values())


def obsolete_source(root, incoming):
    current_keys = {path.as_posix().casefold() for path in incoming}
    manifest = root / STATE_FILE
    if is_link(manifest):
        raise ValueError("Refusing to read a linked updater file list.")
    previous = set()
    if manifest.exists():
        state = json.loads(manifest.read_text(encoding="utf-8"))
        for name in state["files"]:
            relative = safe_path(name)
            if not is_source(relative):
                raise ValueError(f"Invalid updater file list entry: {name}")
            previous.add(Path(*relative.parts))
    # Include locally added files in app code locations. Editor definitions may be user-created.
    previous.update(path.relative_to(root) for path in root.iterdir()
                    if path.suffix.lower() in {".py", ".bat", ".iss"} and not path.is_dir())
    for folder in SOURCE_DIRS - {"editor_definitions"}:
        directory = root / folder
        if is_link(directory):
            raise ValueError(f"Refusing to scan a linked app folder: {directory}")
        for parent, subfolders, files in os.walk(directory, followlinks=False):
            if "archive.sqlite3" in files:
                subfolders.clear()
                continue
            subfolders[:] = [name for name in subfolders if not name.startswith(".")
                             and name != "__pycache__" and not is_link(Path(parent) / name)]
            for name in files:
                relative = (Path(parent) / name).relative_to(root)
                if is_source(relative):
                    previous.add(relative)
    return sorted(path for path in previous if path.as_posix().casefold() not in current_keys)


def install(root, staged, paths, obsolete, scratch):
    changes = {}
    for relative in [*obsolete, *paths]:
        destination = root / relative
        for parent in destination.parents:
            if parent == root:
                break
            if is_link(parent):
                raise ValueError(f"Refusing to update through a link: {parent}")
            if (parent / "archive.sqlite3").is_file():
                raise ValueError(f"Refusing to update app files inside a save archive: {parent}")
        if is_link(destination) or (destination.exists() and not destination.is_file()):
            raise ValueError(f"Expected a regular source file: {destination}")
        source = staged / relative
        if source.is_file():
            if not destination.exists() or destination.read_bytes() != source.read_bytes():
                changes[relative] = source
        elif destination.exists():
            changes[relative] = None
    if not changes:
        return None, 0

    backup_root = root / ".update-backups"
    if is_link(backup_root):
        raise ValueError(f"Refusing to use a linked backup folder: {backup_root}")
    backup_root.mkdir(exist_ok=True)
    backup = Path(mkdtemp(prefix="before-update-", dir=backup_root))
    original = set()
    for relative in changes:
        destination = root / relative
        if destination.exists():
            saved = backup / relative
            saved.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(destination, saved)
            original.add(relative)

    applied = []
    try:
        for relative, source in changes.items():
            destination = root / relative
            if source is None:
                destination.unlink()
            else:
                destination.parent.mkdir(parents=True, exist_ok=True)
                source.replace(destination)
            applied.append(relative)
    except (OSError, KeyboardInterrupt):
        for relative in reversed(applied):
            destination = root / relative
            try:
                if relative in original:
                    recovery = scratch / "restore"
                    shutil.copy2(backup / relative, recovery)
                    recovery.replace(destination)
                else:
                    destination.unlink()
            except OSError as error:
                print(f"Could not roll back {relative}: {error}", file=sys.stderr)
        print(f"Update interrupted. Previous copies are in {backup}", file=sys.stderr)
        raise
    return backup, sum(source is None for source in changes.values())


def update(root):
    if (root / ".git").exists():
        raise ValueError("This folder is a Git checkout. Use Git to update it.")
    if not (root / "main.py").is_file():
        raise ValueError("Put this script beside main.py in your extracted Save Archive folder.")

    lock = root / ".archive-update.lock"
    descriptor = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    os.close(descriptor)
    try:
        revision = latest_revision()
        print(f"Checking GitHub main at {revision[:7]}…")
        with TemporaryDirectory(prefix=".archive-update-", dir=root) as temp:
            scratch = Path(temp)
            zipped = scratch / "source.zip"
            download_source(revision, zipped)
            staged = scratch / "source"
            with ZipFile(zipped) as archive:
                paths = stage_source(archive, revision, staged)
            obsolete = obsolete_source(root, paths)
            state = {"revision": revision, "files": sorted(path.as_posix() for path in paths)}
            (staged / STATE_FILE).write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
            backup, removed = install(root, staged, [*paths, STATE_FILE], obsolete, scratch)
        if backup is None:
            print(f"App source already matches {revision[:7]}.")
        else:
            print(f"Synced app source to {revision[:7]}. Removed {removed} obsolete source file(s).")
            print(f"Previous copies are in {backup}")
    finally:
        lock.unlink()


if __name__ == "__main__":
    try:
        update(Path(__file__).resolve().parent)
    except FileExistsError as error:
        print(f"Update stopped. A lock or conflicting file exists: {error}", file=sys.stderr)
        sys.exit(1)
    except (Exception, KeyboardInterrupt) as error:
        print(f"Update stopped: {error}", file=sys.stderr)
        sys.exit(1)
