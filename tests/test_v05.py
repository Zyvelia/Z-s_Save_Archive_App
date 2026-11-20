import tempfile, unittest
from pathlib import Path
from zarchive.library_v05 import LibraryArchive,canonical_name

JPEG=b'\xff\xd8\xff\xe0'+b'fake-image-for-copy-test'

class LibraryFeatures(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        self.archive=LibraryArchive(self.root/'archive');self.addCleanup(self.archive.close)
        source=self.root/'game.dat';source.write_bytes(b'content')
        self.archive.import_pc_save(source,'Test PC Game')

    def test_cover_copy_retains_original(self):
        source=self.root/'source.jpg';source.write_bytes(JPEG)
        cover=self.archive.add_cover('PC','Test PC Game',source)
        self.assertEqual(cover.read_bytes(),JPEG)
        self.assertEqual(self.archive.cover_for('PC','Test PC Game'),cover)
        source.unlink()
        self.assertTrue(cover.is_file())
        reopened=LibraryArchive(self.root/'archive')
        self.assertEqual(reopened.cover_for('PC','Test PC Game'),cover)
        reopened.close()

    def test_no_cover_for_missing_game(self):
        img=self.root/'cover.jpg';img.write_bytes(JPEG)
        with self.assertRaises(ValueError):self.archive.add_cover('PC','Missing',img)

    def test_reject_invalid_image(self):
        bad=self.root/'fake.jpg';bad.write_bytes(b'not an image')
        with self.assertRaises(ValueError):self.archive.add_cover('PC','Test PC Game',bad)

    def test_reject_oversized_image(self):
        img=self.root/'cover.jpg';img.write_bytes(JPEG+b'a'*5_000_000)
        with self.assertRaises(ValueError):self.archive.add_cover('PC','Test PC Game',img)

    def test_collections_preserve_saves(self):
        cid=self.archive.create_collection('Favorites')
        self.archive.add_to_collection(cid,'PC','Test PC Game')
        self.archive.rename_collection(cid,'Top Picks')
        self.assertEqual(self.archive.collections()[0]['name'],'Top Picks')
        self.archive.remove_from_collection(cid,'PC','Test PC Game')
        self.assertEqual(self.archive.collection_games(cid),[])
        self.archive.add_to_collection(cid,'PC','Test PC Game')
        self.archive.delete_collection(cid)
        self.assertEqual(self.archive.collections(),[])
        self.assertEqual(len(self.archive.list_saves()),1)

    def test_name_normalization(self):
        self.assertEqual(canonical_name('Game: Deluxe!'),canonical_name('GAME deluxe'))

    def test_steam_cover_restricted_to_pc(self):
        with self.assertRaises(ValueError):self.archive.steam_cover('PS3','Test PC Game','123')

if __name__=='__main__':unittest.main()
