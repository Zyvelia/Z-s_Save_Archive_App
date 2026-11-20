import struct
import tempfile
import unittest
from pathlib import Path
from zarchive.storage import Archive, discover_saves, folder_digest, read_param_sfo


def write_sfo(path, entries=None):
    entries = entries or {'TITLE':'Borderlands 2','TITLE_ID':'BLUS30982','SUB_TITLE':'Chapter 01'}
    keys=bytearray();values=bytearray();indexes=bytearray()
    for key,value in entries.items():
        key_offset=len(keys);keys += key.encode()+b'\x00'
        raw=value.encode()+b'\x00';value_offset=len(values);values += raw
        indexes += struct.pack('<HHIII',key_offset,0x0204,len(raw),len(raw),value_offset)
    ks=20+len(indexes);vs=ks+len(keys)
    path.write_bytes(struct.pack('<4sIIII',b'\x00PSF',0x101,ks,vs,len(entries))+indexes+keys+values)

class Tests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.home=Path(self.tmp.name);self.source=self.home/'USB'/'SAVE1';self.source.mkdir(parents=True)
        write_sfo(self.source/'PARAM.SFO');(self.source/'DATA.BIN').write_bytes(b'example save data')
        self.db=Archive(self.home/'library');self.addCleanup(self.db.close)
    def test_sfo(self):
        self.assertEqual(read_param_sfo(self.source/'PARAM.SFO')['TITLE_ID'],'BLUS30982')
    def test_discovery(self):
        self.assertEqual(discover_saves(self.home/'USB'),[self.source])
    def test_corrupted_sfo(self):
        (self.source/'PARAM.SFO').write_bytes(b'bad')
        with self.assertRaises(ValueError):read_param_sfo(self.source/'PARAM.SFO')
    def test_import_and_original_preserved(self):
        record=self.db.import_save(self.source,'Legit')
        self.assertEqual(record['title_id'],'BLUS30982')
        self.assertEqual(self.db.stats(),(1,1,0))
        self.assertEqual((self.source/'DATA.BIN').read_bytes(),b'example save data')
        self.assertEqual((self.db.root/record['stored_path']/'DATA.BIN').read_bytes(),b'example save data')
    def test_duplicate_rejected(self):
        self.db.import_save(self.source)
        with self.assertRaisesRegex(ValueError,'Identical save'):self.db.import_save(self.source)
        self.assertEqual(len(self.db.list_saves()),1)
    def test_update(self):
        record=self.db.import_save(self.source)
        self.db.update(record['id'],category='Modded',label='Boosted',notes='Max money',status='Verified')
        row=self.db.list_saves('Boosted')[0]
        self.assertEqual((row['category'],row['notes'],row['status']),('Modded','Max money','Verified'))
        self.assertEqual(self.db.stats(),(1,1,1))
    def test_bad_category(self):
        with self.assertRaises(ValueError):self.db.import_save(self.source,'Fake')
    def test_digest_changes(self):
        a=folder_digest(self.source)[0];(self.source/'DATA.BIN').write_bytes(b'different')
        self.assertNotEqual(a,folder_digest(self.source)[0])
    def test_settings_persist(self):
        self.db.import_save(self.source);self.assertEqual(len(self.db.games()),1)
        other=Archive(self.home/'library')
        try:self.assertEqual(len(other.list_saves()),1)
        finally:other.close()
    def test_no_meta(self):
        (self.source/'PARAM.SFO').unlink()
        with self.assertRaises(ValueError):self.db.import_save(self.source)

if __name__=='__main__':unittest.main()
