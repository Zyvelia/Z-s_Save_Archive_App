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


if __name__ == '__main__':
    unittest.main()
