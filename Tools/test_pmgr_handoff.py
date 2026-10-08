import unittest
from inspect_pmgr_handoff import inspect_properties


def u32(value):
    return value.to_bytes(4, "little").hex()


class PMGRHandoffTests(unittest.TestCase):
    def test_ipsw_missing_settings_are_not_hardware_register_faults(self):
        report = inspect_properties({"#bridges": u32(14), "optional-bridge-mask": u32(0x2000),
                                     "bridge-counter-version": u32(1)})
        self.assertEqual(report["missing_required_properties"], [f"bridge-settings-{i}" for i in range(13)])
        self.assertEqual(report["bridge_settings_version"], 0)
        self.assertFalse(report["settings_complete"])

    def test_present_empty_and_absent_settings_differ(self):
        report = inspect_properties({"#bridges": u32(2), "bridge-settings-0": ""})
        self.assertEqual(report["missing_required_properties"], ["bridge-settings-1"])
        self.assertTrue(report["entries"][0]["present"])

    def test_metadata_never_claims_boot_success(self):
        report = inspect_properties({"#bridges": u32(1), "bridge-settings-0": "0000000001000000"})
        self.assertTrue(report["settings_complete"])
        self.assertFalse(report["booted_ios"])
        malformed = inspect_properties({"#bridges": u32(1), "bridge-settings-0": "00000000"})
        self.assertFalse(malformed["settings_complete"])

    def test_legacy_version_and_bounds(self):
        report = inspect_properties({"#bridges": u32(1), "bridge-settings-version": u32(1)})
        self.assertEqual(report["missing_required_properties"], [])
        with self.assertRaises(ValueError):
            inspect_properties({"#bridges": u32(33)})
        with self.assertRaises(ValueError):
            inspect_properties({"#bridges": "01"})
