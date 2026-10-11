import pathlib
import tempfile
import unittest
from unittest.mock import patch
from export_boot_bundle import export


class ExportTests(unittest.TestCase):
    def testExistingDestinationRefusedWithoutDiskMutation(self):
        with tempfile.TemporaryDirectory() as root:
            directory = pathlib.Path(root)
            disk = directory / 'disk.raw'
            disk.write_bytes(b'preserve')
            output = directory / 'existing'
            output.mkdir()
            with patch('export_boot_bundle.sys.platform', 'darwin'):
                with self.assertRaisesRegex(ValueError, 'destination exists'):
                    export(directory, disk, output)
            self.assertEqual(disk.read_bytes(), b'preserve')

    def testBlankOrWrongSizeDiskNeverExpandedOrReplaced(self):
        with tempfile.TemporaryDirectory() as root:
            directory = pathlib.Path(root)
            disk = directory / 'disk.raw'
            disk.write_bytes(b'not an installed APFS image')
            with patch('export_boot_bundle.sys.platform', 'darwin'):
                with self.assertRaisesRegex(ValueError, 'prepared regular'):
                    export(directory, disk, directory / 'new')
            self.assertEqual(disk.read_bytes(), b'not an installed APFS image')
            self.assertFalse((directory / 'new').exists())
