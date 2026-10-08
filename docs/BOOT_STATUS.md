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
