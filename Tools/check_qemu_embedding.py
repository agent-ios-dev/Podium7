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
    # Embedded apps have no QEMU executable-relative ROM search directory.
    # Networking is not part of this prepared iPod profile.
    if '--version' not in arguments and '-nic' not in arguments:
        arguments = arguments + ['-nic', 'none']
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
    parser.add_argument('--arguments', type=pathlib.Path)
    parser.add_argument('host_arguments', nargs=argparse.REMAINDER)
    args = parser.parse_args()
    arguments = json.loads(args.arguments.read_text()) if args.arguments else args.host_arguments
    if arguments and arguments[0] == '--':
        arguments = arguments[1:]
    run(args.library, arguments)
