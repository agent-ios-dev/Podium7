"""Exercise original T8010 error-handler register windows with an ARM64 guest."""
import argparse
import json
import pathlib
import subprocess
import tempfile

from check_qemu_registers import text_section
from qemu_probe import elf_image


def check(executable, report):
    assembly = '''.text
movz x3, #8
movk x3, #208, lsl #16
movk x3, #2, lsl #32
ldr w4, [x3]
cbnz w4, failure
mov w5, #-1
str w5, [x3]
ldr w4, [x3]
cmp w4, w5
b.ne failure
movz x3, #12284
movk x3, #209, lsl #16
movk x3, #2, lsl #32
ldr w4, [x3]
cbnz w4, failure
mov w5, #-1
str w5, [x3]
ldr w4, [x3]
cmp w4, w5
b.ne failure
movz x3, #8
movk x3, #210, lsl #16
movk x3, #2, lsl #32
ldr w4, [x3]
cbnz w4, failure
mov w5, #-1
str w5, [x3]
ldr w4, [x3]
cmp w4, w5
b.ne failure
movz x3, #4092
movk x3, #210, lsl #16
movk x3, #2, lsl #32
ldr w4, [x3]
cbnz w4, failure
mov w5, #-1
str w5, [x3]
ldr w4, [x3]
cmp w4, w5
b.ne failure
movz x3, #8
movk x3, #217, lsl #16
movk x3, #2, lsl #32
ldr w4, [x3]
cbnz w4, failure
mov w5, #-1
str w5, [x3]
ldr w4, [x3]
cmp w4, w5
b.ne failure
movz x3, #4092
movk x3, #217, lsl #16
movk x3, #2, lsl #32
ldr w4, [x3]
cbnz w4, failure
mov w5, #-1
str w5, [x3]
ldr w4, [x3]
cmp w4, w5
b.ne failure
movz x3, #8
movk x3, #226, lsl #16
movk x3, #2, lsl #32
ldr w4, [x3]
cbnz w4, failure
mov w5, #-1
str w5, [x3]
ldr w4, [x3]
cmp w4, w5
b.ne failure
movz x3, #4092
movk x3, #226, lsl #16
movk x3, #2, lsl #32
ldr w4, [x3]
cbnz w4, failure
mov w5, #-1
str w5, [x3]
ldr w4, [x3]
cmp w4, w5
b.ne failure
movz x3, #8
movk x3, #233, lsl #16
movk x3, #2, lsl #32
ldr w4, [x3]
cbnz w4, failure
mov w5, #-1
str w5, [x3]
ldr w4, [x3]
cmp w4, w5
b.ne failure
movz x3, #4092
movk x3, #233, lsl #16
movk x3, #2, lsl #32
ldr w4, [x3]
cbnz w4, failure
mov w5, #-1
str w5, [x3]
ldr w4, [x3]
cmp w4, w5
b.ne failure
movz x3, #8
movk x3, #209, lsl #16
movk x3, #2, lsl #32
mov w5, #-1
str w5, [x3]
ldr w4, [x3]
cbnz w4, failure
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
            "model": "original T8010 error-handler register apertures",
            "checks": ["observed 0x200d10008 status acknowledgment remains clear",
                       "reset-empty status and writable controls in all five apertures"],
            "returncode": result.returncode, "stdout": result.stdout,
            "stderr": result.stderr}, indent=2))
        if not passed:
            raise RuntimeError("T8010 error-handler MMIO checks failed")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--qemu", required=True)
    parser.add_argument("--report", type=pathlib.Path,
                        default=pathlib.Path(".firmware/error-handler-checks.json"))
    arguments = parser.parse_args()
    check(arguments.qemu, arguments.report)
