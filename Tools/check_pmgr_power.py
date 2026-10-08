"""Exercise the T8010 PMGR power-state handshake with an ARM64 guest."""
import argparse
import json
import pathlib
import subprocess
import tempfile

from check_qemu_registers import text_section
from qemu_probe import elf_image


def check(executable, report):
    assembly = '''.text
movz x3, #0x160
movk x3, #0x0e08, lsl #16
movk x3, #2, lsl #32
ldr w4, [x3]
cbnz w4, failure
mov w5, #9
str w5, [x3]
ldr w4, [x3]
cmp w4, #0x99
b.ne failure
movz w5, #3
movk w5, #0x1000, lsl #16
str w5, [x3]
ldr w4, [x3]
movz w6, #0x33
movk w6, #0x1000, lsl #16
cmp w4, w6
b.ne failure
mov w5, #0xf0
str w5, [x3]
ldr w4, [x3]
cbnz w4, failure
mov w5, #15
str w5, [x3]
ldr w4, [x3]
cmp w4, #0xff
b.ne failure
// The third ps-regs field is not a validity mask.
sub x3, x3, #8
mov w5, #9
str w5, [x3]
ldr w4, [x3]
cmp w4, #0x99
b.ne failure
// Reproduce the actual XNU polling loop at bank 0x200 offset 0x30.
movz x3, #0x230
movk x3, #0x0e08, lsl #16
movk x3, #2, lsl #32
mov w5, #15
str w5, [x3]
ldr w4, [x3]
cmp w4, #0xff
b.ne failure
// The adjacent control word must remain an ordinary latch.
str w5, [x3, #4]
ldr w4, [x3, #4]
cmp w4, #15
b.ne failure
// Raw aperture latches must not shadow the specific power-state bank.
movz x3, #0x3c
movk x3, #0x0e04, lsl #16
movk x3, #2, lsl #32
ldr w4, [x3]
cbnz w4, failure
mov w5, #0x4567
str w5, [x3]
ldr w4, [x3]
cmp w4, w5
b.ne failure
movz x3, #0x160
movk x3, #0x0e08, lsl #16
movk x3, #2, lsl #32
ldr w4, [x3]
cmp w4, #0xff
b.ne failure
// AOP aperture must have independent storage.
movz x3, #0x3c
movk x3, #0x1024, lsl #16
movk x3, #2, lsl #32
ldr w4, [x3]
cbnz w4, failure
mov w5, #0x1234
str w5, [x3]
ldr w4, [x3]
cmp w4, w5
b.ne failure
// XNU performs 64-bit accesses in PMGR aperture 6.
movz x3, #0x40
movk x3, #0x02f8, lsl #16
movk x3, #2, lsl #32
ldr x4, [x3]
cbnz x4, failure
movz x5, #0xabcd
movk x5, #0x1234, lsl #16
movk x5, #0x5678, lsl #32
movk x5, #0x9876, lsl #48
str x5, [x3]
ldr x4, [x3]
cmp x4, x5
b.ne failure
ldr w4, [x3]
movz w6, #0xabcd
movk w6, #0x1234, lsl #16
cmp w4, w6
b.ne failure
ldr w4, [x3, #4]
movz w6, #0x5678
movk w6, #0x9876, lsl #16
cmp w4, w6
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
'''
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
            "model": "T8010 deterministic virtual power-state handshake",
            "checks": ["zero initialization", "desired 9 acknowledges actual 9",
                       "control bits survive", "actual field cannot be forged",
                       "power-off and power-on", "bank 0x200 offset 0x30 completes XNU state polling",
                       "adjacent control word remains a latch",
                       "raw aperture round-trip", "power-state overlay has priority",
                       "AP and AOP aperture storage are independent",
                       "64-bit aperture 6 round-trip and little-endian halves"],
            "returncode": result.returncode, "stdout": result.stdout,
            "stderr": result.stderr}, indent=2))
        if not passed:
            raise RuntimeError("PMGR power-state guest MMIO checks failed")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--qemu", required=True)
    parser.add_argument("--report", type=pathlib.Path,
                        default=pathlib.Path(".firmware/pmgr-power-checks.json"))
    arguments = parser.parse_args()
    check(arguments.qemu, arguments.report)
