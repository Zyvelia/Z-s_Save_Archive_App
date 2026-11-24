"""PS4 PKG extractor preflight tests. No publisher tools required."""
import tempfile
import unittest
from pathlib import Path
from zarchive.ps4_pkg_extract import prepare_extract, redact, validate_executable


class PkgExtractionTests(unittest.TestCase):
    def fixture(self, folder):
        root = Path(folder)
        executable = root / "orbis-pub-cmd.exe"
        executable.write_bytes(b"MZ" + bytes(16))
        pkg_dir = root / "packages"
        pkg_dir.mkdir()
        source = pkg_dir / "test.pkg"
        source.write_bytes(b"PKG TEST")
        output = root / "output"
        output.mkdir()
        return source, output, executable

    def test_extract_args_and_output(self):
        with tempfile.TemporaryDirectory() as folder:
            source, output, exe = self.fixture(folder)
            info = prepare_extract(source, output, exe, "0" * 32)
            self.assertEqual(info["args"][:3],
                             ["img_extract", "--passcode", "0" * 32])
            self.assertEqual(Path(info["target"]).name, "test_extracted")
            self.assertFalse(Path(info["target"]).exists())

    def test_reject_existing_destination(self):
        with tempfile.TemporaryDirectory() as folder:
            source, output, exe = self.fixture(folder)
            (output / "test_extracted").mkdir()
            with self.assertRaises(FileExistsError):
                prepare_extract(source, output, exe, "")

    def test_reject_invalid_passcode(self):
        with tempfile.TemporaryDirectory() as folder:
            source, output, exe = self.fixture(folder)
            with self.assertRaises(ValueError):
                prepare_extract(source, output, exe, "not-valid")

    def test_reject_unsafe_tool(self):
        with tempfile.TemporaryDirectory() as folder:
            executable = Path(folder) / "orbis-pub-cmd.exe"
            executable.write_bytes(b"not-an-executable")
            with self.assertRaises(ValueError):
                validate_executable(executable, "orbis-pub-cmd.exe")

    def test_redaction(self):
        self.assertNotIn("a" * 32, redact("secret=" + "a" * 32, "a" * 32))


if __name__ == "__main__":
    unittest.main()
