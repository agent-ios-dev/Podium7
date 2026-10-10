import hashlib
import unittest
from unittest.mock import patch
import guest_patches as gp


class GuestPatchTests(unittest.TestCase):
    def test_unsealed_diagnostic_is_exact_opt_in_and_never_reports_authenticated_root(self):
        original, segments = self.fixture()
        offset = len(original)
        original += gp.SYSTEM_ROOT_AUTH_SIGNATURE + b'TAIL'
        segments += [{'address': hex(gp.SYSTEM_ROOT_AUTH_BRANCH-8),
                      'file_size': 16, 'offset': offset}]
        with patch.object(gp, 'REFERENCE_SHA256', hashlib.sha256(original).hexdigest()):
            control, report = gp.skip_restore_secure_root(original, segments)
            changed, report = gp.skip_restore_secure_root(original, segments, unsealed_system_root=True)
        self.assertEqual(changed[:offset+8], control[:offset+8])
        self.assertEqual(changed[offset+8:offset+12], bytes.fromhex('1f2003d5'))
        self.assertEqual(changed[offset+12:], control[offset+12:])
        self.assertFalse(report['additional_edits'][0]['guest_root_authenticated'])
        with patch.object(gp, 'REFERENCE_SHA256', hashlib.sha256(original).hexdigest()):
            with self.assertRaisesRegex(ValueError, 'not file-backed'):
                gp.skip_restore_secure_root(original, segments[:1], unsealed_system_root=True)
        wrong = original[:offset+8] + bytes(4) + original[offset+12:]
        with patch.object(gp, 'REFERENCE_SHA256', hashlib.sha256(wrong).hexdigest()):
            with self.assertRaisesRegex(ValueError, 'signature mismatch'):
                gp.skip_restore_secure_root(wrong, segments, unsealed_system_root=True)

    def fixture(self):
        original = b"PREFIX!!" + gp.ENTRY_SIGNATURE + b"SUFFIX!!"
        segment = {"address": hex(gp.SECURE_ROOT_ENTRY), "file_size": len(gp.ENTRY_SIGNATURE), "offset": 8}
        return original, [segment]

    def test_edit_is_four_bytes_and_original_is_unchanged(self):
        original, segments = self.fixture()
        with patch.object(gp, "REFERENCE_SHA256", hashlib.sha256(original).hexdigest()):
            changed, report = gp.skip_restore_secure_root(original, segments)
        self.assertEqual(changed[:8], original[:8])
        self.assertEqual(changed[8:12], gp.RETURN)
        self.assertEqual(changed[12:], original[12:])
        self.assertEqual(original[8:32], gp.ENTRY_SIGNATURE)
        self.assertFalse(report["authenticated_boot"])
        self.assertNotEqual(report["original_kernel_sha256"], report["effective_kernel_sha256"])

    def test_other_kernel_and_wrong_entry_are_rejected(self):
        original, segments = self.fixture()
        with self.assertRaisesRegex(ValueError, "exact original"):
            gp.skip_restore_secure_root(original, segments)
        wrong = original[:8] + b"WRONG!!!" + original[16:]
        with patch.object(gp, "REFERENCE_SHA256", hashlib.sha256(wrong).hexdigest()):
            with self.assertRaisesRegex(ValueError, "signature mismatch"):
                gp.skip_restore_secure_root(wrong, segments)
        with patch.object(gp, "REFERENCE_SHA256", hashlib.sha256(original).hexdigest()):
            with self.assertRaisesRegex(ValueError, "not file-backed"):
                gp.skip_restore_secure_root(original, [])

    def test_aes_fallback_is_opt_in_exact_and_preserves_all_other_bytes(self):
        original, segments = self.fixture()
        offset = len(original)
        original += gp.AES_CALL_SIGNATURE + b"TAIL"
        segments += [{"address": hex(gp.AES_SECURE_ROOT_CALL), "file_size": len(gp.AES_CALL_SIGNATURE), "offset": offset}]
        with patch.object(gp, "REFERENCE_SHA256", hashlib.sha256(original).hexdigest()):
            control, report = gp.skip_restore_secure_root(original, segments)
            self.assertEqual(control[offset:], original[offset:])
            self.assertEqual(report["additional_edits"], [])
            changed, report = gp.skip_restore_secure_root(original, segments, aes_root_fallback=True)
        self.assertEqual(changed[:offset], control[:offset])
        self.assertEqual(changed[offset:offset+8], gp.AES_UNSUPPORTED)
        self.assertEqual(changed[offset+8:], original[offset+8:])
        self.assertEqual(len(report["additional_edits"]), 1)
        self.assertFalse(report["authenticated_boot"])
        with patch.object(gp, "REFERENCE_SHA256", hashlib.sha256(original).hexdigest()):
            with self.assertRaisesRegex(ValueError, "not file-backed"):
                gp.skip_restore_secure_root(original, segments[:1], aes_root_fallback=True)
        wrong = original[:offset] + b"WRONG!!!" + original[offset+8:]
        with patch.object(gp, "REFERENCE_SHA256", hashlib.sha256(wrong).hexdigest()):
            with self.assertRaisesRegex(ValueError, "signature mismatch"):
                gp.skip_restore_secure_root(wrong, segments, aes_root_fallback=True)
