"""Regression coverage for legacy PS3 FTP directory encoding."""
import ftplib
import unittest
from unittest.mock import patch
from zarchive.transfer_v06 import PS3FTP


class FTPEncodingTests(unittest.TestCase):
    def test_connect_sets_latin1_before_server_reply_and_listing(self):
        seen=[]
        class FakeFTP:
            encoding='utf-8'
            def connect(self,*args,**kwargs):
                seen.append(('connect',self.encoding))
                # Reproduces the original error's byte 0xb0.
                self.decode_reply=b'220 PS3 \xb0 FTP'.decode(self.encoding)
            def login(self,*args):seen.append(('login',self.encoding))
            def set_pasv(self,value):seen.append(('pasv',value))
        with patch('zarchive.transfer_v06.ftplib.FTP',FakeFTP):
            session=PS3FTP('192.168.1.55').connect()
        self.assertEqual(session.decode_reply,'220 PS3 ° FTP')
        self.assertEqual(seen,[('connect','latin-1'),('login','latin-1'),('pasv',True)])

    def test_listing_with_non_utf8_comment_preserves_safe_entries(self):
        class FakeFTP:
            encoding='utf-8'
            def connect(self,*args,**kwargs):pass
            def login(self,*args):pass
            def set_pasv(self,*args):pass
            def __enter__(self):return self
            def __exit__(self,*args):pass
            def cwd(self,path):self.path=path
            def mlsd(self):
                # Simulate raw bytes delivered by a legacy PS3 FTP server:
                lines=[b'00000001',b'save-\xb0',b'00000002']
                for name in lines:yield name.decode(self.encoding),{'type':'dir'}
        with patch('zarchive.transfer_v06.ftplib.FTP',FakeFTP):
            entries=PS3FTP('192.168.1.55').list()
        self.assertEqual([entry.name for entry in entries],['00000001','00000002'])

    def test_default_utf8_would_fail_on_ps3_legacy_byte(self):
        with self.assertRaises(UnicodeDecodeError):b'save-\xb0'.decode('utf-8')

if __name__=='__main__':unittest.main()
