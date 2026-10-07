"""Exercise the T8010 GPIO/pinctrl MMIO model with an ARM64 guest."""
import argparse
import json
import pathlib
import subprocess
import tempfile

from check_qemu_registers import text_section
from qemu_probe import elf_image


def check(executable, report):
    assembly = '''.text
mov x3, #0xf10
lsl x3, x3, #16
movk x3, #2, lsl #32
ldr w4, [x3]
cmp w4, #0
b.ne failure
mov w5, #0x1234
str w5, [x3]
ldr w4, [x3]
cmp w4, w5
b.ne failure
mov w5, #0x4321
str w5, [x3, #0x33c]
ldr w4, [x3, #0x33c]
cmp w4, w5
b.ne failure
ldr w4, [x3, #0x340]
cmp w4, #0
b.ne failure
mov w5, #0x7f
str w5, [x3, #0x340]
ldr w4, [x3, #0x340]
cmp w4, #0
b.ne failure
mov w5, #0xffffffff
str w5, [x3, #0x800]
ldr w4, [x3, #0x800]
cmp w4, #0
b.ne failure
str w5, [x3, #0x980]
ldr w4, [x3, #0x980]
cmp w4, #0
b.ne failure
str w5, [x3, #0x820]
ldr w4, [x3, #0x820]
cmp w4, #0
b.ne failure
mov x3, #0x100f
lsl x3, x3, #16
movk x3, #2, lsl #32
ldr w4, [x3]
cmp w4, #0
b.ne failure
mov w5, #0x42
str w5, [x3, #0xa4]
ldr w4, [x3, #0xa4]
cmp w4, w5
b.ne failure
ldr w4, [x3, #0xa8]
cmp w4, #0
b.ne failure
str w5, [x3, #0xa8]
ldr w4, [x3, #0xa8]
cmp w4, #0
b.ne failure
mov w5, #0xffffffff
str w5, [x3, #0x800]
ldr w4, [x3, #0x800]
cmp w4, #0
b.ne failure
str w5, [x3, #0x984]
ldr w4, [x3, #0x984]
cmp w4, #0
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
        command = [executable, "-machine", "virt,secure=off,virtualization=off",
                   "-cpu", "podium7-research", "-m", "128", "-display", "none",
                   "-monitor", "none", "-serial", "none", "-semihosting-config",
                   "enable=on,target=native", "-device", f"loader,file={image},cpu-num=0"]
        result = subprocess.run(command, capture_output=True, text=True, timeout=10)
        checks = ["main GPIO first/last pins and 208-pin boundary",
                  "AOP GPIO first/last pins and 42-pin boundary",
                  "GPIO interrupt status write-one-to-clear for groups 0 and 6",
                  "AOP GPIO interrupt status groups and reserved pin boundary",
                  "reserved interrupt register gap"]
        passed = result.returncode == 0
        report.write_text(json.dumps({"passed": passed,
            "model": "T8010 GPIO/pinctrl minimal bootstrap register bank",
            "checks": checks, "returncode": result.returncode,
            "stdout": result.stdout, "stderr": result.stderr}, indent=2))
        if not passed:
            raise RuntimeError("T8010 GPIO guest MMIO checks failed")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--qemu", required=True)
    parser.add_argument("--report", type=pathlib.Path,
                        default=pathlib.Path(".firmware/gpio-checks.json"))
    args = parser.parse_args()
    check(args.qemu, args.report)
