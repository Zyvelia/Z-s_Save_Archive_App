"""BL3 character loading diagnostics: never overwrite source on failed decode."""
import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from zarchive.bl3_native import _read_codec
from tests.test_bl3_native import fixture


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
