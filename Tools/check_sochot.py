"""Exercise the T8010 SoCHot/thermal sensor window with an ARM64 guest."""
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
movk x3, #0x02f3, lsl #16
movk x3, #2, lsl #32
ldr x4, [x3, #0x470]
cmp x4, #0
b.ne failure
movz x5, #0x5678
movk x5, #0x1234, lsl #16
str x5, [x3, #0x470]
ldr x4, [x3, #0x470]
cmp x4, x5
b.ne failure
mov w5, #0x7f
str w5, [x3, #0x7ffc]
ldr w4, [x3, #0x7ffc]
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
        result = subprocess.run([executable, "-machine", "virt,secure=off,virtualization=off",
            "-cpu", "podium7-research", "-m", "128", "-display", "none", "-monitor", "none",
            "-serial", "none", "-semihosting-config", "enable=on,target=native", "-device",
            f"loader,file={image},cpu-num=0"], capture_output=True, text=True, timeout=10)
        passed = result.returncode == 0
        report.write_text(json.dumps({"passed": passed,
            "model": "T8010 SoCHot/thermal register backing store",
            "checks": ["64-bit read/write at failing offset 0x470",
                       "32-bit read/write at end of 0x8000-byte window"],
            "returncode": result.returncode, "stdout": result.stdout,
            "stderr": result.stderr}, indent=2))
        if not passed:
            raise RuntimeError("T8010 thermal sensor guest MMIO checks failed")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--qemu", required=True)
    parser.add_argument("--report", type=pathlib.Path,
                        default=pathlib.Path(".firmware/sochot-checks.json"))
    arguments = parser.parse_args()
    check(arguments.qemu, arguments.report)
