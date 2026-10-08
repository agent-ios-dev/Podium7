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
