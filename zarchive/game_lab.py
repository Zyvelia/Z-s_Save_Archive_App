"""PS4-first game research tracker and safe, read-only save tools.
Separate SQLite database. Never overwrites source saves or archive records.
"""
from __future__ import annotations
import hashlib
import json
import os
import re
import sqlite3
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path

PLATFORMS = ("PS4", "PS3", "PC", "Switch")
STAGES = ("Not started", "Analyzing", "Values discovered",
          "Editor in development", "Testing", "Verified", "Published")
MAX_FILE = 64 * 1024 * 1024
MAX_PACKAGE = 512 * 1024 * 1024
MAX_PACKAGE_FILES = 1000

def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")

def atomic_write(path, content):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = None
    try:
        with tempfile.NamedTemporaryFile(prefix=".game-lab-", dir=path.parent, delete=False) as fh:
            tmp = Path(fh.name)
            fh.write(content)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    finally:
        if tmp is not None:
            tmp.unlink(missing_ok=True)

class GameLabStore:
    """Game development records stored outside the main archive database."""
    def __init__(self, archive_root):
        folder = Path(archive_root) / "game_lab"
        folder.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(folder / "game_lab.sqlite3")
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("""CREATE TABLE IF NOT EXISTS projects (
            id INTEGER PRIMARY KEY,
            game TEXT NOT NULL, platform TEXT NOT NULL, status TEXT NOT NULL,
            title_id TEXT NOT NULL DEFAULT '', game_version TEXT NOT NULL DEFAULT '',
            editable_values TEXT NOT NULL DEFAULT '', notes TEXT NOT NULL DEFAULT '',
            updated_at TEXT NOT NULL)""")
        self.connection.commit()

    def close(self):
        self.connection.close()

    def list(self, query="", platform="All", status="All"):
        rows = [dict(row) for row in self.connection.execute(
            "SELECT * FROM projects ORDER BY updated_at DESC, game COLLATE NOCASE")]
        query = query.strip().casefold()
        return [row for row in rows
                if (not query or any(query in str(row[k]).casefold()
                    for k in ("game", "title_id", "editable_values", "notes")))
                and (platform == "All" or row["platform"] == platform)
                and (status == "All" or row["status"] == status)]

    def save(self, *, game, platform, status, title_id="", game_version="",
             editable_values="", notes="", record_id=None):
        game = game.strip()
        title_id = title_id.strip().upper()
        if not game or len(game) > 140:
            raise ValueError("Game name must contain 1–140 characters")
        if platform not in PLATFORMS or status not in STAGES:
            raise ValueError("Invalid platform or development status")
        if title_id and not re.fullmatch(r"[A-Z0-9_-]{1,80}", title_id):
            raise ValueError("Invalid game title ID")
        if len(game_version) > 80 or len(editable_values) > 5000 or len(notes) > 10000:
            raise ValueError("Text exceeds allowed length")
        values = (game, platform, status, title_id, game_version,
                  editable_values, notes, utc_now())
        with self.connection:
            if record_id is None:
                return self.connection.execute(
                    """INSERT INTO projects
                    (game,platform,status,title_id,game_version,editable_values,notes,updated_at)
                    VALUES (?,?,?,?,?,?,?,?)""", values).lastrowid
            cursor = self.connection.execute(
                """UPDATE projects SET game=?,platform=?,status=?,title_id=?,
                game_version=?,editable_values=?,notes=?,updated_at=? WHERE id=?""",
                values + (int(record_id),))
            if not cursor.rowcount:
                raise ValueError("Record not found")
            return int(record_id)

    def delete(self, record_id):
        with self.connection:
            self.connection.execute("DELETE FROM projects WHERE id=?", (int(record_id),))

    def export_json(self, path):
        atomic_write(path, json.dumps({"schema_version": 1,
            "generated_at": utc_now(), "projects": self.list()},
            ensure_ascii=False, indent=2).encode("utf-8"))

def inspect_file(path):
    path = Path(path)
    if path.is_symlink() or not path.is_file():
        raise ValueError("Choose an existing regular file")
    size = path.stat().st_size
    if size > MAX_FILE:
        raise ValueError("Inspection is limited to 64 MiB per file")
    data = path.read_bytes()
    if len(data) != size:
        raise ValueError("Save changed during inspection")
    hint = "Unknown binary"
    if data.startswith(b"PK\x03\x04"):
        hint = "ZIP-like"
    elif data.startswith(b"\x1f\x8b"):
        hint = "GZIP-like"
    elif data.lstrip().startswith((b"{", b"[")):
        try:
            json.loads(data.decode("utf-8"))
            hint = "JSON"
        except (UnicodeError, ValueError):
            pass
    elif data.lstrip().startswith((b"<?xml", b"<SaveGame")):
        hint = "Possibly XML"
    return {"file": path.name, "size": size,
            "sha256": hashlib.sha256(data).hexdigest(),
            "header_hex": data[:64].hex(" "), "format_hint": hint}

