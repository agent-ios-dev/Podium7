"""Bounded read-only launch configuration metadata; never export binaries."""
import argparse
import json
import pathlib
import plistlib
from prepare_install_layout import SYSTEM_UUID, command, fixture_container, mount_volume

FIELDS = ('Label', 'Program', 'ProgramArguments', 'UserName', 'GroupName',
          'Disabled', 'RunAtLoad', 'KeepAlive', 'LaunchEvents', 'MachServices',
          'LimitLoadToSessionType', 'ProcessType', 'EnableTransactions',
          'POSIXSpawnType', 'LaunchOnlyOnce', 'EnablePressuredExit',
          'WaitForDebugger', 'SessionCreate', 'LaunchConstraints',
          'ThrottleInterval', 'ExitTimeOut', 'IOKitMatching')
TARGETS = ('springboard', 'backboard', 'frontboard', 'runningboard',
           'keybag', 'usermanager', 'loginwindow', 'graphics', 'display', 'iomobile')


def bounded(value, depth=0):
    if depth > 8:
        raise ValueError('launch metadata nesting exceeds bound')
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str) and len(value) <= 4096:
        return value
    if isinstance(value, list) and len(value) <= 256:
        return [bounded(item, depth + 1) for item in value]
    if isinstance(value, dict) and len(value) <= 256:
        if not all(isinstance(key, str) and len(key) <= 256 for key in value):
            raise ValueError('invalid launch metadata key')
        return {key: bounded(item, depth + 1) for key, item in value.items()}
    raise ValueError('unsupported or oversized launch metadata')


def collect(source):
    source = pathlib.Path(source).resolve()
    files, count = [], 0
    for directory in ('System/Library/LaunchDaemons', 'System/Library/LaunchAgents'):
        folder = source / directory
        if not folder.resolve().is_relative_to(source):
            raise ValueError('launch directory escapes fixture')
        for candidate in sorted(folder.glob('*.plist')):
            count += 1
            if count > 3000:
                raise ValueError('launch file count exceeds bound')
            if not candidate.resolve().is_relative_to(source):
                raise ValueError('launch path escapes fixture')
            if candidate.stat().st_size > 4 << 20:
                raise ValueError('launch plist exceeds size bound')
            data = plistlib.loads(candidate.read_bytes())
            if not isinstance(data, dict):
                raise ValueError('launch plist is not a dictionary')
            identity = ' '.join(str(data.get(key, '')) for key in
                                ('Label', 'Program', 'ProgramArguments')) + ' ' + candidate.name
            if any(target in identity.lower() for target in TARGETS):
                files.append({'path': candidate.relative_to(source).as_posix(),
                              'configuration_keys': sorted(data),
                              'configuration': {key: bounded(data[key]) for key in FIELDS if key in data}})
    return {'read_only': True, 'binary_exported': False, 'plists_scanned': count, 'services': files}


def inspect(image):
    root = pathlib.Path.cwd().resolve() / '.firmware'
    image = pathlib.Path(image).resolve()
    if image != root / 'system-disk/storage-16g.raw' or image.stat().st_size != 16 << 30:
        raise ValueError('only isolated fixed 16-GiB downloaded fixture is permitted')
    attached = plistlib.loads(command(['hdiutil', 'attach', '-readonly', '-nomount', '-plist',
                                      '-imagekey', 'diskimage-class=CRawDiskImage', str(image)]))
    devices = [entry['dev-entry'] for entry in attached.get('system-entities', []) if entry.get('dev-entry')]
    if not devices:
        raise ValueError('fixture attachment returned no device')
    whole = min(devices, key=len)
    try:
        container = fixture_container(whole)
        volumes = container.get('Volumes', [])
        if len(volumes) != 1 or volumes[0].get('APFSVolumeUUID') != SYSTEM_UUID or volumes[0].get('Roles') != ['System']:
            raise ValueError('expected unchanged official single System-volume fixture')
        source = mount_volume(volumes[0], root / 'launch-system', readonly=True)
        return collect(source)
    finally:
        command(['hdiutil', 'detach', whole])


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--disk', required=True)
    parser.add_argument('--output', type=pathlib.Path, required=True)
    args = parser.parse_args()
    args.output.write_text(json.dumps(inspect(args.disk), indent=2), encoding='utf-8')
