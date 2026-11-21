import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from zipfile import ZipFile

from zarchive.github_manager import Destination, GitHubManager, repository_name


@unittest.skipUnless(shutil.which('git'), 'Git is required for repository tests')
class RepositoryTests(unittest.TestCase):
    def setUp(self):
        scratch = tempfile.TemporaryDirectory()
        self.addCleanup(scratch.cleanup)
        self.root = Path(scratch.name)
        self.remote = self.root / 'remote.git'
        self.remote.mkdir()
        self.manager = GitHubManager()
        self.manager._git('init', '--bare', '-q', cwd=self.remote)
        self.target = Destination('Example/Archive', True, None)

    def local_network(self, *args, cwd=None):
        args = [str(self.remote) if value == self.target.url + '.git' else value for value in args]
        return self.manager._git(*args, cwd=cwd)

    def test_uploaded_snapshot_excludes_local_data_and_updates_existing_branch(self):
        source = self.root / 'local source'
        (source / 'zarchive').mkdir(parents=True)
        (source / 'ArchiveData').mkdir()
        (source / 'ArchiveData' / 'Saves.sqlite').write_text('private')
        (source / '.env').write_text('private')
        (source / 'ZSaveArchive.iss').touch()
        (source / 'zarchive' / '__init__.py').touch()
        main = source / 'main.py'
        main.write_text('first')
        with patch.object(self.manager, 'destination', return_value=self.target), \
             patch.object(self.manager, '_remote_git', side_effect=self.local_network), \
             patch.object(self.manager, 'account', return_value='test-account'):
            self.manager.publish(str(source), self.target.name, 'main')
            main.write_text('second')
            self.manager._git('init', '-q', cwd=source)
            self.manager.publish(str(source), self.target.name, 'main', snapshot=True)
        git = self.manager._git
        self.assertEqual(git('rev-list', '--count', 'main', cwd=self.remote), '2')
        self.assertEqual(git('show', 'main:main.py', cwd=self.remote), 'second')
        tracked = git('ls-tree', '-r', '--name-only', 'main', cwd=self.remote).splitlines()
        self.assertEqual(tracked, ['ZSaveArchive.iss', 'main.py', 'zarchive/__init__.py'])
        self.assertEqual(git('ls-files', cwd=source), '')

    def test_bundle_republishes_local_branches_and_tags(self):
        source = self.root / 'working'
        source.mkdir()
        git = self.manager._git
        git('init', '-q', cwd=source)
        (source / 'README.md').write_text('initial')
        git('add', 'README.md', cwd=source)
        git('-c', 'user.name=Test', '-c', 'user.email=test@example.com',
            'commit', '--no-gpg-sign', '-m', 'Initial', cwd=source)
        git('branch', 'old-project', cwd=source)
        git('tag', 'v1', cwd=source)
        output = self.root / 'archive.bundle'
        self.manager.save_bundle(str(source), str(output))
        with self.assertRaises(FileExistsError):
            self.manager.save_bundle(str(source), str(output))
        with patch.object(self.manager, 'create', return_value=self.target), \
             patch.object(self.manager, '_remote_git', side_effect=self.local_network):
            self.manager.publish(str(output), self.target.name, '', create=True, all_refs=True)
        ref = git('rev-parse', 'HEAD', cwd=source)
        self.assertEqual(git('rev-parse', 'old-project', cwd=self.remote), ref)
        self.assertEqual(git('rev-parse', 'v1', cwd=self.remote), ref)
        downloaded = self.root / 'remote.bundle'
        with patch.object(self.manager, '_remote_git', side_effect=self.local_network):
            self.manager.download_bundle(self.target.name, str(downloaded))
        self.assertIn('refs/heads/old-project', git('bundle', 'list-heads', str(downloaded), cwd=source))


class GitHubValidationTests(unittest.TestCase):
    def test_repository_input_accepts_only_github_names_and_urls(self):
        self.assertEqual(repository_name('https://github.com/Owner/Project.git'), 'Owner/Project')
        for value in ('https://example.com/Owner/Project', 'Owner/../Project',
                      'Owner/Project?public=true', '--Owner/Project', 'Owner/..'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                repository_name(value)

    def test_backup_is_only_sent_to_a_private_draft(self):
        manager = GitHubManager()
        with tempfile.TemporaryDirectory() as scratch:
            path = Path(scratch) / 'backup.zip'
            with ZipFile(path, 'w') as archive:
                archive.writestr('save.bin', 'selected data')
            with patch.object(manager, 'destination', return_value=Destination('Owner/Repo', False, 'main')), \
                 patch.object(manager, '_run') as run:
                with self.assertRaisesRegex(ValueError, 'private GitHub'):
                    manager.upload_backup(str(path), 'Owner/Repo')
                run.assert_not_called()
            with patch.object(manager, 'create', return_value=Destination('Owner/Repo', True, 'main')) as create, \
                 patch.object(manager, '_run', return_value='https://github.com/Owner/Repo/releases/tag/backup') as run:
                _, url = manager.upload_backup(str(path), 'Owner/Repo', create=True)
                create.assert_called_once_with('Owner/Repo', initialize=True)
                self.assertIn('--draft', run.call_args.args)
                self.assertIn(str(path), run.call_args.args)
                self.assertIn('/releases/', url)
