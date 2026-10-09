import struct
import unittest
import zlib
from nvram_handoff import empty_bank


class NVRAMTests(unittest.TestCase):
    def test_bank_matches_xnu_chrp_and_adler_checks(self):
        bank = empty_bank()
        self.assertEqual(len(bank), 8192)
        self.assertEqual(struct.unpack_from('<I', bank, 16)[0], zlib.adler32(bank[20:]))
        partitions = []
        offset = 0
        while offset < len(bank):
            signature, checksum, blocks, name = struct.unpack_from('<BBH12s', bank, offset)
            total = signature + sum(bank[offset+2:offset+16])
            while total > 255:
                total = (total & 255) + (total >> 8)
            self.assertEqual(checksum, total)
            self.assertGreater(blocks, 0)
            partitions.append((name.rstrip(b'\0'), blocks * 16))
            offset += blocks * 16
        self.assertEqual(offset, len(bank))
        self.assertEqual(partitions, [(b'nvram',32),(b'common',2048),(b'system',6112)])
        self.assertFalse(any(bank[48:2080]))
        self.assertFalse(any(bank[2096:]))
