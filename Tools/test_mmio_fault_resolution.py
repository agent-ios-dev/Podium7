import unittest
from resolve_mmio_fault import physical_address


class MMIOFaultResolutionTests(unittest.TestCase):
    def test_exact_mapping_wins_over_nearby_watchdog_mapping(self):
        trace = "KVA-OUTSIDE-HARNESS-RAM va=ffff0000160 pa=20e080160 page-size=16384\n"
        trace += "KVA-OUTSIDE-HARNESS-RAM va=ffff0000100 pa=210200100 page-size=16384\n"
        self.assertEqual(physical_address(trace, 0xffff0000160), 0x20e080160)

    def test_nearby_mapping_requires_matching_page_offsets(self):
        trace = "KVA-OUTSIDE-HARNESS-RAM va=ffff0000100 pa=20e080100 page-size=16384\n"
        self.assertEqual(physical_address(trace, 0xffff0000160), 0x20e080160)
        self.assertIsNone(physical_address(trace, 0xffff0008160))
        bad = "KVA-OUTSIDE-HARNESS-RAM va=ffff0000100 pa=20e080101 page-size=16384\n"
        self.assertIsNone(physical_address(bad, 0xffff0000160))
