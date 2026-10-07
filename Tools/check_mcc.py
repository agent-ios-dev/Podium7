"""Exercise actual QEMU MMIO and RAM protection; no canned boot-success flag."""
import argparse
import json
import pathlib
import subprocess
import tempfile
from check_qemu_registers import text_section
from qemu_probe import elf_image


def check(executable, report):
    with tempfile.TemporaryDirectory() as temporary:
        root = pathlib.Path(temporary)
        assembly = '''.text
mov x3, #2
lsl x3, x3, #32
mov x4, #0x44000000
mov w5, #0xa5
strb w5, [x4]
mov w5, #0x1000
str w5, [x3, #0x7e4]
str w5, [x3, #0x7e8]
mov w5, #1
str w5, [x3, #0x7ec]
ldr w6, [x3, #0x7ec]
cmp w6, #1
b.ne failure
mov w5, #0x1001
str w5, [x3, #0x7e4]
ldr w6, [x3, #0x7e4]
cmp w6, #0x1000
b.ne failure
mov w5, #0x5a
strb w5, [x4]
ldrb w6, [x4]
cmp w6, #0xa5
b.ne failure
add x4, x4, #4, lsl #12
strb w5, [x4]
ldrb w6, [x4]
cmp w6, #0x5a
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
        (root / "test.s").write_text(assembly)
        subprocess.run(["xcrun", "clang", "-arch", "arm64", "-c", str(root / "test.s"), "-o", str(root / "test.o")], check=True)
        code = text_section((root / "test.o").read_bytes())
        image = root / "test.elf"
        image.write_bytes(elf_image(0x45000000, [(0x45000000, len(code), code)]))
        result = subprocess.run([executable, "-machine", "virt,secure=off,virtualization=off",
            "-cpu", "podium7-research", "-m", "128", "-display", "none", "-monitor", "none", "-serial", "none",
            "-semihosting-config", "enable=on,target=native", "-device", f"loader,file={image},cpu-num=0"],
            capture_output=True, text=True, timeout=10)
        report.write_text(json.dumps({"passed": result.returncode == 0, "model": "minimal one-plane MCC",
            "checks": ["range lock", "locked registers immutable", "guest STRB write rejected", "adjacent guest RAM writable"],
            "returncode": result.returncode, "stderr": result.stderr}, indent=2))
        if result.returncode != 0:
            raise RuntimeError("MCC guest memory-protection test failed")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--qemu", required=True)
    parser.add_argument("--report", type=pathlib.Path, default=pathlib.Path(".firmware/mcc-checks.json"))
    arguments = parser.parse_args()
    check(arguments.qemu, arguments.report)
