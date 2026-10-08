import struct
import unittest
from analyze_firmware import device_tree
from prepare_device_tree import prepare


def node(properties, children=()):
    data = struct.pack("<II", len(properties), len(children))
    for name, value in properties:
        data += name.encode().ljust(32, b"\0") + struct.pack("<I", len(value) | 0x80000000) + value + bytes((-len(value)) & 3)
    return data + b"".join(children)


class DeviceTreePreparationTests(unittest.TestCase):
    def test_cpu_clocks_match_counter_and_other_devices_are_preserved(self):
        cpu = node([("name", b"cpu0\0"), ("device_type", b"cpu\0"), ("timebase-frequency", bytes(4))])
        uart = node([("name", b"uart0\0"), ("reg", bytes(range(16)))])
        tree = node([("name", b"device-tree\0")], [node([("name", b"cpus\0")], [cpu]), uart])
        prepared, changes = prepare(tree, 24_000_000, random_seed=bytes(64))
        self.assertEqual(len(changes), 2)
        self.assertEqual(device_tree(prepared)[-1], device_tree(tree)[-1])
        self.assertIn(struct.pack("<Q", 24_000_000), prepared)
        again, _ = prepare(prepared, 24_000_000, random_seed=bytes(64))
        self.assertEqual(prepared, again)
    def test_no_cpu_and_bad_frequency_are_rejected(self):
        tree = node([("name", b"root\0")])
        with self.assertRaises(ValueError): prepare(tree, 24_000_000)
        with self.assertRaises(ValueError): prepare(tree, 0)
    def test_boot_seed_is_fresh_and_has_exact_required_length(self):
        cpu = node([("name", b"cpu0\0"), ("device_type", b"cpu\0")])
        tree = node([("name", b"device-tree\0")], [node([("name", b"cpus\0")], [cpu]), node([("name", b"chosen\0")])])
        first, changes = prepare(tree, 24_000_000)
        second, _ = prepare(tree, 24_000_000)
        self.assertNotEqual(first, second)
        self.assertEqual(next(x for x in changes if x["property"] == "random-seed")["bytes"], 64)
        self.assertIn(b"random-seed", first)
        with self.assertRaises(ValueError): prepare(tree, 24_000_000, random_seed=bytes(32))
        self.assertIn(b"dram-base", first)
        self.assertIn(b"dram-size", first)
        self.assertEqual(next(x for x in changes if x["property"] == "dram-base")["value"], "0x40000000")
        with self.assertRaises(ValueError): prepare(tree, 24_000_000, dram_base=0xffffffffffffffff, dram_size=2)

    def test_aic_ipid_mask_is_preserved_for_hardware_sized_model(self):
        mask = bytes(range(40))
        aic = node([("name", b"aic\0"), ("compatible", b"aic,1\0"), ("ipid-mask", mask)])
        arm_io = node([("name", b"arm-io\0")], [aic])
        cpu = node([("name", b"cpu0\0"), ("device_type", b"cpu\0")])
        tree = node([("name", b"device-tree\0")], [node([("name", b"cpus\0")], [cpu]), arm_io])

        prepared, changes = prepare(tree, 24_000_000, random_seed=bytes(64))

        encoded_property = b"ipid-mask".ljust(32, b"\0") + struct.pack("<I", len(mask)) + mask
        self.assertIn(encoded_property, prepared)
        self.assertFalse(any(x.get("property") == "ipid-mask" for x in changes))


class ResearchBridgeHandoffTests(unittest.TestCase):
    def make_tree(self, compatible=b"pmgr1,t8010\0"):
        cpu = node([("name", b"cpu0\0"), ("device_type", b"cpu\0")])
        pmgr = node([("name", b"pmgr\0"), ("compatible", compatible),
                     ("#bridges", struct.pack("<I", 14)),
                     ("optional-bridge-mask", struct.pack("<I", 0x2000)),
                     ("bridge-settings-3", bytes(range(8)))])
        return node([("name", b"device-tree\0")], [node([("name", b"cpus\0")], [cpu]),
                         node([("name", b"arm-io\0")], [pmgr])])

    def test_opt_in_preserves_real_settings_and_mask(self):
        tree = self.make_tree()
        unchanged, _ = prepare(tree, 24000000, random_seed=bytes(64))
        original = device_tree(unchanged)[-1]["properties"]
        self.assertNotIn("bridge-settings-0", original)
        prepared, changes = prepare(tree, 24000000, random_seed=bytes(64), research_bridge_handoff=True)
        properties = device_tree(prepared)[-1]["properties"]
        self.assertEqual(properties["bridge-settings-0"], "")
        self.assertEqual(properties["bridge-settings-3"], bytes(range(8)).hex())
        self.assertEqual(properties["optional-bridge-mask"], "00200000")
        self.assertNotIn("bridge-settings-version", properties)
        self.assertFalse(next(c for c in changes if c.get("source") == "synthetic research bridge model")["authentic_iboot_handoff"])

    def test_other_platforms_rejected(self):
        with self.assertRaises(ValueError):
            prepare(self.make_tree(b"pmgr,t8103\0"), 24000000, random_seed=bytes(64), research_bridge_handoff=True)
