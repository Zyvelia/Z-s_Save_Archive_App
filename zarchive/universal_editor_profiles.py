"""Registered universal save-editor profiles.

A profile chooses the game, platform, file type and codec. Planned platforms
are visible as roadmap entries but cannot be used to edit real saves.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class GameEditorProfile:
    key: str
    game: str
    platform: str
    file_type: str
    codec: str | None
    status: str

    @property
    def editable(self) -> bool:
        return self.codec is not None and self.status == 'supported'


PROFILES = (
    GameEditorProfile('bl3-pc-character', 'Borderlands 3', 'PC', 'Character', 'bl3', 'supported'),
    GameEditorProfile('bl3-ps4-character', 'Borderlands 3', 'PS4', 'Character', 'bl3', 'supported'),
    GameEditorProfile('bl3-pc-profile', 'Borderlands 3', 'PC', 'Profile', 'bl3', 'supported'),
    GameEditorProfile('bl3-ps4-profile', 'Borderlands 3', 'PS4', 'Profile', 'bl3', 'supported'),
    GameEditorProfile('bl3-xbox-character', 'Borderlands 3', 'Xbox', 'Character', None, 'planned'),
    GameEditorProfile('bl2-ps3-character', 'Borderlands 2', 'PS3', 'Character', None, 'planned'),
)


def profile_for(key):
    return next((profile for profile in PROFILES if profile.key == key), None)


def available_profiles():
    return [profile for profile in PROFILES if profile.editable]


def validate_profile(key):
    profile = profile_for(key)
    if profile is None:
        raise ValueError('Unknown editor profile.')
    if not profile.editable:
        raise ValueError(f'{profile.game} {profile.platform} {profile.file_type} is not supported.')
    return profile
