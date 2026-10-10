"""Exercise original T8010 display reset/discovery windows with an ARM64 guest."""
import argparse
import json
import pathlib
import subprocess
import tempfile

from check_qemu_registers import text_section
from qemu_probe import elf_image


def check(executable, report):
    assembly = '''.text
adr x10, banks
mov x7, #9
next_bank:
ldp x3, x4, [x10], #16
str wzr, [x3]
mov w5, #1
str w5, [x3]
str wzr, [x3]
ldr w6, [x3]
cbnz w6, failure
ldr w6, [x3, #4]
orr w6, w6, #0x1000
str w6, [x3, #4]
ldr w5, [x3, #4]
cmp w5, w6
b.ne failure
sub x4, x4, #4
ldr w6, [x3, x4]
cbnz w6, failure
mov w5, #0x1234
str w5, [x3, x4]
ldr w6, [x3, x4]
cmp w6, w5
b.ne failure
movz x5, #0x5678
movk x5, #0xabcd, lsl #48
str x5, [x3, #8]
ldr x6, [x3, #8]
cmp x6, x5
b.ne failure
subs x7, x7, #1
b.ne next_bank
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
.quad 0x206200000, 0x9000, 0x20620c000, 0x4000, 0x206400000, 0x4000, 0x206440000, 0x4000, 0x206480000, 0x8000, 0x2064c0000, 0x8000, 0x206500000, 0x4000, 0x206540000, 0x4000, 0x2067c0000, 0x4000
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
            "model": "original T8010 display0 primary/secondary discovery/reset apertures",
            "checks": ["original display reset writes and zero initial controls",
                       "word/doubleword controls, bank independence and exact aperture boundaries"],
            "returncode": result.returncode, "stdout": result.stdout,
            "stderr": result.stderr}, indent=2))
        if not passed:
            raise RuntimeError("T8010 display control MMIO checks failed")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--qemu", required=True)
    parser.add_argument("--report", type=pathlib.Path,
                        default=pathlib.Path(".firmware/display-checks.json"))
    arguments = parser.parse_args()
    check(arguments.qemu, arguments.report)
