import pathlib
import tempfile
import unittest
from unittest.mock import patch
import patch_qemu_embedding as embedding


class EmbeddingTests(unittest.TestCase):
    def testWrongRevisionRefusedBeforeMutation(self):
        with tempfile.TemporaryDirectory() as root:
            with patch.object(embedding.subprocess, 'check_output', return_value='wrong'):
                with self.assertRaisesRegex(ValueError, 'revision'):
                    embedding.patch(pathlib.Path(root))
            self.assertEqual(list(pathlib.Path(root).iterdir()), [])

    def testVerifiedMachineRequiredAndPatchIsSingleUse(self):
        with tempfile.TemporaryDirectory() as root:
            directory = pathlib.Path(root)
            (directory / 'hw/arm').mkdir(parents=True)
            (directory / 'target/arm').mkdir(parents=True)
            (directory / 'system').mkdir()
            cpu = directory / 'target/arm/cpu64.c'
            cpu.write_text('vanilla')
            (directory / 'meson.build').write_text(embedding.ANCHOR)
            with patch.object(embedding.subprocess, 'check_output', return_value=embedding.PIN):
                with self.assertRaisesRegex(ValueError, 'research machine'):
                    embedding.patch(directory)
                cpu.write_text('podium7-research')
                embedding.patch(directory)
                with self.assertRaisesRegex(ValueError, 'already applied'):
                    embedding.patch(directory)


if __name__ == '__main__':
    unittest.main()
