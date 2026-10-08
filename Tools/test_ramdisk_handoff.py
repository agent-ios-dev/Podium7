import struct
import unittest
from ramdisk_handoff import attach_ramdisk, validate_hfs
from test_device_tree_preparation import node
from qemu_probe import boot_args


class RamdiskTests(unittest.TestCase):
    def test_real_geometry_and_sector_trailer(self):
        image = bytearray(8192 + 1536)
        struct.pack_into(">HH", image, 1024, 0x4858, 5)
        struct.pack_into(">II", image, 1064, 4096, 2)
        self.assertEqual(validate_hfs(image)["filesystem"], "HFSX")
        with self.assertRaises(ValueError): validate_hfs(image[:8191])
        struct.pack_into(">II", image, 1064, 4096, 3)
        with self.assertRaises(ValueError): validate_hfs(image)

    def test_creates_or_extends_memory_map_without_losing_entries(self):
        for children in [[], [node([("name", b"memory-map\0"), ("existing", b"KEEP")])]]:
            tree = node([("name", b"device-tree\0")], [node([("name", b"chosen\0")], children)])
            prepared = attach_ramdisk(tree, 0x48000000, 8192)
            self.assertIn(b"RAMDisk".ljust(32, b"\0") + struct.pack("<IQQ", 16, 0x48000000, 8192), prepared)
            if children: self.assertIn(b"KEEP", prepared)
            with self.assertRaises(ValueError): attach_ramdisk(prepared, 0x48000000, 8192)
        with self.assertRaises(ValueError): attach_ramdisk(tree, 0x48000001, 8192)
        with self.assertRaises(ValueError): attach_ramdisk(tree, 0x48000000, 8193)
        with self.assertRaises(ValueError): attach_ramdisk(node([("name", b"device-tree\0")]), 0x48000000, 8192)

    def test_root_argument_and_reserved_top(self):
        args = boot_args(0xfffffff004000000, 0xfffffff008000000, 100, 0x51000000, ramdisk=True)
        self.assertEqual(struct.unpack_from("<Q", args, 32)[0], 0x51000000)
        self.assertEqual(args[108:716].split(b"\0", 1)[0], b"-v serial=3 debug=0x8 rd=md0")
