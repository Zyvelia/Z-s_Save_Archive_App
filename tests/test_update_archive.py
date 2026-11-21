from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from zipfile import ZipFile

import update_archive as updater


class SourceUpdateTests(unittest.TestCase):
    revision = "1" * 40
    required = {path: f"upstream {path}\n" for path in updater.REQUIRED}

    def setUp(self):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        (self.root / "main.py").write_text("local main\n")

    def write_local(self, name, contents):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(contents)
        return path

    def make_archive(self, revision, files):
        def download(actual_revision, destination):
            self.assertEqual(actual_revision, revision)
            prefix = f"Z-s_Save_Archive_App-{revision}"
            with ZipFile(destination, "w") as archive:
                for name, contents in files.items():
                    archive.writestr(f"{prefix}/{name}", contents)
        return download

    def sync(self, files=None, revision=None):
        revision = revision or self.revision
        files = self.required if files is None else files
        with (patch.object(updater, "latest_revision", return_value=revision),
              patch.object(updater, "download_source", side_effect=self.make_archive(revision, files)),
              patch("builtins.print")):
            updater.update(self.root)

    def test_sync_replaces_and_removes_app_code_and_backs_it_up(self):
        obsolete = self.write_local("zarchive/obsolete.py", "obsolete")
        obsolete_root = self.write_local("old_launcher.bat", "old launcher")
        paths = [self.write_local(path, "private") for path in
                 ("ArchiveData/Saves.sqlite", "portable.flag", "notes.txt",
                  "editor_definitions/my_editor.json", "zarchive/local.sqlite",
                  "assets/my_archive/archive.sqlite3", "assets/my_archive/objects/Save.png")]
        self.sync({**self.required, "downloads/history.zip": "ignored"})
        self.assertEqual((self.root / "main.py").read_text(), self.required["main.py"])
        self.assertFalse(obsolete.exists())
        self.assertFalse(obsolete_root.exists())
        self.assertFalse((self.root / "downloads").exists())
        self.assertTrue(all(path.read_text() == "private" for path in paths))
        backup, = (self.root / ".update-backups").iterdir()
        self.assertEqual((backup / "main.py").read_text(), "local main\n")
        self.assertEqual((backup / "zarchive/obsolete.py").read_text(), "obsolete")
        self.assertEqual((backup / "old_launcher.bat").read_text(), "old launcher")

    def test_second_sync_removes_upstream_deleted_and_locally_added_code(self):
        definition = "editor_definitions/old_example.json"
        self.sync({**self.required, definition: "old example"})
        extra = self.write_local("zarchive/local.py", "local addition")
        self.sync(revision="2" * 40)
        self.assertFalse(extra.exists())
        self.assertFalse((self.root / definition).exists())

    def test_same_commit_still_restores_local_changes(self):
        self.sync()
        self.sync()
        backups = self.root / ".update-backups"
        self.assertEqual(len(list(backups.iterdir())), 1)
        self.write_local("main.py", "edited after update")
        self.sync()
        self.assertEqual((self.root / "main.py").read_text(), self.required["main.py"])

    def test_invalid_snapshot_leaves_local_files_in_place(self):
        obsolete = self.write_local("zarchive/obsolete.py", "leave in place")
        for files in ({"main.py": "incomplete"},
                      {**self.required, "zarchive/../../escape.py": "unsafe"},
                      {**self.required, "MAIN.py": "duplicate"}):
            with self.assertRaises(ValueError):
                self.sync(files)
            self.assertTrue(obsolete.is_file())
            self.assertEqual((self.root / "main.py").read_text(), "local main\n")
            self.assertFalse((self.root / ".archive-update.lock").exists())

    def test_failed_install_restores_removed_and_replaced_files(self):
        obsolete = self.write_local("zarchive/obsolete.py", "restore me")
        replace = Path.replace

        def fail_on_updater_script(path, destination):
            if path.name == "update_archive.py":
                raise OSError("simulated locked file")
            return replace(path, destination)

        # Use an explicit order so main.py and the obsolete file change before the failure.
        ordered = {"main.py": self.required["main.py"], "update_archive.py": self.required["update_archive.py"],
                   **self.required}
        with patch.object(Path, "replace", fail_on_updater_script):
            with self.assertRaisesRegex(OSError, "locked file"):
                self.sync(ordered)
        self.assertEqual(obsolete.read_text(), "restore me")
        self.assertEqual((self.root / "main.py").read_text(), "local main\n")
        self.assertFalse((self.root / updater.STATE_FILE).exists())
