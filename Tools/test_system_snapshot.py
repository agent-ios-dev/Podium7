import os
import pathlib
import plistlib
import struct
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from prepare_system_snapshot import prepare
from test_system_volume_handoff import container


class SnapshotPreparationTests(unittest.TestCase):
    def test_outside_fixture_path_rejected_before_any_host_command(self):
        with patch('prepare_system_snapshot.subprocess.check_output') as command:
            with self.assertRaisesRegex(ValueError, 'isolated downloaded'):
                prepare('outside.raw', 'not-read', 'not-run', '.firmware/mount')
            command.assert_not_called()

    def test_wrong_mounted_device_blocks_snapshot_and_always_detaches(self):
        previous = pathlib.Path.cwd()
        with tempfile.TemporaryDirectory() as temporary:
            os.chdir(temporary)
            try:
                image = pathlib.Path('.firmware/system-disk/storage-16g.raw')
                image.parent.mkdir(parents=True); image.write_bytes(b'fixture')
                auth = pathlib.Path('.firmware/isys.im4p')
                auth.write_bytes(container(struct.pack('<4I', 2, 0, 1, 32)+bytes(192)))
                listing = {'Containers': [{'PhysicalStores': [{'DeviceIdentifier': 'disk12s1'}],
                    'Volumes': [{'Roles': ['System'], 'DeviceIdentifier': 'disk13s1',
                    'APFSVolumeUUID': 'C16ECAF9-9EC3-42EB-9553-B3DA1A53090F'}]}]}
                responses = [{'system-entities': [{'dev-entry': '/dev/disk12'}]}, listing,
                             {'DeviceIdentifier': 'disk0s1', 'MountPoint': str(pathlib.Path('.firmware/mount').resolve())}]
                with patch('prepare_system_snapshot.pathlib.Path.stat', return_value=SimpleNamespace(st_size=16*1024**3)), patch(
                        'prepare_system_snapshot.subprocess.check_output', side_effect=[plistlib.dumps(r) for r in responses]), patch(
                        'prepare_system_snapshot.subprocess.run') as command:
                    with self.assertRaisesRegex(ValueError, 'mount does not identify'):
                        prepare(image, auth, '.firmware/helper', '.firmware/mount')
                    self.assertFalse(any(c.args[0][0] == 'sudo' for c in command.call_args_list))
                    self.assertEqual(command.call_args_list[-1].args[0], ['hdiutil', 'detach', '/dev/disk12'])
            finally:
                os.chdir(previous)
