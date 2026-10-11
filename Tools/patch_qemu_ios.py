"""iPhone-only coroutine portability on the pinned embedded research backend.

Uses UTM's Darwin-compatible libucontext, without native iOS getcontext.
No CPU/device guest behavior is changed. GPL-2.0-or-later.
"""
import argparse
import pathlib
import subprocess
from patch_qemu import PIN, replace_once


def patch(directory):
    actual = subprocess.check_output(['git', '-C', str(directory), 'rev-parse', 'HEAD'], text=True).strip()
    if actual != PIN or not (directory / 'system/podium7-embedding.c').exists():
        raise ValueError('pinned embedded backend required')
    replace_once(directory / 'meson.build',
                 "  if host_os != 'darwin' and cc.links(ucontext_probe)",
                 "  if cc.get_define('PODIUM7_IOS') == '1' or (host_os != 'darwin' and cc.links(ucontext_probe))")
    replace_once(directory / 'util/coroutine-ucontext.c', '#include <ucontext.h>', '''#ifdef PODIUM7_IOS
#include <libucontext/libucontext.h>
#define ucontext_t libucontext_ucontext_t
#define getcontext libucontext_getcontext
#define makecontext libucontext_makecontext
#define swapcontext libucontext_swapcontext
#define setcontext libucontext_setcontext
#else
#include <ucontext.h>
#endif''')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=pathlib.Path)
    patch(parser.parse_args().directory)
