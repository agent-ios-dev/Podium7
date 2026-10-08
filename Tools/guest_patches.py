"""Explicit, opt-in restore-userland experiment; not authenticated iOS boot.
Never modify firmware files. Guard a single in-memory kernel edit by the
complete original 19H422 kernel hash and exact IOSecureBSDRoot entry bytes.
"""
import hashlib

REFERENCE_SHA256 = "115489dd3e2adbe3e0d646413adb9397cfaf1c47f7b5d03620f78dd7d9371814"
SECURE_ROOT_ENTRY = 0xfffffff0077b9084
ENTRY_SIGNATURE = bytes.fromhex("f657bda9f44f01a9fd7b02a9fd830091f30300aac0c6ffd0")
RETURN = bytes.fromhex("c0035fd6")


def skip_restore_secure_root(kernel, segments):
    original_digest = hashlib.sha256(kernel).hexdigest()
    if original_digest != REFERENCE_SHA256:
        raise ValueError("restore root experiment requires the exact original 19H422 kernel")
    for segment in segments:
        base = int(segment["address"], 16)
        if base <= SECURE_ROOT_ENTRY and SECURE_ROOT_ENTRY + len(ENTRY_SIGNATURE) <= base + segment["file_size"]:
            offset = segment["offset"] + SECURE_ROOT_ENTRY - base
            if kernel[offset:offset + len(ENTRY_SIGNATURE)] != ENTRY_SIGNATURE:
                raise ValueError("IOSecureBSDRoot entry signature mismatch")
            changed = bytearray(kernel)
            changed[offset:offset+4] = RETURN
            changed = bytes(changed)
            return changed, {"name": "research restore SecureRootName gate skip",
                "virtual_address": hex(SECURE_ROOT_ENTRY), "file_offset": offset,
                "original_bytes": ENTRY_SIGNATURE[:4].hex(), "replacement_bytes": RETURN.hex(),
                "original_kernel_sha256": original_digest,
                "effective_kernel_sha256": hashlib.sha256(changed).hexdigest(),
                "authenticated_boot": False,
                "reason": "isolate userland startup from blocked virtual-platform root security callback"}
    raise ValueError("IOSecureBSDRoot entry is not file-backed")
