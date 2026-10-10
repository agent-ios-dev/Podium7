"""Exercise original T8010 uart reset/discovery windows with an ARM64 guest."""
import argparse
import json
import pathlib
import subprocess
import tempfile

from check_qemu_registers import text_section
from qemu_probe import elf_image


def check(executable, report):
    assembly = '''.text
adr x10, banks
mov x7, #5
next_bank:
ldr x3, [x10], #8
ldr w6, [x3, #4]
cbnz w6, failure
mov w5, #0x1234
str w5, [x3, #4]
ldr w6, [x3, #4]
cmp w6, w5
b.ne failure
ldr w6, [x3, #0x10]
cmp w6, #6
b.ne failure
ldr w6, [x3, #0x18]
cbnz w6, failure
ldr w6, [x3, #0x14]
cbnz w6, failure
ldr w6, [x3, #0x24]
cbnz w6, failure
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
banks:
.quad 0x20a0c0000, 0x20a0c4000, 0x20a0d0000, 0x20a0d4000, 0x20a0d8000
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
            "model": "original T8010 uart0 five isolated polling UART control apertures",
            "checks": ["independent original UCON controls",
                       "TX empty flags, no RX/FIFO data or error status"],
            "returncode": result.returncode, "stdout": result.stdout,
            "stderr": result.stderr}, indent=2))
        if not passed:
            raise RuntimeError("T8010 uart control MMIO checks failed")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--qemu", required=True)
    parser.add_argument("--report", type=pathlib.Path,
                        default=pathlib.Path(".firmware/uart-checks.json"))
    arguments = parser.parse_args()
    check(arguments.qemu, arguments.report)
