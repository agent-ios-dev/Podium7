"""Full-system userland gate; CI success must not mean only a timed probe.

SpringBoard/display boot remains a separate, unconfirmed milestone.
"""
import argparse
import json
import pathlib
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
            "springboard_confirmed": False, "booted_ios": False}


def verify(directory):
    directory = pathlib.Path(directory)
    result = evidence((directory/'qemu-serial.txt').read_text(errors='replace'),
                      (directory/'qemu-trace.txt').read_text(errors='replace'))
    (directory/'system-userland-checks.json').write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=2))
    if not result['system_userland_confirmed']:
        raise RuntimeError('Full-system userland not confirmed; inspect root/DMA/PMP evidence')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=pathlib.Path)
    verify(parser.parse_args().directory)
