"""Full-system userland gate; CI success must not mean only a timed probe.

SpringBoard/display boot remains a separate, unconfirmed milestone.
"""
import argparse
import json
import pathlib
import re
from boot_milestones import inspect


def evidence(serial, trace):
    stages = inspect(serial, trace)
    return {"userland_execution_confirmed": stages['userland_execution_confirmed'],
            "restore_environment_seen": stages['restore_environment_seen'],
            "el0_return_count": stages['el0_return_count'],
            "waiting_for_root_seen": 'Still waiting for root device' in serial,
            "dma_rejection_seen": 'NVME-DART rejected' in trace,
            "kernel_panic_seen": 'panic(cpu ' in serial,
            "system_userland_confirmed": stages['userland_execution_confirmed'] and not stages['restore_environment_seen'] and 'panic(cpu ' not in serial,
            "filesystem_quickcheck_clean": "QUICKCHECK ONLY; FILESYSTEM CLEAN" in serial,
            "early_boot_complete_seen": stages['early_boot_complete_seen'],
            "keybag_diagnostic_skip_seen": 'DIAGNOSTICS MODE ENABLED, SKIP INIT' in serial,
            "debug_diagnostic_profile_seen": 'debug=0x14e' in serial,
            "launchd_boot_tasks_observed": re.findall(r'Doing boot task: ([^\r\n]+)', serial),
            "launchd_boot_failures": re.findall(r'Boot task failed: ([^\r\n]+)', serial),
            "fstab_missing_roles": [int(role) for role in re.findall(r'failed to get volume for role: (\d+)', serial)],
            "springboard_confirmed": False, "booted_ios": False}


def verify(directory):
    directory = pathlib.Path(directory)
    result = evidence((directory/'qemu-serial.txt').read_text(errors='replace'),
                      (directory/'qemu-trace.txt').read_text(errors='replace'))
    patches = json.loads((directory/'guest-patches.json').read_text()) if (directory/'guest-patches.json').exists() else []
    result['unsealed_root_diagnostic'] = any(edit.get('name') == 'research unsealed system root diagnostic'
        for patch in patches for edit in patch.get('additional_edits', []))
    probe = json.loads((directory/'qemu-probe.json').read_text()) if (directory/'qemu-probe.json').exists() else {}
    result['probe_stop_reason'] = probe.get('stop')
    result['probe_trace_budget_exhausted'] = 'trace limit reached' in (probe.get('stop') or '')
    tree_report = json.loads((directory/'device-tree-preparation.json').read_text()) if (directory/'device-tree-preparation.json').exists() else {}
    result['fastsim_diagnostic'] = any(change.get('value') == 'FastSim' for change in tree_report.get('device_tree_changes', []))
    result['no_sep_diagnostic'] = any(change.get('action') == 'omit' and change.get('path') == '/device-tree/arm-io/sep' for change in tree_report.get('device_tree_changes', []))
    result['keybag_diagnostic_handoff'] = any(change.get('property') == 'boot-ios-diagnostics' and change.get('value') == 1 for change in tree_report.get('device_tree_changes', []))
    result['sep_data_protection_confirmed'] = False
    result['authenticated_boot_confirmed'] = False
    (directory/'system-userland-checks.json').write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=2))
    if not result['system_userland_confirmed']:
        raise RuntimeError('Full-system userland not confirmed; inspect root/DMA/PMP evidence')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=pathlib.Path)
    verify(parser.parse_args().directory)
