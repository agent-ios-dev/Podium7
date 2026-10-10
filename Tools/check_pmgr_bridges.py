"""Test all n112ap PMGR bridge windows with an assembler-built ARM64 guest."""
import argparse
import json
import pathlib
import struct
import subprocess
import tempfile
from analyze_firmware import device_tree
from check_qemu_registers import text_section
from qemu_probe import elf_image


def bridge_windows(tree):
    nodes = device_tree(tree)
    pmgr = next(n for n in nodes if n["path"] == "/device-tree/arm-io/pmgr")["properties"]
    armio = next(n for n in nodes if n["path"] == "/device-tree/arm-io")["properties"]
    ranges = bytes.fromhex(armio["ranges"])
    if not ranges or len(ranges) % 24:
        raise ValueError("invalid 64-bit arm-io translation ranges")
    translations = list(struct.iter_unpack("<QQQ", ranges))
    first = int.from_bytes(bytes.fromhex(pmgr["bridge-reg-index"]), "little")
    count = int.from_bytes(bytes.fromhex(pmgr["#bridges"]), "little")
    regs = list(struct.iter_unpack("<QQ", bytes.fromhex(pmgr["reg"])))
    if first + count > len(regs) or count != 14:
        raise ValueError("unexpected n112ap PMGR bridge table")
    banks = []
    for address, size in regs[first:first + count]:
        matches = [(child, parent) for child, parent, length in translations
                   if child <= address and address + size <= child + length]
        if len(matches) != 1 or size < 8 or size % 4:
            raise ValueError("PMGR bridge outside unique arm-io translation")
        child, parent = matches[0]
        banks.append((parent + address - child, size))
    return banks


def address_register(address):
    return [f"movz x3, #{address & 0xffff}"] + [
        f"movk x3, #{(address >> shift) & 0xffff}, lsl #{shift}" for shift in (16, 32, 48)]


def check(executable, tree, report):
    banks = bridge_windows(tree)
    assembly = [".text"]
    # Initialize distinct values at both ends. Read them all back in a second
    # pass to detect accidental shared storage or truncated high addresses.
    for index, (base, size) in enumerate(banks):
        for edge, address in enumerate((base, base + size - 4)):
            assembly += address_register(address)
            assembly += ["ldr w4, [x3]", "cbnz w4, failure",
                         f"mov w5, #{0x100 + index * 2 + edge}", "str w5, [x3]"]
    for index, (base, size) in enumerate(banks):
        for edge, address in enumerate((base, base + size - 4)):
            assembly += address_register(address)
            assembly += ["ldr w4, [x3]", f"cmp w4, #{0x100 + index * 2 + edge}", "b.ne failure"]
    # Original ApplePMGR telemetry reads an aligned 64-bit pair at +0x8110.
    # Check the actual faulting offset and paired-word semantics in every bank.
    for base, size in banks:
        offsets = [8, size - 16] + ([0x8110] if size > 0x8118 else [])
        for offset in offsets:
            assembly += address_register(base + offset)
            assembly += ["movz x5, #0x1234", "movk x5, #0xabcd, lsl #48",
                         "str x5, [x3]", "ldr x6, [x3]", "cmp x5, x6", "b.ne failure",
                         "ldr w6, [x3]", "mov w5, #0x1234", "cmp w5, w6", "b.ne failure",
                         "ldr w6, [x3, #4]", "mov w5, #0xabcd0000", "cmp w5, w6", "b.ne failure"]
    assembly += ["mov x0, #0x20", "adr x1, success_exit", "hlt #0xf000", "b .",
                 "failure:", "mov x0, #0x20", "adr x1, failure_exit", "hlt #0xf000", "b .",
                 ".p2align 3", "success_exit:", ".quad 0x20026, 0",
                 "failure_exit:", ".quad 0x20026, 1"]
    with tempfile.TemporaryDirectory() as temporary:
        root = pathlib.Path(temporary)
        (root / "test.s").write_text("\n".join(assembly) + "\n")
        subprocess.run(["xcrun", "clang", "-arch", "arm64", "-c", str(root / "test.s"),
                        "-o", str(root / "test.o")], check=True)
        code = text_section((root / "test.o").read_bytes())
        image = root / "test.elf"
        image.write_bytes(elf_image(0x45000000, [(0x45000000, len(code), code)]))
        result = subprocess.run([executable, "-machine", "virt,secure=off,virtualization=off",
            "-cpu", "podium7-research", "-m", "128", "-display", "none", "-monitor", "none",
            "-serial", "none", "-semihosting-config", "enable=on,target=native", "-device",
            f"loader,file={image},cpu-num=0"], capture_output=True, text=True, timeout=10)
        report.write_text(json.dumps({"passed": result.returncode == 0,
            "scope": "PMGR bridge backing registers; no iBoot settings or power transition claim",
            "banks": [{"base": hex(base), "size": size} for base, size in banks],
            "checks": ["zero initialization", "both boundaries persist", "independent banks",
                       "bridge 11 preserves physical address above 16 GiB", "64-bit pairs, word order, and original +0x8110 telemetry access"],
            "returncode": result.returncode, "stderr": result.stderr}, indent=2))
        if result.returncode:
            raise RuntimeError("PMGR bridge guest MMIO checks failed")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--qemu", required=True)
    parser.add_argument("--tree", type=pathlib.Path, default=pathlib.Path(".firmware/DeviceTree.bin"))
    parser.add_argument("--report", type=pathlib.Path, default=pathlib.Path(".firmware/pmgr-bridge-checks.json"))
    args = parser.parse_args()
    check(args.qemu, args.tree.read_bytes(), args.report)
