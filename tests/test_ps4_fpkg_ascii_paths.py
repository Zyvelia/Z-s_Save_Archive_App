"""Regression checks for ASCII-safe output names and GP4 staging."""
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
import xml.etree.ElementTree as ET

from test_ps4_fpkg import make_dump, make_package
from zarchive.ps4_fpkg import build_packages, inspect_dump, safe_title, staging_parent


class AsciiPackagePathsTests(unittest.TestCase):
    def test_safe_title_removes_non_ascii_symbols(self):
        self.assertEqual(safe_title("Borderlands®: Game of the Year Edition"),
                         "Borderlands_ Game of the Year Edition")
        self.assertEqual(safe_title("Pokémon™"), "Pokemon")
        self.assertEqual(safe_title("CON"), "_CON")

    def test_builder_uses_ascii_paths_and_preserves_source(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            dump = make_dump(root / "game", "gd",
                             TITLE="Borderlands®: Game of the Year Edition")
            (dump / "eboot.bin").write_bytes(b"test executable")
            tool = root / "orbis-pub-cmd.exe"
            tool.write_bytes(b"MZmock")
            output = root / "output"
            output.mkdir()
            seen = []

            def builder(_tool, project, package, log, progress, cancelled):
                seen.append((project, package))
                self.assertTrue(str(project).isascii())
                self.assertTrue(str(package).isascii())
                self.assertEqual(ET.parse(project).getroot().tag, "psproject")
                make_package(package, dump)

            paths = build_packages([inspect_dump(dump)], tool, output, runner=builder)
            self.assertEqual(len(paths), 1)
            self.assertTrue(paths[0].exists())
            self.assertTrue(str(paths[0]).isascii())
            self.assertTrue((dump / "sce_sys" / "param.sfo").exists())
            self.assertFalse(seen[0][0].exists())

    def test_staging_parent_keeps_short_ascii_paths(self):
        with TemporaryDirectory() as temporary:
            output = Path(temporary) / "games"
            output.mkdir()
            self.assertEqual(staging_parent(output / "game.pkg"), output)


if __name__ == "__main__":
    unittest.main()
