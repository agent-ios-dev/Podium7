"""Execute original-driver CFI query/program operations in a genuine ARM64 guest."""
import argparse
import json
import pathlib
import subprocess
import tempfile

from check_qemu_registers import text_section
from qemu_probe import elf_image
from cfi_nvram_handoff import flash_image


def check(executable, report):
    assembly = '''.text
movz x3, #0
movk x3, #0xf000, lsl #16
movk x3, #2, lsl #32
ldrb w4, [x3]
cmp w4, #0x70
b.ne failure
mov w5, #0x98
mov x6, #0x5555
strb w5, [x3, x6]
ldrb w4, [x3, #0x10]
cmp w4, #0x51
b.ne failure
ldrb w4, [x3, #0x11]
cmp w4, #0x52
b.ne failure
ldrb w4, [x3, #0x12]
cmp w4, #0x59
b.ne failure
mov w5, #0xf0
strb w5, [x3]
// Original Apple driver uses unlock/unlock/query, not direct query.
mov w5, #0xaa
strb w5, [x3, x6]
mov x7, #0x2aaa
mov w5, #0x55
strb w5, [x3, x7]
mov w5, #0x98
strb w5, [x3, x6]
ldrb w4, [x3, #0x10]
cmp w4, #0x51
b.ne failure
ldrb w4, [x3, #0x2d]
cmp w4, #3
b.ne failure
ldrb w4, [x3, #0x2f]
cmp w4, #0x20
b.ne failure
mov w5, #0xf0
strb w5, [x3]
// Darwin memcpy reads pairs of 64-bit words before lazy ROMD is restored.
ldp x9, x10, [x3]
and w4, w9, #0xff
cmp w4, #0x70
b.ne failure
mov w5, #0xaa
strb w5, [x3, x6]
mov x7, #0x2aaa
mov w5, #0x55
strb w5, [x3, x7]
mov w5, #0xa0
strb w5, [x3, x6]
mov x7, #0x7000
mov w5, #0x5a
strb w5, [x3, x7]
mov w5, #0xf0
strb w5, [x3]
ldrb w4, [x3, x7]
cmp w4, #0x5a
b.ne failure
// Erase the last sector, wait for completion, then program it again.
mov w5, #0xaa
strb w5, [x3, x6]
mov x7, #0x2aaa
mov w5, #0x55
strb w5, [x3, x7]
mov w5, #0x80
strb w5, [x3, x6]
mov w5, #0xaa
strb w5, [x3, x6]
mov w5, #0x55
strb w5, [x3, x7]
mov x7, #0x7000
mov w5, #0x30
strb w5, [x3, x7]
mov w8, #0x200000
poll_erase:
ldrb w4, [x3, x7]
cmp w4, #0xff
b.eq erased
subs w8, w8, #1
b.ne poll_erase
b failure
erased:
mov w5, #0xaa
strb w5, [x3, x6]
mov x7, #0x2aaa
mov w5, #0x55
strb w5, [x3, x7]
mov w5, #0xa0
strb w5, [x3, x6]
mov x7, #0x7000
mov w5, #0x5a
strb w5, [x3, x7]
ldrb w4, [x3, x7]
cmp w4, #0x5a
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
        flash = root / "nvram.raw"
        flash.write_bytes(flash_image())
        result = subprocess.run([executable, "-machine", "virt,secure=off,virtualization=off",
            "-cpu", "podium7-research", "-m", "128", "-display", "none", "-monitor", "none",
            "-serial", "none", "-semihosting-config", "enable=on,target=native", "-device",
            f"loader,file={image},cpu-num=0", "-drive",
            f"if=none,id=podium7-nvram,format=raw,file={flash}"], capture_output=True, text=True, timeout=10)
        passed = result.returncode == 0 and flash.read_bytes()[0x7000] == 0x5a
        report.write_text(json.dumps({"passed": passed,
            "model": "synthetic AMD CFI NOR for original CHRP NVRAM driver",
            "checks": ["CHRP bank backing bytes", "CFI QRY query at Apple unlock address 0x5555",
                       "Apple unlock/unlock/query yields correct erase geometry",
                       "64-bit pair read immediately after query reset",
                       "AMD sector erase and reprogram", "programmed byte persisted in backing file"],
            "returncode": result.returncode, "stdout": result.stdout,
            "stderr": result.stderr}, indent=2))
        if not passed:
            raise RuntimeError("CFI NVRAM guest checks failed")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--qemu", required=True)
    parser.add_argument("--report", type=pathlib.Path,
                        default=pathlib.Path(".firmware/cfi-nvram-checks.json"))
    arguments = parser.parse_args()
    check(arguments.qemu, arguments.report)
