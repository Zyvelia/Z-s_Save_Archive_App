"""Borderlands 3 app-specific layout helpers.

Keeps the game-specific navigation separate from save parsers. Navigation
items become usable only after their corresponding file is loaded.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class Page:
    title: str
    file_kind: str


PAGES = (
    Page('Character Overview', 'character'),
    Page('Profile Overview', 'profile'),
    Page('Inventory & Weapons', 'character'),
    Page('Skills & Progression', 'character'),
    Page('Guardian & Vault', 'profile'),
    Page('Cosmetics & Bank', 'profile'),
    Page('Weapon Workshop', 'character'),
)


def can_open(page, available):
    return page.file_kind in available
