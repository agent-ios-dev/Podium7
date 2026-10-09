## Error-handler acknowledgment regression caught before kernel execution

Run 37940003866 failed the genuine ARM64 MMIO check: writing all ones to
+0x10008 read back all ones. The generated handler retained the generic
control latch because its replacement targeted a nonexistent `s` variable
rather than `bank`. The replacement now uses the actual store and requires
exactly one source match, so generation fails if that anchor changes.
The existing ARM64 check covers the faulty behavior directly. A new kernel
run is required; neither launchd recovery nor iOS desktop is yet confirmed.

---

## Single-CPU topology releases AIC's CPU registration: run 37938836505

With cpus=1 the original AIC registerInterrupt for source 0 returns success
at 0xfffffff0068fcb98. Its unused source 1 returns a resource/index error and
the startup continues. The new actual fault is a 32-bit store at physical
0x200d10008, inside /arm-io/error-handler's third register window. It is not
a CLPC window. Restore userland regressed because this newly reached device
was absent; the CI launchd gate correctly fails instead of claiming boot.

The next model provides the five missing error-handler apertures at
0x200d00000/0x13000 and 0x200d20000, 0x200d90000, 0x200e20000,
0x200e90000 (each 0x1000). Only the observed status acknowledgment at +0x10008
is write-one-to-clear; other words are discovery/control backing stores.
The first two original windows already fall inside MCC and are not remapped.
No synthetic faults, full fabric-error handling or error IRQs are claimed.
A genuine ARM64 regression checks the exact faulting acknowledgment and
first/last control words of every added bank. Kernel validation is pending.

Separately, run 37938174593 confirms NVRAM preservation across two actual
kernel starts: second handoff selects bank 1 generation 3, guest userland
runs again, and backing banks finish at generations 5 and 4 with valid
checksums and the guest restore-outcome variable present. No SpringBoard.

---

## Match XNU CPU topology to the single realized QEMU CPU

Original IOCPUInterruptController::registerInterrupt waits while enabledCPUs
is different from numCPUs. The trace confirms entry to registerInterrupt and
enableCPUInterrupt, but AIC's first CPU-source registration does not return.
The harness realizes one CPU (-smp 1), while original DeviceTree describes
multiple CPUs. XNU ml_parse_cpu_topology accepts the supported cpus=N boot
argument and excludes additional CPU nodes. All single-CPU probe boot args
now include cpus=1. No original interrupt wait/check is patched out, and no
CPU enable state is fabricated. Actual AIC registration remains pending.

Sources:
https://github.com/apple-oss-distributions/xnu/blob/xnu-8019.80.24/iokit/Kernel/IOCPU.cpp
https://github.com/apple-oss-distributions/xnu/blob/xnu-8019.80.24/osfmk/arm64/machine_routines.c

---

## Guest NVRAM writes now persist: run 37936769787

Original AppleARMCHRPNVRAM now writes both banks successfully. Host backing
bank 0 has generation 2 and bank 1 generation 3; both Adler-32 checks pass
and both contain the guest restore-outcome variable. No raw variables or
backing key material are exported. Restore userland remains confirmed with
17,107 EL0 returns. These are research NOR banks, not real n112ap NVMe.

The two diagnosed CFI faults are fixed: AMD unlock/unlock/query now enters
query mode (the former zero erase geometry caused kIOReturnNotAligned), and
64-bit reads after query are split into supported 32-bit callbacks (the
former access-size rejection caused a genuine XNU memcpy data abort).
The immediate-program virtual NOR advertises a matching 1-us byte program
time; original Apple driver code and alignment checks are retained.

On the next launch the research handoff selects the newest checksum-valid
saved bank, including UInt32 generation wrap handling, and restores its
proxy bytes. It never resets an image whose two banks are corrupt. A second
actual kernel start is now part of CI; its result is pending.

AES startup remains blocked because original AIC startup calls provider
registerInterrupt for CPU source 0 at PC 0xfffffff0068fcb94 and never records
its return at 0xfffffff0068fcb98. Only IOPlatformInterruptController registers;
IOInterruptController00000018 (AIC) is requested but never registered.
Therefore the next genuine panic remains missing IOAESAccelerator after
90 seconds. No successful AES operations or SpringBoard boot are claimed.

---

