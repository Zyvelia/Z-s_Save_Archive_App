"""TrueAncestor handoff for CFW2OFW converted output.

Stages copies of verified conversion folders. It does not run or bundle TrueAncestor,
claim PKG compatibility, touch the original ISO, or install anything on the PS3.
"""
from __future__ import annotations
import json
import os
import shutil
from pathlib import Path
from .converter_output_v21 import inspect_conversion_output


def prepare_trueancestor(workspace: str | Path, destination: str | Path, *, max_folders: int = 8) -> dict:
    """Copy detected converted game folders to a new TrueAncestor staging directory.

    The supplied destination must not exist. Symlinks and crossing symlinked paths
    inside conversion folders are forbidden to avoid leaking outside content.
    """
    root=Path(workspace).resolve(strict=True)
    report=inspect_conversion_output(root)
    folders=report['folders']
    if not folders:
        raise ValueError('No converted game folders with PARAM.SFO found. Complete CFW2OFW conversion first.')
    if len(folders)>max_folders:
        raise ValueError('Too many converted folders for a single handoff')
    target=Path(destination).expanduser().absolute()
    if target.exists():
        raise FileExistsError('Select a new destination; existing data will never be overwritten')
    if target==root or root in target.parents or target in root.parents:
        raise ValueError('The handoff must be outside the conversion workspace')
    if target.parent.resolve()!=target.parent.absolute():
        # The user may choose a symlinked external location. Reject for predictable copying.
        raise ValueError('Destination parent must not contain symbolic links')
    if not target.parent.is_dir():
        raise ValueError('Destination parent does not exist')
    names=set()
    for f in folders:
        path=root/f['relative_path']
        if path.is_symlink() or not path.is_dir():raise ValueError('Invalid converted folder')
        if f['name'] in names:raise ValueError('Duplicate converted title IDs')
        names.add(f['name'])
        for current, dirs, files in os.walk(path,followlinks=False):
            for name in dirs+files:
                child=Path(current)/name
                if child.is_symlink():raise ValueError('Symlink found in converted game files')
    try:
        game=target/'game';game.mkdir(parents=True,exist_ok=False)
        for f in folders:
            shutil.copytree(root/f['relative_path'],game/f['name'],symlinks=False)
        guidance=('TrueAncestor PKG Repacker: use your trusted installed version and its documented input layout; '
                  'the game/ directory here is a staging handoff, not a finished PKG. '
                  'TrueAncestor BACKUP Retailer is a different tool for backup injection. '
                  'Only use a supported conversion, inspect the builder output, and test on your CFW PS3. '
                  'After generating a PKG, put it inside the conversion workspace for the existing FTP upload step.')
        manifest={'source_title':report['title'],'source_title_id':report['title_id'],
                  'folders':[x['name'] for x in folders], 'workflow':'manual-TrueAncestor-PKG-Repacker',
                  'instructions':guidance}
        (target/'TRUEANCESTOR_README.txt').write_text(guidance+'\n',encoding='utf-8')
        (target/'handoff_manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
        return {'destination':str(target),'folders':manifest['folders'],'instructions':guidance}
    except Exception:
        if target.exists():shutil.rmtree(target)
        raise
