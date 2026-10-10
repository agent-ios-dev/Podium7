"""Prepare missing install volumes only in an isolated 16-GiB fixture.

This is an unsealed diagnostic layout, not an authenticated Apple restore.
"""
import argparse
import json
import pathlib
import plistlib
import subprocess
import time
import struct

SYSTEM_UUID = 'C16ECAF9-9EC3-42EB-9553-B3DA1A53090F'


def command(args):
    return subprocess.check_output(args, stderr=subprocess.STDOUT, timeout=120)


def fixture_container(whole):
    listing = plistlib.loads(command(['diskutil', 'apfs', 'list', '-plist']))
    containers = [c for c in listing.get('Containers', []) if any(
        s.get('DeviceIdentifier', '').startswith(whole.removeprefix('/dev/') + 's')
        for s in c.get('PhysicalStores', []))]
    if len(containers) != 1:
        raise ValueError('isolated fixture container not uniquely identified')
    return containers[0]


def mount_volume(volume, path, *, readonly=False):
    path.mkdir(exist_ok=True)
    args = ['diskutil', 'mount'] + (['readOnly'] if readonly else [])
    command(args + ['-mountPoint', str(path), volume['DeviceIdentifier']])
    info = plistlib.loads(command(['diskutil', 'info', '-plist', str(path)]))
    if info.get('DeviceIdentifier') != volume['DeviceIdentifier'] or info.get('MountPoint') != str(path):
        raise ValueError('fixture mount does not identify selected image volume')
    return path


def prepare(image):
    image = pathlib.Path(image).resolve()
    root = pathlib.Path.cwd().resolve() / '.firmware'
    if image != root / 'system-disk' / 'storage-16g.raw':
        raise ValueError('only isolated downloaded system-disk fixture is permitted')
    if image.stat().st_size != 16 << 30:
        raise ValueError('fixture must be exactly 16 GiB')
    with image.open('rb') as stream:
        stream.seek(34 * 512)
        nx = stream.read(4096)
    if nx[32:36] != b'NXSB': raise ValueError('expected official APFS partition superblock')
    nx_diagnostic = {'max_file_systems': struct.unpack_from('<I', nx, 180)[0],
                     'flags': hex(struct.unpack_from('<Q', nx, 1264)[0]),
                     'block_count': struct.unpack_from('<Q', nx, 40)[0]}
    attached = plistlib.loads(command(['hdiutil', 'attach', '-readwrite', '-nomount',
        '-plist', '-imagekey', 'diskimage-class=CRawDiskImage', str(image)]))
    devices = [e['dev-entry'] for e in attached.get('system-entities', []) if e.get('dev-entry')]
    if not devices:
        raise ValueError('fixture attachment returned no device')
    whole = min(devices, key=len)
    try:
        container = None
        for attempt in range(10):
            try:
                container = fixture_container(whole)
                break
            except ValueError:
                if attempt == 9: raise
                time.sleep(1)
        systems = [v for v in container.get('Volumes', []) if v.get('Roles') == ['System']
                   and v.get('APFSVolumeUUID') == SYSTEM_UUID]
        if len(systems) != 1 or len(container['Volumes']) != 1:
            raise ValueError('expected unchanged official single System-volume fixture')
        system = systems[0]
        source = mount_volume(system, root / 'install-system', readonly=True)
        for relative in ('private/var', 'private/etc/fstab', 'usr/standalone/firmware'):
            if not (source/relative).resolve().is_relative_to(source):
                raise ValueError('source path escapes mounted guest: ' + relative)
        report = {'system_fstab': (source/'private/etc/fstab').read_text() if (source/'private/etc/fstab').is_file() else None,
                  'source_var_present': (source/'private/var').is_dir(),
                  'source_firmware_present': (source/'usr/standalone/firmware').is_dir()}
        report['container_before'] = container
        report['nx_superblock'] = nx_diagnostic
        print(json.dumps(report), flush=True)
        # A lone read-only mounted volume can keep its container read-only.
        # Detach that mount before asking APFS to allocate new volumes.
        command(['diskutil', 'unmount', system['DeviceIdentifier']])
        for role, name in [('B', 'Preboot'), ('D', 'Data')]:
            args = ['sudo', 'diskutil', 'apfs', 'addVolume', container['ContainerReference'], 'APFSX', name, '-role', role, '-nomount']
            if role == 'D': args += ['-groupWith', system['DeviceIdentifier']]
            try:
                command(args)
            except subprocess.CalledProcessError as error:
                if role == 'B':
                    error.preparation_context = report
                    raise
                report['data_creation_error'] = error.output.decode(errors='replace')
                observed = fixture_container(whole)
                if any(v.get('Roles') == ['Data'] for v in observed.get('Volumes', [])):
                    raise ValueError('Data allocation failed after a partial volume creation')
        updated = fixture_container(whole)
        mounted = {}
        for role, label in [('Data', 'data'), ('Preboot', 'preboot')]:
            volumes = [v for v in updated['Volumes'] if v.get('Roles') == [role]]
            if not volumes and role == 'Data': continue
            if len(volumes) != 1: raise ValueError('created role not uniquely present: ' + role)
            mounted[role] = mount_volume(volumes[0], root / ('install-' + label))
        source = mount_volume(system, root / 'install-system', readonly=True)
        # iOS mounts the Data volume at /private/var, unlike macOS.
        if report['source_var_present'] and 'Data' in mounted:
            command(['sudo', 'ditto', '--rsrc', '--extattr', str(source/'private/var'), str(mounted['Data'])])
        # Current synthetic handoff has no boot-manifest hash; original mount
        # selected this exact 48-byte zero namespace in run 38053476211.
        firmware = mounted['Preboot'] / ('0' * 96) / 'usr/standalone/firmware'
        command(['sudo', 'mkdir', '-p', str(firmware)])
        if report['source_firmware_present']:
            command(['sudo', 'ditto', '--rsrc', '--extattr', str(source/'usr/standalone/firmware'), str(firmware)])
        report.update(volumes=updated['Volumes'], synthetic_manifest_namespace=True,
                      data_volume_prepared='Data' in mounted, xart_volume_prepared=False,
                      authenticated_boot_confirmed=False, springboard_confirmed=False,
                      firmware_files=sum(1 for f in firmware.rglob('*') if f.is_file()))
        return report
    finally:
        command(['hdiutil', 'detach', whole])


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--disk', required=True)
    parser.add_argument('--output', type=pathlib.Path, required=True)
    args = parser.parse_args()
    try:
        report = prepare(args.disk)
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        report = {'preparation_error': str(error)}
        if isinstance(error, subprocess.CalledProcessError):
            report['command_output'] = error.output.decode(errors='replace')
            report['context'] = getattr(error, 'preparation_context', None)
    args.output.write_text(json.dumps(report, indent=2, default=str), encoding='utf-8')
    print(json.dumps(report, indent=2, default=str))
    if 'preparation_error' in report: raise SystemExit(1)
