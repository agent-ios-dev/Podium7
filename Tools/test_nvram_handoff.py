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

    def test_persisted_proxy_uses_newest_valid_bank_and_never_resets_corruption(self):
        from cfi_nvram_handoff import flash_image, select_bank
        raw = bytearray(flash_image())
        marker = b'restore-outcome=test\0'
        raw[8192+48:8192+48+len(marker)] = marker
        struct.pack_into('<I',raw,8192+20,3)
        struct.pack_into('<I',raw,8192+16,zlib.adler32(raw[8192+20:16384]))
        index,generation,proxy = select_bank(bytes(raw))
        self.assertEqual((index,generation),(1,3))
        self.assertIn(marker,proxy)
        raw[8192+100] ^= 1
        self.assertEqual(select_bank(bytes(raw))[0],0)
        raw[100] ^= 1
        with self.assertRaises(ValueError): select_bank(bytes(raw))
        with self.assertRaises(ValueError): select_bank(bytes(8192))

    def test_generation_wrap_is_ordered_as_uint32_serial(self):
        from cfi_nvram_handoff import flash_image, select_bank
        raw = bytearray(flash_image())
        for offset,generation in [(0,0xffffffff),(8192,0)]:
            struct.pack_into('<I',raw,offset+20,generation)
            struct.pack_into('<I',raw,offset+16,zlib.adler32(raw[offset+20:offset+8192]))
        self.assertEqual(select_bank(bytes(raw))[:2],(1,0))

    def test_restore_proxy_contains_persisted_variables_not_empty_factory(self):
        from cfi_nvram_handoff import flash_image, attach
        from test_device_tree_preparation import node
        raw = bytearray(flash_image())
        marker = b'restore-outcome=kept\0'
        raw[8192+48:8192+48+len(marker)] = marker
        struct.pack_into('<I',raw,8192+20,3)
        struct.pack_into('<I',raw,8192+16,zlib.adler32(raw[8192+20:16384]))
        tree = node([('name',b'device-tree\0')], [
            node([('name',b'chosen\0'),('nvram-bank-count',bytes(4)),('nvram-current-bank',bytes(4)),
                  ('nvram-proxy-data',empty_bank())]),
            node([('name',b'arm-io\0'),('ranges',struct.pack('<QQQ',0,0x200000000,0x100000000))])])
        restored = attach(tree,bytes(raw))
        self.assertIn(bytes(raw[8192:16384]),restored)
        self.assertIn(b'nvram-current-bank'.ljust(32,b'\0')+struct.pack('<II',4,1),restored)
        self.assertEqual(restored.count(b'nvram-proxy-data'),1)
