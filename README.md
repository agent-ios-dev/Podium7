# Podium7

Отдельный проект эмулятора iPod touch 7, почти с нуля. Текущий результат — начальное ARM64-ядро и диагностическое приложение; **iOS, iBoot и SpringBoard пока не загружаются**. Прошивки Apple в репозиторий не включены.

Реализованы MOVZ/MOVK, MOV (ORR alias), ADD/SUB immediate и shifted register с NZCV, ADR/ADRP, B/BL/BR/BLR/RET, условные ветвления, CBZ/CBNZ, TBZ/TBNZ, LDR 32/64, STRB/LDRB, NOP и начальные OSLAR/DAIF/VBAR. BRK #0 останавливает диагностическую машину; полноценная обработка исключений ещё не реализована. Есть ограничение исполнения, 28 Swift-тестов, 13 Python-тестов и проверка кодировок штатным ассемблером Apple.

Добавлены StikDebug и нативный JIT блоков регистровой арифметики с возвратом в интерпретатор для остальных инструкций. [Настройка и проверенные ограничения JIT](docs/JIT.md). Соединение с StikDebug на физическом iPhone пока не проверено.

ROM использует синтетическую плату с 64 КиБ RAM. Для реального kernelcache отдельно реализована ограниченная сегментная память с адресами Mach-O. Это не готовая физическая шина A10 и не MMU. Исходники Podium не скопированы.

## Настоящая прошивка и текущая остановка

Добавлена загрузка только нужных ZIP-компонентов iOS 15.8.8 / 19H422 / iPod9,1 по проверяемым HTTP Range-запросам к Apple. ZIP CRC проверяется, SHA-256 компонентов записываются. Разбираются BuildManifest, IM4P, LZFSE, универсальный ARM64 Mach-O и device tree. Выбрана identity n112ap; разобрано 190 узлов устройства.

Оригинальное ядро начинается по виртуальному адресу `0xfffffff0071904e8`. Строгий Swift-интерпретатор без opt-in модели APRR выполняет 38 его инструкций и останавливается на неизвестном регистре. Внешний QEMU-бэкенд с исследовательскими Apple-регистрами продвинулся дальше: включена MMU, выполняется C-инициализация XNU, получена настоящая panic через UART об отсутствовавшем dram-base. **Полная iOS, launchd и SpringBoard ещё не загружаются.** Подробности и отчёты: [docs/BOOT_STATUS.md](docs/BOOT_STATUS.md).

Отдельная opt-in модель `podium7-research` на закреплённом QEMU 10.0.0 позволяет исследовать следующий этап: APRR и наблюдаемые HID/LSU-регистры представлены хранилищем значений, UART TX привязан к адресу из настоящего n112ap device tree. Эта модель прошла начальное включение MMU и перешла в C-инициализацию, но полной загрузки XNU/пользовательской системы нет. APRR-разрешения ещё не применяются при трансляции страниц; состояние регистров проверено отдельным гостевым тестом. В штатном `max` CPU такое поведение не включается. Сборку и запуск выполняет workflow `Probe Apple bootstrap with explicit research register model`.

QEMU используется как внешнее исследовательское средство. `Tools/qemu_probe.py` создаёт загрузочный ELF с boot_args iOS 15 и запускает немодифицированное ядро на синтетической плате `virt` с TCG. CPU/MMU QEMU ещё не встроены в приложение. Плата virt, её память, UART и контроллер прерываний не соответствуют iPod touch 7. Успех workflow проверки означает получение трассы, а не достижение рабочего стола.

## Запуск и сборка

На Mac с Xcode: `swift test`, затем `swift run podium7`. Ожидается `Podium7 ARM64 OK`. Для приложения: установите XcodeGen, выполните `xcodegen generate`, откройте Podium7.xcodeproj, назначьте свой Team и включите подпись. GitHub Actions проверяет ядро, выполняет ROM и собирает неподписанную лабораторную IPA; для установки её нужно подписать.

Для анализа настоящей прошивки на Mac:

```sh
python3 -m unittest discover -s Tools -p 'test_*.py'
python3 Tools/fetch_firmware.py
python3 Tools/analyze_firmware.py
swift run podium7 --probe-kernel .firmware/KernelCache.macho
brew install qemu
python3 Tools/qemu_probe.py
```

Результаты сохраняются в `.firmware/`. Компоненты Apple не коммитятся и не входят в IPA. Workflow `Inspect genuine iPod touch 7 firmware` повторяет анализ и сохраняет только метаданные, отчёты и трассу. Исходный IPSW размером около 5 ГБ целиком не скачивается.

