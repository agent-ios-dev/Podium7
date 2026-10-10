"""Inspect original port0 DART tables at a real NVMe submission; no translation guess is applied."""
import re
from qmp_diagnostics import capture


def word_pair(snapshot):
    text = snapshot["physical_windows"][0]["backend_result"]
    values = re.findall(r"0x([0-9a-fA-F]{8})(?![0-9a-fA-F])", text.split(":", 1)[-1])
    if len(values) < 2:
        raise ValueError("QMP did not return both words of the original DART PTE")
    return int(values[0], 16) | (int(values[1], 16) << 32)


def inspect(path, trace, *, dump_root_pages=False):
    queues = re.findall(r"pci_nvme_mmio_asqaddr .*address=(0x[0-9a-fA-F]+)", trace)
    if not queues:
        raise ValueError("original NVMe ASQ address missing")
    iova = int(queues[-1], 16)
    roots = {int(offset, 16): int(value, 16) for offset, value in re.findall(
        r"PODIUM7 DART base=0000000601008000 write offset=(004[048c]) value=([0-9a-fA-F]+)", trace)}
    report = {"original_asq_iova": hex(iova), "candidates": [],
              "translation_applied": False, "guest_stopped_for_table_inspection": True}
    if dump_root_pages:
        windows = []
        for value in roots.values():
            base = (value & 0xfffffff) << 12
            if value & 0x80000000 and 0x40000000 <= base <= 0xbffff000:
                windows.extend((base + offset, 64) for offset in range(0, 4096, 256))
        if windows:
            report["original_root_table_pages"] = capture(path, physical_windows=tuple(windows))["physical_windows"]
    # Extra port-address candidate comes from actual root-table occupancy;
    # this diagnostic never installs an assumed PCIe inbound translation.
    for shift, iova_mask in ((12, 0xffffffff), (14, 0xffffffff), (12, 0x7fffffff)):
        walk_iova = iova & iova_mask
        bits = shift - 3
        index = walk_iova >> (shift + bits * 2)
        candidate = {"page_shift": shift, "root_index": index, "iova_mask": hex(iova_mask)}
        report["candidates"].append(candidate)
        ttbr = roots.get(0x40 + index * 4, 0)
        candidate["ttbr"] = hex(ttbr)
        if index >= 4 or not ttbr & 0x80000000:
            candidate["error"] = "root descriptor is absent or invalid"
            continue
        base = (ttbr & 0xfffffff) << 12
        l1 = base + ((walk_iova >> (shift + bits)) & ((1 << bits) - 1)) * 8
        candidate["l1_address"] = hex(l1)
        if not 0x40000000 <= l1 <= 0xbffffff8:
            candidate["error"] = "root table outside research RAM"
            continue
        first = word_pair(capture(path, physical_windows=((l1, 2),)))
        candidate["l1_descriptor"] = hex(first)
        if not first & 1:
            candidate["error"] = "invalid level1 descriptor"
            continue
        mask = ((1 << 40) - 1) & ~((1 << shift) - 1)
        l2 = (first & mask) + ((walk_iova >> shift) & ((1 << bits) - 1)) * 8
        candidate["l2_address"] = hex(l2)
        if not 0x40000000 <= l2 <= 0xbffffff8:
            candidate["error"] = "level2 table outside research RAM"
            continue
        second = word_pair(capture(path, physical_windows=((l2, 2),)))
        candidate["l2_descriptor"] = hex(second)
        if not second & 1:
            candidate["error"] = "invalid level2 descriptor"
            continue
        physical = (second & mask) | (walk_iova & ((1 << shift) - 1))
        candidate["translated_asq"] = hex(physical)
        if not 0x40000000 <= physical <= 0xbfffffc0:
            candidate["error"] = "submission queue outside research RAM"
            continue
        candidate["queue_words"] = capture(path, physical_windows=((physical, 16),))["physical_windows"][0]
    return report
