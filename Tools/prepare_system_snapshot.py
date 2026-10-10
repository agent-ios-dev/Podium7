"""Bounded host experiment on an isolated downloaded system-disk fixture.

The source GitHub artifact is preserved. No host/internal volume is selected.
Guest authentication and boot are still required after snapshot creation.
"""
import argparse
import json
import pathlib
import plistlib
import subprocess
import time
from analyze_firmware import payload


def prepare(image, auth, helper, mount, *, apple_systemsnapshot=False, apple_bless=False):
    image, helper, mount = (pathlib.Path(p).resolve() for p in (image, helper, mount))
    workspace = pathlib.Path.cwd().resolve()
    if not image.is_relative_to(workspace / '.firmware' / 'system-disk') or image.name != 'storage-16g.raw':
        raise ValueError('only isolated downloaded system-disk fixture is permitted')
    if image.stat().st_size != 16 * 1024**3 or not mount.is_relative_to(workspace / '.firmware'):
        raise ValueError('invalid fixture disk size or workspace mount')
    raw = payload(pathlib.Path(auth).read_bytes(), b'isys')
    if len(raw) != 208:
        raise ValueError('unsupported system auth payload')
    name = 'com.apple.os.update-' + raw[16:48].hex().upper()
    mount.mkdir(exist_ok=False)
    attached = plistlib.loads(subprocess.check_output([
        'hdiutil', 'attach', '-readwrite', '-nomount', '-plist',
        '-imagekey', 'diskimage-class=CRawDiskImage', str(image)], timeout=60))
    devices = [e['dev-entry'] for e in attached.get('system-entities', []) if e.get('dev-entry')]
    if not devices:
        raise ValueError('fixture attachment returned no device')
    whole = min(devices, key=len)
    try:
        containers = []
        for _ in range(10):
            listing = plistlib.loads(subprocess.check_output(['diskutil', 'apfs', 'list', '-plist'], timeout=60))
            containers = [c for c in listing.get('Containers', []) if any(
                s.get('DeviceIdentifier', '').startswith(whole.removeprefix('/dev/')+'s')
                for s in c.get('PhysicalStores', []))]
            if containers: break
            time.sleep(1)
        if len(containers) != 1:
            raise ValueError('isolated fixture container not uniquely identified')
        volumes = containers[0].get('Volumes', [])
        systems = [v for v in volumes if v.get('Roles') == ['System'] and v.get('APFSVolumeUUID') ==
                   'C16ECAF9-9EC3-42EB-9553-B3DA1A53090F']
        if len(systems) != 1:
            raise ValueError('official source System volume UUID/role mismatch')
        device = systems[0]['DeviceIdentifier']
        subprocess.run(['diskutil', 'mount', '-mountPoint', str(mount), device], check=True, timeout=60)
        mounted = plistlib.loads(subprocess.check_output(['diskutil', 'info', '-plist', str(mount)], timeout=60))
        if mounted.get('DeviceIdentifier') != device or mounted.get('MountPoint') != str(mount):
            raise ValueError('fixture mount does not identify the selected image volume')
        command = ['sudo', '/System/Library/Filesystems/apfs.fs/Contents/Resources/apfs_systemsnapshot',
                   '-s', name, '-v', str(mount)] if apple_systemsnapshot else ['sudo', str(helper), str(mount), name]
        if apple_bless:
            # No --setBoot: operate solely on the attached image's folder.
            command = ['sudo', 'bless', '--folder', str(mount), '--create-snapshot', '--verbose']
        created = subprocess.run(command, check=True, timeout=60,
                                 capture_output=True, text=True)
        print(created.stdout, end='')
        snapshots = plistlib.loads(subprocess.check_output([
            'diskutil', 'apfs', 'listSnapshots', device, '-plist'], timeout=60))
        subprocess.run(['diskutil', 'unmount', device], check=True, timeout=60)
        if name not in json.dumps(snapshots, default=str):
            raise ValueError('host snapshot tool returned success without expected name; listing: ' +
                             json.dumps(snapshots, default=str)[:16384])
        return {'snapshot_created_by_host_api': True, 'expected_name': name,
                'snapshot_listing': snapshots, 'authenticated_guest_root': False, 'booted_ios': False}
    finally:
        subprocess.run(['hdiutil', 'detach', whole], check=True, timeout=60)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--disk', required=True)
    parser.add_argument('--auth', required=True)
    parser.add_argument('--helper', required=True)
    parser.add_argument('--mount', required=True)
    parser.add_argument('--output', type=pathlib.Path, required=True)
    parser.add_argument('--apple-systemsnapshot', action='store_true', help='Use installed Apple-signed snapshot utility')
    parser.add_argument('--apple-bless', action='store_true', help='Use signed bless on image folder without changing host boot settings')
    args = parser.parse_args()
    try:
        report = prepare(args.disk, args.auth, args.helper, args.mount, apple_systemsnapshot=args.apple_systemsnapshot,
                         apple_bless=args.apple_bless)
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        report = {'preparation_error': str(error), 'booted_ios': False}
        if isinstance(error, subprocess.CalledProcessError):
            report.update(command_stdout=error.stdout, command_stderr=error.stderr,
                          command_exit=error.returncode)
    args.output.write_text(json.dumps(report, indent=2, default=str), encoding='utf-8')
    print(json.dumps(report, indent=2, default=str))
    if 'preparation_error' in report:
        raise SystemExit(1)
