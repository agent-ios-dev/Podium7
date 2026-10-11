"""Prepare a PRIVATE app-importable fixture from the user's official firmware.

Run on macOS with a prepared APFS disk. No firmware is uploaded/published.
Existing VM/disk files are never overwritten; APFS clone preserves sparse space.
"""
import argparse
import json
import pathlib
import shutil
import subprocess
import sys
import tempfile
from qemu_probe import make_probe
from probe_pmp_core import extract

PROFILE = '19H422-disabled-aks-root-unsupported-v1'


def export(firmware, disk, output):
    if sys.platform != 'darwin':
        raise ValueError('macOS required for sparse APFS clone and prepared handoff')
    if output.exists():
        raise ValueError('destination exists; refusing to replace any VM')
    if disk.is_symlink() or not disk.is_file() or disk.stat().st_size != 16 << 30:
        raise ValueError('a prepared regular 16-GiB APFS system disk is required')
    required = ['KernelCache.macho', 'DeviceTree.bin', 'StaticTrustCache.im4p', 'SystemVolume.im4p']
    for name in required:
        source = firmware / name
        if source.is_symlink() or not source.is_file():
            raise ValueError(f'missing official firmware input: {name}')
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='p7-export-', dir=output.parent) as temporary:
        working = pathlib.Path(temporary)
        for name in required:
            shutil.copyfile(firmware / name, working / name)
        image, _, rorgn = make_probe(working,
            research_bridge_handoff=True, trust_cache=working / 'StaticTrustCache.im4p',
            system_volume=working / 'SystemVolume.im4p', research_system_root='disk0s1s1',
            research_cfi_nvram=True, research_aes_root_fallback=True,
            research_unsealed_root=True, research_fastsim=True, research_no_sep=True,
            research_keybag_diagnostics=True, research_sep_manager_probe=True,
            research_disabled_aks=True, research_platform_root_unsupported=True)
        prepared = working / 'bundle'
        prepared.mkdir()
        image.rename(prepared / 'boot.elf')
        (prepared / 'pmp.bin').write_bytes(extract((working / 'KernelCache.macho').read_bytes()))
        shutil.copyfile(working / 'nvram-flash.raw', prepared / 'nvram.raw')
        # -c requires clonefile: fail rather than unexpectedly filling 16 GiB.
        subprocess.run(['cp', '-c', str(disk.resolve()), str(prepared / 'disk.raw')], check=True)
        (prepared / 'boot.json').write_text(json.dumps({'schema': 1, 'profile': PROFILE,
            'diskBytes': 16 << 30, 'rorgn': list(rorgn)}, indent=2))
        prepared.rename(output)
    print(json.dumps({'private_bundle': str(output), 'disk_bytes': 16 << 30,
        'authenticated_boot_confirmed': False, 'sep_confirmed': False,
        'iphone_execution_confirmed': False}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--firmware', type=pathlib.Path, required=True)
    parser.add_argument('--disk', type=pathlib.Path, required=True)
    parser.add_argument('--output', type=pathlib.Path, required=True)
    args = parser.parse_args()
    export(args.firmware, args.disk, args.output)
