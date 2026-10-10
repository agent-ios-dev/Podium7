import unittest
from verify_pmp_integration import evidence


class IntegrationEvidenceTests(unittest.TestCase):
    def test_realization_alone_does_not_prove_firmware_execution(self):
        result = evidence("PODIUM7 PMP integrated ARM32 core realized")
        self.assertTrue(result["arm32_core_realized"])
        self.assertFalse(result["driver_released_firmware"])
        self.assertFalse(result["original_reset_body_executed"])
        self.assertFalse(result["ios_boot_confirmed"])

    def test_hello_send_does_not_prove_ap_receipt(self):
        result = evidence("PODIUM7 SEP-MAILBOX base=000000020e300000 write offset=0bb0 value=000c000c\n"
                          "PODIUM7 SEP-MAILBOX base=000000020e300000 write offset=0bb4 value=00100000")
        self.assertTrue(result["original_boot_hello_written"])
        self.assertFalse(result["ap_read_original_boot_hello"])
        self.assertFalse(result["ios_boot_confirmed"])

    def test_other_iop_hello_cannot_be_counted_as_pmp(self):
        result = evidence("PODIUM7 SEP-MAILBOX base=000000020da00000 write offset=0bb0 value=000c000c\n"
                          "PODIUM7 SEP-MAILBOX base=000000020da00000 write offset=0bb4 value=00100000")
        self.assertFalse(result["original_boot_hello_written"])

    def test_startup_text_without_executed_protocol_is_not_boot(self):
        result = evidence("", "ApplePMP: started\n[PMP:main.cpp:579] PMP started\n")
        self.assertTrue(result["pmp_driver_started"])
        self.assertTrue(result["original_firmware_started"])
        self.assertFalse(result["pmp_boot_confirmed"])
        self.assertFalse(result["ios_boot_confirmed"])

    def test_saved_fault_translation_must_match_exact_virtual_address(self):
        from resolve_mmio_fault import snapshot_physical_address
        snapshot = {"translations": [{"virtual_address": "0xffffffe84dc6c008", "backend_result": "gpa: 0x207b00008\r\n"}]}
        self.assertEqual(snapshot_physical_address(snapshot, 0xffffffe84dc6c008), 0x207b00008)
        self.assertIsNone(snapshot_physical_address(snapshot, 0xffffffe84dc6c000))
        snapshot["translations"][0]["backend_result"] = "translation failed: gpa: 0x207b00008"
        self.assertIsNone(snapshot_physical_address(snapshot, 0xffffffe84dc6c008))
