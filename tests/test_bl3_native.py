"""BL3 platform translation and non-destructive output tests (no codec install)."""
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import hashlib
import struct
import unittest

from zarchive.bl3_platform_codec import (
    KEYS, convert_platform, gvas_payload_bounds, transform_payload,
)
from zarchive.bl3_native import load_character, load_profile, write_character_copy
from zarchive.universal_editor_profiles import available_profiles, validate_profile


def fixture(kind='character', platform='PS4'):
    raw = b'\x08\x01\x10\x2a\x1a\x03abc'
    name = b'OakSaveGame\x00' if kind == 'character' else b'BP_DefaultOakProfile_C\x00'
    build = b'OAK-PATCHAWSPS4-434\x00'
    header = (b'GVAS' + struct.pack('<IIHHHI', 2, 516, 4, 20, 3, 0)
              + struct.pack('<I', len(build)) + build
              + struct.pack('<II', 3, 0)
              + struct.pack('<I', len(name)) + name)
    encoded = transform_payload(raw, platform, kind, decrypt=False)
    return header + struct.pack('<I', len(encoded)) + encoded


class FakeSave:
    def __init__(self, file=None):
        self.character = 'Zane'
        self.level = 1
        self.money = 42
        self.eridium = 2
        self.build_id = 'OAK-PATCHAWSPS4-434'
        self.sg_type = 'OakSaveGame'

    def get_char_name(self):
        return self.character

    def set_char_name(self, value):
        self.character = value

    def get_class(self, eng=False):
        return 'Operative'

    def get_level(self):
        return self.level

    def set_level(self, value):
        self.level = value

    def get_xp(self):
        return 0

    def get_money(self):
        return self.money

    def set_money(self, value):
        self.money = value

    def get_eridium(self):
        return self.eridium

    def set_eridium(self, value):
        self.eridium = value

    def get_items(self):
        return []

    def save_to(self, path):
        Path(path).write_bytes(fixture('character', 'PC'))


class NativeBL3Tests(unittest.TestCase):
    def test_profiles_are_explicit_and_future_console_is_disabled(self):
        self.assertEqual(len(available_profiles()), 4)
        with self.assertRaisesRegex(ValueError, 'not supported'):
            validate_profile('bl3-xbox-character')

    def test_pc_ps4_roundtrip_for_character_and_profile(self):
        for kind in ('character', 'profile'):
            for platform in ('PC', 'PS4'):
                with self.subTest(kind=kind, platform=platform):
                    data = fixture(kind, platform)
                    begin, size, actual = gvas_payload_bounds(data)
                    self.assertEqual(actual, kind)
                    self.assertEqual(begin + size, len(data))
                    other = 'PC' if platform == 'PS4' else 'PS4'
                    converted = convert_platform(data, platform, other, expected_kind=kind)
                    self.assertEqual(convert_platform(converted, other, platform,
                                                      expected_kind=kind), data)
                    self.assertEqual(converted[:begin], data[:begin])

    def test_mismatched_profile_rejected(self):
        with self.assertRaisesRegex(ValueError, 'Expected a profile'):
            convert_platform(fixture('character'), 'PS4', 'PC',
                             expected_kind='profile')

    def test_bad_header_rejected(self):
        with self.assertRaisesRegex(ValueError, 'GVAS'):
            gvas_payload_bounds(b'NOPE')
        with self.assertRaisesRegex(ValueError, 'length'):
            gvas_payload_bounds(fixture()[:-1])

    @patch('zarchive.bl3_native._read_codec', return_value=FakeSave())
    def test_preview_and_copy_preserve_original(self, backend):
        with TemporaryDirectory() as scratch:
            root = Path(scratch)
            source = root / '1'
            source.write_bytes(fixture())
            original = source.read_bytes()
            info = load_character(source, 'PS4')
            self.assertEqual(info['character'], 'Zane')
            self.assertEqual(info['platform'], 'PS4')
            self.assertEqual(info['inventory_count'], 0)
            dest = root / 'edited'
            self.assertEqual(write_character_copy(
                source, dest, name='Zane', level=20, money=999,
                eridium=500, expected_sha256=info['sha256'],
                platform='PS4'), dest)
            self.assertEqual(source.read_bytes(), original)
            self.assertEqual(gvas_payload_bounds(dest.read_bytes())[2], 'character')
            with self.assertRaises(FileExistsError):
                write_character_copy(source, dest, name='Zane', level=10,
                                     money=1, eridium=1,
                                     expected_sha256=info['sha256'])
            source.write_bytes(fixture('character', 'PC'))
            with self.assertRaisesRegex(ValueError, 'changed'):
                write_character_copy(source, root / 'new', name='Zane', level=2,
                                     money=1, eridium=1,
                                     expected_sha256=info['sha256'])
            self.assertFalse((root / 'new').exists())


if __name__ == '__main__':
    unittest.main()
