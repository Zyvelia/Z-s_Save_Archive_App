"""Regression tests for the PS4-first Game Lab. Does not require PySide6."""
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from zarchive.game_lab import GameLabStore, inspect_file, compare_files, package_save, PLATFORMS

class GameLabTests(unittest.TestCase):
    def test_tracker_persistence_and_filters(self):
        with tempfile.TemporaryDirectory() as temp:
            store = GameLabStore(temp)
            rid = store.save(game="Borderlands 3", platform="PS4", status="Analyzing",
                             title_id="CUSA00001", editable_values="Money")
            self.assertEqual(len(store.list(platform="PS4")), 1)
            store.save(game="Borderlands 3", platform="PS4", status="Testing",
                       record_id=rid, editable_values="Money, Eridium")
            self.assertEqual(store.list(status="Testing")[0]["editable_values"], "Money, Eridium")
            store.close()
            again = GameLabStore(temp)
            self.assertEqual(len(again.list(query="Eridium")), 1)
            again.delete(rid)
            self.assertEqual(again.list(), [])
            again.close()

    def test_inspector_and_comparison_read_only(self):
        with tempfile.TemporaryDirectory() as temp:
            first = Path(temp) / "a.bin"
            second = Path(temp) / "b.bin"
            first.write_bytes(b"abc12345")
            second.write_bytes(b"abc12945")
            self.assertEqual(inspect_file(first)["size"], 8)
            report = compare_files(first, second)
            self.assertEqual(report["changed_bytes"], 1)
            self.assertEqual(report["ranges"][0]["offset"], 5)
            self.assertEqual(first.read_bytes(), b"abc12345")

    def test_package_manifest(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "save"
            root.mkdir()
            (root / "data.sav").write_bytes(b"safe")
            out = Path(temp) / "package.zip"
            package_save(root, out, {"game": "Example", "platform": "PS4",
                                    "title_id": "CUSA00001", "variant": "Starter Boost"})
            with zipfile.ZipFile(out) as archive:
                self.assertIsNone(archive.testzip())
                self.assertEqual(archive.read("save/data.sav"), b"safe")
                metadata = json.loads(archive.read("metadata.json"))
                self.assertEqual(metadata["metadata"]["platform"], "PS4")

    def test_refuse_package_inside_source(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp) / "save"
            folder.mkdir()
            (folder / "file").write_bytes(b"test")
            with self.assertRaises(ValueError):
                package_save(folder, folder / "output.zip", {"platform": "PS4"})

    def test_four_platforms(self):
        self.assertEqual(set(PLATFORMS), {"PS4", "PS3", "PC", "Switch"})

if __name__ == "__main__":
    unittest.main()
