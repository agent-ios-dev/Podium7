"""Explicit, opt-in restore-userland experiment; not authenticated iOS boot.
Never modify firmware files. Guard a single in-memory kernel edit by the
complete original 19H422 kernel hash and exact IOSecureBSDRoot entry bytes.
"""
import hashlib

REFERENCE_SHA256 = "115489dd3e2adbe3e0d646413adb9397cfaf1c47f7b5d03620f78dd7d9371814"
SECURE_ROOT_ENTRY = 0xfffffff0077b9084
ENTRY_SIGNATURE = bytes.fromhex("f657bda9f44f01a9fd7b02a9fd830091f30300aac0c6ffd0")
RETURN = bytes.fromhex("c0035fd6")


AES_SECURE_ROOT_CALL = 0xfffffff005b6d664
AES_CALL_SIGNATURE = bytes.fromhex("060080d200013fd6")
AES_UNSUPPORTED = bytes.fromhex("e05880520000bc72")


def skip_restore_secure_root(kernel, segments, *, aes_root_fallback=False):
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
            additional_edits = []
            if aes_root_fallback:
                aes_segment = next((s for s in segments if int(s["address"], 16) <= AES_SECURE_ROOT_CALL and
                    AES_SECURE_ROOT_CALL + len(AES_CALL_SIGNATURE) <= int(s["address"], 16) + s["file_size"]), None)
                if aes_segment is None:
                    raise ValueError("AES SecureRoot call is not file-backed")
                aes_offset = aes_segment["offset"] + AES_SECURE_ROOT_CALL - int(aes_segment["address"], 16)
                if kernel[aes_offset:aes_offset + len(AES_CALL_SIGNATURE)] != AES_CALL_SIGNATURE:
                    raise ValueError("AES SecureRoot call signature mismatch")
                changed[aes_offset:aes_offset + len(AES_CALL_SIGNATURE)] = AES_UNSUPPORTED
                additional_edits.append({"name": "research AES SecureRoot unsupported fallback",
                    "virtual_address": hex(AES_SECURE_ROOT_CALL), "file_offset": aes_offset,
                    "original_bytes": AES_CALL_SIGNATURE.hex(), "replacement_bytes": AES_UNSUPPORTED.hex(),
                    "reason": "isolate missing SecureRoot callback after the explicit restore root gate skip; no AES operations bypassed"})
            changed = bytes(changed)
            return changed, {"name": "research restore SecureRootName gate skip",
                "virtual_address": hex(SECURE_ROOT_ENTRY), "file_offset": offset,
                "original_bytes": ENTRY_SIGNATURE[:4].hex(), "replacement_bytes": RETURN.hex(),
                "original_kernel_sha256": original_digest,
                "effective_kernel_sha256": hashlib.sha256(changed).hexdigest(),
                "authenticated_boot": False,
                "additional_edits": additional_edits,
                "reason": "isolate userland startup from blocked virtual-platform root security callback"}
    raise ValueError("IOSecureBSDRoot entry is not file-backed")