## Original NVRAM driver registers: run 37926905157

The separate CFI experiment now executes original AppleARMCHRPNVRAM startup:
`bank size=0x2000, bank count=0x2, current bank=0`. Actual controller
registerService at 0xfffffff0077bfe10 is translated, and restored reports
`NVRAM access available on initial check`. IOResources/IONVRAM waits disappear.
The guest sets and reads restore-outcome in its NVRAM service.

Persistent synchronization is NOT yet successful: original CHRP sync returns
0xe00002d0 (kIOReturnNotAligned), before CFI programming. The next trace captures
the original CFI write alignment check at 0xfffffff005b898e4, including real
length, offset, erase geometry and mask. No alignment check is removed.
The assembler guest CFI QRY/program/persistent-byte regression passed.

Userland remains real: 17,099 EL1-to-EL0 returns and launchd early boot markers.
The next explicit kernel panic is `cannot find IOAESAccelerator: timeout = 90
seconds`. This is another missing service/device dependency; the existing
minimal AES register-window model is not a working IOAESAccelerator.
No SpringBoard or regular iOS system-volume boot is claimed. CFI NOR remains
an opt-in alternative research provider, not the original n112ap NVMe board.

---

## Separate synthetic NOR NVRAM experiment

Original AppleARMPlatform.kext contains AppleARMCFIFlashController matching
nor-flash,cfi on AppleARMIODevice, and AppleARMCHRPNVRAM matching nvram,chrp
on AppleARMNORFlashDevice. Disassembly confirms #device-bytes/#port-devices
properties, 8-byte (UInt32 offset/length) child reg tuples, and an AMD CFI
query at command address 0x5555. This provides an alternative research
provider; it does not reproduce the n112ap NVMe NVRAM hardware.

The new opt-in --research-cfi-nvram probe adds a 32-KiB NOR device at synthetic
physical 0x2f0000000, using the original arm-io address range. It passes two
8-KiB CHRP banks to the original driver and supplies a writable raw backing
file. Standard probes do not get the controller. Existing backing contents
are retained. QEMU's CFI02 implementation handles query, programming and
erase; its query address check additionally accepts the configured AMD
unlock address used by the Apple driver. No forced IONVRAM publication or
Apple driver/kernel instruction modification is added by this experiment.

An assembler-built ARM64 regression checks QRY, programming and the changed
byte in the host backing file. The separate real-kernel probe is pending;
driver registration, guest variable writes and reboot persistence are not
yet claimed. 48 local Python tests pass.

The native application's fixed 16-GiB sparse backing file passes macOS Swift
tests, including holes, boundary rejection, existing-image preservation,
and persistent writes above 4 GiB. iPhone app build run 37926551859 passed.
This backing file is not yet connected to a guest NVMe controller.

Source: https://github.com/qemu/qemu/blob/7c949c53e936aa3a658d84ab53bae5cadaa5d59c/hw/block/pflash_cfi02.c

---

## NVRAM proxy tested: run 37922572838

The zero-placeholder replacement is active on the real n112ap DeviceTree.
Restore launchd/userland still execute: 12,989 EL1-to-EL0 returns and all
three launchd markers (hello, restore environment, early boot complete).
No SpringBoard or regular system-volume boot is confirmed.

IONVRAM resource waits remain. Original IOPlatformExpert::publishNVRAM at
0xfffffff007780ddc is translated; neither IONVRAMController::registerService
at 0xfffffff0077bfe10 nor IOPlatformExpert::registerNVRAMController at
0xfffffff00777f8dc appears in the execution trace. Source publishes the
IONVRAM resource on controller registration, not proxy initialization.
Thus the proxy does not solve the missing controller. No forced resource
publication or fabricated security variables are used.

Restored services also report no enumerated IOMobileFramebuffer display,
and restored_external exits after disable_watchdog fails. These are separate
remaining hardware/service dependencies. The original-kernel comparison
still does not reach EL0 within its 30-second bound.

A CI regression gate now independently reads serial and execution traces:
actual restore launchd and EL0 execution are required. Mere successful QEMU
exit, a load attempt, or compiler success cannot pass this gate. Modified
kernel provenance and absence of a desktop-boot claim are mandatory.
47 local tests pass; the gate passes on both downloaded genuine traces.

---

## Confirmed restore userland: run 37840981874

