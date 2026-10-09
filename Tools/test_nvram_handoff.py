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

    def test_cfi_provider_is_explicit_and_bounded_by_existing_armio_ranges(self):
        from test_device_tree_preparation import node
        from cfi_nvram_handoff import attach, flash_image, SIZE
        from analyze_firmware import device_tree
        tree = node([('name',b'device-tree\0')], [
            node([('name',b'chosen\0'),('nvram-bank-count',bytes(4)),('nvram-current-bank',bytes(4))]),
            node([('name',b'arm-io\0'),('ranges',struct.pack('<QQQ',0,0x200000000,0x100000000))])])
        result = attach(tree)
        controllers = [n for n in device_tree(result) if n['path'].endswith('/podium7-nvram-cfi')]
        self.assertEqual(len(controllers),1)
        self.assertEqual(bytes.fromhex(controllers[0]['properties']['reg']),struct.pack('<QQ',0xf0000000,32768))
        self.assertEqual(len(flash_image()),SIZE)
        self.assertEqual(flash_image()[:8192],empty_bank())
        with self.assertRaises(ValueError): attach(result)
        with self.assertRaises(ValueError): attach(node([('name',b'device-tree\0')]))
