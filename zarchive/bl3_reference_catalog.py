"""Optional user-provided BL3 item and weapon-part reference catalogs.

Original parser written for Z's Save Archive. Reads CSVs from a file/ZIP chosen
by the user; does not bundle, download, execute or redistribute third-party
editor binaries, source code, game data or catalogs.

Supported schemas:
    Name,Code,Link
    Part,Positives,Negatives,Effects

The reference entries are descriptive only. Item codes still pass through
the existing BL3 game codec before any backup-first save is committed.
"""
from __future__ import annotations

import csv
from dataclasses import dataclass
import io
from pathlib import Path
import re
import zipfile

MAX_SOURCE_BYTES = 6 * 1024 * 1024
MAX_CSV_BYTES = 3 * 1024 * 1024
MAX_ROWS = 20_000
CODE = re.compile(r'^bl3\(([A-Za-z0-9+/=]+)\)$', re.IGNORECASE)


@dataclass(frozen=True)
class CatalogItem:
    name: str
    code: str
    url: str


@dataclass(frozen=True)
class PartInfo:
    part: str
    positives: str
    negatives: str
    effects: str


@dataclass(frozen=True)
class ReferenceCatalog:
    items: tuple[CatalogItem, ...]
    parts: tuple[PartInfo, ...]

    def search_items(self, query: str, limit: int = 120) -> list[CatalogItem]:
        query = query.strip().casefold()
        return [
            item for item in self.items
            if query in item.name.casefold()
        ][:max(0, min(limit, 500))]

    def describe_part(self, asset: str) -> PartInfo | None:
        # BL3 serials typically contain full UE asset paths; CSV names
        # are short suffixes. Match only complete asset name or basename.
        name = str(asset).replace('\\', '/').split('/')[-1].split('.')[-1].casefold()
        return next((p for p in self.parts if p.part.casefold() == name), None)


def normalize_item_code(code: str) -> str:
    """Normalize only a well-formed BL3(...) wrapper; never parse arbitrary text."""
    if not isinstance(code, str):
        raise ValueError('BL3 item code must be a string.')
    code = code.strip()
    if len(code) > 8192 or not CODE.fullmatch(code):
        raise ValueError('Invalid BL3 item code. Expected BL3(base64).')
    return 'BL3(' + code[4:-1] + ')'


def _parse_table(data: bytes):
    if len(data) > MAX_CSV_BYTES:
        raise ValueError('Reference CSV exceeds the 3 MiB import limit.')
    try:
        reader = csv.DictReader(io.StringIO(data.decode('utf-8-sig')))
        if not reader.fieldnames:
            raise ValueError('Reference CSV is missing headers.')
        names = {col.strip().casefold() for col in reader.fieldnames}
        if {'name', 'code', 'link'} <= names:
            kind = 'items'
        elif {'part', 'positives', 'negatives', 'effects'} <= names:
            kind = 'parts'
        else:
            raise ValueError('Unknown catalog CSV headers.')
        records = []
        for index, raw in enumerate(reader):
            if index >= MAX_ROWS:
                raise ValueError('Reference CSV has too many records.')
            line = {str(k).strip().casefold(): str(v or '').strip()
                    for k, v in raw.items() if k is not None}
            if kind == 'items':
                name = line['name'][:180]
                try:
                    code = normalize_item_code(line['code'])
                except ValueError:
                    continue
                if not name:
                    continue
                url = line['link'][:400]
                # Avoid exposing untrusted executable/script links in the UI.
                if not url.startswith('https://www.lootlemon.com/'):
                    url = ''
                records.append(CatalogItem(name, code, url))
            else:
                part = line['part'][:160]
                if part:
                    records.append(PartInfo(
                        part,
                        line['positives'][:1200],
                        line['negatives'][:1200],
                        line['effects'][:1600],
                    ))
        return kind, records
    except UnicodeError as exc:
        raise ValueError('Reference CSV must use UTF-8 encoding.') from exc


def load_reference_catalog(path: str | Path) -> ReferenceCatalog:
    source = Path(path).expanduser()
    if source.is_symlink() or not source.is_file() or source.stat().st_size > MAX_SOURCE_BYTES:
        raise ValueError('Choose a regular ZIP/CSV file under 6 MiB.')
    items: dict[tuple[str, str], CatalogItem] = {}
    parts: dict[str, PartInfo] = {}

    def add_table(data: bytes):
        kind, parsed = _parse_table(data)
        if kind == 'items':
            for item in parsed:
                items.setdefault((item.name.casefold(), item.code), item)
        else:
            for part in parsed:
                parts.setdefault(part.part.casefold(), part)

    if source.suffix.casefold() == '.zip':
        try:
            with zipfile.ZipFile(source) as archive:
                candidates = [
                    info for info in archive.infolist()
                    if not info.is_dir() and
                    info.filename.lower().endswith(('.csv',)) and
                    info.file_size <= MAX_CSV_BYTES and
                    info.compress_size <= MAX_SOURCE_BYTES and
                    not (info.flag_bits & 0x1)
                ]
                if len(candidates) > 20:
                    raise ValueError('ZIP has too many CSV entries.')
                for info in candidates:
                    basename = Path(info.filename.replace('\\', '/')).name.casefold()
                    if basename not in (
                        'lootlemon_bl3_items.csv',
                        'inventory_parts_info_all.csv',
                    ):
                        continue
                    try:
                        add_table(archive.read(info))
                    except ValueError:
                        continue
        except (zipfile.BadZipFile, RuntimeError, OSError) as exc:
            raise ValueError('Unable to read selected catalog ZIP.') from exc
    elif source.suffix.casefold() == '.csv':
        add_table(source.read_bytes())
    else:
        raise ValueError('Choose a ZIP archive or a CSV reference file.')

    if not items and not parts:
        raise ValueError('No supported item or part reference catalogs found.')
    return ReferenceCatalog(tuple(items.values()), tuple(parts.values()))
