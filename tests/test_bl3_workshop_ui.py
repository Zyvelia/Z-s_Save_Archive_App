"""Offscreen smoke tests for the BL3 workshop's real editor controls.

These tests require PySide6 but do not need game files or modify user saves.
"""
import os
import unittest
from unittest.mock import patch


class WorkshopWidgetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
        try:
            from PySide6.QtWidgets import QApplication
        except ImportError:
            raise unittest.SkipTest('PySide6 is unavailable')
        cls.app = QApplication.instance() or QApplication([])

    def test_inventory_search_and_queued_part_anointment(self):
        from zarchive.ui_bl3_workshop import WeaponWorkshop
        source_details = {'path': 'fake.sav', 'platform': 'PS4', 'sha256': 'digest'}
        inventory = [
            {'index': 0, 'name': 'Hellwalker', 'level': 72, 'mayhem': 10,
             'balance': 'Shotgun-A', 'code': 'BL3(code1)'},
            {'index': 1, 'name': 'Hellwalker B', 'level': 72, 'mayhem': 10,
             'balance': 'Shotgun-A', 'code': 'BL3(code2)'},
            {'index': 2, 'name': 'Different', 'level': 5, 'mayhem': 0,
             'balance': 'Pistol-B', 'code': 'BL3(code3)'},
        ]
        weapons = [
            {'item_index': 0, 'balance': 'Shotgun-A', 'category': 'shotgun',
             'parts': [{'slot': 0, 'asset': 'Barrel A'}], 'anointments': []},
            {'item_index': 1, 'balance': 'Shotgun-A', 'category': 'shotgun',
             'parts': [{'slot': 0, 'asset': 'Barrel B'}],
             'anointments': [{'asset': '/AnointA', 'db_index': 10}]},
            {'item_index': 2, 'balance': 'Pistol-B', 'category': 'pistol',
             'parts': [{'slot': 0, 'asset': 'Pistol A'}], 'anointments': []},
        ]
        with (patch('zarchive.ui_bl3_workshop.list_inventory', return_value=inventory),
              patch('zarchive.ui_bl3_workshop.list_visual_weapons', return_value=weapons)):
            widget = WeaponWorkshop()
            widget.load_character(source_details)
        self.addCleanup(widget.close)
        self.assertEqual(widget.item_list.count(), 3)
        widget.search.setText('hellwalker')
        self.assertEqual(widget.item_list.count(), 2)
        widget.item_list.setCurrentRow(0)
        self.assertEqual(widget.donor.count(), 1)
        self.assertEqual(widget.donor.currentData(), 1)
        self.assertEqual(widget.anointment.count(), 1)
        widget.queue_part()
        widget.queue_anointment()
        self.assertEqual(len(widget.queue), 2)
        self.assertEqual(widget.queue[0]['op'], 'weapon_part')
        self.assertEqual(widget.queue[1]['op'], 'weapon_anointment')
        widget.clear()
        self.assertFalse(widget.item_list.count())
        self.assertEqual(widget.queue, [])
        self.assertFalse(widget.search.isEnabled())

    def test_all_item_selector_filters_unsupported_and_experiment_donors(self):
        from zarchive.ui_bl3_workshop import WeaponWorkshop
        details = {'path': 'fake.sav', 'platform': 'PS4', 'sha256': 'digest'}
        inventory = [
            {'index': 0, 'name': 'Gun A', 'level': 72, 'mayhem': 10,
             'balance': 'GunBalanceA', 'code': 'BL3(BAAA==)'},
            {'index': 1, 'name': 'Gun B', 'level': 72, 'mayhem': 10,
             'balance': 'GunBalanceB', 'code': 'BL3(BAAB==)'},
            {'index': 2, 'name': 'Eridium', 'level': 1, 'mayhem': 0,
             'balance': 'EridiumBalance', 'code': 'BL3(BAAC==)'},
        ]
        weapon_parts = [
            {'item_index': 0, 'balance': 'GunBalanceA', 'category': 'shotgun',
             'parts': [{'slot': 0, 'asset': 'PartA'}], 'anointments': []},
            {'item_index': 1, 'balance': 'GunBalanceB', 'category': 'shotgun',
             'parts': [{'slot': 0, 'asset': 'PartB'}], 'anointments': []},
        ]
        with (patch('zarchive.ui_bl3_workshop.list_inventory', return_value=inventory),
              patch('zarchive.ui_bl3_workshop.list_visual_weapons', return_value=weapon_parts)):
            widget = WeaponWorkshop()
            widget.load_character(details)
        self.addCleanup(widget.close)
        self.assertEqual(widget.item_selector.count(), 3)
        widget.item_selector.setCurrentIndex(2)
        self.assertEqual(widget.selected_index(), 2)
        self.assertFalse(widget.swap_button.isEnabled())
        widget.item_scope.setCurrentIndex(1)
        self.assertEqual(widget.item_selector.count(), 2)
        widget.item_scope.setCurrentIndex(2)
        self.assertEqual(widget.item_selector.count(), 1)
        widget.item_scope.setCurrentIndex(0)
        widget.item_selector.setCurrentIndex(0)
        self.assertEqual(widget.donor.count(), 0)
        widget.experimental.setChecked(True)
        self.assertEqual(widget.donor.count(), 1)
        self.assertTrue(widget.swap_button.isEnabled())
        widget.queue_part()
        self.assertEqual(widget.queue[0]['op'], 'weapon_part_experiment')
        self.assertIn('EXPORT COPY ONLY', widget.queue_info.text())



if __name__ == '__main__':
    unittest.main()
