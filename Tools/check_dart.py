"""Exercise original T8010 DART discovery/configuration windows with an ARM64 guest."""
import argparse
import json
import pathlib
import subprocess
import tempfile

from check_qemu_registers import text_section
from qemu_probe import elf_image


def check(executable, report):
    assembly = '''.text
adr x7, banks
mov x9, #12
next_bank:
ldp x3, x6, [x7], #16
ldr w4, [x3, #0x24]
cbnz w4, failure
mov w5, #0xfffc
movk w5, #0x20, lsl #16
str w5, [x3, #0x24]
ldr w4, [x3, #0x24]
cmp w4, w5
b.ne failure
mov w5, #0x80808080
str w5, [x3, #0xc]
ldr w4, [x3, #0xc]
cmp w4, w5
b.ne failure
mov w5, #0x1234
str w5, [x3, #0x30]
str w5, [x3, #0x20]
ldr w4, [x3, #0x20]
cmp w4, w5
b.ne failure
sub x6, x6, #4
ldr w4, [x3, x6]
cbnz w4, failure
str w5, [x3, x6]
ldr w4, [x3, x6]
cmp w4, w5
b.ne failure
subs x9, x9, #1
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
banks:
.quad 0x206304000, 0x4000, 0x206300000, 0x4000
.quad 0x207908000, 0x2000, 0x207904000, 0x4000
.quad 0x207b04000, 0x4000, 0x207b0c000, 0x4000
.quad 0x205b28000, 0x4000, 0x205b2c000, 0x4000
.quad 0x207c30000, 0x4000, 0x207c20000, 0x4000
.quad 0x601008000, 0x4000, 0x604008000, 0x4000
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
            "model": "original T8010 DART discovery apertures; DMA translation not implemented",
            "checks": ["original table-address and stream configuration writes",
                       "12 independent DART banks including PCIe and short scaler window"],
            "returncode": result.returncode, "stdout": result.stdout,
            "stderr": result.stderr}, indent=2))
        if not passed:
            raise RuntimeError("T8010 DART control MMIO checks failed")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--qemu", required=True)
    parser.add_argument("--report", type=pathlib.Path,
                        default=pathlib.Path(".firmware/dart-checks.json"))
    arguments = parser.parse_args()
    check(arguments.qemu, arguments.report)
