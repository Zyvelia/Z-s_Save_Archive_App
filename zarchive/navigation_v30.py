"""UI action routing for the simplified v3.0 archive interface.

Only navigation changes here; tool callbacks still belong to their original QActions.
The library's organization utilities are accessible from its Organize control.
"""
from __future__ import annotations

DEFAULT_ACTIONS = ('Saves & Backups','Save Editor','PS3 Tools','Releases','Settings','Game Library')


def collect_legacy_actions(menu):
    """Walk nested QMenus and return leaf QActions once, retaining signal bindings."""
    result=[]
    seen=set()
    def walk(node):
        for action in node.actions():
            if action.isSeparator():continue
            if action.menu() is not None:
                walk(action.menu())
            elif id(action) not in seen and action.text().strip() not in ('Find tool…','Find tool...'):
                seen.add(id(action));result.append(action)
    if menu is not None:walk(menu)
    return result


def classify_action(label):
    name=label.casefold()
    if any(x in name for x in ('github','publishing','release','public website','public html','pages catalog','catalog export','pre-release','batch release')):
        return 'Releases'
    if any(x in name for x in ('homebrew','pkg','package builder','iso','xmb','firmware','conversion preflight')):
        return 'PS3 Tools'
    if any(x in name for x in ('ftp','console','ps3 connection','apollo','param.sfo','ps3 metadata','ps3 compatib','lan diagnostics')):
        return 'PS3 Tools'
    if any(x in name for x in ('editor','edit','compare two saves','save variant','save profiles','completion','workflow status','metadata','privacy check','character')):
        return 'Save Editor'
    if any(x in name for x in ('collection','tag','pin','timeline','duplicate hashes','name for selected','search all save','fast archive search','large library','cover image','organize')):
        return 'Game Library'
    if any(x in name for x in ('settings','theme','appearance','density','dashboard layout','reorder dashboard','quick actions','health','recovery','activity','background jobs','archive storage','storage report','verify archived','mirror')):
        return 'Settings'
    if any(x in name for x in ('backup','restore','snapshot','pc discovery','pc saves','pc game','steam','cloud','game path','custom pc','known pc','preview files','external drive','import community','bulk zip','find pc')):
        return 'Saves & Backups'
    # Keep unknown tool actions reachable, but not promoted to primary navigation.
    return 'Settings'


def is_advanced_action(label):
    name=label.casefold()
    return any(x in name for x in ('experimental','prototype','unfinished','simulat','preflight','compatibility',
        'diagnostic','advanced','background jobs','debug','recovery','archive mirror','mirror',
        'public website','public html','community game','bulk','undo','reorder','density',
        'workflow status','start-up','startup','manual'))