The GPU startup command-completion fix passed its genuine guest regression.
The explicit modified-root experiment now executes actual Apple userland:
launchd prints `hello`, `Restore environment starting`, and `Early boot complete`.
The QEMU trace contains 13,025 EL1-to-EL0 returns, beginning at 0x104f81170.
Restore services including restored_extern run. The official restore trust
cache permits this execution with AMFI validation enabled.

This is the restore ramdisk environment, not SpringBoard, the regular system
volume, or a usable IPA. The IOSecureBSDRoot experiment remains explicitly
modified; the original kernel comparison remains separate.

The next observed dependency is repeated IOResources/IONVRAM waiting.
Original /chosen contains all-zero iBoot placeholders for nvram-bank-size
and the 8-KiB nvram-proxy-data. XNU's
IODTNVRAM::init requires the former; start parses the latter. The research
handoff now supplies an empty 8-KiB CHRP v1 bank with checked header sums,
Adler-32, and empty common/system partitions. Nonzero existing handoff bytes are
preserved; only absent properties or the exact zero-placeholder pair are initialized. This is volatile proxy initialization only: no persistent NVRAM
controller, nonce seeds, security-variable fabrication, or forced resource
publication is included. Actual service availability needs the next run.

The probe now records separate evidence fields for EL0 returns, launchd hello,
restore environment, and NVRAM waits. It never labels these as desktop boot.

Source: https://github.com/apple-oss-distributions/xnu/blob/xnu-8019.80.24/iokit/Kernel/IONVRAM.cpp

---

## SGX/GFX command-completion stall: run 37839672173

The restore probes now receive the official trust-cache region. No userland
entry is yet confirmed: the modified-root probe ran for 120 seconds in
original GPU startup code at PC 0xfffffff005fd2460. That code writes 0x11 at
0x201d01000 and polls bit 4 until it clears. The backing model kept 0x11
forever. The next change completes that command by clearing only bit 4,
retaining bit 0 and other fields, with a genuine guest regression. This is
startup command semantics, not GPU rendering or command-stream emulation.
AMFI acceptance of launchd remains unconfirmed until the next actual load.

---

## Actual launchd load attempt: run 37836967932

The explicit modified-kernel restore experiment progresses beyond the root
security gate and attempts to load /sbin/launchd. Original AMFI rejects its
adhoc signature with unsuitable CT policy 0; init receives SIGKILL. This is
an execution/load attempt, not confirmed launchd userland entry.

The official n112ap erase BuildManifest supplies RestoreTrustCache at
Firmware/098-68700-067.dmg.trustcache. Its rtsc IM4P contains a v1 module with
233 entries (including one valid identical duplicate), UUID
d0516b3d23844c8f9edd1d3bcfe65fca. No hashes, hash types or flags are changed.
XNU osfmk/arm/trustcache.c expects a serialized module-count/offset region.
The next probe passes it through /chosen/memory-map/TrustCache, at physical
0x454e0000 immediately below the first kernel segment, in a 16-KiB region.
The modeled MCC read-only range now includes that page. ELF regions were
verified non-overlapping. Both original and explicitly modified root probes
receive the official cache; AMFI validation remains enabled. Guest acceptance
is pending. 41 local Python tests pass.

Sources:
https://github.com/apple-oss-distributions/xnu/blob/xnu-8019.80.24/osfmk/arm/trustcache.c
https://github.com/apple-oss-distributions/xnu/blob/xnu-8019.80.24/osfmk/arm64/arm_vm_init.c

---

## Confirmed post-mount block: run 37834592824

Original HFS root mounting repeats successfully. Runtime tracing reaches
IOSecureBSDRoot entry and the SecureRootName platform dispatch, but never
records its return within 120 seconds. This isolates the next dependency.

An explicitly separate restore-userland experiment now accepts
--research-ramdisk-root. It changes only the IOSecureBSDRoot entry instruction
in the generated ELF to RET. The original kernel file is untouched. The edit
requires exact kernel SHA-256 115489dd3e2adbe3e0d646413adb9397cfaf1c47f7b5d03620f78dd7d9371814
and a matching 24-byte function signature; other kernels are rejected.
Both hashes and the exact edit are recorded in guest-patches.json. This is an
unauthenticated, modified-kernel research test to isolate userland startup,
not a completed virtual secure-boot implementation or an ordinary iOS desktop.
The unpatched restore test remains separate. No launchd execution is yet
confirmed. Local patch guards/regressions pass (37 Python tests total).

