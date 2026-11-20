import unittest
from pathlib import Path
from zarchive.homebrew_v22 import CATALOG
from zarchive.homebrew_v23 import catalog_items, RELEASE_SOURCES
from zarchive.homebrew_v24 import installation_checklist

class V26Tests(unittest.TestCase):
    def test_catalog_expanded_and_unique(self):
        self.assertGreaterEqual(len(CATALOG), 20)
        names=[app['name'] for app in CATALOG]
        self.assertEqual(len(names),len(set(names)))

    def test_catalog_links_use_https(self):
        for app in CATALOG:
            self.assertTrue(app['url'].startswith('https://'),app['name'])
            self.assertTrue(app['description'])

    def test_release_sources_are_known_catalog_entries(self):
        self.assertTrue(set(RELEASE_SOURCES).issubset({a['name'] for a in CATALOG}))
        self.assertEqual(next(x for x in catalog_items() if x['name']=='PS3 ezRemote Client')['source'], 'cy33hc/ps3-ezremote-client')

    def test_checklist_for_new_homebrew(self):
        self.assertGreaterEqual(len(installation_checklist('ManaGunZ')),4)

    def test_converter_has_one_click_stage_action_and_status(self):
        s=(Path(__file__).resolve().parents[1]/'zarchive'/'ui_v20.py').read_text()
        self.assertIn('begin_auto_convert',s)
        self.assertIn('Stage && Convert',s)
        self.assertIn('self.status.setText(',s)
        self.assertIn('self.run_converter()',s)

if __name__=='__main__':unittest.main()
