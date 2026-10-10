import unittest
from unittest.mock import patch
from nvme_dma_diagnostics import inspect, word_pair


class DARTInspectionTests(unittest.TestCase):
    def test_missing_original_submission_is_not_invented(self):
        with self.assertRaisesRegex(ValueError, "ASQ"):
            inspect("qmp", "")

    def test_absent_tables_never_read_unrelated_guest_memory(self):
        with patch("nvme_dma_diagnostics.capture") as read:
            result = inspect("qmp", "pci_nvme_mmio_asqaddr wrote address=0x857b4000")
        read.assert_not_called()
        self.assertFalse(result["translation_applied"])
        self.assertTrue(all("error" in item for item in result["candidates"]))

    def test_little_endian_descriptor_and_bounded_two_level_inspection(self):
        trace = ("pci_nvme_mmio_asqaddr wrote address=0x857b4000\n"
                 "PODIUM7 DART base=0000000601008000 write offset=0048 value=80055000")
        replies = [
            {"physical_windows": [{"backend_result": "0x55000158: 0x55100001 0x00000000"}]},
            {"physical_windows": [{"backend_result": "0x55100da0: 0x55234003 0x00000000"}]},
            {"physical_windows": [{"backend_result": "0x55234000: 0x00000006"}]},
        ]
        with patch("nvme_dma_diagnostics.capture", side_effect=replies) as read:
            result = inspect("qmp", trace)
        self.assertEqual(result["candidates"][0]["translated_asq"], "0x55234000")
        self.assertEqual([c.kwargs["physical_windows"] for c in read.call_args_list],
                         [((0x55000158, 2),), ((0x55100da0, 2),), ((0x55234000, 16),)])
        self.assertFalse(result["translation_applied"])
        self.assertEqual(word_pair({"physical_windows": [{"backend_result":
            "0x40000000: 0x89abcdef 0x01234567"}]}), 0x0123456789abcdef)


if __name__ == "__main__":
    unittest.main()