def compare_files(before, after, max_ranges=200):
    left = inspect_file(before)
    right = inspect_file(after)
    a, b = Path(before).read_bytes(), Path(after).read_bytes()
    if hashlib.sha256(a).hexdigest() != left["sha256"] or hashlib.sha256(b).hexdigest() != right["sha256"]:
        raise ValueError("Save changed while comparing")
    ranges, start, count, total = [], None, 0, min(len(a), len(b))
    for i in range(total):
        if a[i] != b[i]:
            count += 1
            if start is None:
                start = i
        elif start is not None:
            if len(ranges) < max_ranges:
                ranges.append({"offset": start, "length": i-start,
                    "before": a[start:min(i,start+16)].hex(" "),
                    "after": b[start:min(i,start+16)].hex(" ")})
            start = None
    if start is not None and len(ranges) < max_ranges:
        ranges.append({"offset": start, "length": total-start,
            "before": a[start:min(total,start+16)].hex(" "),
            "after": b[start:min(total,start+16)].hex(" ")})
    count += abs(len(a)-len(b))
    if len(a) != len(b) and len(ranges) < max_ranges:
        ranges.append({"offset": total, "length": abs(len(a)-len(b)),
                       "note": "File length differs"})
    return {"original": left, "modified": right, "changed_bytes": count,
            "ranges": ranges, "truncated": len(ranges) >= max_ranges,
            "warning": "Byte differences are candidates, not proven editable fields."}

def package_save(folder, destination, metadata):
    """Creates a local ZIP, never uploads a save or modifies its source."""
    root = Path(folder)
    if root.is_symlink() or not root.is_dir():
        raise ValueError("Choose a regular save folder")
    root = root.resolve(strict=True)
    destination = Path(destination).resolve()
    if destination == root or root in destination.parents:
        raise ValueError("Output must be outside the source folder")
    if not isinstance(metadata, dict) or metadata.get("platform") not in PLATFORMS:
        raise ValueError("Valid platform metadata is required")
    files, size = [], 0
    for p in sorted(root.rglob("*")):
        if p.is_symlink():
            raise ValueError("Symlinks are not allowed")
        if not p.is_file():
            continue
        if len(files) >= MAX_PACKAGE_FILES:
            raise ValueError("Too many files")
        size += p.stat().st_size
        if size > MAX_PACKAGE:
            raise ValueError("Package exceeds 512 MiB")
        files.append((p, p.relative_to(root).as_posix()))
    if not files:
        raise ValueError("Folder has no files")
    manifest = {"schema_version": 1, "generated_at": utc_now(),
                "metadata": {k: str(metadata.get(k, ""))[:5000] for k in
                    ("game", "platform", "title_id", "game_version", "variant", "notes")},
                "files": []}
    for p, relative in files:
        digest = hashlib.sha256()
        with p.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1048576), b""):
                digest.update(chunk)
        manifest["files"].append({"path": relative, "size": p.stat().st_size,
                                  "sha256": digest.hexdigest()})
    destination.parent.mkdir(parents=True, exist_ok=True)
    tmp = None
    try:
        with tempfile.NamedTemporaryFile(dir=destination.parent,
                                         prefix=".save-package-", suffix=".zip", delete=False) as f:
            tmp = Path(f.name)
        with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
            for path, relative in files:
                archive.write(path, "save/" + relative)
            archive.writestr("metadata.json", json.dumps(manifest, indent=2, ensure_ascii=False))
            archive.writestr("README.txt",
                "Z's Save Archive community save. Check personal data before sharing.\\n"
                "Import and resign requirements depend on game and platform.\\n")
        with zipfile.ZipFile(tmp) as archive:
            if archive.testzip() is not None:
                raise ValueError("ZIP integrity verification failed")
        os.replace(tmp, destination)
        return destination
    finally:
        if tmp is not None:
            tmp.unlink(missing_ok=True)

# Descriptors are informational only; no external Python code is loaded.
BUILTIN_GAME_PLUGINS = (
    {"game": "Borderlands 3", "platform": "PS4", "support": "External editor",
     "notes": "Existing Borderlands workspace launches an external editor for decrypted PS4 saves."},
    {"game": "Tiny Tina's Wonderlands", "platform": "PS4", "support": "External editor",
     "notes": "Uses existing Borderlands workspace for decrypted PS4 exports."},
)