---

## Genuine root filesystem mount: run 37832777803

After the MCA reset-completion fix, original XNU selects md0 and prints:
`hfs: mounted SkyUpdate19H422.arm64CustomerRamDisk on device b(3, 0)`.
This confirms the real Apple restore HFSX root volume mounted in the guest.
The 120-second run captured no panic. It does not confirm launchd or a home
screen; restore userland is distinct from an ordinary iOS desktop.

Next diagnostics trace the actual IOSecureBSDRoot entry and its SecureRootName
platform call/return at 0xfffffff0077b9084/0xfffffff0077b9108/0xfffffff0077b910c.
The original Apple source calls this immediately after mountroot. The helper
only logs registers and never changes guest instructions or return values.
The goal is to distinguish security/resource waiting from userland execution
failure, using actual runtime evidence. The backend is still external to IPA.

---

## Two minutes without panic; MCA reset stall: run 37831773255

The genuine PMGR boundary setter now receives count 4, P-core-lowest 2.
The former P-core assertion is resolved. CPU debug-map accesses also proceed.
The restore probe runs for its full 120-second budget without a captured
panic, but it does not confirm root mounting or userland.

Actual CPU PC=0xfffffff0071c0a20 is a delay routine, with LR=0xfffffff00657c730.
The original MCA reset routine writes bits 0/1 at offset 0xc, then polls each
until it clears. The register backing retained bit 0 indefinitely, as proven
by repeated reads at 0x20a0ac00c. The next model completes those reset commands
immediately while preserving other fields. A guest test covers both commands
on all three banks. It still provides no PCM, DMA or MCA interrupt delivery.

---

## CPU group ordering and debug-map diagnosis: run 37830662740

The P-core boundary setter still received zero with ascending E/P frequencies.
Original generic PMGR at 0xfffffff0066e0018 detects a group boundary when the
frequency decreases. The revised research table therefore uses 396/1092 MHz
E states followed by 756/1644 MHz P states, directly from the original static
VFC endpoints. The single drop occurs at index 2. Nominal virtual voltage
metadata is 900 so the kernel's V-squared power calculation is nonzero; it is
not a recovered iBoot voltage or simulated physical rail. ACC records 2/3
are classified P; records 0/1 are E.

The actual next fault was a kernel debug-map store of the CoreSight access
key 0xc5acce55 at 0x202010fb0 (PC 0xfffffff0072dc118). Four original CLPC
register ranges at 0x202010000/0x202030000/0x202110000/0x202130000, each 64 KiB,
are now backed for bootstrap with a guest access/boundary test. This does not
emulate CPU debug or profiling machinery. Out-of-RAM translation diagnostics
now also cover static kernel VAs, which the former heap-only filter missed.
Kernel validation of these changes is pending; root/userland are unconfirmed.

---

## Verified SGX/GFX mapping progress: run 37829444239

SGX/GFX bank checks pass and the former GPU-control store fault is gone.
The next original-kernel assertion is _statePcoreLowest > 0 at
AppleT8010PMGR.cpp:602. A single synthetic state is insufficient to express
both efficiency and performance classes. The next explicit research handoff
uses two nominal states: 396 MHz from the original ecore-static-vvfc, and
1644 MHz from mcx-fast-cpu-frequency. Their period encodings remain type-1
PMGR periods. The modeled ACC state records classify state 0 as E and state 1
as P using bit 23, which the original method reads at 0xfffffff006943678.

This is synthetic nominal metadata and immediate transitions, not recovered
iBoot voltages or physical DVFS. Nonzero original tables remain untouched.
Runtime tracing also captures the P-core boundary setter arguments so the
next kernel run can verify its actual result. Root/userland are unconfirmed.

---

## Verified MIPI-DSIM progress: run 37828651313

The MIPI-DSIM range guest test passes and XNU progresses past its initial
read. The next failure is a 32-bit store of 0x11 to 0x201d01000, PC
0xfffffff005fd2458. Original sgx and gfx-kf nodes share the 128-KiB physical
range at 0x201d00000. The next model creates that bank once, plus their
separate 1-MiB SGX and 64-KiB GFX-KF banks. Guest checks cover the observed
store, bank independence and boundaries. This is register backing only, not
GPU command execution, rendering, DMA or GPU interrupt emulation.
Boot to root/userland/desktop remains unconfirmed.

