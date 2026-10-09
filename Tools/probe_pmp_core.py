"""Bounded ARMv7 execution of actual embedded PMP firmware, not a PMP board."""
import argparse
import hashlib
import json
import pathlib
import re
import subprocess
import time
import tempfile
from qmp_diagnostics import capture as capture_cpu
from analyze_firmware import macho

KERNEL_SHA256 = "115489dd3e2adbe3e0d646413adb9397cfaf1c47f7b5d03620f78dd7d9371814"
FIRMWARE_SHA256 = "5672a1724a8238d29c45a6740c9c4d68acc895e1d3461acb3e0c12147b949bfd"
FIRMWARE_ADDRESS = 0xfffffff007b01000
FIRMWARE_BYTES = 0x1e1a0  # Observed original RTBuddy copy length, run 37973299612.


def extract(kernel):
    if hashlib.sha256(kernel).hexdigest() != KERNEL_SHA256:
        raise ValueError("PMP extraction requires the audited original 19H422 kernel")
    segment = next((s for s in macho(kernel)["segments"] if
                    int(s["address"], 16) <= FIRMWARE_ADDRESS and
                    FIRMWARE_ADDRESS + FIRMWARE_BYTES <= int(s["address"], 16) + s["file_size"]), None)
    if segment is None:
        raise ValueError("PMP firmware span is not wholly file-backed")
    offset = segment["offset"] + FIRMWARE_ADDRESS - int(segment["address"], 16)
    firmware = kernel[offset:offset + FIRMWARE_BYTES]
    if hashlib.sha256(firmware).hexdigest() != FIRMWARE_SHA256:
        raise ValueError("embedded PMP firmware hash changed")
    return firmware


def probe(executable, directory, output):
    output.mkdir(parents=True, exist_ok=True)
    firmware = extract((directory / "KernelCache.macho").read_bytes())
    blob = output / "PMPFirmware.bin"
    blob.write_bytes(firmware)
    trace = output / "qemu-trace.txt"
    socket_root = tempfile.TemporaryDirectory(prefix="pmp-qmp-")
    qmp = pathlib.Path(socket_root.name) / "qmp.sock"
    command = [executable, "-machine", "virt,secure=off,virtualization=off,gic-version=2",
        "-cpu", "cortex-a7,cntfrq=24000000", "-m", "128", "-display", "none", "-monitor", "none",
        "-serial", "none", "-no-reboot", "-d", "in_asm,exec,int,guest_errors",
        "-D", str(trace), "-qmp", f"unix:{qmp},server=on,wait=off",
        "-drive", f"if=none,id=podium7-pmp-core,format=raw,read-only=on,file={blob}", "-device",
        f"loader,file={blob},addr=0x41000000,cpu-num=0,force-raw=on"]
    process = subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
    deadline = time.monotonic() + 3
    limit_hit = False
    while process.poll() is None and time.monotonic() < deadline:
        if trace.exists() and trace.stat().st_size > 16 * 1024 * 1024:
            limit_hit = True
            break
        time.sleep(0.05)
    snapshot = {}
    if process.poll() is None:
        try:
            faults = []
            if trace.exists():
                faults = [int(address, 16) for address in re.findall(
                    r"DFAR\s+(0x[0-9a-fA-F]{8})\b", trace.read_text(errors="replace"))]
            addresses_to_translate = tuple(dict.fromkeys([0xc0500040, 0xc0500008] + faults[-8:]))
            snapshot = capture_cpu(qmp, addresses_to_translate, ((0x010144b0, 44),))
        except (OSError, ValueError) as error:
            snapshot = {"error": str(error)}
        process.terminate()
    try:
        _, stderr = process.communicate(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        _, stderr = process.communicate()
    socket_root.cleanup()
    (output / "cpu-snapshot.json").write_text(json.dumps(snapshot, indent=2))
    text = trace.read_text(errors="replace") if trace.exists() else ""
    blocks = re.findall(r"Trace.*?\[[^/]*/([0-9a-fA-F]+)/", text)
    addresses = sorted({int(pc, 16) for pc in blocks})
    reset_executed = 0x41000068 in addresses
    # Guarded firmware bytes: THUMB DSB/WFI/BX LR at offset 0x7712.
    wait_code = firmware[0x7712:0x771a] == bytes.fromhex("bff34f8f30bf7047")
    stopped_pc = re.search(r"R15=([0-9a-fA-F]{8})", snapshot.get("registers", ""))
    scheduler_wait = wait_code and stopped_pc is not None and int(stopped_pc.group(1), 16) in (0x01007716, 0x01007718)
    data_fault = "DFAR" in text
    report = {"firmware_sha256": FIRMWARE_SHA256, "firmware_bytes": len(firmware),
        "cpu_model": "generic Cortex-A7 ARMv7-A research baseline",
        "synthetic_load_address": "0x41000000",
        "cpu_snapshot": snapshot,
        "exact_pmp_cpu_model": False, "firmware_reset_body_executed": reset_executed,
        "pmp_boot_confirmed": False, "ios_boot_confirmed": False,
        "firmware_scheduler_wfi_observed": scheduler_wait,
        "firmware_data_abort_seen": data_fault,
        "pmp_hardware_or_mailbox_peer_implemented": False,
        "mapped_discovery_apertures": ["0x20e300000/0x20000", "0x20e400000/0x10000"],
        "distinct_executed_blocks": len(addresses),
        "first_executed_pcs": [hex(pc) for pc in addresses[:32]],
        "last_executed_pcs": [hex(int(pc, 16)) for pc in blocks[-16:]],
        "fault_evidence": re.findall(r".*(?:DFSR|DFAR|IFSR|IFAR).*", text)[-12:],
        "trace_limit_hit": limit_hit, "returncode": process.returncode, "stderr": stderr,
        "limitations": "synthetic virt RAM map; passive PMP discovery controls only; no mailbox peer or ARM32/ARM64 integration"}
    (output / "qemu-probe.json").write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))
    if not reset_executed:
        raise RuntimeError("real embedded PMP reset execution was not observed; inspect backend report")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--qemu", required=True)
    parser.add_argument("--directory", type=pathlib.Path, default=pathlib.Path(".firmware"))
    parser.add_argument("--output", type=pathlib.Path, default=pathlib.Path(".firmware/pmp-core-experiment"))
    args = parser.parse_args()
    probe(args.qemu, args.directory, args.output)
