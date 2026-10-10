"""Require actual firmware execution in the dual-core research experiment."""
import argparse
import json
import pathlib
import re


def evidence(trace, serial=""):
    def mmio(operation, offset, value=None):
        suffix = r"[0-9a-f]{8}" if value is None else value
        return bool(re.search(r"SEP-MAILBOX base=000000020e300000 " + operation +
                              " offset=" + offset + " value=" + suffix, trace))
    result = {
        "arm32_core_realized": "PMP integrated ARM32 core realized" in trace,
        "driver_released_firmware": "PMP firmware release result=0" in trace,
        "original_reset_body_executed": bool(re.search(r"0x41000068:", trace)),
        "original_boot_hello_written": mmio("write", "0bb0", "000c000c") and mmio("write", "0bb4", "00100000"),
        "ap_read_original_boot_hello": mmio("read", "4038", "000c000c") and mmio("read", "403c", "00100000"),
        "ap_sent_message": mmio("write", "4014"),
        "pmp_consumed_message": mmio("read", "0b9c"),
        "ios_boot_confirmed": False,
        "limitations": "generic ARMv7 research core and private low SRAM alias; exact PMP hardware and full iOS boot remain unconfirmed",
    }
    result["pmp_driver_started"] = bool(re.search(r"^ApplePMP: started$", serial, re.MULTILINE))
    result["original_firmware_started"] = bool(re.search(r"^\[PMP:main\.cpp:\d+\] PMP started$", serial, re.MULTILINE))
    result["pmp_boot_confirmed"] = all(result[key] for key in (
        "original_reset_body_executed", "ap_read_original_boot_hello",
        "ap_sent_message", "pmp_consumed_message", "pmp_driver_started", "original_firmware_started"))
    return result


def verify(directory):
    trace = (directory / "qemu-trace.txt").read_text(errors="replace")
    result = evidence(trace, (directory / "qemu-serial.txt").read_text(errors="replace"))
    (directory / "pmp-integration.json").write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=2))
    if not all(result[key] for key in ("arm32_core_realized", "driver_released_firmware", "original_reset_body_executed", "pmp_boot_confirmed")):
        raise RuntimeError("integrated PMP startup was not confirmed; inspect shared SRAM/core diagnostics")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("directory", type=pathlib.Path)
    verify(parser.parse_args().directory)
