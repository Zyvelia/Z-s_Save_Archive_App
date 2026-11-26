"""Advanced BL3 editor action validation and tab-scoped operation tests.

Tests use fake codec objects; runtime PS4 restoration still requires hardware.
"""
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from zarchive.bl3_advanced import _action, _code, _fingerprint, write_advanced_copy


class FakeItem:
    def __init__(self, code='BL3(YWJj)'):
        self.code = code
        self.level = 10
        self.mayhem_level = 0
        self.can_parse = True

    def get_serial_base64(self):
        return self.code

    def can_have_mayhem(self):
        return True


class FakeCharacter:
    def __init__(self):
        self.items = [FakeItem()]
        self.mayhem = [1, 2]
        self.sdus = {'backpack': 1}
        self.save = SimpleNamespace(ability_data=SimpleNamespace(tree_grade=0))

    def get_items(self):
        return self.items

    def add_new_item_encoded(self, code):
        self.items.append(FakeItem(code))

    def get_pt_mayhem_levels(self):
        return self.mayhem

    def set_all_mayhem_level(self, level):
        self.mayhem = [level] * len(self.mayhem)

    def get_sdus(self):
        return self.sdus

    def set_max_sdus(self):
        self.sdus['backpack'] = 99

    def get_level(self):
        return 20

    def unlock_skill_tree(self, level):
        if level > 1:
            self.save.ability_data.tree_grade = 2


class FakeProfile:
    def __init__(self):
        self.bank = []
        self.tokens = 0
        self.sdus = {'bank': 1}
        self.keys = [0, 0, 0]
        self.chests = [0, 0, 0]
        self.cosmetics = {k: set() for k in (
            'heads', 'skins', 'emotes', 'echo_themes',
            'room_decorations', 'weapon_skins', 'weapon_trinkets')}

    def get_bank_items(self):
        return self.bank

    def create_new_item_encoded(self, code):
        return FakeItem(code)

    def add_bank_item(self, item):
        self.bank.append(item)

    def get_guardian_rank_tokens(self):
        return self.tokens

    def set_guardian_rank_tokens(self, tokens):
        self.tokens = tokens

    def get_sdus(self):
        return self.sdus

    def set_max_sdus(self):
        self.sdus['bank'] = 99

    def __getattr__(self, name):
        for n in (1, 2, 3):
            if name == f'get_vaultcard{n}_keys':
                return lambda n=n: self.keys[n - 1]
            if name == f'set_vaultcard{n}_keys':
                return lambda val, n=n: self.keys.__setitem__(n - 1, val)
            if name == f'get_vaultcard{n}_chests':
                return lambda n=n: self.chests[n - 1]
            if name == f'set_vaultcard{n}_chests':
                return lambda val, n=n: self.chests.__setitem__(n - 1, val)
        for category, method in (
            ('heads', 'char_heads'), ('skins', 'char_skins'),
            ('emotes', 'emotes'), ('echo_themes', 'echo_themes'),
            ('room_decorations', 'room_decos'),
            ('weapon_skins', 'weapon_skins'),
            ('weapon_trinkets', 'weapon_trinkets'),
        ):
            if name == f'get_{method}':
                return lambda category=category: self.cosmetics[category]
            if name == f'unlock_{method}':
                return lambda category=category: self.cosmetics[category].add('unlocked')
        raise AttributeError(name)


class AdvancedBL3Tests(unittest.TestCase):
    def test_item_code_requires_wrapper(self):
        with self.assertRaisesRegex(ValueError, 'BL3'):
            _code('not-a-code')

    def test_character_inventory_and_progression(self):
        save = FakeCharacter()
        _action(save, 'character', {'op': 'item_duplicate', 'index': 0})
        self.assertEqual(len(save.get_items()), 2)
        _action(save, 'character', {'op': 'item_add', 'code': 'BL3(YWJj)'})
        self.assertEqual(len(save.get_items()), 3)
        _action(save, 'character', {'op': 'item_level', 'index': 1, 'level': 65})
        _action(save, 'character', {'op': 'item_mayhem', 'index': 1, 'level': 10})
        _action(save, 'character', {'op': 'mayhem_all', 'level': 11})
        _action(save, 'character', {'op': 'max_sdu'})
        _action(save, 'character', {'op': 'unlock_skill_tree'})
        self.assertEqual(save.get_items()[1].level, 65)
        self.assertEqual(save.get_items()[1].mayhem_level, 10)
        self.assertEqual(save.mayhem, [11, 11])
        self.assertEqual(save.sdus['backpack'], 99)
        self.assertEqual(save.save.ability_data.tree_grade, 2)
        self.assertEqual(len(_fingerprint(save, 'character')['items']), 3)

    def test_profile_guardian_vault_bank_and_cosmetics(self):
        save = FakeProfile()
        for action in (
            {'op': 'bank_add', 'code': 'BL3(YWJj)'},
            {'op': 'guardian_tokens', 'value': 100},
            {'op': 'vault_keys', 'card': 1, 'value': 25},
            {'op': 'vault_chests', 'card': 2, 'value': 9},
            {'op': 'max_sdu'},
            {'op': 'unlock_cosmetic', 'category': 'heads'},
        ):
            _action(save, 'profile', action)
        check = _fingerprint(save, 'profile')
        self.assertEqual(len(check['bank']), 1)
        self.assertEqual(check['guardian_tokens'], 100)
        self.assertEqual(check['vault_keys'], (25, 0, 0))
        self.assertEqual(check['vault_chests'], (0, 9, 0))
        self.assertEqual(save.sdus['bank'], 99)
        self.assertIn('unlocked', save.cosmetics['heads'])

    def test_invalid_save_type_and_values(self):
        save = FakeCharacter()
        for action in (
            {'op': 'item_duplicate', 'index': 999},
            {'op': 'item_level', 'index': 0, 'level': -1},
            {'op': 'mayhem_all', 'level': 99},
            {'op': 'bank_add', 'code': 'BL3(YWJj)'},
        ):
            with self.subTest(action=action), self.assertRaises(ValueError):
                _action(save, 'character', action)

    @patch('zarchive.bl3_advanced._publish')
    def test_action_batch_bound_and_invalid_kind(self, writer):
        with self.assertRaisesRegex(ValueError, '1–40'):
            write_advanced_copy('source', 'dest', expected_sha256='abc',
                                platform='PC', kind='character', actions=[])
        with self.assertRaisesRegex(ValueError, 'Choose Character'):
            write_advanced_copy('source', 'dest', expected_sha256='abc',
                                platform='PC', kind='invalid',
                                actions=[{'op': 'max_sdu'}])
        writer.assert_not_called()


if __name__ == '__main__':
    unittest.main()
