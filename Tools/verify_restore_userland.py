"""Regression gate for actual restore userland, never a desktop-boot claim."""
import argparse
import json
from pathlib import Path
from boot_milestones import inspect


def verify(directory):
    directory = Path(directory)
    summary = json.loads((directory / "qemu-probe.json").read_text())
    evidence = inspect((directory / "qemu-serial.txt").read_text(errors="replace"),
                       (directory / "qemu-trace.txt").read_text(errors="replace"))
    if not all(evidence[key] for key in ("userland_execution_confirmed",
                                         "restore_environment_seen", "early_boot_complete_seen")):
        raise RuntimeError("Restore userland regression: actual launchd and EL0 execution not confirmed")
    if summary.get("booted_ios") is not False or summary.get("original_kernel_unpatched") is not False:
        raise RuntimeError("Restore experiment provenance must declare modified kernel and no desktop boot")
    return evidence


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    args = parser.parse_args()
    print(json.dumps(verify(args.directory), indent=2))
