import struct
import unittest
from check_pmgr_bridges import bridge_windows
from test_device_tree_preparation import node


def tree(ranges):
    regs = [(0, 0x1000)] * 10 + [(0x7000000 + i * 0x10000, 0x1000) for i in range(14)]
    regs[21] = (0x600010000, 0x5000)
    pmgr = node([("name", b"pmgr\0"), ("bridge-reg-index", struct.pack("<I", 10)),
                 ("#bridges", struct.pack("<I", 14)),
                 ("reg", b"".join(struct.pack("<QQ", a, s) for a, s in regs))])
    return node([("name", b"device-tree\0")], [
        node([("name", b"arm-io\0"), ("ranges", ranges)], [pmgr])])


class PMGRBridgeTranslationTests(unittest.TestCase):
    def test_second_range_is_not_shifted_by_first_range(self):
        ranges = struct.pack("<6Q", 0, 0x200000000, 0x100000000,
                             0x600000000, 0x600000000, 0x200000000)
        banks = bridge_windows(tree(ranges))
        self.assertEqual(banks[0], (0x207000000, 0x1000))
        self.assertEqual(banks[11], (0x600010000, 0x5000))
        self.assertEqual(len(banks), 14)

    def test_unmapped_or_ambiguous_ranges_are_rejected(self):
        with self.assertRaises(ValueError):
            bridge_windows(tree(struct.pack("<3Q", 0, 0x200000000, 0x100000000)))
        overlapping = struct.pack("<6Q", 0, 0x200000000, 0x800000000, 0, 0, 0x800000000)
        with self.assertRaises(ValueError):
            bridge_windows(tree(overlapping))
