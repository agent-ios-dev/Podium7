import struct
import os
import subprocess
from types import SimpleNamespace
import pathlib
import plistlib
import tempfile
import unittest
from unittest.mock import patch
from prepare_install_layout import prepare, fixture_container, mount_volume


class InstallLayoutTests(unittest.TestCase):
    def test_outside_fixture_never_invokes_host_commands(self):
        with patch('prepare_install_layout.command') as command:
            with self.assertRaisesRegex(ValueError, 'isolated downloaded'):
                prepare('outside.raw')
            command.assert_not_called()

    def test_unrelated_host_container_cannot_be_selected(self):
        listing = {'Containers': [{'ContainerReference': 'disk1',
            'PhysicalStores': [{'DeviceIdentifier': 'disk0s2'}]}]}
        with patch('prepare_install_layout.command', return_value=plistlib.dumps(listing)):
            with self.assertRaisesRegex(ValueError, 'uniquely identified'):
                fixture_container('/dev/disk12')

    def test_wrong_mount_blocks_copying(self):
        with tempfile.TemporaryDirectory() as temporary:
            mount = pathlib.Path(temporary) / 'mount'
            info = plistlib.dumps({'DeviceIdentifier': 'disk0s1', 'MountPoint': str(mount)})
            with patch('prepare_install_layout.command', side_effect=[b'', info]) as command:
                with self.assertRaisesRegex(ValueError, 'selected image volume'):
                    mount_volume({'DeviceIdentifier': 'disk13s1'}, mount, readonly=True)
                self.assertEqual(command.call_args_list[0].args[0][:3], ['diskutil', 'mount', 'readOnly'])
                self.assertFalse(any(call.args[0][0] == 'sudo' for call in command.call_args_list))

    def test_readonly_source_unmounted_before_mutation_and_failure_detaches(self):
        previous = pathlib.Path.cwd()
        with tempfile.TemporaryDirectory() as temporary:
            os.chdir(temporary)
            try:
                root = pathlib.Path.cwd() / '.firmware'
                image = root / 'system-disk/storage-16g.raw'
                image.parent.mkdir(parents=True)
                raw = bytearray(34 * 512 + 4096);raw[34 * 512 + 32:34 * 512 + 36] = b'NXSB'
                struct.pack_into('<I', raw, 34 * 512 + 180, 1)
                image.write_bytes(raw)
                source = root / 'install-system'
                container = {'ContainerReference': 'disk13',
                    'PhysicalStores': [{'DeviceIdentifier': 'disk12s1'}],
                    'Volumes': [{'Roles': ['System'], 'DeviceIdentifier': 'disk13s1',
                                 'APFSVolumeUUID': 'C16ECAF9-9EC3-42EB-9553-B3DA1A53090F'}]}
                error = subprocess.CalledProcessError(1, ['sudo', 'diskutil'], output=b'rejected')
                responses = [plistlib.dumps({'system-entities': [{'dev-entry': '/dev/disk12'}]}),
                    plistlib.dumps({'Containers': [container]}), b'', plistlib.dumps({'Containers': [container]}), b'',
                    plistlib.dumps({'DeviceIdentifier': 'disk13s1', 'MountPoint': str(source)}),
                    b'', error, b'']
                original_stat = pathlib.Path.stat
                def stat(path, *args, **kwargs):
                    return SimpleNamespace(st_size=16 << 30) if path == image else original_stat(path, *args, **kwargs)
                with patch('prepare_install_layout.pathlib.Path.stat', stat), patch(
                        'prepare_install_layout.command', side_effect=responses) as command, patch(
                        'prepare_install_layout.expose_full_disk_capacity', return_value={}):
                    with self.assertRaises(subprocess.CalledProcessError): prepare(image)
                    calls = [c.args[0] for c in command.call_args_list]
                    self.assertEqual(calls[6], ['diskutil', 'unmount', 'disk13s1'])
                    self.assertEqual(calls[7][:5], ['sudo', 'diskutil', 'apfs', 'addVolume', 'disk13'])
                    self.assertEqual(calls[-1], ['hdiutil', 'detach', '/dev/disk12'])
            finally:
                os.chdir(previous)
