import struct
import unittest
from qemu_probe import boot_args, elf_image, PHYSICAL_BASE, RAM_SIZE, virtual_base_for_kernel, panic_capture_complete


class QEMUProbeTests(unittest.TestCase):
    def test_panic_capture_waits_for_complete_first_saved_state(self):
        state = (b"pc: 0xfffffff005e45984 cpsr: 0x80400204 "
                 b"esr: 0x96000010 far: 0xffffffe0004ac020\n")
        header = b"panic(cpu 0 caller 0xfffffff00780f61c): Kernel data abort.\n"
        self.assertFalse(panic_capture_complete(header + b"x16: 0xfffffff007823ffc"))
        self.assertFalse(panic_capture_complete(state + header))
        self.assertFalse(panic_capture_complete(header + state[:-1]))
        self.assertTrue(panic_capture_complete(header + state))

    def test_assertion_panic_completes_without_watchdog_saved_state(self):
        header = b'panic(cpu 0 caller 0xfffffff006705ac8): "REQUIRE failed" @ApplePMGR.cpp:1148'
        self.assertFalse(panic_capture_complete(header))
        self.assertTrue(panic_capture_complete(header + b"\n"))

    def test_kernel_base_covers_lower_prelinked_and_upper_text_segments(self):
        base = virtual_base_for_kernel(0xfffffff0054e4000, 0xfffffff007dd0000)
        self.assertEqual(base, 0xfffffff004000000)
        for address in [0xfffffff005b0c500, 0xfffffff0071904e8]:
            physical = PHYSICAL_BASE + address - base
            self.assertEqual(physical & 0x1ffffff, address & 0x1ffffff)
            self.assertEqual(base + physical - PHYSICAL_BASE, address)
        with self.assertRaises(ValueError):
            virtual_base_for_kernel(0xfffffff0054e4000, 0xfffffff007dd0000, 0x42000000)
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
