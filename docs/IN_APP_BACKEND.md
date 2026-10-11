# In-app backend integration

The real SpringBoard/backboardd processes in run 38092985645 executed in a
desktop QEMU executable. They do **not** establish an iPhone app boot.

Full-system run 38130597536 (49a00c4) subsequently verified the original guest
through the shared-library host: 104 real process identities, SpringBoard PID 158,
backboardd PID 61 (both UID 501), and 539006 EL0 returns during the 300-second
execution budget. See `evidence/embedded-processes-38130597536.json`. This confirms
the embedded engine reaches real iOS processes on macOS; it still does not
confirm execution on an iPhone or display scanout.

Run 38130230235 (bf4336b) passed the actual in-process PMGR guest test and native
run/stop/reinitialization guards on macOS. The ordinary iPhone app build also
passed on bf4336b. Cross-compilation of the QEMU framework and execution on an
iPhone are separate checks; neither is implied by this macOS result.

Run 38132738456 (07f8c22) subsequently passed the iPhone cross-build, framework
platform/export gates, and unsigned IPA packaging. The IPA contains a 32,994,928
byte iPhoneOS QEMU binary; its ZIP integrity was checked after downloading.
This is a compilation/package result, not a physical-iPhone boot result. The
follow-up 613c532 removes MAP_JIT from the TCI bytecode allocation as well as
the already excluded executable protection/write-protection toggle.

The app now has a prepared-fixture folder importer, host-controlled boot arguments,
an in-process framework loader, worker-thread execution, serial log display/export
and a native QEMU shutdown request. Only one QEMU lifetime is permitted per app
process; restart the app after stopping. This is emulator shutdown/flush, not a
guest-initiated orderly iOS shutdown. Existing imported disks are retained.

`Tools/patch_qemu_embedding.py` adds a loadable library alongside the existing
executable on the same pinned QEMU sources; existing CPU/device semantics remain
unchanged. It exposes ABI version, run and stop. The library must return to its
host after shutdown and refuse a second initialization. Fatal upstream QEMU
initialization errors can still terminate the app, so import/preflight errors must
be caught before entry.

`embedded-ios.yml` first executes actual guest ARM64 PMGR MMIO instructions through
the dylib, observes guest UART output, requests shutdown, verifies clean return,
then tests rejection of reinitialization. Only after that does it cross-compile
GLib/libffi/libucontext and QEMU for iPhoneOS, embed the framework and package an
unsigned research IPA. iOS platform metadata and exported ABI are required.
The ordinary app-build workflow does not package a missing library as functional
iOS emulation; its UI explicitly identifies that state.

The app packages TCI and a separate native TCG framework. Without StikDebug it
selects TCI; with a successfully prepared NativeJIT pool it supplies 64 MiB of
executable memory to native TCG. The first MiB stays reserved for diagnostics.
QEMU uses the pool's RX/RW mappings, including distinct aliases on TXM, and the
app retains the pool for the entire VM lifetime. A failing handoff prevents boot.
CI gates packaging on real guest execution through TCI and the native borrowed
pool. Physical StikDebug/TXM execution, measured speedup, memory budget and
graphics/input remain unverified. No display imitation is added:
the prepared machine currently has `-display none`, since guest scanout is not yet
implemented. An embedded IPA is not proof of visible SpringBoard.

## Installing the app

Use the `Podium7-embedded-research-unsigned.ipa` artifact from `embedded-ios.yml`,
not the ordinary laboratory app artifact. Minimum host version is iOS 17.
Sign the app and both embedded QEMU frameworks with your installation
tool before installing. TCI does not require StikDebug; native TCG requires a
successfully prepared executable pool. Import the prepared
folder below, then start the machine. The screen currently shows status and
serial logs rather than a rendered guest display. Stop requests QEMU shutdown;
close and reopen the app before starting another machine session.

## Preparing the private boot fixture

No developer-only image is required. On macOS, the full preparation from Apple's
official IPSW can be invoked with one command (Python 3 and the project's
capstone dependency are required):

```
python3 -m pip install capstone==5.0.9
python3 Tools/create_boot_bundle.py --output ~/Podium7Boot
```

This downloads the original firmware, decodes the boot components, converts the
official OS DMG, prepares real install volumes and exports the fixed 16-GiB
folder. It refuses existing destinations and keeps its private intermediate
workspace. The app directly downloads the official IPSW and converts its stored
OS DMG using Apple's Compression/LZFSE API. The verified DMG contains 5002 LZFSE
blocks, 299 raw blocks and 3 skipped/zero regions; raw blocks are streamed in
bounded chunks. It creates a new sparse 16-GiB disk, refuses overwrites and
removes only its staging file if decoding fails. This is an intermediate OS
disk, not an installed VM. GPT relocation, APFS install roles, boot-component
preparation, real display scanout and touchscreen/button input remain incomplete
in the app. The UI states this.

Prepare official 19H422 firmware and the established 16-GiB APFS install disk on
macOS, then run:

```
python3 Tools/export_boot_bundle.py --firmware .firmware \
  --disk .firmware/system-disk/storage-16g.raw --output /path/to/Podium7Boot
```

The firmware directory must contain KernelCache.macho, DeviceTree.bin,
StaticTrustCache.im4p and SystemVolume.im4p. The existing hash/signature guards in
make_probe remain mandatory. The exporter applies exactly the explicit altered,
unsealed FastSim/disabled-AKS/unsupported-SecureRoot research profile, extracts
the actual PMP firmware, prepares NVRAM and APFS-clones the disk into a new folder.
It never overwrites the source disk or an existing destination. Do not publish
this private folder in GitHub artifacts/releases; it contains original firmware.

Transfer the folder to Files and choose it in the app's Import action. The app
copies four fixed filenames plus the manifest into a new internal directory and
validates the fixed 16-GiB size and ARM64 ELF identity. The disk remains disk-backed,
separate from the 2-GiB guest RAM. A Files provider may materialize sparse holes
during transfer: actual device storage/copy behavior must be measured.

This profile does not implement SEP, authenticated boot, trusted keybags or
physical iPod7 hardware equivalence. The app should not be used with personal
credentials. Device runtime/display success is not currently claimed.

Primary implementation references:
- QEMU 10.0.0 system/main.c: https://github.com/qemu/qemu/blob/v10.0.0/system/main.c
- UTM in-process architecture: https://github.com/utmapp/UTM/blob/main/Documentation/Architecture.md
- UTM iOS dependencies/coroutines: https://github.com/utmapp/UTM/blob/main/scripts/build_dependencies.sh
- Darwin libucontext pin: https://github.com/utmapp/libucontext/tree/9b1d8f01a6e99166f9808c79966abe10786de8b6
