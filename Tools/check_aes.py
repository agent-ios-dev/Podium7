"""Exercise the T8010 AES register-window bootstrap model with an ARM64 guest."""
import argparse
import json
import pathlib
import subprocess
import tempfile

from check_qemu_registers import text_section
from qemu_probe import elf_image


def check(executable, report):
    assembly = '''.text
movz x3, #0x8000
movk x3, #0x0a10, lsl #16
movk x3, #2, lsl #32
ldr w4, [x3, #0xc]
and w4, w4, #0x180
cmp w4, #0x180
b.ne failure
mov w5, #1
str w5, [x3, #8]
mov w5, #-1
str w5, [x3, #0x18]
mov w5, #0x20
str w5, [x3, #0x1c]
movz w5, #4112, lsl #16
str w5, [x3, #0x200]
adr x10, key0
ldr w5, [x10, #0]
str w5, [x3, #0x200]
ldr w5, [x10, #4]
str w5, [x3, #0x200]
ldr w5, [x10, #8]
str w5, [x3, #0x200]
ldr w5, [x10, #12]
str w5, [x3, #0x200]
movz w5, #0x10
movk w5, #0x5000, lsl #16
str w5, [x3, #0x200]
str wzr, [x3, #0x200]
adr x10, source0
str w10, [x3, #0x200]
adr x11, output
str w11, [x3, #0x200]
movz w5, #1
movk w5, #0x8c00, lsl #16
str w5, [x3, #0x200]
ldr w4, [x3, #0x18]
cmp w4, #0x20
b.ne failure
ldp x4, x5, [x11]
adr x10, expected0
ldp x6, x7, [x10]
cmp x4, x6
b.ne failure
cmp x5, x7
b.ne failure
mov w5, #1
str w5, [x3, #8]
mov w5, #-1
str w5, [x3, #0x18]
mov w5, #0x20
str w5, [x3, #0x1c]
movz w5, #4113, lsl #16
str w5, [x3, #0x200]
adr x10, key1
ldr w5, [x10, #0]
str w5, [x3, #0x200]
ldr w5, [x10, #4]
str w5, [x3, #0x200]
ldr w5, [x10, #8]
str w5, [x3, #0x200]
ldr w5, [x10, #12]
str w5, [x3, #0x200]
movz w5, #0x2000, lsl #16
str w5, [x3, #0x200]
adr x10, iv1
ldr w5, [x10, #0]
str w5, [x3, #0x200]
ldr w5, [x10, #4]
str w5, [x3, #0x200]
ldr w5, [x10, #8]
str w5, [x3, #0x200]
ldr w5, [x10, #12]
str w5, [x3, #0x200]
movz w5, #0x10
movk w5, #0x5000, lsl #16
str w5, [x3, #0x200]
str wzr, [x3, #0x200]
adr x10, source1
str w10, [x3, #0x200]
adr x11, output
str w11, [x3, #0x200]
movz w5, #1
movk w5, #0x8c00, lsl #16
str w5, [x3, #0x200]
ldr w4, [x3, #0x18]
cmp w4, #0x20
b.ne failure
ldp x4, x5, [x11]
adr x10, expected1
ldp x6, x7, [x10]
cmp x4, x6
b.ne failure
cmp x5, x7
b.ne failure
mov w5, #1
str w5, [x3, #8]
mov w5, #-1
str w5, [x3, #0x18]
mov w5, #0x20
str w5, [x3, #0x1c]
movz w5, #4097, lsl #16
str w5, [x3, #0x200]
adr x10, key2
ldr w5, [x10, #0]
str w5, [x3, #0x200]
ldr w5, [x10, #4]
str w5, [x3, #0x200]
ldr w5, [x10, #8]
str w5, [x3, #0x200]
ldr w5, [x10, #12]
str w5, [x3, #0x200]
movz w5, #0x2000, lsl #16
str w5, [x3, #0x200]
adr x10, iv2
ldr w5, [x10, #0]
str w5, [x3, #0x200]
ldr w5, [x10, #4]
str w5, [x3, #0x200]
ldr w5, [x10, #8]
str w5, [x3, #0x200]
ldr w5, [x10, #12]
str w5, [x3, #0x200]
movz w5, #0x10
movk w5, #0x5000, lsl #16
str w5, [x3, #0x200]
str wzr, [x3, #0x200]
adr x10, source2
str w10, [x3, #0x200]
adr x11, output
str w11, [x3, #0x200]
movz w5, #1
movk w5, #0x8c00, lsl #16
str w5, [x3, #0x200]
ldr w4, [x3, #0x18]
cmp w4, #0x20
b.ne failure
ldp x4, x5, [x11]
adr x10, expected2
ldp x6, x7, [x10]
cmp x4, x6
b.ne failure
cmp x5, x7
b.ne failure
// Unsupported hardware key must produce an error and leave output intact.
mov w5, #1
str w5, [x3, #8]
mov w5, #-1
str w5, [x3, #0x18]
movz w5, #0x1100, lsl #16
str w5, [x3, #0x200]
ldr w4, [x3, #0x18]
cmp w4, #0x80
b.ne failure
movz w5, #0x10
movk w5, #0x5000, lsl #16
str w5, [x3, #0x200]
str wzr, [x3, #0x200]
adr x10, source0
str w10, [x3, #0x200]
adr x11, output
str w11, [x3, #0x200]
ldp x4, x5, [x11]
cmp x4, x6
b.ne failure
cmp x5, x7
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
output:
.space 16
key0:
.byte 0x00,0x01,0x02,0x03,0x04,0x05,0x06,0x07,0x08,0x09,0x0a,0x0b,0x0c,0x0d,0x0e,0x0f
source0:
.byte 0x00,0x11,0x22,0x33,0x44,0x55,0x66,0x77,0x88,0x99,0xaa,0xbb,0xcc,0xdd,0xee,0xff
expected0:
.byte 0x69,0xc4,0xe0,0xd8,0x6a,0x7b,0x04,0x30,0xd8,0xcd,0xb7,0x80,0x70,0xb4,0xc5,0x5a
key1:
.byte 0x2b,0x7e,0x15,0x16,0x28,0xae,0xd2,0xa6,0xab,0xf7,0x15,0x88,0x09,0xcf,0x4f,0x3c
source1:
.byte 0x6b,0xc1,0xbe,0xe2,0x2e,0x40,0x9f,0x96,0xe9,0x3d,0x7e,0x11,0x73,0x93,0x17,0x2a
expected1:
.byte 0x76,0x49,0xab,0xac,0x81,0x19,0xb2,0x46,0xce,0xe9,0x8e,0x9b,0x12,0xe9,0x19,0x7d
iv1:
.byte 0x00,0x01,0x02,0x03,0x04,0x05,0x06,0x07,0x08,0x09,0x0a,0x0b,0x0c,0x0d,0x0e,0x0f
key2:
.byte 0x2b,0x7e,0x15,0x16,0x28,0xae,0xd2,0xa6,0xab,0xf7,0x15,0x88,0x09,0xcf,0x4f,0x3c
source2:
.byte 0x76,0x49,0xab,0xac,0x81,0x19,0xb2,0x46,0xce,0xe9,0x8e,0x9b,0x12,0xe9,0x19,0x7d
expected2:
.byte 0x6b,0xc1,0xbe,0xe2,0x2e,0x40,0x9f,0x96,0xe9,0x3d,0x7e,0x11,0x73,0x93,0x17,0x2a
iv2:
.byte 0x00,0x01,0x02,0x03,0x04,0x05,0x06,0x07,0x08,0x09,0x0a,0x0b,0x0c,0x0d,0x0e,0x0f
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
            "model": "T8010 AES-v2 software-key ECB/CBC with physical RAM DMA",
            "checks": ["AES-128 ECB NIST encryption known answer",
                       "AES-128 CBC NIST encryption and decryption known answers",
                       "completion status and unsupported hardware key rejection without DMA writes"],
            "returncode": result.returncode, "stdout": result.stdout,
            "stderr": result.stderr}, indent=2))
        if not passed:
            raise RuntimeError("T8010 AES guest MMIO checks failed")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--qemu", required=True)
    parser.add_argument("--report", type=pathlib.Path,
                        default=pathlib.Path(".firmware/aes-checks.json"))
    arguments = parser.parse_args()
    check(arguments.qemu, arguments.report)
