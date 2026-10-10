import struct
import unittest
from guest_proxy_label import inspect


class ProxyLabelTests(unittest.TestCase):
    def fixture(self, label='com.apple.backboardd', start=0x100010000):
        proc, task, vmmap, pmap, root = [0xffffffe100000000 + i * 0x1000 for i in range(5)]
        payload = b'executable_path=/usr/libexec/xpcproxy\0/usr/libexec/xpcproxy\0' + label.encode() + b'\000123\0SECRET_ENV=not-exported\0'
        kernel = {proc+0x340: struct.pack('<II', len(payload), 3),
                  proc+0x348: struct.pack('<Q', start+len(payload)),
                  proc+0x10: struct.pack('<Q', task), task+0x28: struct.pack('<Q', vmmap),
                  vmmap+0x40: struct.pack('<Q', pmap), pmap: struct.pack('<Q', root),
                  root+((start>>36)&7)*8: struct.pack('<Q', 0x40010003)}
        physical = {0x40010000+((start>>25)&0x7ff)*8: struct.pack('<Q', 0x40014003)}
        pages = {}
        for i, value in enumerate(payload):
            address = start+i
            slot = (address >> 14) & 0x7ff
            pa = 0x40018000+(slot-((start>>14)&0x7ff))*0x4000
            physical[0x40014000+slot*8] = struct.pack('<Q', pa|3)
            pages.setdefault(pa, bytearray(0x4000))[address&0x3fff] = value
        def read_physical(address, size):
            if address in physical:
                return physical[address]
            page = address & ~0x3fff
            return bytes(pages[page][address-page:address-page+size])
        return proc, kernel, physical, read_physical

    def test_label_only_and_cross_page_arguments(self):
        for start in (0x100010000, 0x100013fe8):
            proc, kernel, _, physical = self.fixture(start=start)
            self.assertEqual(inspect(proc, lambda a,s: kernel[a], physical,
                                     {'com.apple.backboardd'}), 'com.apple.backboardd')

    def test_unknown_label_is_not_exported(self):
        proc, kernel, _, physical = self.fixture('secret-value')
        with self.assertRaisesRegex(ValueError, 'original launch metadata'):
            inspect(proc, lambda a,s: kernel[a], physical, {'com.apple.backboardd'})

    def test_invalid_mapping_never_reads_mmio(self):
        proc, kernel, entries, physical = self.fixture()
        entries[next(iter(entries))] = struct.pack('<Q', 0x20e300003)
        with self.assertRaisesRegex(ValueError, 'outside research DRAM'):
            inspect(proc, lambda a,s: kernel[a], physical, {'com.apple.backboardd'})

    def test_invalid_argc_does_not_read_user_memory(self):
        proc, kernel, _, _ = self.fixture()
        kernel[proc+0x340] = struct.pack('<II', 100, 1)
        with self.assertRaisesRegex(ValueError, 'argument layout'):
            inspect(proc, lambda a,s: kernel[a],
                    lambda a,s: self.fail('user memory read'), {'com.apple.backboardd'})
