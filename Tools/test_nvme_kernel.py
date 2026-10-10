import unittest
from verify_nvme_kernel import evidence


class OriginalStorageEvidenceTests(unittest.TestCase):
    serial = "Successfully initialized NVMe drive\nIONVMeBlockStorageDevice RegistryID : 1\ndisk0\n"
    trace = ("pci_nvme_create_cq create completion queue, addr=0x825cc000, cqid=1, vector=0, qsize=256, qflags=3, ien=1\n"
             "pci_nvme_create_sq create submission queue, addr=0x825e0000, sqid=1, cqid=1, qsize=256, qflags=5\n"
             "pci_nvme_read cid 5 nsid 1 nlb 1 count 512 lba 0x0\n"
             "pci_nvme_read cid 8 nsid 1 nlb 1 count 512 lba 0x1\n"
             "PODIUM7 NVME-MSI delivered data=0 aic=288\n")

    def test_hardware_guest_alone_is_not_original_driver_proof(self):
        self.assertFalse(evidence("", self.trace)["storage_confirmed"])

    def test_original_driver_and_reads_confirm_storage_only(self):
        result = evidence(self.serial, self.trace)
        self.assertTrue(result["storage_confirmed"])
        self.assertFalse(result["booted_ios"])

    def test_timeout_or_missing_sector_fails_gate(self):
        self.assertFalse(evidence(self.serial + ". Command timeout.", self.trace)["storage_confirmed"])
        self.assertFalse(evidence(self.serial, self.trace.replace("lba 0x1", "lba 0x0"))["storage_confirmed"])


if __name__ == "__main__":
    unittest.main()
