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
