"""BL3 game-level PC/PS4 codec translation for Apollo-exported GVAS files.

Platform-specific encryption constants match the public technical implementation
in ZakisM/bl3_save_edit. Its redistribution terms must be confirmed before
shipping a binary release. Apollo must first export the PS4 save container.
No offsets are guessed: all GVAS strings/format records are length-checked.
"""
from __future__ import annotations

import struct

# Constant pairs: (prefix, XOR). PC and PS4 each have separate
# character and profile payload ciphers. The GVAS header stays unchanged.
KEYS = {
    ('PC', 'character'): (
        '713436b35663255feae28373f498b8182ee5422e50a20f498724e6659af07cd7',
        '7c076983317e0c825f2e367f76b4a271382b6e87390502c6cdd8b1cca133f9b6',
    ),
    ('PS4', 'character'): (
        'd17bbf754cc180303792bdd0183e4a5f43a246a0eddb2d9f565f8b3d6e73e6b8',
        'fbfdfd513a5cdb20bb5ec7af666fb69a9a52670f195dd3841519c94a7967da6d',
    ),
    ('PC', 'profile'): (
        'd804b9085c4e2bc0619f7c8d5d340056e77b4ec0a4d6a7011415a9931f272c8f',
        'e8dc3a66f7ef85e0bd4aa9735799308c946359a8c9aed9587d51b01ebed07743',
    ),
    ('PS4', 'profile'): (
        'ad1e604e429ea933b2f501e1024d0875b1ad1a3da1036b1a17e6ec0f608db4f9',
        'ba0e861d58e1922130d6cbf0d082d5583612e1f6394488ea4efb047407953aa2',
    ),
}
KEYS = {key: tuple(bytes.fromhex(part) for part in pair) for key, pair in KEYS.items()}

# Fail immediately on transcription mistakes instead of producing a mysterious
# IndexError halfway through PS4/PC game-level encoding.
for _key, (_prefix, _xor) in KEYS.items():
    if len(_prefix) != 32 or len(_xor) != 32:
        raise RuntimeError(f'Invalid BL3 cipher key length for {_key}.')


def gvas_payload_bounds(data: bytes):
    """Return (payload offset, length, type) with strict GVAS framing checks."""
    if len(data) < 56 or len(data) > 32 * 1024 * 1024 or data[:4] != b'GVAS':
        raise ValueError('Expected an Apollo-exported BL3 GVAS save (32 MiB maximum).')
    pos = 4 + 4 + 4 + 2 + 2 + 2 + 4

    def integer():
        nonlocal pos
        if pos + 4 > len(data):
            raise ValueError('Truncated GVAS header.')
        number = struct.unpack_from('<I', data, pos)[0]
        pos += 4
        return number

    def string():
        nonlocal pos
        length = integer()
        if not 1 <= length <= 4096 or pos + length > len(data) or data[pos + length - 1] != 0:
            raise ValueError('Invalid GVAS string.')
        result = data[pos:pos + length - 1].decode('utf-8')
        pos += length
        return result

    string()  # build id
    integer()  # custom format version
    count = integer()
    if count > 512 or pos + count * 20 > len(data):
        raise ValueError('Invalid GVAS custom-format entries.')
    pos += count * 20
    save_type = string()
    kind = 'profile' if 'profile' in save_type.casefold() else 'character' if 'savegame' in save_type.casefold() else None
    if kind is None:
        raise ValueError('Unrecognized BL3 GVAS save type: ' + save_type)
    size = integer()
    if size < 1 or pos + size != len(data):
        raise ValueError('GVAS payload length is inconsistent with file size.')
    return pos, size, kind


def transform_payload(payload: bytes, platform: str, kind: str, *, decrypt: bool):
    """Apply the exact BL3 rolling XOR cipher in the required order."""
    prefix, xor = KEYS[(platform, kind)]
    output = bytearray(payload)
    if decrypt:
        positions = range(len(output) - 1, -1, -1)
    else:
        positions = range(len(output))
    for index in positions:
        previous = prefix[index] if index < 32 else output[index - 32]
        output[index] ^= previous ^ xor[index % 32]
    return bytes(output)


def convert_platform(data: bytes, source_platform: str, destination_platform: str,
                     *, expected_kind: str | None = None):
    """Re-key the encoded BL3 payload; keep all GVAS metadata untouched."""
    if source_platform not in ('PC', 'PS4') or destination_platform not in ('PC', 'PS4'):
        raise ValueError('Only PC and PS4 exports are currently supported.')
    start, size, kind = gvas_payload_bounds(data)
    if expected_kind is not None and expected_kind != kind:
        raise ValueError(f'Expected a {expected_kind} save, got {kind}.')
    if source_platform == destination_platform:
        return data
    raw = transform_payload(data[start:start + size], source_platform, kind, decrypt=True)
    encoded = transform_payload(raw, destination_platform, kind, decrypt=False)
    return data[:start] + encoded
