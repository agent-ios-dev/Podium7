import unittest
from verify_system_userland import evidence


class SystemUserlandTests(unittest.TestCase):
    trace = 'Exception return from AArch64 EL1 to AArch64 EL0 PC 0x100000000'
    hello = 'com.apple.xpc.launchd|1970 (system) <Notice>: hello\n'

    def test_root_wait_and_dma_failure_are_not_a_successful_boot(self):
        result = evidence('Still waiting for root device', 'NVME-DART rejected unmapped')
        self.assertFalse(result['system_userland_confirmed'])
        self.assertTrue(result['waiting_for_root_seen'])
        self.assertTrue(result['dma_rejection_seen'])

    def test_restore_launchd_does_not_pass_full_system_gate(self):
        self.assertFalse(evidence(self.hello + '<Notice>: Restore environment starting.', self.trace)['system_userland_confirmed'])

    def test_clean_fsck_is_a_distinct_milestone_not_a_complete_boot(self):
        result = evidence(self.hello + "QUICKCHECK ONLY; FILESYSTEM CLEAN", self.trace)
        self.assertTrue(result['filesystem_quickcheck_clean'])
        self.assertFalse(result['springboard_confirmed'])
        self.assertFalse(result['booted_ios'])
        self.assertFalse(evidence(self.hello, self.trace)['filesystem_quickcheck_clean'])

    def test_actual_system_launchd_and_el0_is_userland_only(self):
        result = evidence(self.hello, self.trace)
        self.assertTrue(result['system_userland_confirmed'])
        self.assertFalse(result['booted_ios'])
        self.assertFalse(evidence(self.hello+'panic(cpu 0', self.trace)['system_userland_confirmed'])

    def test_mount_tasks_and_failure_report_exact_observations(self):
        serial = self.hello + ('Doing boot task: fsck\r\nDoing boot task: mount-phase-1\n'
            'DT_get_fstab_entries:9975: failed to get volume for role: 256\n'
            'Boot task failed: mount-phase-1 - exited due to exit(66)\n')
        result = evidence(serial, self.trace)
        self.assertEqual(result['launchd_boot_tasks_observed'], ['fsck', 'mount-phase-1'])
        self.assertEqual(result['launchd_boot_failures'], ['mount-phase-1 - exited due to exit(66)'])
        self.assertEqual(result['fstab_missing_roles'], [256])
        self.assertFalse(result['springboard_confirmed'])
        result = evidence(self.hello, self.trace)
        self.assertEqual(result['launchd_boot_tasks_observed'], [])
        self.assertEqual(result['fstab_missing_roles'], [])


if __name__ == '__main__':unittest.main()
