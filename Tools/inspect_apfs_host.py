"""Inspect APFS volumes on macOS with an explicitly read-only, unmounted image."""
import argparse
import json
import pathlib
import plistlib
import subprocess
import sys


def inspect(image):
    if sys.platform != 'darwin':
        raise RuntimeError('host APFS inspection requires macOS')
    attached = plistlib.loads(subprocess.check_output([
        'hdiutil', 'attach', '-readonly', '-nomount', '-plist',
        '-imagekey', 'diskimage-class=CRawDiskImage', str(image)], timeout=60))
    devices = [e['dev-entry'] for e in attached.get('system-entities', []) if e.get('dev-entry')]
    if not devices:
        raise ValueError('read-only attachment returned no device')
    whole = min(devices, key=len)
    try:
        listing = plistlib.loads(subprocess.check_output(['diskutil', 'apfs', 'list', '-plist'], timeout=60))
        identifier = whole.removeprefix('/dev/')
        containers = [c for c in listing.get('Containers', []) if any(
            store.get('DeviceIdentifier', '').startswith(identifier + 's')
            for store in c.get('PhysicalStores', []))]
        if not containers:
            # Keep the actual attachment/listing: older iOS containers can be
            # attached without macOS synthesizing volumes automatically.
            return {'read_only_attachment': True, 'attachment': attached,
                    'apfs_listing': listing, 'containers': [], 'booted_ios': False,
                    'inspection_error': 'prepared image has no host-recognized APFS container'}
        snapshots = {}
        for container in containers:
            for volume in container.get('Volumes', []):
                device = volume.get('DeviceIdentifier')
                if not device:
                    continue
                try:
                    snapshots[device] = plistlib.loads(subprocess.check_output([
                        'diskutil', 'apfs', 'listSnapshots', device, '-plist'], timeout=60,
                        stderr=subprocess.STDOUT))
                except subprocess.CalledProcessError as error:
                    snapshots[device] = {'command_exit': error.returncode,
                                         'output': (error.output or b'').decode(errors='replace')}
        return {'read_only_attachment': True, 'containers': containers,
                'snapshots': snapshots, 'booted_ios': False}
    finally:
        subprocess.run(['hdiutil', 'detach', whole], check=True, timeout=60)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('image', type=pathlib.Path)
    parser.add_argument('--output', type=pathlib.Path, required=True)
    args = parser.parse_args()
    try:
        result = inspect(args.image)
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        result = {'inspection_error': str(error), 'booted_ios': False}
    args.output.write_text(json.dumps(result, indent=2, default=str), encoding='utf-8')
    print(json.dumps(result, indent=2, default=str))
