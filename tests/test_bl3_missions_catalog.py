"""Tests for importing the user's mission archive metadata without asset execution."""
import tempfile
import unittest
import zipfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from zarchive.bl3_missions_catalog import (
    classify_mission, mission_key, parse_missions_zip, mission_status_lookup,
)


class MissionCatalogTests(unittest.TestCase):
    def test_simple_mission_zip_and_asset_refs(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / 'Missions.zip'
            with zipfile.ZipFile(path, 'w') as z:
                z.writestr('Missions/Plot/Mission_Ep01_ChildrenOfTheVault.uasset',
                           b'/Game/GameData/Challenges/Missions/Plot/Challenge_Mission_Plot_01'
                           b'\\x00/Game/GameData/Loot/ItemPools/Guns/FirstGun')
                z.writestr('Missions/Side/Zone_1/Mission_KillKillavolt.uasset',
                           b'/Game/Missions/Side/Zone_1/Mission_KillKillavolt')
                z.writestr('Missions/Side/Zone_1/SomePickup.uasset', b'data')
                z.writestr('Missions/Side/Zone_1/Mission_KillKillavolt.uexp', b'data')
            missions = parse_missions_zip(path)
            self.assertEqual(len(missions), 2)
            by_name = {x.name: x for x in missions}
            self.assertEqual(by_name['Mission_Ep01_ChildrenOfTheVault'].category,
                             'Main Story')
            self.assertIn('/Game/GameData/Loot/ItemPools/Guns/FirstGun',
                          by_name['Mission_Ep01_ChildrenOfTheVault'].references)
            self.assertEqual(by_name['Mission_KillKillavolt'].category,
                             'Side Mission')

    def test_zip_rejects_missing_mission_definitions(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / 'Missions.zip'
            with zipfile.ZipFile(path, 'w') as z:
                z.writestr('Missions/Plot/SomeMesh.uasset', b'data')
            with self.assertRaisesRegex(ValueError, 'No Mission'):
                parse_missions_zip(path)

    def test_category_and_status_key(self):
        self.assertEqual(mission_key('/Game/Missions/Plot/Mission_Test.Mission_Test_C'),
                         mission_key('Missions/Plot/Mission_Test.uasset'))
        self.assertEqual(classify_mission('Missions/Side/Raid/Mission_Raid.uasset'), 'Raid')
        self.assertEqual(classify_mission('Missions/Side/ProvingGrounds/Mission_A.uasset'),
                         'Proving Grounds')

    def test_status_uses_save_mission_entries(self):
        from enum import IntEnum
        class State(IntEnum):
            MS_Active = 1
            MS_Complete = 2
        record_a = SimpleNamespace(
            mission_class_path='/Game/Missions/Plot/Mission_Test.Mission_Test_C',
            status=State.MS_Active,
        )
        record_b = SimpleNamespace(
            mission_class_path='/Game/Missions/Plot/Mission_Finish.Mission_Finish_C',
            status=State.MS_Complete,
        )
        save = SimpleNamespace(save=SimpleNamespace(mission_playthroughs_data=[
            SimpleNamespace(mission_list=[record_a]),
            SimpleNamespace(mission_list=[record_b]),
        ]))
        with patch.dict('sys.modules', {
            'bl3save': __import__('types').ModuleType('bl3save'),
            'bl3save.bl3save': SimpleNamespace(MissionState=State),
        }):
            result = mission_status_lookup(save)
        self.assertEqual(result[(0, 'mission_test')], 'Active')
        self.assertEqual(result[(1, 'mission_finish')], 'Completed')


if __name__ == '__main__':
    unittest.main()
