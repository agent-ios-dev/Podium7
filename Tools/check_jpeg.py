"""Exercise original T8010 JPEG reset/discovery windows with an ARM64 guest."""
import argparse
import json
import pathlib
import subprocess
import tempfile

from check_qemu_registers import text_section
from qemu_probe import elf_image


def check(executable, report):
    assembly = '''.text
movz x3, #0
movk x3, #0x7b0, lsl #16
movk x3, #2, lsl #32
mov x7, #2
next_bank:
mov w5, #0x100
str w5, [x3, #8]
mov w5, #0x13e
str w5, [x3, #8]
str wzr, [x3]
mov w5, #0x17f
str w5, [x3, #8]
ldr w6, [x3, #8]
cmp w6, w5
b.ne failure
ldr w6, [x3, #0x1004]
cbnz w6, failure
mov w5, #1
str w5, [x3, #0x1014]
ldr w6, [x3, #0x1014]
cmp w6, w5
b.ne failure
mov x4, #0x3ffc
ldr w6, [x3, x4]
cbnz w6, failure
mov w5, #0x1234
str w5, [x3, x4]
ldr w6, [x3, x4]
cmp w6, w5
b.ne failure
add x3, x3, #8, lsl #12
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
            "model": "original T8010 JPEG0/JPEG1 discovery/reset apertures",
            "checks": ["original AppleJPEGDriver reset writes and idle status",
                       "control readbacks, bank independence, and 16-KiB aperture boundaries"],
            "returncode": result.returncode, "stdout": result.stdout,
            "stderr": result.stderr}, indent=2))
        if not passed:
            raise RuntimeError("T8010 JPEG control MMIO checks failed")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--qemu", required=True)
    parser.add_argument("--report", type=pathlib.Path,
                        default=pathlib.Path(".firmware/jpeg-checks.json"))
    arguments = parser.parse_args()
    check(arguments.qemu, arguments.report)
