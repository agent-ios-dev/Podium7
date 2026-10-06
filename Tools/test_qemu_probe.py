import struct
import unittest
from qemu_probe import boot_args, elf_image, PHYSICAL_BASE, RAM_SIZE


class QEMUProbeTests(unittest.TestCase):
    def test_boot_args_ios15_layout(self):
        args = boot_args(0xfffffff0054e4000, 0xfffffff007d00000, 1234, 0x48000000)
        self.assertEqual(len(args), 736)
        self.assertEqual(struct.unpack_from("<HH", args), (2, 2))
        self.assertEqual(struct.unpack_from("<Q", args, 16)[0], PHYSICAL_BASE)
        self.assertEqual(struct.unpack_from("<Q", args, 24)[0], RAM_SIZE)
        self.assertEqual(struct.unpack_from("<QI", args, 96), (0xfffffff007d00000, 1234))
        self.assertEqual(args[108:716].split(b"\0", 1)[0], b"-v serial=3 debug=0x8")
        self.assertEqual(struct.unpack_from("<Q", args, 720)[0], 0)
        self.assertEqual(struct.unpack_from("<Q", args, 728)[0], RAM_SIZE)

    def test_elf_load_addresses_and_zero_fill(self):
        data = elf_image(0x40004000, [(0x40004000, 0x1000, b"test")])
        self.assertEqual(data[:4], b"\x7fELF")
        self.assertEqual(struct.unpack_from("<H", data, 18)[0], 183)
        self.assertEqual(struct.unpack_from("<Q", data, 24)[0], 0x40004000)
        self.assertEqual(struct.unpack_from("<II6Q", data, 64), (1, 7, 120, 0x40004000, 0x40004000, 4, 0x1000, 1))
        self.assertEqual(data[120:], b"test")
        with self.assertRaises(ValueError):
            elf_image(0, [(0, 1, b"test")])
