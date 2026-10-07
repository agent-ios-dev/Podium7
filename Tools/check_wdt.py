"""Exercise the Apple SoC watchdog MMIO register bank with an ARM64 guest."""
import argparse
import json
import pathlib
import subprocess
import tempfile

from check_qemu_registers import text_section
from qemu_probe import elf_image


def check(executable, report):
    assembly = '''.text
mov x3, #0x102b
lsl x3, x3, #16
movk x3, #2, lsl #32
ldr w4, [x3, #0x1c]
cmp w4, #0
b.ne failure
mov w5, #0x1234
str w5, [x3, #0x10]
ldr w4, [x3, #0x10]
cmp w4, w5
b.ne failure
mov w5, #0x5678
str w5, [x3, #0x14]
ldr w4, [x3, #0x14]
cmp w4, w5
b.ne failure
mov w5, #4
str w5, [x3, #0x1c]
ldr w4, [x3, #0x1c]
cmp w4, w5
b.ne failure
mov w5, #0xffffffff
str w5, [x3, #0x1c]
ldr w4, [x3, #0x1c]
mov w6, #5
cmp w4, w6
b.ne failure
ldr w4, [x3, #0x18]
cmp w4, #0
b.ne failure
ldr w4, [x3, #0x28]
cmp w4, #0
b.ne failure
mov w5, #4
str w5, [x3, #0x2c]
ldr w4, [x3, #0x2c]
cmp w4, w5
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
        checks = ["WD1_CTRL read at the panic address", "WD1 current and bite-time registers",
                  "WD1 control write/read and reserved-bit mask", "reserved WD1/WD2 offsets",
                  "WD2 control write/read"]
        passed = result.returncode == 0
        report.write_text(json.dumps({"passed": passed,
            "model": "Apple SoC watchdog minimal T8010 bootstrap register bank",
            "checks": checks, "returncode": result.returncode,
            "stdout": result.stdout, "stderr": result.stderr}, indent=2))
        if not passed:
            raise RuntimeError("Apple watchdog guest MMIO checks failed")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--qemu", required=True)
    parser.add_argument("--report", type=pathlib.Path,
                        default=pathlib.Path(".firmware/wdt-checks.json"))
    args = parser.parse_args()
    check(args.qemu, args.report)
