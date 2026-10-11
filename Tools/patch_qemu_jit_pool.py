"""Supply QEMU native TCG with the host-owned executable code region."""
import argparse
import pathlib
import subprocess
from patch_qemu import PIN, replace_once


def patch(directory):
    if subprocess.check_output(['git', '-C', str(directory), 'rev-parse', 'HEAD'], text=True).strip() != PIN:
        raise ValueError('unverified QEMU source revision')
    if not (directory / 'system/podium7-embedding.c').exists():
        raise ValueError('embedded QEMU entry required')
    replace_once(directory / 'tcg/region.c',
                 'static int alloc_code_gen_buffer(size_t size, int splitwx, Error **errp)\n{\n    ERRP_GUARD();',
                 '''static int alloc_code_gen_buffer(size_t size, int splitwx, Error **errp)
{
#ifdef PODIUM7_IOS_JIT
    extern void *podium7_jit_rx, *podium7_jit_rw;
    extern size_t podium7_jit_size;
    if (!podium7_jit_rx || !podium7_jit_rw || size > podium7_jit_size) {
        error_setg(errp, "StikDebug executable buffer was not supplied");
        return -1;
    }
    region.start_aligned = podium7_jit_rw;
    region.total_size = size;
    tcg_splitwx_diff = (uintptr_t)podium7_jit_rx - (uintptr_t)podium7_jit_rw;
    return PROT_READ | PROT_WRITE | (tcg_splitwx_diff ? 0 : PROT_EXEC);
#endif
    ERRP_GUARD();''')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=pathlib.Path)
    patch(parser.parse_args().directory)
