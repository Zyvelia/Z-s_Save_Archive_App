"""Tests for opt-in third-party BL3 reference CSV interoperability."""
import csv
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from zipfile import ZipFile

from zarchive.bl3_reference_catalog import load_reference_catalog, normalize_item_code
from zarchive.bl3_advanced import _code


class CatalogTests(unittest.TestCase):
    def test_normalizes_lowercase_codes_without_touching_payload(self):
        self.assertEqual(normalize_item_code('bl3(BAAA==)'), 'BL3(BAAA==)')
        self.assertEqual(_code('bl3(BAAA==)'), 'BL3(BAAA==)')
        for text in ('python();', 'BL2(BAAA==)', 'bl3(not valid)', '', 'BL3(x);'):
            with self.subTest(text=text), self.assertRaises(ValueError):
                normalize_item_code(text)

    def test_user_provided_zip_imports_supported_tables_only(self):
        items = (
            'Name,Code,Link\n'
            '9-Volt,bl3(BAAA==),https://www.lootlemon.com/weapon/9-volt-bl3\n'
            'Example,BL3(BBBB==),https://example.com/bad\n'
            'Bad Entry,not-an-item,https://example.com\n'
        )
        parts = (
            'Part,Positives,Negatives,Effects\n'
            'Part_SR_VLA_Barrel_Septimator,Damage +100%,,Special effect\n'
        )
        with TemporaryDirectory() as scratch:
            source = Path(scratch) / 'reference.zip'
            with ZipFile(source, 'w') as archive:
                archive.writestr(
                    'BL3/LOOTLEMON_BL3_ITEMS.csv', items)
                archive.writestr(
                    'BL3/INVENTORY_PARTS_INFO_ALL.csv', parts)
                archive.writestr('BL3/BL3Tools.dll', b'not executed')
            catalog = load_reference_catalog(source)
            self.assertEqual(len(catalog.items), 2)
            self.assertEqual(len(catalog.parts), 1)
            self.assertEqual(
                [item.name for item in catalog.search_items('volt')], ['9-Volt']
            )
            self.assertEqual(catalog.items[1].url, '')
            info = catalog.describe_part(
                '/Game/Weapons/Part_SR_VLA_Barrel_Septimator.Part_SR_VLA_Barrel_Septimator'
            )
            self.assertIsNotNone(info)
            self.assertEqual(info.positives, 'Damage +100%')

    def test_unknown_csv_and_zip_without_catalog_fail_cleanly(self):
        with TemporaryDirectory() as scratch:
            filename = Path(scratch) / 'missing.csv'
            filename.write_text('Wrong,Headers\nexample,example\n', encoding='utf8')
            with self.assertRaisesRegex(ValueError, 'headers'):
                load_reference_catalog(filename)
            source = Path(scratch) / 'invalid.zip'
            with ZipFile(source, 'w') as archive:
                archive.writestr('BL3SaveEditor.exe', b'test')
            with self.assertRaisesRegex(ValueError, 'No supported'):
                load_reference_catalog(source)


if __name__ == '__main__':
    unittest.main()
