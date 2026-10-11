"""Run real PMGR guest instructions in-process, then stop and reject re-init."""
import argparse
import ctypes
import json
import pathlib
import subprocess
import threading
import time
from check_qemu_registers import text_section
from qemu_probe import elf_image


def check(library, output):
    output.mkdir(parents=True, exist_ok=True)
    source = output / 'guest.s'
    source.write_text('''.text
movz x3, #0x160
movk x3, #0x0e08, lsl #16
movk x3, #2, lsl #32
mov w4, #9
str w4, [x3]
ldr w5, [x3]
cmp w5, #0x99
b.ne failed
movz x6, #0
movk x6, #0x0900, lsl #16
adr x7, message
loop:
ldrb w8, [x7], #1
cbz w8, done
str w8, [x6]
b loop
done:
wfi
b done
failed:
wfi
b failed
message:
.asciz "P7-LIB-PASS\\n"
''')
    obj = output / 'guest.o'
    subprocess.run(['xcrun', 'clang', '-arch', 'arm64', '-c', str(source), '-o', str(obj)], check=True)
    code = text_section(obj.read_bytes())
    image = output / 'guest.elf'
    image.write_bytes(elf_image(0x45000000, [(0x45000000, len(code), code)]))
    serial = output / 'serial.txt'
    backend = ctypes.CDLL(str(library.resolve()))
    backend.p7_qemu_abi.restype = ctypes.c_int
    assert backend.p7_qemu_abi() == 1
    backend.p7_qemu_run.argtypes = [ctypes.c_int, ctypes.POINTER(ctypes.c_char_p)]
    backend.p7_qemu_run.restype = ctypes.c_int
    backend.p7_qemu_stop.restype = ctypes.c_int
    assert backend.p7_qemu_stop() == -1
    args = ['Podium7QEMU', '-machine', 'virt,secure=off,virtualization=off',
            '-cpu', 'podium7-research', '-m', '128', '-display', 'none',
            '-monitor', 'none', '-nic', 'none', '-serial', f'file:{serial}',
            '-device', f'loader,file={image},cpu-num=0']
    encoded = [a.encode() for a in args]
    argv = (ctypes.c_char_p * (len(encoded) + 1))(*encoded, None)
    result = []
    worker = threading.Thread(target=lambda: result.append(backend.p7_qemu_run(len(encoded), argv)), daemon=True)
    worker.start()
    deadline = time.monotonic() + 15
    passed = False
    while time.monotonic() < deadline and worker.is_alive():
        if serial.exists() and b'P7-LIB-PASS\n' in serial.read_bytes():
            passed = True
            break
        time.sleep(.1)
    stop = backend.p7_qemu_stop()
    worker.join(timeout=10)
    if worker.is_alive() or not passed or result != [0] or stop != 0:
        raise RuntimeError(f'in-process guest/lifecycle failed: guest={passed}, return={result}, stop={stop}')
    second = backend.p7_qemu_run(len(encoded), argv)
    assert second == -2
    assert backend.p7_qemu_stop() == -1
    (output / 'embedding.json').write_text(json.dumps({'embedded_guest_pmgr_passed': passed,
        'returned_to_host': True, 'second_init_rejected': True,
        'ios_device_execution_confirmed': False, 'visible_springboard_confirmed': False}, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--library', type=pathlib.Path, required=True)
    parser.add_argument('--output', type=pathlib.Path, required=True)
    args = parser.parse_args()
    check(args.library, args.output)
