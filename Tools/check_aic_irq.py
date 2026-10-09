"""Execute real AIC software and I2C level IRQs in an EL1 ARM64 guest."""
import argparse
import json
import pathlib
import subprocess
import tempfile
from check_qemu_registers import text_section
from qemu_probe import elf_image


def check(executable, report):
    assembly = """.text
msr daifset, #15
msr spsel, #1
movz x0, #0
movk x0, #0x4501, lsl #16
mov sp, x0
adr x0, vectors
msr vbar_el1, x0
isb
mov x20, #0
movz x3, #0
movk x3, #0xe10, lsl #16
movk x3, #2, lsl #32
mov w5, #1
str w5, [x3, #0x3000]
add x7, x3, #4, lsl #12
str w5, [x7, #0x180]
str w5, [x7]
msr daifclr, #2
first_wait:
cmp x20, #1
b.ne first_wait
msr daifset, #2
mov w5, #1
str w5, [x3, #0x33a0]
mov w5, #0x100
str w5, [x7, #0x19c]
movz x8, #0
movk x8, #0xa11, lsl #16
movk x8, #2, lsl #32
mov w5, #0x80000000
str w5, [x8, #0x10]
mov w5, #0x08200000
str w5, [x8, #0x18]
mov w5, #0x150
str w5, [x8]
mov w5, #0x255
str w5, [x8]
msr daifclr, #2
second_wait:
cmp x20, #2
b.ne second_wait
msr daifset, #2
ldr w4, [x3, #0x2004]
cbnz w4, failure
ldr w4, [x8, #0x14]
mov w5, #0x10000
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
irq_handler:
ldr w4, [x3, #0x2004]
cbnz x20, i2c_handler
mov w5, #0x10000
cmp w4, w5
b.ne failure
mov w5, #1
str w5, [x7, #0x80]
str w5, [x7, #0x180]
b completed
i2c_handler:
mov w5, #0xe8
movk w5, #1, lsl #16
cmp w4, w5
b.ne failure
mov w5, #0x08200000
str w5, [x8, #0x14]
mov w5, #0x100
str w5, [x7, #0x19c]
completed:
add x20, x20, #1
eret
.p2align 3
success_exit:
.quad 0x20026, 0
failure_exit:
.quad 0x20026, 1
.p2align 11
vectors:
"""
    for slot in range(16):
        assembly += ("b irq_handler" if slot in (1, 5, 9, 13) else "b failure") + "\n.space 124\n"
    with tempfile.TemporaryDirectory() as temporary:
        root = pathlib.Path(temporary)
        source = root / "timer.s"
        obj = root / "timer.o"
        source.write_text(assembly)
        subprocess.run(["xcrun", "clang", "-arch", "arm64", "-c", str(source), "-o", str(obj)], check=True)
        code = text_section(obj.read_bytes())
        image = root / "timer.elf"
        image.write_bytes(elf_image(0x45000000, [(0x45000000, len(code), code)]))
        result = subprocess.run([executable, "-machine", "virt,secure=off,virtualization=off",
            "-cpu", "podium7-research,cntfrq=24000000", "-m", "128", "-display", "none",
            "-monitor", "none", "-serial", "none", "-semihosting-config", "enable=on,target=native",
            "-device", f"loader,file={image},cpu-num=0"], capture_output=True, text=True, timeout=10)
        report.write_text(json.dumps({"passed": result.returncode == 0,
            "checks": ["software AIC event enters real EL1 IRQ vector",
                       "I2C NACK/STOP drives external AIC source 232",
                       "event auto-masks; W1C deasserts; ERET resumes without duplicate events"],
            "returncode": result.returncode, "stdout": result.stdout, "stderr": result.stderr}, indent=2))
        if result.returncode: raise RuntimeError("real AIC IRQ delivery failed")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--qemu", required=True)
    parser.add_argument("--report", type=pathlib.Path, default=pathlib.Path(".firmware/aic-irq-checks.json"))
    args = parser.parse_args()
    check(args.qemu, args.report)
