"""Exercise original AOP counter, system controls and firmware SRAM with an ARM64 guest."""
import argparse
import json
import pathlib
import subprocess
import tempfile

from check_qemu_registers import text_section
from qemu_probe import elf_image


def check(executable, report):
    assembly = '''.text
movz x3, #0x408
movk x3, #0x1000, lsl #16
movk x3, #2, lsl #32
stable:
ldr w21, [x3, #4]
ldr w20, [x3]
ldr w22, [x3, #4]
cmp w21, w22
b.ne stable
mrs x22, cntvct_el0
mov x5, #48000
add x22, x22, x5
delay:
mrs x0, cntvct_el0
cmp x0, x22
b.lo delay
ldr w22, [x3]
cmp w22, w20
b.ls failure
str wzr, [x3]
ldr w4, [x3]
cmp w4, w22
b.lo failure
movz x3, #0x500
movk x3, #0x1000, lsl #16
movk x3, #2, lsl #32
ldr w4, [x3]
cbnz w4, failure
mov w5, #0x1234
str w5, [x3]
ldr w4, [x3]
cmp w4, w5
b.ne failure
str w5, [x3, #0xfc]
ldr w4, [x3, #0xfc]
cmp w4, w5
b.ne failure
movz x3, #0
movk x3, #0x10e0, lsl #16
movk x3, #2, lsl #32
ldr x4, [x3]
cbnz x4, failure
movz x5, #0x1234
movk x5, #0xabcd, lsl #48
str x5, [x3]
ldr x4, [x3]
cmp x4, x5
b.ne failure
mov x6, #0xfff8
movk x6, #9, lsl #16
ldr x4, [x3, x6]
cbnz x4, failure
str x5, [x3, x6]
ldr x4, [x3, x6]
cmp x4, x5
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
            "-cpu", "podium7-research,cntfrq=24000000", "-m", "128", "-display", "none", "-monitor", "none",
            "-serial", "none", "-semihosting-config", "enable=on,target=native", "-device",
            f"loader,file={image},cpu-num=0"], capture_output=True, text=True, timeout=10)
        passed = result.returncode == 0
        report.write_text(json.dumps({"passed": passed,
            "model": "AOP read-only 32768-Hz counter and separate system/SRAM apertures",
            "checks": ["original high/low/high reads; monotonic virtual time and ignored counter writes",
                       "system controls and wide SRAM access at both boundaries"],
            "returncode": result.returncode, "stdout": result.stdout,
            "stderr": result.stderr}, indent=2))
        if not passed:
            raise RuntimeError("T8010 AOP counter and aperture checks failed")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--qemu", required=True)
    parser.add_argument("--report", type=pathlib.Path,
                        default=pathlib.Path(".firmware/aop-checks.json"))
    arguments = parser.parse_args()
    check(arguments.qemu, arguments.report)
