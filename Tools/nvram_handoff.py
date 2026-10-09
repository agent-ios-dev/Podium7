"""Synthetic volatile CHRP v1 NVRAM proxy for XNU 8019 research handoff.

Based on Apple iokit/Kernel/IONVRAM.cpp. No physical controller or persistence.
No nonce seeds, device identities or security variables are manufactured.
"""
import struct
import zlib


def empty_bank():
    size = 0x2000
    image = bytearray(size)
    def header(offset, length, name):
        struct.pack_into("<BBH12s", image, offset, 0x70, 0, length // 16, name)
        checksum = image[offset] + sum(image[offset + 2:offset + 16])
        while checksum > 255:
            checksum = (checksum & 255) + (checksum >> 8)
        image[offset + 1] = checksum
    header(0, 32, b"nvram")
    header(32, 0x800, b"common")
    header(32 + 0x800, size - 32 - 0x800, b"system")
    struct.pack_into("<I", image, 20, 1)
    struct.pack_into("<I", image, 16, zlib.adler32(image[20:]))
    return bytes(image)
