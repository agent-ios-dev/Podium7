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
