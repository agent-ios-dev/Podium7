import unittest
from boot_milestones import inspect


class MilestoneTests(unittest.TestCase):
    def test_load_attempt_and_kernel_only_are_not_userland(self):
        self.assertFalse(inspect("AMFI: launchd rejected", "")['userland_execution_confirmed'])
        self.assertFalse(inspect("com.apple.xpc.launchd|time <Notice>: hello", "EL1 to AArch64 EL1")['userland_execution_confirmed'])

    def test_restore_execution_does_not_claim_desktop(self):
        result = inspect("com.apple.xpc.launchd|time <Notice>: hello\n<Notice>: Restore environment starting.",
                         "Exception return from AArch64 EL1 to AArch64 EL0 PC 0x104f81170")
        self.assertTrue(result['userland_execution_confirmed'])
        self.assertTrue(result['restore_environment_seen'])
        self.assertEqual(result['first_el0_pc'], '0x104f81170')
        self.assertFalse(result['booted_ios'])
        self.assertFalse(result['springboard_confirmed'])
