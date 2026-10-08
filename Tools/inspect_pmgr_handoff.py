"""Audit PMGR bootloader handoff without inventing bridge register values.

The original 19H422 ApplePMGR checks bridge-settings-N unless its settings
version is 1. Missing non-optional entries cause initDriver line 1148 panic.
"""
import argparse
import json
import pathlib
from analyze_firmware import device_tree


def inspect_properties(properties):
    def integer(name, default=0):
        value = bytes.fromhex(properties[name]) if name in properties else None
        if value is None:
            return default
        if len(value) != 4:
            raise ValueError(f"PMGR {name} must be a 32-bit property")
        return int.from_bytes(value, "little")

    count = integer("#bridges")
    if count > 32:
        raise ValueError("PMGR bridge count exceeds the 32-bit optional mask")
    version = integer("bridge-settings-version")
    optional = integer("optional-bridge-mask")
    entries, missing, invalid = [], [], []
    for index in range(count):
        name = f"bridge-settings-{index}"
        value = bytes.fromhex(properties[name]) if name in properties else None
        required = version != 1 and not (optional & (1 << index))
        valid = value is None or len(value) % 8 == 0
        if required and value is None:
            missing.append(name)
        if not valid:
            invalid.append(name)
        entries.append({"index": index, "property": name, "required": required,
                        "present": value is not None, "bytes": None if value is None else len(value),
                        "pairs": None if value is None else len(value) // 8})
    return {"bridge_count": count, "bridge_settings_version": version,
            "version_property_present": "bridge-settings-version" in properties,
            "optional_bridge_mask": hex(optional), "entries": entries,
            "missing_required_properties": missing, "invalid_pair_lengths": invalid,
            "settings_complete": count > 0 and not missing and not invalid,
            "booted_ios": False,
            "scope": "PMGR metadata only; complete settings do not prove working hardware or iOS boot"}


def inspect_tree(data):
    nodes = device_tree(data)
    matches = [node for node in nodes if node["path"] == "/device-tree/arm-io/pmgr"]
    if len(matches) != 1:
        raise ValueError("expected one T8010 PMGR node")
    return inspect_properties(matches[0]["properties"])


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--directory", type=pathlib.Path, default=pathlib.Path(".firmware"))
    root = parser.parse_args().directory
    report = inspect_tree((root / "DeviceTree.bin").read_bytes())
    (root / "pmgr-handoff.json").write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))
