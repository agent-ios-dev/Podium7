# Original A10 display handoff investigation

Firmware kernel SHA-256:
`115489dd3e2adbe3e0d646413adb9397cfaf1c47f7b5d03620f78dd7d9371814`.
Addresses below apply only to this verified kernel.

The genuine guest in run
https://github.com/agent-ios-dev/Podium7/actions/runs/38059471628
reports `display-timing-info` absent in EDT, then
`ERROR: APPLE CLCD DRIVER DIDN'T LOAD`. This is a separate remaining
problem from filesystem mounting and SEP data protection.

`AppleMobileADBE0::startWithIBoot` references the property string at
`0xfffffff0055ad937` from `0xfffffff005d2a73c`. The call at
`0xfffffff005d2a750` supplies a count of eight 32-bit words. Its stub at
`0xfffffff005d471d4` resolves through GOT `0xfffffff006da37e0` to
`IOMobileFramebufferLegacy::readDataInEDT` at `0xfffffff005cfaef8`.
That function checks OSData length equals count times four before copying.
Thus this property requires exactly 32 bytes, not merely width and height.

The caller copies all eight words into its timing state and propagates
words zero and four into fields at object offsets `0xfc0` and `0xfc4`.
Interpreting these as horizontal and vertical geometry is a working
hypothesis; the other words and validation must still be traced before
constructing a virtual panel mode.

Original DeviceTree `disp0` is `disp0,t8010`, linked to `dart-disp0`.
The panel is `lcd,pinot` under `mipi-dsim`. Its `raw-panel-id` and
`lcd-panel-id` are bootloader placeholders containing zeroes.
The tree also lacks recovered display timings and has zero dot pitch.
Current register apertures do not establish display scanout or GPU support.

To claim a visible SpringBoard, the backend must provide a coherent panel
mode, framebuffer allocation/mapping, guest framebuffer updates and actual
host readback/display. Kernel log messages or a host-rendered imitation
are insufficient evidence. No display or SpringBoard success is claimed.

## Concrete timing register ABI recovered

The original framebuffer profile getter at `0xfffffff005d0f494` returns the
static object at `0xfffffff007a2a028`; its initializer sets vtable
`0xfffffff006da44c8`. Factory slot +0x40 calls `0xfffffff005d0f4b8`, whose
constructor at `0xfffffff005d33e00` sets concrete driver vtable
`0xfffffff006da97e8`. This resolves the earlier indirect-call ambiguity.

Its timing setter (+0x1d0) is `0xfffffff005d38a64`, getter (+0x1e0) is
`0xfffffff005d38b64`. They exchange all eight words symmetrically:

| MMIO byte offset | low 16 bits | high 16 bits |
| --- | --- | --- |
| 0x0c | word 0 | word 4 |
| 0x10 | word 2 | word 6 |
| 0x14 | word 3 | word 7 |
| 0x18 | word 1 | word 5 |

Read slot +0xb8 resolves to `0xfffffff005d36388`; write slot +0xc0 to
`0xfffffff005d363ac`. Both access the mapped pointer in driver object +0x10
and require its register-access-enabled byte +0x30. The setter truncates each
component to 16 bits; the getter returns zero-extended components through
ARM64 x8 structure-return storage. This is a recovered packing ABI, not yet a
validated panel timing, register bank physical address or working scanout.
The meanings of porch/sync words and framebuffer mapping remain to be verified.

The concrete driver init `0xfffffff005d38958` calls the generic register mapper
`0xfffffff005d36184` with region kind 1. Profile virtual +0xa8 resolves to
`0xfffffff005d0f71c`; its index table at `0xfffffff0055b25e4` maps kind 1 to
DeviceTree `disp0` reg tuple 2 (zero-based), offset 0x06400000, size 0x4000.
With the original arm-io aperture base 0x200000000, the timing bank therefore
maps to physical 0x206400000. Runtime MMIO tracing must still confirm this
before claiming the controller is working.
