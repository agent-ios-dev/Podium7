"""Execute assembler-built APRR read/write checks under the real QEMU backend.

This validates only latches, NOT MMU permission enforcement. Semihosting is
used solely to return an exit code from this generated diagnostic program.
"""
import argparse
import json
import pathlib
import struct
import subprocess
import tempfile
from qemu_probe import elf_image


def text_section(data):
    count = struct.unpack_from("<I", data, 16)[0]
    cursor = 32
    for _ in range(count):
        command, size = struct.unpack_from("<II", data, cursor)
        if command == 0x19:
            sections = struct.unpack_from("<I", data, cursor + 64)[0]
            for index in range(sections):
                section = cursor + 72 + index * 80
                if data[section:section + 16].rstrip(b"\0") == b"__text":
                    length = struct.unpack_from("<Q", data, section + 40)[0]
                    offset = struct.unpack_from("<I", data, section + 48)[0]
                    return data[offset:offset + length]
        cursor += size
    raise ValueError("assembler object has no text section")


def diagnostic():
    lines = [".text", ".p2align 2", "start:"]
    for index, number in enumerate([0, 1, 6, 7]):
        register = f"S3_4_C15_C2_{number}"
        lines += [f"mrs x1, {register}", "cbnz x1, failure",
                  f"mov x0, #{0x1234 + index}", "movk x0, #0xabcd, lsl #48",
                  f"msr {register}, x0", f"mrs x1, {register}", "cmp x0, x1", "b.ne failure"]
    # Re-read each after the other controls changed to detect shared storage.
    for index, number in enumerate([0, 1, 6, 7]):
        lines += [f"mov x0, #{0x1234 + index}", "movk x0, #0xabcd, lsl #48",
                  f"mrs x1, S3_4_C15_C2_{number}", "cmp x0, x1", "b.ne failure"]
    for number in [5, 4, 0, 1]:
        lines += [f"mov x0, #{0x4321 + number}", f"msr S3_0_C15_C{number}_0, x0",
                  f"mrs x1, S3_0_C15_C{number}_0", "cmp x0, x1", "b.ne failure"]
    lines += ["mov x3, #0", "movk x3, #0x0a0c, lsl #16", "movk x3, #2, lsl #32"]
    lines += ["mov x0, #0x7654", "msr S3_3_C15_C1_0, x0", "mrs x1, S3_3_C15_C1_0", "cmp x0, x1", "b.ne failure"]
    lines += ["mov x0, #0x6543", "msr S3_2_C15_C0_0, x0", "mrs x1, S3_2_C15_C0_0", "cmp x0, x1", "b.ne failure"]
    lines += ["mov x0, #0x5432", "msr S3_2_C15_C1_0, x0", "mrs x1, S3_2_C15_C1_0", "cmp x0, x1", "b.ne failure",
              "mov x0, #0x4321", "msr S3_1_C15_C0_0, x0", "mrs x1, S3_1_C15_C0_0", "cmp x0, x1", "b.ne failure"]
    for number in range(1, 5):
        lines += [f"mov x0, #{0x3456 + number}", f"msr S3_1_C15_C{number}_0, x0",
                  f"mrs x1, S3_1_C15_C{number}_0", "cmp x0, x1", "b.ne failure"]
    for byte in b"Podium7 UART OK\n":
        lines += [f"mov w0, #{byte}", "strb w0, [x3, #0x20]"]
    lines += ["mov x0, #0x20", "adr x1, success_exit", "hlt #0xf000", "b .",
              "failure:", "mov x0, #0x20", "adr x1, failure_exit", "hlt #0xf000", "b .",
              ".p2align 3", "success_exit:", ".quad 0x20026, 0", "failure_exit:", ".quad 0x20026, 1"]
    return "\n".join(lines) + "\n"


def check(executable, destination):
    with tempfile.TemporaryDirectory() as temporary:
        root = pathlib.Path(temporary)
        (root / "test.s").write_text(diagnostic())
        subprocess.run(["xcrun", "clang", "-arch", "arm64", "-c", str(root / "test.s"), "-o", str(root / "test.o")], check=True)
        code = text_section((root / "test.o").read_bytes())
        image = root / "test.elf"
        image.write_bytes(elf_image(0x44000000, [(0x44000000, len(code), code)]))
        trace = destination.with_name("register-check-trace.txt")
        command = [executable, "-machine", "virt,secure=off,virtualization=off", "-cpu", "podium7-research",
                   "-accel", "tcg", "-m", "128", "-display", "none", "-monitor", "none", "-serial", "none",
                   "-semihosting-config", "enable=on,target=native", "-device", f"loader,file={image},cpu-num=0",
                   "-d", "in_asm,int,guest_errors,unimp", "-D", str(trace)]
        timed_out = False
        try:
            result = subprocess.run(command, capture_output=True, text=True, timeout=5)
        except subprocess.TimeoutExpired as error:
            timed_out = True
            result = subprocess.CompletedProcess(command, -1,
                (error.stdout or b"").decode(errors="replace"), (error.stderr or b"").decode(errors="replace"))
        passed = not timed_out and result.returncode == 0 and "Podium7 UART OK\n" in result.stdout
        report = {"passed": passed, "checks": "reset, register independence and read/write, APRR, HID0/1/4/5, LSU_ERR_CTL, PMC0/1 and PMCR0..4 latches, UART TX",
                  "aprr_permissions_enforced": False, "timed_out": timed_out,
                  "returncode": result.returncode, "stdout": result.stdout, "stderr": result.stderr}
        destination.write_text(json.dumps(report, indent=2))
        print(json.dumps(report, indent=2))
        if not passed:
            raise RuntimeError("guest APRR latch checks failed")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--qemu", required=True)
    parser.add_argument("--report", type=pathlib.Path, default=pathlib.Path(".firmware/qemu-register-checks.json"))
    arguments = parser.parse_args()
    check(arguments.qemu, arguments.report)