## Следующие этапы

1. Расширение ISA: флаги, загрузки/сохранения, вызовы, системные регистры, исключения, атомарные инструкции и SIMD. Проверять поведение сравнением с AArch64-ассемблером и эталонным исполнением.
2. MMU и таблицы страниц, таймеры и контроллер прерываний. Подтвердить карту T8010/N112AP по первичным данным перед реализацией устройств.
3. Разбор BuildManifest, IMG4 и device tree iPod9,1. Загрузка только реально поддерживаемых контейнеров, с явными ошибками для зашифрованных компонентов.
4. Boot arguments, UART и первые сообщения XNU. Проверка на реальной прошивке, без имитации успешной загрузки.
5. Накопитель, дисплей, touch, устройства безопасности и необходимые гостю драйверы; затем SpringBoard.
6. Производительность, сеть, звук, камера и микрофон после стабильной загрузки.

Конкретный срок запуска iOS не установлен: перечисленные устройства и загрузочная цепочка требуют исследования. Наличие ARM64-интерпретатора само по себе не обеспечивает запуск iOS.

## Первичные источники

- Apple, характеристики iPod touch 7 (A10): https://support.apple.com/en-us/111961
- QEMU t8030 (модель iPhone 11, другая платформа; здесь код не используется): https://github.com/TrungNguyen1909/qemu-t8030
- Спецификация ISA Arm: https://developer.arm.com/documentation/ddi0602/latest

### PMGR handoff blocker (19H422)

The original kernel reaches ApplePMGR::initDriver and requires missing
`bridge-settings-0` through `bridge-settings-12`. The original optional mask
`0x2000` allows only bridge 13 to be absent. The missing `bridge-settings-version`
defaults to 0; `bridge-counter-version=1` is a separate property.
Original code checks these at `0xfffffff0066df9a8` (property lookup),
`0xfffffff0066dfa58` (optional mask), and `0xfffffff0066e40b8` (panic call).

`Tools/inspect_pmgr_handoff.py` records `pmgr-handoff.json`. The bootstrap
workflow also preserves assertion branch disassembly. This identifies the
missing iBoot handoff stage; it does not fix the boot. The next task is to
recover n112ap bridge configuration and model its hardware semantics.
Changing the optional mask or adding empty properties would not establish
correct emulation. The extracted iBoot component is encrypted and was not
used to fabricate settings.

The research backend now maps all fourteen PMGR bridge register windows from
n112ap. `Tools/check_pmgr_bridges.py` derives their addresses independently
from the original DeviceTree and executes boundary/isolation checks in an
ARM64 guest. The second arm-io translation places bridge 11 at `0x600010000`,
not `0x800010000`. These banks preserve 32-bit register writes only; bridge
counters, power transitions and iBoot bridge tuning remain unimplemented.

An additional `--research-bridge-handoff` probe tests synthetic empty tuning
lists for the existing register-backing bridge model. This is deliberately
separate from the original-metadata probe. It does not recover real iBoot
settings, implement bridge tuning, or prove working power management.
Existing settings, the optional mask and settings version remain unchanged.
Both traces and explicit provenance are retained in the CI artifact.

The synthetic PMGR probe additionally replaces only an all-zero 128-byte
CPU `voltage-states1` placeholder with one nominal TCG state (24 MHz, no
physical voltage). Original voltage tables are preserved in the baseline
probe. This is a fixed-frequency virtual domain, not recovered A10 DVFS.

The synthetic PMGR probe passed bridge and CPU-domain metadata checks and
then reached the unmapped n112ap state register `0x20e080160` (original XNU
PC `0xfffffff0066ef4c4`). Eight windows selected by the original `ps-regs`
triples now expose valid-slot-aware state registers. Writes to DESIRED[3:0]
are acknowledged immediately in ACTUAL[7:4]; status bits cannot be supplied
by the guest. This models a deterministic virtual transition, not analog
power rails, dependency timing or physical A10 DVFS. The field layout agrees
with the [m1n1 PMGR register definition](https://github.com/AsahiLinux/m1n1/blob/main/proxyclient/m1n1/hw/pmgr.py).
`check_pmgr_power.py` executes power-on/off, control preservation and masked
slot checks in an ARM64 guest. Original-metadata boot still stops on missing
iBoot bridge settings; the separate experiment is not an authentic handoff.
