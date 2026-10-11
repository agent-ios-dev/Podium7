"""Build the app's private 16-GiB boot folder directly from official Apple IPSW.

No developer-provided image is an input. macOS is currently required for
the real hdiutil/APFS preparation; this is not an on-iPhone installer.
"""
import argparse
import pathlib
import shutil
import subprocess
import sys
import tempfile


def create(output):
    output = output.absolute()
    if output.exists() or output.is_symlink():
        raise FileExistsError('existing destination preserved; choose a new folder')
    if sys.platform != 'darwin':
        raise RuntimeError('macOS required: the APFS preparation has not yet been ported to iPhone')
    for executable in ('hdiutil', 'diskutil', 'xcrun'):
        if not shutil.which(executable):
            raise RuntimeError(f'missing macOS dependency: {executable}')
    output.parent.mkdir(parents=True, exist_ok=True)
    # Preserve failed inputs for diagnosis/resume; never erase a user VM.
    workspace = pathlib.Path(tempfile.mkdtemp(prefix='Podium7-preparation-', dir=output.parent))
    tools = pathlib.Path(__file__).resolve().parent
    firmware = workspace / '.firmware'
    steps = [
        ('Fetch official Apple firmware components', 'fetch_firmware.py',
         ['--output', str(firmware), '--system-trust-cache', '--system-volume']),
        ('Decode and check original kernel and device tree', 'analyze_firmware.py',
         ['--directory', str(firmware)]),
        ('Download official OS and create the fixed 16-GiB disk', 'prepare_os_disk.py',
         ['--output', str(firmware / 'system-disk')]),
        ('Prepare real APFS install volumes', 'prepare_install_layout.py',
         ['--disk', str(firmware / 'system-disk/storage-16g.raw'),
          '--output', str(firmware / 'install-layout.json')]),
        ('Export the app-importable boot folder', 'export_boot_bundle.py',
         ['--firmware', str(firmware), '--disk', str(firmware / 'system-disk/storage-16g.raw'),
          '--output', str(output)]),
    ]
    print(f'Private preparation workspace: {workspace}', flush=True)
    for description, script, arguments in steps:
        print(description, flush=True)
        subprocess.run([sys.executable, str(tools / script), *arguments], cwd=workspace, check=True)
    print(f'Prepared folder: {output}\nOriginal inputs retained in: {workspace}', flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=pathlib.Path, required=True)
    create(parser.parse_args().output)
