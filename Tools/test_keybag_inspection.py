import struct
import unittest
from unittest.mock import patch
from inspect_keybag_host import adrp_page, adr_target, mappings, string_references, inspect, inspect_bytes


class KeybagInspectionTests(unittest.TestCase):
    def test_cache_bounds_and_overlapping_addresses_rejected(self):
        data = bytearray(4096)
        data[:16] = b'dyld_v1  arm64  '
        struct.pack_into('<II', data, 16, 32, 2)
        struct.pack_into('<QQQII', data, 32, 0x180000000, 4096, 0, 5, 5)
        struct.pack_into('<QQQII', data, 64, 0x180000800, 512, 2048, 1, 1)
        with self.assertRaisesRegex(ValueError, 'overlapping'): mappings(data)
        struct.pack_into('<Q', data, 32 + 8, 8192)
        with self.assertRaisesRegex(ValueError, 'exceeds'): mappings(data)

    def test_reference_requires_matching_register_and_executable_mapping(self):
        data = bytearray(64)
        # ADRP x1, current page; ADD x0, x1, #0x123.
        struct.pack_into('<II', data, 0, 0x90000001, 0x91048c20)
        address = 0x180001000
        refs = string_references(data, [(address, 64, 0, 5)], {address + 0x123})
        self.assertEqual(refs[address + 0x123][0]['address'], address)
        self.assertEqual(string_references(data, [(address, 64, 0, 1)], {address + 0x123})[address + 0x123], [])
        struct.pack_into('<I', data, 4, 0x91048c40)  # ADD source x2.
        self.assertEqual(string_references(data, [(address, 64, 0, 5)], {address + 0x123})[address + 0x123], [])

    def test_adrp_sign_extension(self):
        self.assertEqual(adrp_page(0x90000001, 0x1234), 0x1000)
        self.assertEqual(adrp_page(0xf0ffffe1, 0x1234), 0)
        self.assertIsNone(adrp_page(0xd503201f, 0x1234))

    def test_linker_relaxed_adr_and_prefixed_diagnostic_string(self):
        data = bytearray(4096)
        data[:16] = b'dyld_v1  arm64  '
        struct.pack_into('<II', data, 16, 32, 1)
        struct.pack_into('<QQQII', data, 32, 0x180000000, 4096, 0, 5, 5)
        marker = b'****** DIAGNOSTICS MODE ENABLED, SKIP INIT ****\0'
        data[256:256+len(marker)] = marker
        # ADR x0, #256 from #128; linker may use ADR/NOP instead of ADRP/ADD.
        struct.pack_into('<II', data, 128, 0x10000400, 0xd503201f)
        self.assertEqual(adr_target(0x10000400, 0x180000080), 0x180000100)
        result = inspect_bytes(data, cache=True)
        self.assertEqual(result['markers'][0]['address'], '0x180000100')
        self.assertEqual(result['markers'][0]['references'][0]['address'], '0x180000080')

    def test_unrelated_image_never_attached(self):
        with patch('inspect_keybag_host.command') as command:
            with self.assertRaisesRegex(ValueError, 'isolated'): inspect('other.raw')
            command.assert_not_called()

    def test_imported_condition_identified_and_corrupt_stub_index_rejected(self):
        data = bytearray(4096)
        # One executable segment/one stub section, SYMTAB and DYSYMTAB.
        struct.pack_into('<8I', data, 0, 0xfeedfacf, 0x100000c, 0, 2, 3, 256, 0, 0)
        struct.pack_into('<II', data, 32, 0x19, 152)
        struct.pack_into('<QQQQII', data, 56, 0x100000000, 4096, 0, 4096, 5, 5)
        struct.pack_into('<I', data, 96, 1)
        struct.pack_into('<QQ', data, 104 + 32, 0x100000240, 12)
        struct.pack_into('<III', data, 104 + 64, 8, 0, 12)
        struct.pack_into('<6I', data, 184, 2, 24, 1024, 1, 1100, 64)
        struct.pack_into('<II', data, 208, 0xb, 80)
        struct.pack_into('<II', data, 208 + 56, 1200, 1)
        struct.pack_into('<I', data, 1024, 1)
        name = b'_os_variant_uses_ephemeral_storage\0'
        data[1101:1101+len(name)] = name
        marker = b'DEVICE HAS EPHEMERAL DATA VOLUME\0'
        data[768:768+len(marker)] = marker
        # BL stub at #576 from #512; ADR string at #768 from #516.
        struct.pack_into('<II', data, 512, 0x94000010, 0x100007e0)
        result = inspect_bytes(data)
        instructions = result['markers'][0]['references'][0]['instructions']
        self.assertEqual(next(i['imported_callee'] for i in instructions if i['mnemonic'] == 'bl'),
                         '_os_variant_uses_ephemeral_storage')
        struct.pack_into('<I', data, 1200, 2)
        with self.assertRaisesRegex(ValueError, 'indirect symbol exceeds'): inspect_bytes(data)
