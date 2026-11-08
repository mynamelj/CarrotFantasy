"""The FF DB FF EE asset container observed in Carrot Fantasy 4 v1.4.1."""

import struct
import zlib
from functools import lru_cache


MAGIC = b"\xff\xdb\xff\xee"


@lru_cache(maxsize=1)
def keystream():
    words = [0] * 1024
    key = (0x43F21B68, 0x9A0F3610, 0x3AC65312, 0xB8926AA3)
    mask = 0xFFFFFFFF
    total = 0
    previous = words[-1]
    for _ in range(8):
        total = (total + 0x9E3779B9) & mask
        selector = (total >> 2) & 3
        for index in range(1024):
            following = words[(index + 1) % 1024]
            mix = (
                (((previous >> 5) ^ (following << 2))
                 + ((following >> 3) ^ (previous << 4)))
                ^ ((total ^ following) + (key[(index & 3) ^ selector] ^ previous))
            )
            previous = words[index] = (words[index] + mix) & mask
    return tuple(words)


def xor(payload):
    result = bytearray(payload)
    count = len(result) // 4
    key = keystream()
    positions = list(range(min(512, count)))
    index = len(positions)
    while index < count - 512:
        positions.append(index)
        index += 4
    positions.extend(range(index, count))
    for key_index, word_index in enumerate(positions):
        offset = word_index * 4
        value = struct.unpack_from("<I", result, offset)[0]
        struct.pack_into("<I", result, offset, value ^ key[key_index % 1024])
    return bytes(result)


def decode(raw):
    if len(raw) < 20 or raw[:4] != MAGIC or raw[4:8] != b"\x66\0\0\0":
        raise ValueError("Unsupported asset container header.")
    data = zlib.decompress(xor(raw[20:]))
    expected_size = struct.unpack_from("<I", raw, 16)[0]
    expected_crc = struct.unpack_from("<I", raw, 8)[0]
    if len(data) != expected_size or zlib.crc32(data) != expected_crc:
        raise ValueError("Decoded asset size or CRC32 mismatch.")
    return data


def encode(original, data):
    if len(original) < 20 or original[:4] != MAGIC:
        raise ValueError("An original asset header is required.")
    header = bytearray(original[:20])
    struct.pack_into("<I", header, 8, zlib.crc32(data))
    struct.pack_into("<I", header, 16, len(data))
    return bytes(header) + xor(zlib.compress(data))
