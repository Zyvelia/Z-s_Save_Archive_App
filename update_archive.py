"""Update an extracted Windows source distribution of Z's Save Archive."""
import hashlib
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import sys
from tempfile import TemporaryDirectory, mkdtemp
from urllib.request import urlopen
from zipfile import ZipFile

DOWNLOADS = "https://raw.githubusercontent.com/Zyvelia/Z-s_Save_Archive_App/main/downloads/"
PACKAGE = re.compile(r"([a-f0-9]{64})\s+Z_Save_Archive_v(\d+\.\d+\.\d+)_Source\.zip")
VERSION = re.compile(r'^#define AppVersion "(\d+\.\d+(?:\.\d+)?)"$', re.MULTILINE)
SOURCE_DIRS = {"assets", "editor_definitions", "tests", "zarchive"}
ROOT_SUFFIXES = {".bat", ".html", ".iss", ".md", ".py", ".txt"}
SOURCE_SUFFIXES = {".ico", ".json", ".png", ".py"}


def version_at(folder):
    match = VERSION.search((folder / "ZSaveArchive.iss").read_text(encoding="utf-8"))
    if not match:
        raise ValueError("Could not read the source version in ZSaveArchive.iss.")
    return match[1]


def download(name, limit):
    with urlopen(DOWNLOADS + name, timeout=30) as response:
        data = response.read(limit + 1)
    if len(data) > limit:
        raise ValueError(f"The download exceeded its size limit: {name}")
    return data


def is_link(path):
    try:
        info = path.lstat()
    except FileNotFoundError:
        return False
    return stat.S_ISLNK(info.st_mode) or bool(
        getattr(info, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    )


def source_paths(archive):
    seen = set()
    size = 0
    for member in archive.infolist():
        if member.is_dir():
            continue
        path = PurePosixPath(member.filename)
        if (not path.parts or any(not re.fullmatch(r"[A-Za-z0-9_ .-]+", part)
                                  or part in {".", ".."} or part.endswith((".", " "))
                                  or re.fullmatch(r"(?i:CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])", part.split(".")[0])
                                  for part in path.parts)
                or path.as_posix() != member.filename
                or stat.S_ISLNK(member.external_attr >> 16)):
            raise ValueError(f"Unsafe ZIP entry: {member.filename}")
        if len(path.parts) == 1:
            allowed = path.suffix in ROOT_SUFFIXES or path.name == ".gitignore"
        else:
            allowed = path.parts[0] in SOURCE_DIRS and path.suffix in SOURCE_SUFFIXES
        if not allowed or member.filename.lower() in seen:
            raise ValueError(f"Unexpected or duplicate ZIP entry: {member.filename}")
        seen.add(member.filename.lower())
        size += member.file_size
        if size > 128 * 1024 * 1024 or len(seen) > 4000:
            raise ValueError("The source ZIP is larger than expected.")
        yield member, Path(*path.parts)


def install(root, staged, paths, scratch):
    changed = []
    for relative in paths:
        destination = root / relative
        for parent in destination.parents:
            if parent == root:
                break
            if is_link(parent):
                raise ValueError(f"Refusing to update through a link: {parent}")
        if is_link(destination) or (destination.exists() and not destination.is_file()):
            raise ValueError(f"Expected a regular source file: {destination}")
        if not destination.exists() or destination.read_bytes() != (staged / relative).read_bytes():
            changed.append(relative)
    if not changed:
        return None

    backup_root = root / ".update-backups"
    if is_link(backup_root):
        raise ValueError(f"Refusing to use a linked backup folder: {backup_root}")
    backup_root.mkdir(exist_ok=True)
    backup = Path(mkdtemp(prefix="before-update-", dir=backup_root))
    original = set()
    for relative in changed:
        destination = root / relative
        if destination.exists():
            saved = backup / relative
            saved.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(destination, saved)
            original.add(relative)

    applied = []
    try:
        for relative in changed:
            destination = root / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            (staged / relative).replace(destination)
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
    return backup


def update(root):
    if (root / ".git").exists():
        raise ValueError("This folder is a Git checkout. Use git pull here.")
    if not (root / "main.py").is_file():
        raise ValueError("Put this script beside main.py in your extracted Save Archive folder.")
    current = version_at(root)
    checksums = download("SHA256SUMS.txt", 64 * 1024).decode("ascii")
    candidates = [match for line in checksums.splitlines() if (match := PACKAGE.fullmatch(line))]
    if len(candidates) != 1:
        raise ValueError("GitHub did not list exactly one desktop source ZIP.")
    digest, latest = candidates[0].groups()
    if tuple(map(int, latest.split("."))) < tuple(map(int, current.split("."))):
        print(f"Keeping local v{current}. GitHub offers the older v{latest}.")
        return

    name = f"Z_Save_Archive_v{latest}_Source.zip"
    print(f"Checking v{current} against GitHub v{latest}…")
    package = download(name, 32 * 1024 * 1024)
    if hashlib.sha256(package).hexdigest() != digest:
        raise ValueError("ZIP checksum mismatch. No files were updated. Try again later.")

    lock = root / ".archive-update.lock"
    descriptor = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    os.close(descriptor)
    try:
        installed = tuple(map(int, version_at(root).split(".")))
        if installed > tuple(map(int, latest.split("."))):
            print("A newer version is already installed.")
            return
        with TemporaryDirectory(prefix=".archive-update-", dir=root) as temp:
            scratch = Path(temp)
            zipped = scratch / name
            zipped.write_bytes(package)
            staged = scratch / "source"
            with ZipFile(zipped) as archive:
                paths = []
                for member, relative in source_paths(archive):
                    destination = staged / relative
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    with archive.open(member) as source, destination.open("xb") as output:
                        shutil.copyfileobj(source, output)
                    paths.append(relative)
            required = ("main.py", "ZSaveArchive.iss", "zarchive/__init__.py", "update_archive.py")
            if not all((staged / name).is_file() for name in required) or version_at(staged) != latest:
                raise ValueError("The ZIP is missing source files or has an unexpected version.")
            # Apply the version file only after the other files are in place.
            paths.sort(key=lambda path: path.name == "ZSaveArchive.iss")
            backup = install(root, staged, paths, scratch)
        if backup is None:
            print(f"You're already up to date (v{latest}).")
        else:
            print(f"Updated source to v{latest}. Previous copies are in {backup}")
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
