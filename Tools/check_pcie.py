"""Exercise original T8010 PCIe control and empty configuration windows with an ARM64 guest."""
import argparse
import json
import pathlib
import subprocess
import tempfile
import struct

from analyze_firmware import device_tree

from check_qemu_registers import text_section
from qemu_probe import elf_image


def check(executable, report, tree):
    nodes = device_tree(tree.read_bytes())
    node = next(n for n in nodes if n["path"] == "/device-tree/arm-io/apcie")
    apertures = list(struct.iter_unpack("<QQ", bytes.fromhex(node["properties"]["reg"])))
    if len(apertures) != 12 or apertures[0] != (0x610000000, 0x1000000):
        raise ValueError("original T8010 PCIe aperture schema changed")
    banks = apertures[1:]
    if any(size < 0x1000 or size > 0x8000 for base, size in banks):
        raise ValueError("unexpected PCIe control aperture size")
    assembly = '''.text
adr x7, banks
mov x9, #11
next_bank:
ldp x3, x6, [x7], #16
ldr w4, [x3, #0x24]
cbnz w4, failure
mov w5, #0xfffc
movk w5, #0x20, lsl #16
str w5, [x3, #0x24]
ldr w4, [x3, #0x24]
cmp w4, w5
b.ne failure
movz x11, #0x8000
movk x11, #6, lsl #32
cmp x3, x11
b.eq skip_phy_status
mov w5, #0x80808080
str w5, [x3, #0xc]
ldr w4, [x3, #0xc]
cmp w4, w5
b.ne failure
skip_phy_status:
mov w5, #0x1234
str w5, [x3, #0x30]
str w5, [x3, #0x20]
ldr w4, [x3, #0x20]
cmp w4, w5
b.ne failure
sub x6, x6, #4
ldr w4, [x3, x6]
cbnz w4, failure
str w5, [x3, x6]
ldr w4, [x3, x6]
cmp w4, w5
b.ne failure
subs x9, x9, #1
b.ne next_bank
movz x3, #0
movk x3, #0x0100, lsl #16
movk x3, #6, lsl #32
mov w5, #0x31
str w5, [x3, #0x124]
movz x11, #0x8000
movk x11, #6, lsl #32
ldr w4, [x11, #0xc]
cmp w4, #3
b.ne failure
str wzr, [x3, #0x124]
ldr w4, [x11, #0xc]
cbnz w4, failure
movz x3, #0x4000
movk x3, #0x0100, lsl #16
movk x3, #6, lsl #32
movz w5, #1, lsl #16
str w5, [x3, #4]
ldr w4, [x3, #4]
cbnz w4, failure
mov w5, #3
str w5, [x3, #4]
ldr w4, [x3, #4]
cmp w4, w5
b.ne failure
movz x3, #0
movk x3, #6, lsl #32
ldr w4, [x3, #0x28]
cbnz w4, failure
mov w5, #1
str w5, [x3, #0x124]
ldr w4, [x3, #0x28]
cmp w4, #0x11
b.ne failure
str wzr, [x3, #0x124]
ldr w4, [x3, #0x28]
cbnz w4, failure
movz x3, #0
movk x3, #0x1000, lsl #16
movk x3, #6, lsl #32
ldr w4, [x3]
movz w5, #0x1b36
movk w5, #0xc, lsl #16
cmp w4, w5
b.ne failure
ldr w4, [x3, #0x34]
cmp w4, #0x80
b.ne failure
ldr w4, [x3, #0x80]
movz w5, #0x10
movk w5, #0x42, lsl #16
cmp w4, w5
b.ne failure
ldr w4, [x3, #0x8c]
cmp w4, #0x11
b.ne failure
str wzr, [x3, #0x8c]
ldr w4, [x3, #0x8c]
cmp w4, #0x11
b.ne failure
ldr w4, [x3, #0xac]
cmp w4, #2
b.ne failure
ldr w4, [x3, #0x90]
cbnz w4, failure
add x3, x3, #0x100, lsl #12
ldr w4, [x3]
cmn w4, #1
b.ne failure
str wzr, [x3]
ldr w4, [x3]
cmn w4, #1
b.ne failure
ldrb w4, [x3, #1]
cmp w4, #255
b.ne failure
ldrh w4, [x3, #2]
mov w5, #0xffff
cmp w4, w5
b.ne failure
mov x6, #0xfffc
movk x6, #0xef, lsl #16
ldr w4, [x3, x6]
cmn w4, #1
b.ne failure
mov x0, #0x20
adr x1, success_exit
hlt #0xf000
b .
failure:
mov x0, #0x20
adr x1, failure_exit
hlt #0xf000
b .
.p2align 3
success_exit:
.quad 0x20026, 0
failure_exit:
.quad 0x20026, 1
banks:
.quad 0x601000000, 0x4000, 0x601004000, 0x4000
.quad 0x602000000, 0x4000, 0x602004000, 0x4000
.quad 0x603000000, 0x4000, 0x603004000, 0x4000
.quad 0x604000000, 0x4000, 0x604004000, 0x4000
.quad 0x600000000, 0x8000, 0x600008000, 0x4000
.quad 0x60a000000, 0x4000
'''
    bank_start = assembly.index("banks:\n")
    assembly = assembly[:bank_start] + "banks:\n" + "".join(
        f".quad {hex(base)}, {hex(size)}\n" for base, size in banks)
    with tempfile.TemporaryDirectory() as temporary:
        root = pathlib.Path(temporary)
        (root / "test.s").write_text(assembly)
        subprocess.run(["xcrun", "clang", "-arch", "arm64", "-c", str(root / "test.s"),
                        "-o", str(root / "test.o")], check=True)
        code = text_section((root / "test.o").read_bytes())
        image = root / "test.elf"
        image.write_bytes(elf_image(0x45000000, [(0x45000000, len(code), code)]))
        result = subprocess.run([executable, "-machine", "virt,secure=off,virtualization=off",
            "-cpu", "podium7-research", "-m", "128", "-display", "none", "-monitor", "none",
            "-serial", "none", "-semihosting-config", "enable=on,target=native", "-device",
            f"loader,file={image},cpu-num=0"], capture_output=True, text=True, timeout=10)
        passed = result.returncode == 0
        report.write_text(json.dumps({"passed": passed,
            "model": "T8010 PCIe controller discovery; no attached endpoints",
            "checks": ["controller register writes and empty ECAM widths",
                       "11 independent control banks and final configuration-space boundary"],
            "returncode": result.returncode, "stdout": result.stdout,
            "stderr": result.stderr}, indent=2))
        if not passed:
            raise RuntimeError("T8010 PCIe discovery MMIO checks failed")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--qemu", required=True)
    parser.add_argument("--report", type=pathlib.Path,
                        default=pathlib.Path(".firmware/pcie-checks.json"))
    parser.add_argument("--device-tree", required=True, type=pathlib.Path)
    arguments = parser.parse_args()
    check(arguments.qemu, arguments.report, arguments.device_tree)
