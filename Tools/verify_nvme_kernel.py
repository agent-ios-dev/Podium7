"""Require original iOS NVMe driver initialization and actual sector DMA.

This is a storage milestone, never a SpringBoard or full OS boot assertion.
"""
import argparse
import json
import pathlib
import re


def evidence(serial, trace):
    reads = re.findall(r"^pci_nvme_read cid \d+ nsid 1 nlb \d+ count \d+ lba (0x[0-9a-f]+)$", trace, re.MULTILINE)
    result = {
        "original_driver_initialized": "Successfully initialized NVMe drive" in serial,
        "block_device_published": "IONVMeBlockStorageDevice RegistryID" in serial,
        "disk0_seen": bool(re.search(r"^disk0\s*$", serial, re.MULTILINE)),
        "original_io_queues_created": all(re.search(pattern, trace, re.MULTILINE) for pattern in (
            r"^pci_nvme_create_cq .*cqid=1,.*ien=1$",
            r"^pci_nvme_create_sq .*sqid=1, cqid=1,")),
        "actual_sector_reads": sorted(set(reads)),
        "msi_delivered": "PODIUM7 NVME-MSI delivered data=0 aic=288" in trace,
        "command_timeout_seen": ". Command timeout." in serial,
        "booted_ios": False,
    }
    result["storage_confirmed"] = all(result[key] for key in (
        "original_driver_initialized", "block_device_published", "disk0_seen",
        "original_io_queues_created", "msi_delivered")) and {"0x0", "0x1"}.issubset(reads) and not result["command_timeout_seen"]
    return result


def verify(directory):
    directory = pathlib.Path(directory)
    result = evidence((directory / "qemu-serial.txt").read_text(errors="replace"),
                      (directory / "qemu-trace.txt").read_text(errors="replace"))
    (directory / "nvme-kernel-checks.json").write_text(json.dumps(result, indent=2))
    if not result["storage_confirmed"]:
        raise RuntimeError("Original NVMe storage regression: driver, queues, IRQ and actual sector reads required")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=pathlib.Path)
    print(json.dumps(verify(parser.parse_args().directory), indent=2))
