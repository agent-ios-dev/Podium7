"""Exercise observed T8010 SEP mailbox accesses; no SEP firmware replies."""
import argparse
import json
import pathlib
import subprocess
import tempfile
from check_qemu_registers import text_section
from qemu_probe import elf_image


def check(executable, report):
    assembly = """.text
movz x3, #0
movk x3, #0xda0, lsl #16
movk x3, #2, lsl #32
mov w5, #0x1111
mov x4, #0x4000
str w5, [x3, x4]
ldr w6, [x3, x4]
cmp w5, w6
b.ne failure
str w5, [x3, #0xc00]
ldr w6, [x3, #0xc00]
cmp w5, w6
b.ne failure
mov x4, #0x4008
ldr w6, [x3, x4]
mov w5, #0x20000
cmp w5, w6
b.ne failure
mov x4, #0x4020
ldr w6, [x3, x4]
cmp w5, w6
b.ne failure
mov w6, #-1
str w6, [x3, x4]
ldr w6, [x3, x4]
mov w5, #1
movk w5, #2, lsl #16
cmp w5, w6
b.ne failure
movz x5, #0x1234
movk x5, #0xabcd, lsl #48
str x5, [x3, #0x4010]
ldr x6, [x3, #0x4010]
cmp x5, x6
b.ne failure
mov x4, #0x4008
ldr w6, [x3, x4]
mov w5, #0x10000
cmp w5, w6
b.ne failure
str wzr, [x3, x4]
ldr w6, [x3, x4]
cmp w5, w6
b.ne failure
str xzr, [x3, #0x4010]
ldr x6, [x3, #0x4010]
movz x5, #0x1234
movk x5, #0xabcd, lsl #48
cmp x5, x6
b.ne failure
str x5, [x3, #0x4038]
ldr x6, [x3, #0x4038]
cbnz x6, failure
mov x4, #0x4020
ldr w6, [x3, x4]
mov w5, #1
movk w5, #2, lsl #16
cmp w5, w6
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
"""
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
        report.write_text(json.dumps({"passed": passed, "sep_firmware_execution": False,
            "checks": ["observed IRQ-mask control writes", "empty receive queue",
                       "64-bit send occupies one slot without overwrite", "queue status cannot be forged"],
            "returncode": result.returncode, "stdout": result.stdout, "stderr": result.stderr}, indent=2))
        if not passed:
            raise RuntimeError("T8010 SEP mailbox MMIO checks failed")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--qemu", required=True)
    parser.add_argument("--report", type=pathlib.Path,
                        default=pathlib.Path(".firmware/sep-mailbox-checks.json"))
    arguments = parser.parse_args()
    check(arguments.qemu, arguments.report)
