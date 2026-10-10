import pathlib
import plistlib
import tempfile
import unittest
from unittest.mock import patch
import inspect_launch_services as services


class LaunchInspectionTests(unittest.TestCase):
    def test_selected_metadata_only(self):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            folder = root / 'System/Library/LaunchDaemons'
            folder.mkdir(parents=True)
            (folder / 'com.apple.backboardd.plist').write_bytes(plistlib.dumps({
                'Label': 'com.apple.backboardd', 'Program': '/usr/libexec/backboardd',
                'KeepAlive': {'AfterInitialDemand': True},
                'LimitLoadFromHardware': {'machine': ['example']}, 'Secret': b'not exported'}))
            (folder / 'other.plist').write_bytes(plistlib.dumps({'Label': 'other'}))
            report = services.collect(root)
            self.assertEqual(report['plists_scanned'], 2)
            self.assertEqual(len(report['services']), 1)
            self.assertNotIn('Secret', report['services'][0]['configuration'])
            self.assertEqual(report['services'][0]['configuration']['KeepAlive'], {'AfterInitialDemand': True})
            self.assertEqual(report['services'][0]['configuration']['LimitLoadFromHardware'], {'machine': ['example']})

    def test_nested_or_binary_metadata_rejected(self):
        with self.assertRaises(ValueError):
            services.bounded(b'raw')
        data = 'end'
        for _ in range(10):
            data = [data]
        with self.assertRaises(ValueError):
            services.bounded(data)

    def test_wrong_disk_rejected_before_attachment(self):
        with patch.object(services, 'command') as command:
            with self.assertRaises(ValueError):
                services.inspect('unrelated.raw')
            command.assert_not_called()

    def test_detach_on_validation_failure(self):
        image = pathlib.Path.cwd().resolve() / '.firmware/system-disk/storage-16g.raw'
        attached = plistlib.dumps({'system-entities': [{'dev-entry': '/dev/disk99'}]})
        with patch.object(pathlib.Path, 'stat') as stat, patch.object(services, 'command', return_value=attached) as command, patch.object(services, 'fixture_container', return_value={'Volumes': []}):
            stat.return_value.st_size = 16 << 30
            with self.assertRaises(ValueError):
                services.inspect(image)
            self.assertEqual(command.call_args.args[0], ['hdiutil', 'detach', '/dev/disk99'])


if __name__ == '__main__':
    unittest.main()
