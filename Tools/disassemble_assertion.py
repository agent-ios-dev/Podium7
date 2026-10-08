"""Retain original ARM64 code responsible for an assertion panic."""
import struct
from analyze_firmware import macho


def branch_target(word, pc):
    if word & 0x7c000000 == 0x14000000:
        immediate, bits = word & 0x3ffffff, 26
    elif word & 0xff000010 == 0x54000000 or word & 0x7e000000 == 0x34000000:
        immediate, bits = (word >> 5) & 0x7ffff, 19
    elif word & 0x7e000000 == 0x36000000:
        immediate, bits = (word >> 5) & 0x3fff, 14
    else:
        return None
    if immediate & (1 << (bits - 1)):
        immediate -= 1 << bits
    return pc + immediate * 4


def assertion_evidence(kernel, caller):
    import capstone
    decoder = capstone.Cs(capstone.CS_ARCH_ARM64, capstone.CS_MODE_ARM)
    decoder.skipdata = True
    segments = macho(kernel)["segments"]
    segment = next((s for s in segments if int(s["address"], 16) <= caller <
                    int(s["address"], 16) + s["file_size"]), None)
    if segment is None:
        return "Assertion caller has no file-backed kernel segment\n"
    base = int(segment["address"], 16)
    targets = {caller - 64}  # typical panic thunk starts 64 bytes before LR
    branches = []
    for offset in range(segment["file_size"] // 4):
        pc = base + offset * 4
        word = struct.unpack_from("<I", kernel, segment["offset"] + offset * 4)[0]
        target = branch_target(word, pc)
        if target is not None:
            branches.append((pc, target))
    incoming = {pc for pc, target in branches if target in targets}
    # Also handle thunks with different prolog sizes by finding the closest
    # preceding incoming target within 128 bytes of the panic return address.
    if not incoming:
        preceding = [target for _, target in branches if caller - 128 <= target < caller]
        if preceding:
            targets = {max(preceding)}
            incoming = {pc for pc, target in branches if target in targets}
    conditional = {pc for pc, target in branches if target in incoming}
    windows = sorted({caller} | incoming | conditional)
    output = [f"Original kernel assertion caller: {caller:#x}"]
    for pc in windows[:32]:
        start, end = max(base, pc - 160), min(base + segment["file_size"], pc + 48)
        offset = segment["offset"] + start - base
        output.append(f"\nOriginal code around {pc:#x}")
        output.extend(f"{i.address:#x}: {i.mnemonic} {i.op_str}" for i in
                      decoder.disasm(kernel[offset:offset + end - start], start))
    return "\n".join(output) + "\n"