---

## Verified MCA progress: run 37827850041

All three MCA banks and reset-register guest checks pass. XNU moves on to a
read fault at physical 0x206600000, PC 0xfffffff0065dc9cc. The original tree
identifies mipi-dsim reg[0], size 1 MiB. The next backing model covers that
exact range with dynamically sized storage and a real ARM64 guest test of
initial reads, independent registers and the final register. Panel signaling,
PLL timing and display output are not implemented by these latches. Boot
remains incomplete; root mounting, launchd and SpringBoard are not confirmed.

---

## Verified DWI progress: run 37827170433

The DWI initialization/boundary guest test passes. XNU reaches a new 32-bit
store fault at physical 0x20a002008, PC 0xfffffff00657ab2c. The original tree
identifies this as mca2 reg[1], a four-byte reset register. The next model
covers the three original MCA banks (mca0/mca2/mca3, 16 KiB each) and their
individual four-byte reset registers, with a guest test of all bank boundaries
and reset/clear accesses. Register storage only: PCM, DMA, codecs and MCA IRQs
remain unimplemented. No root mount or userspace is confirmed.

---

## Verified USB-complex progress: run 37826471006

The USB-complex parent control test passes and XNU proceeds past its control
write. The next fault is a 32-bit write at physical 0x20e200000 from PC
0xfffffff006507514. The original DeviceTree identifies dwi,t8010/dwi,s8000,
IRQ 5, with a 16-KiB register range. The observed initialization writes offsets
0, 0xd0, 4, 0x84 and 0x80. A separate DWI backing-store model and ARM64 guest
initialization/boundary test are added next. DWI bus transfers and IRQ delivery
are unimplemented; no root mount, launchd or SpringBoard is confirmed.

---

## Verified ACC page progress: run 37825946490

The observed ACC control page test passes and XNU progresses past its former
store fault. The next failure is a 32-bit write of 0x108 at physical
0x20c90001c, PC 0xfffffff006d0f600. This resolves to the original DeviceTree's
usb-complex parent control range, base 0x20c900000, size 0xa0. The next patch
adds that exact range using independent backing registers and a guest test
of the observed write and last register. USB host/device signaling, DMA and
interrupt delivery are still not implemented. No root mount or userland is
confirmed.

---

## Verified CPU performance fix: run 37825327929

The real guest CPU performance tests pass. The original kernel no longer
panics on readACCReg64 with state 254. The next captured fault is a 64-bit
store at PC 0xfffffff006ce380c to physical 0x202f38008, value 0x8033.
Its saved registers show the driver mapping [0x202f38000,0x202f39000).
This page is not in the PMGR DeviceTree reg list. The next model provides
backing control latches for that observed page and a 64-bit guest test.
No extra PLL/timing semantics are claimed. Root mounting and userland remain
unconfirmed, and the research backend remains external to the IPA.

---

## ACC assertion diagnosis from run 37824318487

Runtime argument tracing captured readACCReg64(0x00f82000), originating from
CPU state 254. The original driver at 0xfffffff006944a18 reads the low nibble
of ACC 0x00f20020, subtracts 2, and masks to 8 bits. The raw backing store
returned 0x61002000 with low nibble zero, producing the invalid state 254.
The physical register is 0x202f20020. This is not a missing MMIO aperture.

The next virtual CPU performance model starts at encoded state 2, preserves
completed state during control initialization, processes UPDATE bit 25, and
clears BUSY bit 31 immediately. It does not simulate physical DVFS/PLL timing.
The guest regression test covers reset state, initialization, requested state,
BUSY clearing and invalid-zero protection. Kernel validation is pending.

---

## Verified FIQ progress: run 37816744771

Physical and virtual timer FIQ delivery passed the real guest test. Original
XNU then progressed beyond the scheduler stall and stopped at a new assertion:
AppleT8010PMGR::readACCReg64(UInt32):1195 REQUIRE failed: 0. This is not a full
iOS boot. The next diagnostic captures the guest stack to recover the ACC read
argument and its caller. Root mounting, launchd and SpringBoard are unconfirmed.

