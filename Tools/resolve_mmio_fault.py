"""Resolve a saved fault VA using observed QEMU translation evidence."""
import re
import struct
from analyze_firmware import device_tree


def physical_address(trace, virtual_address):
    candidates = []
    for match in re.finditer(r"KVA-OUTSIDE-HARNESS-RAM va=([0-9a-f]+) pa=([0-9a-f]+) page-size=(\d+)", trace):
        va, pa, page = int(match[1], 16), int(match[2], 16), int(match[3])
        if page <= 0 or page & (page - 1) or (va & (page - 1)) != (pa & (page - 1)):
            continue
        if va == virtual_address:
            candidates.append((2, match.start(), pa))
        elif va // page == virtual_address // page:
            candidates.append((1, match.start(), pa + virtual_address - va))
    return max(candidates)[2] if candidates else None


def snapshot_physical_address(snapshot, virtual_address):
    """Accept only the exact VA's successful stopped-CPU QMP translation."""
    for entry in snapshot.get("translations", []):
        try:
            if int(entry["virtual_address"], 16) != virtual_address:
                continue
        except (KeyError, TypeError, ValueError):
            continue
        match = re.fullmatch(r"\s*gpa:\s*(0x[0-9a-fA-F]+)\s*", entry.get("backend_result", ""))
        if match and int(match[1], 16) < 1 << 64:
            return int(match[1], 16)
    return None


def owners(tree, physical):
    nodes = device_tree(tree)
    armio = next((n for n in nodes if n["path"] == "/device-tree/arm-io"), None)
    if armio is None:
        return []
    encoded = bytes.fromhex(armio["properties"].get("ranges", ""))
    if not encoded or len(encoded) % 24:
        return []
    ranges = list(struct.iter_unpack("<QQQ", encoded))
    matches = []
    for node in nodes:
        if node["path"].rsplit("/", 1)[0] != armio["path"]:
            continue
        regs = bytes.fromhex(node["properties"].get("reg", ""))
        if len(regs) % 16:
            continue
        for index, (address, size) in enumerate(struct.iter_unpack("<QQ", regs)):
            for child, parent, length in ranges:
                if child <= address and address + size <= child + length:
                    base = parent + address - child
                    if base <= physical < base + size:
                        matches.append({"path": node["path"], "reg_index": index,
                                        "physical_base": hex(base), "size": size,
                                        "offset": hex(physical - base)})
    return matches
