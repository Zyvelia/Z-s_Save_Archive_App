"""BL3 native character editing safeguards; no real game save needed."""
import hashlib
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from zarchive.bl3_native import load_character, write_character_copy


class FakeSave:
    records = {}

    def __init__(self, file):
        self.path = Path(file)
        data = self.path.read_bytes()
        if data[:4] != b'GVAS':
            raise ValueError('bad header')
        self.data = self.records.get(data, ('Zane', 1, 42, 2))
        self.build_id = 'OAK-PATCHAWSPS4-434'
        self.sg_type = 'OakSaveGame'

    def get_char_name(self):
        return self.data[0]

    def get_class(self, eng=False):
        return 'Operative'

    def get_level(self):
        return self.data[1]

    def get_xp(self):
        return 0

    def get_money(self):
        return self.data[2]

    def get_eridium(self):
        return self.data[3]

    def get_items(self):
        return []

    def set_char_name(self, name):
        self.data = (name, *self.data[1:])

    def set_level(self, value):
        self.data = (self.data[0], value, *self.data[2:])

    def set_money(self, value):
        self.data = (*self.data[:2], value, self.data[3])

    def set_eridium(self, value):
        self.data = (*self.data[:3], value)

    def save_to(self, filename):
        payload = b'GVAS' + repr(self.data).encode()
        self.records[payload] = self.data
        Path(filename).write_bytes(payload)


class BL3NativeTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / '1'
        self.source.write_bytes(b'GVAS' + b'x' * 50)
        FakeSave.records.clear()

    @patch('zarchive.bl3_native._codec', return_value=FakeSave)
    def test_load_character(self, _codec):
        info = load_character(self.source)
        self.assertEqual(info['character'], 'Zane')
        self.assertEqual(info['class'], 'Operative')
        self.assertEqual(info['level'], 1)
        self.assertEqual(info['inventory_count'], 0)

    @patch('zarchive.bl3_native._codec', return_value=FakeSave)
    def test_export_copy_does_not_overwrite_original(self, _codec):
        before = self.source.read_bytes()
        out = self.root / '1_edited'
        info = load_character(self.source)
        result = write_character_copy(self.source, out, name='Zane', level=42,
                                      money=1000, eridium=250,
                                      expected_sha256=info['sha256'])
        self.assertEqual(result, out)
        self.assertEqual(self.source.read_bytes(), before)
        self.assertEqual(FakeSave(str(out)).get_level(), 42)
        with self.assertRaises(FileExistsError):
            write_character_copy(self.source, out, name='Zane', level=2,
                                 money=1, eridium=1,
                                 expected_sha256=info['sha256'])

    @patch('zarchive.bl3_native._codec', return_value=FakeSave)
    def test_changed_original_blocks_edit(self, _codec):
        original = load_character(self.source)
        self.source.write_bytes(b'GVAS' + b'y' * 50)
        with self.assertRaisesRegex(ValueError, 'changed'):
            write_character_copy(self.source, self.root / 'out', name='Zane',
                                 level=10, money=1, eridium=1,
                                 expected_sha256=original['sha256'])
        self.assertFalse((self.root / 'out').exists())

    def test_encrypted_or_unknown_rejected(self):
        self.source.write_bytes(b'NOT GVAS')
        with self.assertRaisesRegex(ValueError, 'GVAS'):
            load_character(self.source)


if __name__ == '__main__':
    unittest.main()
