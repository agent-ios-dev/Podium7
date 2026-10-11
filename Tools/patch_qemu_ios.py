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
    # ARM64 macOS and ARM64 iOS share CPU/system labels but not executable ABI.
    # Force Meson to compile/link probes without trying to execute iOS binaries.
    replace_once(directory / 'configure',
                 '  echo "[properties]" >> $cross',
                 '  echo "[properties]" >> $cross\n  echo "needs_exe_wrapper = true" >> $cross')
    replace_once(directory / 'meson.build',
                 "  if host_os != 'darwin' and cc.links(ucontext_probe)",
                 "  if cc.get_define('PODIUM7_IOS') == '1' or (host_os != 'darwin' and cc.links(ucontext_probe))")
    replace_once(directory / 'meson.build',
                 "glib_pc = dependency('glib-2.0', version: glib_req_ver, required: true,",
                 "glib_pc = dependency('glib-2.0', static: true, version: glib_req_ver, required: true,")
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
    # TCI executes bytecode, not generated host machine code. Its code buffers
    # do not need the macOS-only MAP_JIT write/execute toggle. Never quietly
    # apply these no-ops to an eventual native iOS TCG build.
    replace_once(directory / 'include/qemu/osdep.h',
                 '#ifdef __APPLE__\nstatic inline void qemu_thread_jit_execute(void)',
                 '''#if defined(PODIUM7_IOS) && !defined(CONFIG_TCG_INTERPRETER)
#error Native QEMU TCG JIT on iOS has not been ported
#endif
#if defined(__APPLE__) && !defined(CONFIG_TCG_INTERPRETER)
static inline void qemu_thread_jit_execute(void)''')
    replace_once(directory / 'include/qemu/osdep.h',
                 '#if defined(PODIUM7_IOS) && !defined(CONFIG_TCG_INTERPRETER)',
                 '''#ifdef PODIUM7_IOS
/* SDK 18.5 exposes strchrnul, but our minimum iOS is 17. Use QEMU's
 * real portable implementation instead of calling a missing weak symbol. */
#undef HAVE_STRCHRNUL
#endif
#if defined(PODIUM7_IOS) && !defined(CONFIG_TCG_INTERPRETER)''')
    replace_once(directory / 'block/file-posix.c',
                 '#include <sys/ioctl.h>\n#if defined(HAVE_HOST_BLOCK_DEVICE)',
                 '#include <sys/ioctl.h>\n#include <sys/param.h>\n#include <sys/mount.h>\n#if defined(HAVE_HOST_BLOCK_DEVICE)')
    # Bytecode needs ordinary read/write pages. MAP_JIT is entitlement-gated
    # on iPhone even when no executable protection is requested.
    replace_once(directory / 'tcg/region.c',
                 '#ifdef CONFIG_DARWIN\n    /* Applicable to both iOS and macOS (Apple Silicon). */',
                 '#if defined(CONFIG_DARWIN) && !defined(CONFIG_TCG_INTERPRETER)\n    /* Native TCG only: TCI stores non-executable bytecode. */')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=pathlib.Path)
    patch(parser.parse_args().directory)
