"""Package selection policies for PS4 base-game and update builds.

Selection controls which independently generated PKG jobs are submitted to the
existing package builder. It never combines a patch payload into a base PKG.
"""
from __future__ import annotations

BUILD_MODES = {
    'selected': 'Selected packages (existing behavior)',
    'separate': 'Base + Update (two separate PKGs)',
    'base': 'Base game only',
    'update': 'Update PKG only',
}


def choose_build_dumps(dumps, mode='selected', *, existing_base=None):
    """Return selected dump objects for a package mode, or raise an actionable error.

    Base/update pairing is scoped to a title ID, not a display name. Patch-only
    builds still require an existing matching base PKG for app_path, which the
    existing builder validates by its full content ID during preflight.
    """
    dumps = list(dumps)
    if mode not in BUILD_MODES:
        raise ValueError(f'Unsupported package build mode: {mode}')
    if not dumps:
        raise ValueError('Check at least one dump row before building.')
    if mode == 'selected':
        return dumps
    allowed = {'separate': {'gd', 'gp'}, 'base': {'gd'}, 'update': {'gp'}}[mode]
    chosen = [dump for dump in dumps if dump.category in allowed]
    if not chosen:
        kind = 'Patch' if mode == 'update' else 'Base' if mode == 'base' else 'Base and Patch'
        raise ValueError(f'This build mode needs a checked {kind} dump row.')
    if mode == 'separate':
        grouped = {}
        for dump in chosen:
            grouped.setdefault(dump.title_id, set()).add(dump.category)
        incomplete = [title_id for title_id, categories in grouped.items()
                      if categories != {'gd', 'gp'}]
        if incomplete:
            raise ValueError(
                'Base + Update requires checked Base and Patch dumps for the SAME '
                'CUSA title ID. Missing matching types for: ' + ', '.join(incomplete)
                + '. Different Tales games are not interchangeable.'
            )
    if mode == 'update':
        if not existing_base:
            raise ValueError(
                'Update-only needs an existing matching base PKG. Select the base '
                'PKG of this SAME CUSA game in Existing base PKG. It is only '
                'referenced during the build, not overwritten or rebuilt.'
            )
        if len({dump.title_id for dump in chosen}) != 1:
            raise ValueError(
                'Update-only with one existing base PKG must target exactly one '
                'CUSA title ID. Build other games in a separate batch.'
            )
    return chosen
