"""Add an in-process library without changing the verified machine/CPU models.

Apply after patch_qemu.py to the same pinned QEMU. GPL-2.0-or-later.
This is deliberately one VM lifetime per app process: upstream QEMU globals
cannot safely be initialized a second time. Fatal QEMU errors still terminate
the process; validated host arguments are required.
"""
import argparse
import pathlib
import subprocess
from patch_qemu import PIN, replace_once

ENTRY = r'''
#include "qemu/osdep.h"
#include "qemu-main.h"
#include "qemu/main-loop.h"
#include "system/replay.h"
#include "system/system.h"
#include "system/runstate.h"

int (*qemu_main)(void);
static gint used;
static gint ready;
__attribute__((visibility("default")))
int p7_qemu_abi(void) { return 1; }
__attribute__((visibility("default")))
int p7_qemu_run(int argc, char **argv)
{
    if (argc < 2 || argc > 128 || !argv || argv[argc] != NULL) {
        return -1;
    }
    for (int i = 0; i < argc; i++) {
        if (!argv[i] || !argv[i][0]) { return -1; }
    }
    if (!g_atomic_int_compare_and_exchange(&used, 0, 1)) { return -2; }
    setenv("PODIUM7_RESEARCH_NVME_DART", "1", 1);
    setenv("PODIUM7_RESEARCH_NVME_MSI", "1", 1);
    setenv("PODIUM7_RESEARCH_DISK_READBACK", "1", 1);
    /* init returns holding the BQL/replay locks, as in system/main.c. */
    qemu_init(argc, argv);
    g_atomic_int_set(&ready, 1);
    int status = qemu_main_loop();
    g_atomic_int_set(&ready, 0);
    qemu_cleanup(status);
    bql_unlock();
    replay_mutex_unlock();
    return status; /* Never exit() merely because the guest stopped. */
}
__attribute__((visibility("default")))
int p7_qemu_stop(void)
{
    if (!g_atomic_int_get(&ready)) { return -1; }
    bql_lock();
    if (!g_atomic_int_get(&ready)) { bql_unlock(); return -1; }
    qemu_system_shutdown_request(SHUTDOWN_CAUSE_HOST_QMP_QUIT);
    bql_unlock();
    return 0;
}
'''

ANCHOR = "    if host_os == 'darwin'\n      icon = 'pc-bios/qemu.rsrc'"
LIBRARY = """    if target == 'aarch64-softmmu'
      embedding_link_args = link_args
      if host_os == 'darwin'
        embedding_link_args += ['-Wl,-exported_symbol,_p7_qemu_abi',
                                '-Wl,-exported_symbol,_p7_qemu_run',
                                '-Wl,-exported_symbol,_p7_qemu_stop']
      endif
      shared_library('Podium7QEMU', files('system/podium7-embedding.c'),
        c_args: c_args,
        dependencies: arch_deps + exe['dependencies'],
        objects: lib.extract_all_objects(recursive: true),
        link_depends: [block_syms, qemu_syms],
        link_args: embedding_link_args,
        install: false)
    endif

"""


def patch(directory):
    actual = subprocess.check_output(['git', '-C', str(directory), 'rev-parse', 'HEAD'], text=True).strip()
    if actual != PIN:
        raise ValueError('unverified QEMU source revision')
    if not (directory / 'hw/arm/podium7-pmgr.c').exists():
        # Verify the existing research CPU rather than quietly building vanilla QEMU.
        if 'podium7-research' not in (directory / 'target/arm/cpu64.c').read_text():
            raise ValueError('apply the verified research machine patch first')
    entry = directory / 'system/podium7-embedding.c'
    if entry.exists():
        raise ValueError('embedding patch already applied')
    replace_once(directory / 'meson.build', ANCHOR, LIBRARY + ANCHOR)
    entry.write_text(ENTRY)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=pathlib.Path)
    patch(parser.parse_args().directory)
