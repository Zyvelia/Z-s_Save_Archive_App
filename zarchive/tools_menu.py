"""Organize legacy Tools actions without changing their callbacks or action identity."""
from __future__ import annotations

CATEGORIES = (
    'PS3 & Connections',
    'PC Discovery & Backups',
    'Save Editing & Metadata',
    'Homebrew, ISO & Packages',
    'Publishing & Releases',
    'Library & Organization',
    'Appearance & Maintenance',
    'Other Tools',
)

def category_for(label: str) -> str:
    name = label.casefold()
    if any(w in name for w in ('homebrew','pkg','package builder','iso →','iso to','xmb assistant')):
        return 'Homebrew, ISO & Packages'
    if any(w in name for w in ('github','release','public website','public html','pages catalog','pre-release','catalog')):
        return 'Publishing & Releases'
    if any(w in name for w in ('ftp','ps3 console','ps3 connection','ps3 compatib','apollo','param.sfo','ps3 metadata')):
        return 'PS3 & Connections'
    if any(w in name for w in ('pc discovery','pc saves','pc backup','pc snapshot','steam','cloud restore','known pc','custom pc','community game path','game path','archive mirror')):
        return 'PC Discovery & Backups'
    if any(w in name for w in ('editor','edit','compare','difference','workflow status','preview files','save variant','save profiles','metadata','privacy check','game completion')):
        return 'Save Editing & Metadata'
    if any(w in name for w in ('tag','collection','pin','timeline','duplicate','name for selected','search all save','fast archive search','large library')):
        return 'Library & Organization'
    if any(w in name for w in ('theme','appearance','density','dashboard','layout','settings','quick actions','activity','health','recovery','background jobs','verify','storage report','startup health')):
        return 'Appearance & Maintenance'
    if any(w in name for w in ('backup','restore')):
        return 'PC Discovery & Backups'
    return 'Other Tools'

def reorganize_tools_menu(button, parent):
    """Retain existing QAction objects and their signal bindings; rebuild only layout."""
    from PySide6.QtWidgets import QInputDialog, QMenu
    menu = button.menu()
    actions = [a for a in menu.actions() if not a.isSeparator()]
    for action in list(menu.actions()):
        menu.removeAction(action)
    sections = {}
    # Put common actions in the root and everything else into concise groups.
    favorites = (
        'PS3 Homebrew Manager', 'PS3 Console Center',
        'Universal Save Editor (game targets + safe copy)',
        'PS3 ISO → XMB Assistant v2.1', 'GitHub Publishing Center',
    )
    for name in favorites:
        for action in actions:
            if action.text() == name:
                menu.addAction(action)
                break
    menu.addSeparator()
    for category in CATEGORIES:
        submenu = menu.addMenu(category)
        sections[category] = submenu
    for action in actions:
        if action.text() in favorites:
            continue
        sections[category_for(action.text())].addAction(action)
    for category, submenu in list(sections.items()):
        if not submenu.actions():
            menu.removeAction(submenu.menuAction())
    menu.insertSeparator(menu.actions()[0])
    def find_tool():
        names = sorted((a.text(), a) for a in actions if a.isEnabled())
        if not names:
            return
        selected, ok = QInputDialog.getItem(parent, 'Find a tool', 'Search or select an action:',
                                            [name for name, _ in names], 0, False)
        if ok:
            for name, action in names:
                if name == selected:
                    action.trigger()
                    break
    find_action = menu.addAction('Find tool…')
    menu.removeAction(find_action)
    menu.insertAction(menu.actions()[0], find_action)
    button.setText('Tools  ▾')
    button.setToolTip('Tools are grouped by function. Use Find tool to locate any action.')
    return {category: len(submenu.actions()) for category, submenu in sections.items()}