---

## Timer interrupt diagnosis after the extended probe

Run 37815576973 completed the genuine 120-second restore experiment. It did
not mount a confirmed root volume or start userland. CPU snapshots from both
30-second and 120-second probes show PC=0xfffffff0071f1884 in the scheduler,
not the former PMGR polling loop. Generic timers were still routed through
virt's GIC, whereas Apple timer delivery uses FIQ. This is the next suspected
cause, not a confirmed fix yet.

The next research backend routes the physical and virtual EL1 timer outputs
through a level-preserving OR to CPU FIQ and disconnects the unused GIC FIQ
output for this CPU only. A genuine guest must receive each timer at the FIQ
vector, observe ISTATUS, disable the timer, and resume with ERET. The kernel
probe follows that test. External device IRQ wiring and Apple EL2 timer-enable
controls remain unimplemented.

Primary references:
https://github.com/torvalds/linux/blob/master/drivers/irqchip/irq-apple-aic.c
https://github.com/qemu/qemu/blob/v10.0.0/hw/arm/virt.c

---

## Latest verified run: 37814842447

The PMGR 64-bit aperture fault and the polling loop at 0x20e080230 are
resolved in the external research backend. Genuine guest tests pass. The
unpatched kernel reaches display, I2C, PCIe and AVE driver startup, with and
without the official restore ramdisk. Both experiments reach the 30-second
execution budget without a captured panic. This is not proof of a mounted
root volume, launchd or SpringBoard: none is confirmed.

The next probe extends the restore experiment to 120 seconds and captures
actual stopped CPU registers using local QMP, rather than inferring the
stopped PC from the last translated block. iOS is not yet booted to its home
screen and the backend is not yet part of the IPA.

---

## October 8, 2026: no iOS desktop confirmed

The external QEMU v10 research backend executes the original iPod9,1
kernelcache (iOS 15.8.8, 19H422). It is not yet integrated in the IPA.
The unchanged DeviceTree stops at ApplePMGR.cpp:1148 because iBoot bridge
settings are absent. The separate opt-in experiment supplies explicitly
synthetic bridge tuning lists and fixed clocks, not recovered iBoot settings.

That experiment passed CPU0, PLL and MCX performance-state checks. The last
completed run, 37809829401, faulted on a 64-bit read at 0x202f80040, PMGR reg[6].
The next change adds the remaining control apertures and 64-bit accesses,
with a genuine guest test. Run 37810433515 was still queued when recorded;
the kernel execution of that fix is not yet confirmed.

The probe now accepts --ramdisk for the official IPSW's raw HFSX restore disk.
It supplies /chosen/memory-map/RAMDisk and rd=md0, reserving the image below
boot_args.topOfKernelData. Local construction of the ELF was verified with
113845760 image bytes at 0x47dfc000, reserved top 0x4ea90000. Host validation
is not a successful guest mount. CI keeps the ramdisk experiment separate.

32 local Python tests pass. A green bootstrap workflow means the next fault
was captured and register tests passed, not that iOS booted. Mounting md0,
launchd and SpringBoard remain unconfirmed. Restore userland would also be
an intermediate milestone, not the ordinary iOS home screen.

Apple's ramdisk handoff source:
https://github.com/apple-oss-distributions/xnu/blob/xnu-8019.80.24/iokit/bsddev/IOKitBSDInit.cpp

---

# Состояние запуска iOS

Цель: загрузить iOS на модели iPod touch 7 / T8010 / n112ap. Цель пока не достигнута: корневой том, launchd и SpringBoard ещё не подтверждены. Настоящий вывод XNU уже получен через UART.

## Обновление 7 октября 2026

