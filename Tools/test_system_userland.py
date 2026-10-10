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

    def test_actual_system_launchd_and_el0_is_userland_only(self):
        result = evidence(self.hello, self.trace)
        self.assertTrue(result['system_userland_confirmed'])
        self.assertFalse(result['booted_ios'])
        self.assertFalse(evidence(self.hello+'panic(cpu 0', self.trace)['system_userland_confirmed'])


if __name__ == '__main__':unittest.main()
