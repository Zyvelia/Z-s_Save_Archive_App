"""Match local save locations to PC game names before archive import."""
from __future__ import annotations

import re
from pathlib import Path

from .workflows_v07 import discover_game_locations

PROVIDERS = ('All sources', 'Steam', 'Epic Games', 'GOG Galaxy', 'Xbox / Microsoft Store')


def game_key(name):
    return re.sub(r'[^a-z0-9]', '', name.casefold().replace('’', "'"))


def detect_pc_saves(archive, provider='All sources'):
    if provider not in PROVIDERS:
        raise ValueError('Unknown PC game source')
    all_sources = provider == PROVIDERS[0]
    steam = archive.steam_installations() if all_sources or provider == 'Steam' else {'games': [], 'libraries': []}
    installations = [({'game': row['name'], 'installation': row['installation']}, 'Steam')
                     for row in steam['games'] if 'installation' in row]
    for source, method in (('Epic Games', archive.epic_installations), ('GOG Galaxy', archive.gog_installations)):
        if all_sources or provider == source:
            installations.extend((row, source) for row in method())
    installed = [(row['name'], 'Steam') for row in steam['games']]
    installed.extend((row['game'], source) for row, source in installations if source != 'Steam')
    known_names = {game_key(name): (name, source) for name, source in installed}
    candidates = {}

    def add(game, path, source, *, selected=True):
        location = Path(path)
        try:
            if location.is_symlink() or getattr(location, 'is_junction', lambda: False)():
                return
            resolved = location.resolve(strict=True)
            if not resolved.is_dir() or not any(resolved.iterdir()):
                return
            root = archive.root.resolve()
            if resolved == root or resolved in root.parents or root in resolved.parents:
                return
        except (OSError, RuntimeError):
            return
        key = str(resolved).casefold()
        if key not in candidates:
            candidates[key] = {'game': game, 'path': str(resolved), 'source': source, 'selected': selected}

    for row in archive.candidate_paths():
        if not row['exists']:
            continue
        game, source = known_names.get(game_key(row['game']), (row['game'], 'Known save path'))
        if all_sources or source == provider:
            add(game, row['path'], source)
    if installed:
        for row in discover_game_locations(games=[{'name': name} for name, _ in installed]):
            add(row['name'], row['path'], known_names[game_key(row['name'])][1])

    # Steam stores these under a Steam account and an exact app ID. Use the
    # remote folder and leave remotecache.vdf and other metadata outside it.
    app_names = {row['appid']: row['name'] for row in steam['games'] if row['appid'].isdigit()}
    steam_roots = {Path(library) / 'userdata' for library in steam['libraries']}
    for userdata in steam_roots:
        try:
            accounts = list(userdata.iterdir()) if userdata.is_dir() else []
        except OSError:
            continue
        for account in accounts:
            if not account.name.isdigit() or account.is_symlink() or not account.is_dir():
                continue
            try:
                for app in account.iterdir():
                    if app.name in app_names and not app.is_symlink():
                        add(app_names[app.name], app / 'remote', 'Steam Cloud cache')
            except OSError:
                continue

    for row, source in installations:
        install = Path(row['installation'])
        if not install.is_absolute():
            continue
        for child in ('Saves', 'SaveGames', 'Saved/SaveGames'):
            add(row['game'], install / child, source, selected=False)
    if all_sources:
        for row in archive.game_paths():
            if row['available']:
                add(row['game'], row['location'], 'Registered path', selected=False)
    if all_sources or provider == PROVIDERS[-1]:
        for row in archive.xbox_candidates():
            path = Path(row['candidate'])
            if path.name.casefold() == 'wgs':
                add(row['package'], path, 'Xbox save container', selected=False)

    return sorted(candidates.values(), key=lambda row: (row['game'].casefold(), row['path'].casefold()))


def import_detected_saves(archive, selections, progress=None):
    results = []
    for index, row in enumerate(selections, 1):
        if progress is not None:
            progress(f"Importing {index}/{len(selections)} · {row['game']}")
        try:
            archive.import_pc_save(Path(row['path']), row['game'])
        except ValueError as exc:
            status = 'Already archived' if 'SHA-256 duplicate' in str(exc) else str(exc)
        except OSError as exc:
            status = str(exc)
        else:
            status = 'Imported'
        results.append(status)
    return results