Первые сообщения настоящего XNU теперь получены через UART: оригинальное ядро выводит `arm_init: Unable to find 'dram-base' entry in the 'chosen' DT node`. Это ранняя panic, не успешная загрузка iOS. [Подтверждённый запуск](https://github.com/agent-ios-dev/Podium7/actions/runs/37646951870), исходный вывод: [evidence/xnu-uart-first.txt](../evidence/xnu-uart-first.txt).

Пройдены прежние остановки на APRR/HID и PMU bootstrap. Исправлены выравнивание виртуальной базы с нижними prelinked-сегментами, iBoot placeholder-флаги длин свойств device tree, частоты timebase/fixed-frequency и 64-байтовый seed загрузчика. В отдельной гостевой программе подтверждены регистры и UART TX. Связанные с контролем производительности регистры пока представлены latch-моделью, без полной логики счётчиков/прерываний; APRR ещё не применяет разрешения к MMU.

Добавлены dram-base/dram-size, соответствующие фактическому RAM машины QEMU virt. [Проверка](https://github.com/agent-ios-dev/Podium7/actions/runs/37647482992) прошла прежнюю panic и не зафиксировала исключений CPU до ограничения трассы. Это не подтверждение полной загрузки. Это исследовательский внешний backend на Mac, ещё не модель полного iPod7 внутри IPA.

В iPhone-приложение добавлены StikDebug universal protocol и настоящий JIT блоков арифметики; проверка готовности выполняет сгенерированную ARM64-функцию. [Инструкция и ограничения](JIT.md). На физическом iPhone интеграция пока не проверена.

Далее сохранена история первоначального исследования; её ранние ограничения не описывают весь нынешний прогресс.

## Что подтверждено 6 октября 2026

- Прошивка Apple: iPod9,1, iOS 15.8.8, build 19H422. Загрузочные компоненты выбраны по BuildManifest, а не по догадкам о названиях.
- IM4P/LZFSE и ARM64-срез kernelcache распакованы; Mach-O segments и LC_UNIXTHREAD обработаны. Device tree имеет 190 узлов и `arm-io,t8010`.
- Swift CPU выполнил 38 исходных инструкций kernelcache, включая реальную проверку пары инструкций pinst и установку VBAR. Затем остановился на неизвестном MSR.
- В отдельном эксперименте QEMU 11.1.1 выполнил загрузочный stub, переход на исходную точку входа ядра, OSLAR/DAIF и pinst. Затем возникло Undefined Instruction на `S3_4_C15_C2_1` (`0xd51cf220`), и гостевая система перешла в ранний exception-vector loop.
- Пройдено 20 Swift-тестов, восемь Python-тестов и проверка десяти opcode fixtures ассемблером Apple. Эти проверки не являются проверкой загрузки iOS.

Первая проверка оригинальной прошивки и трассы: https://github.com/agent-ios-dev/Podium7/actions/runs/37517496146

В исследовательском QEMU запуске физический entry — `0x43cac4e8`, адрес операции отказа — `0x44338030`; это релокация на синтетическую плату virt, не карта физической памяти настоящего A10. Аргументы загрузки соответствуют структуре iOS 15 с CommandLine 608 байт и bootFlags по смещению 720. Отчёт содержит `kernel_entry_seen: true` и `booted_ios: false`.

## Что требуется дальше

1. Подтвердить и реализовать семантику Apple-регистров, начиная с S3_4_C15_C2_1. Нельзя считать хранение записанного значения полной реализацией защиты памяти.
2. Выбрать окончательный CPU/MMU-бэкенд и реализовать модель T8010 вместо virt. Исследовательский QEMU сейчас запускается внешним процессом на Mac; для IPA нужен отдельный перенос.
3. Реальная физическая карта, таймеры, прерывания, UART и корректная передача boot args/device tree. Первые строки UART должны происходить от гостевого XNU.
4. Накопитель и загрузка корневого тома, необходимые драйверы устройств, пользовательское окружение и SpringBoard.

Нельзя выводить успешную загрузку из успешной компиляции, ненулевого счётчика инструкций или зелёного статуса workflow анализа.

## Первичные источники

- Формат аргументов: https://github.com/apple-oss-distributions/xnu/blob/xnu-8019.80.24/pexpert/pexpert/arm64/boot.h
- Начальная загрузка CPU: https://github.com/apple-oss-distributions/xnu/blob/xnu-8019.80.24/osfmk/arm64/start.s
- Исследуемый существующий XNU-бэкенд (iOS 12.1 / iPhone 6s Plus, не iPod7): https://github.com/alephsecurity/xnu-qemu-arm64
- Исследуемые Apple CPU-модели: https://github.com/TrungNguyen1909/qemu-t8030/tree/master/hw/arm

Код этих QEMU-форков пока не скопирован в репозиторий. Перенос их кода требует сохранения исходных лицензий и атрибуции.
