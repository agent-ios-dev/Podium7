import plistlib
import unittest
from unittest.mock import patch
from inspect_apfs_host import inspect


class HostAPFSTests(unittest.TestCase):
    def test_only_image_container_inspected_read_only_and_detached(self):
        attached = {'system-entities': [{'dev-entry': '/dev/disk12'}, {'dev-entry': '/dev/disk12s1'}]}
        volume = {'DeviceIdentifier': 'disk13s1', 'Name': 'SkyUpdate', 'Roles': ['System']}
        own = {'PhysicalStores': [{'DeviceIdentifier': 'disk12s1'}], 'Volumes': [volume]}
        unrelated = {'PhysicalStores': [{'DeviceIdentifier': 'disk1s2'}]}
        replies = [attached, {'Containers': [unrelated, own]}, {'Snapshots': []}]
        with patch('inspect_apfs_host.sys.platform', 'darwin'), patch(
                'inspect_apfs_host.subprocess.check_output', side_effect=[plistlib.dumps(x) for x in replies]) as read, patch(
                'inspect_apfs_host.subprocess.run') as detach:
            result = inspect('image.raw')
            self.assertEqual(result['containers'], [own])
            self.assertEqual(result['snapshots'], {'disk13s1': {'Snapshots': []}})
            self.assertIn('-readonly', read.call_args_list[0].args[0])
            self.assertIn('-nomount', read.call_args_list[0].args[0])
            detach.assert_called_once_with(['hdiutil', 'detach', '/dev/disk12'], check=True, timeout=60)

    def test_detach_even_when_container_listing_fails(self):
        attached = {'system-entities': [{'dev-entry': '/dev/disk12'}]}
        with patch('inspect_apfs_host.sys.platform', 'darwin'), patch(
                'inspect_apfs_host.subprocess.check_output', side_effect=[plistlib.dumps(attached), ValueError('bad listing')]), patch(
                'inspect_apfs_host.subprocess.run') as detach:
            with self.assertRaises(ValueError): inspect('image.raw')
            detach.assert_called_once()
