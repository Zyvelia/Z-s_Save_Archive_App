"""BL3 character loading diagnostics: never overwrite source on failed decode."""
import struct
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from zarchive.bl3_native import _read_codec
from zarchive.bl3_platform_codec import transform_payload


def fixture(kind='character', platform='PS4'):
    raw = b'\\x08\\x01\\x10\\x2a\\x1a\\x03abc'
    name = b'OakSaveGame\\x00' if kind == 'character' else b'BP_DefaultOakProfile_C\\x00'
    build = b'OAK-PATCHAWSPS4-434\\x00'
    header = (b'GVAS' + struct.pack('<IIHHHI', 2, 516, 4, 20, 3, 0)
              + struct.pack('<I', len(build)) + build
              + struct.pack('<II', 3, 0) + struct.pack('<I', len(name)) + name)
    encoded = transform_payload(raw, platform, kind, decrypt=False)
    return header + struct.pack('<I', len(encoded)) + encoded



class FailingCodec:
    def __init__(self, filename):
        raise AssertionError('unrecognized protobuf fields')


class LoadDiagnosticTests(unittest.TestCase):
    def test_ps4_save_rejects_wrong_pc_selection(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / '1.sav'
            original = fixture('character', 'PS4')
            source.write_bytes(original)
            with self.assertRaisesRegex(ValueError, 'Select PS4'):
                _read_codec(source, 'PC', 'character')
            self.assertEqual(source.read_bytes(), original)

    @patch('zarchive.bl3_native._codec', return_value=FailingCodec)
    def test_codec_error_explains_underlying_exception(self, codec):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / '1.sav'
            data = fixture('character', 'PS4')
            source.write_bytes(data)
            with self.assertRaisesRegex(ValueError, 'AssertionError.*unrecognized protobuf fields'):
                _read_codec(source, 'PS4', 'character')
            self.assertEqual(source.read_bytes(), data)

    @patch('zarchive.bl3_native._codec')
    def test_correct_ps4_platform_reaches_decoder(self, codec):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / '1.sav'
            source.write_bytes(fixture('character', 'PS4'))
            codec.return_value.return_value = 'decoded-character'
            self.assertEqual(_read_codec(source, 'PS4', 'character'), 'decoded-character')
            self.assertEqual(codec.call_count, 1)
            codec.return_value.assert_called_once()


if __name__ == '__main__':
    unittest.main()
