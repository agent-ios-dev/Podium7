"""Require a real guest PMGR test to execute through the loadable library."""
import argparse
import ctypes
import json
import pathlib
import sys


def run(library, arguments):
    # Standalone test host. The iOS app uses the identical ABI on a worker thread.
    backend = ctypes.CDLL(str(pathlib.Path(library).resolve()))
    backend.p7_qemu_abi.restype = ctypes.c_int
    if backend.p7_qemu_abi() != 1:
        raise ValueError('unsupported embedding ABI')
    backend.p7_qemu_run.argtypes = [ctypes.c_int, ctypes.POINTER(ctypes.c_char_p)]
    backend.p7_qemu_run.restype = ctypes.c_int
    encoded = [b'Podium7QEMU'] + [item.encode() for item in arguments]
    argv = (ctypes.c_char_p * (len(encoded) + 1))(*encoded, None)
    result = backend.p7_qemu_run(len(encoded), argv)
    if result != 0:
        raise RuntimeError(f'embedded QEMU returned {result}')
    if backend.p7_qemu_run(len(encoded), argv) != -2:
        raise RuntimeError('unsafe second initialization accepted')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--library', required=True)
    parser.add_argument('--arguments', type=pathlib.Path, required=True)
    args = parser.parse_args()
    run(args.library, json.loads(args.arguments.read_text()))
