"""Game-owned editor layouts and per-file prerequisites.

Future games should register a dedicated UI factory rather than inheriting
Borderlands 3's character/profile controls or data semantics.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class EditorSection:
    key: str
    label: str
    requires: str


@dataclass(frozen=True)
class GameEditorLayout:
    game: str
    title: str
    sections: tuple[EditorSection, ...]
    designer: str


LAYOUTS = {
    'Borderlands 3': GameEditorLayout(
        'Borderlands 3',
        'BORDERLANDS 3 / SAVE ENGINEERING',
        (
            EditorSection('character', 'Character Save', 'character'),
            EditorSection('profile', 'Profile Data', 'profile'),
        ),
        'bl3',
    ),
}


def layout_for(game):
    """Return an explicitly registered layout, never silently use another game."""
    return LAYOUTS.get(game)


def section_enabled(game, platform, kind, loaded, profiles):
    layout = layout_for(game)
    if layout is None or not platform:
        return False
    section = next((s for s in layout.sections if s.key == kind), None)
    return bool(section and section.requires in loaded and any(
        p.game == game and p.platform == platform and p.editable and
        p.file_type.casefold() == section.requires for p in profiles
    ))
