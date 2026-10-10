## Original DART root pages captured before command timeout

Run 38039924882 captures the original tables before any NVMe FatalHandling:
ASQ IOVA0x86b9c000, TTBR0..3=0x80055e80..83. Four nonzero64-bit root entries
appear at physical0x55e801a0..1b8:0x55e64003,0x55e65003,0x55e66003,0x55e67003.
Both unmodified-address4K/16K table walks select invalid zero entries. A separate
31-bit PCIe-address candidate matches the observed4K root occupancy and will
read the next-level descriptors and actual submission queue. This candidate is
diagnostic only: no assumed inbound remapping or DMA translation is installed.

Run38039538343 again confirms real launchd hello, restore environment and14237
EL0 returns. Its16 GiB disk uses16384 physical bytes after persisted sector I/O.
A strict independent NVMe restore-userland regression check is now added;
the preexisting PMP/control boot gates remain intact. Full desktop boot is absent.

Evidence: https://github.com/agent-ios-dev/Podium7/actions/runs/38039924882

---

## Original iOS restore launchd and restored_extern now execute with real NVMe attached

Run 38039000833 boots the independent NVMe+CFI+PMP research experiment far
past the PCIe assertion: original IONVMeController binds to the real QEMU NVMe.
The actual serial log contains launchd pid1 hello, early boot completion and
restored_extern pid3 restore checkpoints. Trace records 14137 EL0 returns,
first PC0x100ddd170. This confirms original restore userland execution; it does
not establish SpringBoard, full system boot or a native working IPA.

NVMe remains broken under the original guest's mapper: the Apple driver queues
Identify Controller, but QEMU DMA reads opcode0 (Delete SQ), returns an error
and raises MSI-X; the guest eventually reports command timeout. Port0 DART
TTBRs are programmed at +0x40..4c and the ASQ IOVA is0x857b4000. The backend
still does direct DMA without DART translation or Apple MSI routing.

The next separate bounded diagnostic stops at the first real NVMe command and
reads the original DART tables before teardown. It reports 4K/16K table-layout
candidates and actual physical queue words without applying guessed translation.
The complete boot experiment remains separate. 66 Python unit tests pass;
real queue DMA/read/write was verified independently on the fixed16 GiB disk.

Evidence: https://github.com/agent-ios-dev/Podium7/actions/runs/38039000833

---

## Real NVMe read/write verified; original driver link-state accessor corrected

Run 38038770887 successfully enumerates the real root-port/NVMe endpoint,
identifies namespace1 as exactly 17179869184 bytes (16 GiB), creates I/O queues,
DMA-writes LBA8 and reads it back. Independent host file inspection confirms
all 512 persisted bytes. This is real stock QEMU block I/O, not a register ACK.
Polling was tested; Apple DART, MSI and native IPA integration are still absent.

Original PCIe trace shows _waitForLinkUp uses PC0xfffffff00694e36c and reads
port0+0x208 bit0, while the separate link-state accessor reads bit6. Both bits
now derive from actual QEMU root-port DLLLA and the original port-enable
controls. Empty-port guest tests reject forged link bits. The independent iOS
NVMe experiment remains gated on genuine admin/I/O DMA guest success.

Restore launchd hello and SpringBoard are still unverified. Original mandatory
PMP and restore launchd boot gates remain unchanged.

Evidence: https://github.com/agent-ios-dev/Podium7/actions/runs/38038770887

---

## Real NVMe backend experiment; original PCIe link timeout isolated

Run 38037759808 passes the exact original DeviceTree PCIe aperture guest
check, but both kernel probes now reach a real port0 link-training timeout.
There was no downstream storage endpoint; the model correctly kept link down.

A separate opt-in backend now connects stock QEMU PCIe root-port and NVMe
at the original ECAM and PCI MMIO windows. Its scratch disk is always 16 GiB;
existing files are never silently resized. Direct DMA and polling are under
test; Apple DART/MSI and native IPA integration remain unimplemented.

Run 38038593460 compiles this backend and its ARM64 guest enumerates PCI,
enables NVMe and completes Identify Controller DMA. The guest then rejects
NN because it mistakenly expected an active namespace count of one. Pinned
QEMU sets NN to its namespace limit. That assertion is corrected; Identify
Namespace and persistent read/write checks must still pass before the kernel
experiment runs. Port0 link status now derives from the actual root-port DLLLA
and the original port-enable controls; the no-disk guest checks cannot forge it.

There is still no restore launchd hello or SpringBoard boot. The strict original
PMP and restore-userland gates are unchanged. The new NVMe kernel probe is
separate and runs only after successful real guest disk I/O verification.

Evidence: https://github.com/agent-ios-dev/Podium7/actions/runs/38038593460

---

## Original DeviceTree validation catches exact PHY span mismatch

Run 38037480360 rejects the new DeviceTree aperture check before boot: the
original final PHY range is base0x60a000000, size0x40000, not0x4000. This single
original span includes all four lane strides0x10000. The model now uses that
exact span and removes the speculative separate lane banks. The guest derives
all bank addresses and bounds from original DeviceTree and separately probes
lane controls. No prepared DeviceTree range is enlarged. Compile and kernel
validation follow. iOS desktop boot remains unverified.

Evidence: https://github.com/agent-ios-dev/Podium7/actions/runs/38037480360

---

## Exact PHY base fixed; original driver requires per-lane stride apertures

Run 38037441527 reads and programs PHY lane0 at exact 0x60a000000, then
aborts at FAR translated by QMP to 0x60a010088, original PC0xfffffff00694d73c.
Original driver addresses lane-specific controls at stride0x10000; the reg[11]
base span alone excludes lane1. Separate bounded0x4000 lane1..3 controls now
follow this observed accessor layout. The guest exercises +0x88 across these
independent banks in addition to the original DeviceTree-declared ranges.
No analog PHY, link-up or DMA completion is inferred. Kernel validation pending.

Evidence: https://github.com/agent-ios-dev/Podium7/actions/runs/38037441527

---

## Genuine PCIe PHY register FAR reveals a preexisting aperture typo

Run 38037265062 passes the lane-state guest and original driver exits its
PHY wait. Both kernel probes then data-abort at PC 0xfffffff00694d73c reading
PHY +0x180. QMP translates the actual FAR to 0x60a000180. Original DeviceTree
reg[11] declares base 0x60a000000 length0x4000, whereas the earlier bank table
mistyped it as 0x6000a0000. The model and guest aperture table now use the exact
original physical range. No kernel panic instruction is patched. Compile and
kernel validation follow; full iOS startup remains unconfirmed.

Evidence: https://github.com/agent-ios-dev/Podium7/actions/runs/38037265062

---

## PCIe speed panic cleared; research PHY lane request state added

Run 38036919703 passes PCIe-v2 speed-vector checks and no longer hits either
capability or speed panic. Its stopped stack reaches 0xfffffff00694eff8,
waiting for PHY lane status at 0x60000800c after enabling port0 +0x124=0x31.
Original lane-cfg=0 handling requests two lanes for port0; DeviceTree exposes
bridge0 storage and bridge3 WLAN. The research model now derives ready bits
from port enable requests (port0 mask3, other ports one lane) and removes them
on disable. This is explicit virtual PHY state, not analog calibration or
PCI link-up. An ARM64 guest verifies enable/disable and status independence.
Original kernel validation is pending. This run's PMP startup evidence is
incomplete and md0 mount fails, so it is not successful userland progression.

Evidence: https://github.com/agent-ios-dev/Podium7/actions/runs/38036919703

---

## Original PCIe v2 speed-vector dependency identified

Run 38036762119 still panics at limitedSpeed > 0 despite valid Gen1
LinkCapabilities. Original code 0xfffffff006822314..3b4 instead reads PCIe v2
Supported Link Speeds Vector (capability +0x2c), searches bits1..7 and rejects
an empty vector. The virtual root port now advertises only Gen1 in this
read-only vector (0x2), covered by the ARM64 config guest. Kernel validation
runs in 38036919703. LinkStatus stays zero and downstream buses stay absent.
No usable iOS boot has been verified.

Evidence: https://github.com/agent-ios-dev/Podium7/actions/runs/38036762119

---

## PCIe capability list accepted; virtual maximum speed added

Run 38036534007 passes root-port configuration guest checks. Both original
kernel probes advance beyond the missing _expressCapOffset panic and stop
at AppleEmbeddedPCIEPort::setMaximumLinkSpeed, limitedSpeed > 0. The virtual
root-port capability omitted its maximum link speed. Gen1 x1 is now declared
read-only in LinkCapabilities and tested while actual LinkStatus stays zero.
This describes research virtual capabilities only; no endpoint or PCI DMA
has been implemented. The next kernel probe must validate this change.

Evidence: https://github.com/agent-ios-dev/Podium7/actions/runs/38036534007

---

## PCIe channel reset removed; virtual root-port capability validation pending

Run 38036292150 passes the channel reset guest: reg[1] +4 bit16 self-clears,
without a DMA completion claim. Both normal and independent kernel probes
advance and panic at AppleT801xPCIePort::enablePortHardware because
_expressCapOffset is zero. The prior empty PCI config aperture supplied no
root-port capabilities. No EL0 or userland is reached in these probes.

fcbbc27 adds explicit virtual QEMU-identity PCIe root-port config on bus0
and leaves downstream buses absent. Type1 headers, capability-list status,
PCIe v2 root-port capability and zero link status are checked by an ARM64
guest. This is research topology, not a claim of exact Apple port config.
Compile, guest checks and original-kernel validation run in 38036534007.
No launchd, SpringBoard or usable iOS IPA has been verified.

Evidence: https://github.com/agent-ios-dev/Podium7/actions/runs/38036292150

---

## Original user code progresses; PCIe common-control second phase added

Run 38035660772 passes the first PCIe request check, confirms PMP startup and
records 901 EL0 returns in its normal 120-second restore probe. The stopped
stack advances from PCIe 0xfffffff00694d69c to 0xfffffff00694eef4: the original
driver first waits for status +0x28 bit4 and then for bit0. No launchd hello or
SpringBoard is observed. Both response bits now derive from the same observed
+0x124 bit0 request, with reset tested; kernel validation is pending in
run 38035964095. This remains an explicit research control acknowledgement,
not an authenticated hardware handoff or a functioning PCIe/NVMe endpoint.

Evidence: https://github.com/agent-ios-dev/Podium7/actions/runs/38035660772

---

## SPI fix validated; next stop is original PCIe control acknowledgement

Run 38035420066 passes the SPI W1C guest check and its normal 120-second boot
records 34 EL0 returns. The stopped stack now waits in original AppleT8010PCIe
at 0xfffffff00694d69c instead of the previous Samsung SPI acknowledgement loop.
The earlier independent CFI/AES experiment recorded 595 EL0 returns and actual
AES work without the prior AES panic. Neither confirms launchd or SpringBoard.

Original PCIe code writes bit0 to common-control +0x124 and loops until bit4
appears at +0x28, with a 10-us delay and no finite retry bound. A research
request acknowledgement now derives that status bit from the request and
clears it when the request clears. It does not advertise PCI link-up, PHY
calibration, endpoints or NVMe. An ARM64 guest checks both request transitions;
real kernel validation is pending in run 38035660772.

Evidence: https://github.com/agent-ios-dev/Podium7/actions/runs/38035420066

---

## First genuine EL0 execution observed; Samsung SPI polling livelock fixed

Run 38035038416 passes QEMU build and all mandatory hardware guests, including
AES CBC STORE_IV DMA. Its normal PMP probe confirms original firmware startup,
mounts restore md0, and records nine genuine EL1-to-EL0 exception returns,
first PC 0x105375170. launchd hello, restore environment and SpringBoard are
absent, so booted_ios and userland_execution_confirmed correctly remain false.
This probe does not enable the AES SecureRoot fallback or CFI NVRAM experiment.

Its stopped PC 0xfffffff005d77b7c and stack are in the original Samsung SPI
controller polling path. Trace repeatedly reads +8 status 0x0040000f, writes
that same value to acknowledge it, and reads the unchanged value again.
The old register backing store manufactured permanently pending events by
latching the acknowledge. SPI +8 now clears written bits (W1C). An ARM64 guest
checks the original mask, configuration independence and refusal to create
pending events by acknowledgement. SPI slave transfers are still absent.
The next real boot probe must establish whether clearing this livelock lets
userland advance; no completed iOS boot is claimed.

Previous independent AES experiment 38034538374 executed actual AES-256 CBC
with the original kernel's software key, then panicked on missing STORE_IV.
The two-word STORE_IV handler writes the actual chaining IV to bounded RAM,
verified against the final ciphertext of the CBC decryption known answer.

Evidence: https://github.com/agent-ios-dev/Podium7/actions/runs/38035038416

---

## AES software-key known answers, DMA guards and IRQ verified; iOS boot pending

Run 38032593352 confirms original PMP startup in both normal fresh-machine
probes and mounts genuine restore md0. Its independent 180-second CFI
experiment panics with `cannot find IOAESAccelerator`. Original disassembly
identifies an unmet SecureRoot callback: the earlier restore-only
IOSecureBSDRoot research return omits that callback.

A separately opted-in, whole-kernel-hash and instruction-signature guarded
experiment returns kIOReturnUnsupported from AES SecureRoot registration.
It does not alter ordinary probes or native IPA. Run 38033374188 then reaches
`AppleS8000AESAccelerator::_enableAES: DPA has not been seeded!`, proving the
next initialization dependency. This is not a successful iOS boot.

The external model now implements software-key AES-v2 ECB/CBC commands and
bounded physical RAM DMA through QEMU crypto. Unknown UID/GID and wrapped
keys remain errors. No encrypted payload is accepted as plaintext. DPA-ready
bits represent explicit research initialization, not physical hardware seeding.
DART/SART translation and cycle-accurate FIFO timing remain unimplemented.
AES-128 NIST ECB encryption and CBC encryption/decryption are mandatory ARM64
guest checks before the original-kernel experiment.

Run 38034381202 exposed a pinned-QEMU cipher enum mismatch, corrected in
67fb4a3. Run 38034538374 successfully builds QEMU and passes ARM64 NIST ECB
encryption/CBC encryption/decryption, real AIC source 237 assertion/deassertion,
and out-of-RAM/partial-block/unknown-key refusal without changing output.
63 local Python tests pass, including bounded physical QMP snapshot coverage.
Original-kernel boot experiments are running. No EL0, launchd, SpringBoard or
usable IPA is verified.
Original-firmware PMP startup evidence remains intermittently incomplete;
its strict gate stays enabled and independent CFI evidence stays separate.

Evidence: https://github.com/agent-ios-dev/Podium7/actions/runs/38033374188

---

## Restore md0 mounted; VXD NULL dereference removed, userland still absent

Run 38031635420 passed UART discovery and mounted the genuine restore HFS
RAMDisk md0, then panicked in AppleD5500 at PC 0xfffffff006451c70 with FAR 0x14.
Original disassembly proves the decoder's firmware descriptor is NULL: its
SRAM-size query +0x500 returns zero, so the embedded-image selector rejects it.
The caller nevertheless dereferences that absent image after logging failure.

The original SRAM-size formula at 0xfffffff006461738 decodes bank geometry;
firmware descriptor VA 0xfffffff007a4f318 has image size 0xa1a0. The model now
explicitly advertises one 64-KiB research SRAM bank (config 0x0e000100). Exact
ASIC geometry is unknown; this is not a claim of a working VXD decoder. An
ARM64 guest checks the exact driver's capacity calculation and read-only config.

Run 38032087540 passes all register checks, mounts md0, and executes the entire
120-second interval without the previous panic. There are zero observed EL0
returns and no launchd hello. ApplePMP reports started, but the original firmware
console startup line is absent, so the mandatory PMP evidence gate correctly
fails. The peer still executes its original scheduler; genuine message exchange
continues. This run is not a confirmed PMP or iOS boot.

A separate firmware-transmit staging word now preserves the published message
while staging the next low word, with an ARM64 consumer-between-words test.
An independent 180-second probe adds the existing synthetic CFI NVRAM provider
to isolate post-mount startup; the ordinary strict probe remains separate. Both
follow-ups are pending. 61 Python tests pass locally. No usable iOS IPA exists.

Evidence: https://github.com/agent-ios-dev/Podium7/actions/runs/38032087540

---

## Repeated genuine PMP startup and progress through ISP/display discovery

Runs 38030604802, 38030933219 and 38031286874 each pass both mandatory
fresh-machine PMP startup probes. The separate bounded message-port log budget
records genuine firmware reads even after AP status polling; all strict protocol
and original-firmware startup evidence is now present in both runs of each pair.

Run 38030604802 passes VXD discovery and stops at ISP revision read
0x205ba0000. Run 38030933219 passes that ISP access and stops at disp0 control
read 0x206400004. Run 38031286874 passes the display read and stops at uart5
UCON read 0x20a0d4004. Every physical address is resolved from the exact stopped
AP virtual fault address by QMP and matched against the original n112ap DT.

Independent discovery/control apertures and ARM64 guest checks were added for
VXD, ISP and all nine disp0 banks. This does not implement image processing,
video decode, display scanout or camera frames. Five separate polling UARTs are
now mapped from the original DT, with console output only for UART0 and no
fabricated RX data or Bluetooth peer; their next kernel validation is pending.

61 Python tests continue to pass. Actual restore launchd/EL0, normal iOS root
storage and graphical SpringBoard are not confirmed. All progress here is in
the external QEMU research backend, not a verified working iOS emulator IPA.

Evidence: https://github.com/agent-ios-dev/Podium7/actions/runs/38031286874

---

## PMP startup, bounded message FIFO and later display/video faults

Runs 38030017923 and 38030307496 both print genuine `ApplePMP: started`
and original firmware `[PMP:main.cpp:579] PMP started`. The second fresh-machine
probe in 38030017923 also reaches both startup messages. Its strict evidence
gate rejects the run because status polling exhausted the shared trace budget
before the firmware data-port read was recorded. A separate bounded data-port
budget has been added; the gate still requires actual consumed-message evidence.

The AP-to-PMP mailbox now uses a research FIFO of capacity 16, rather than a
single slot which dropped original endpoint-start bursts. Its exact ASIC depth
is not established. ARM64 guest checks cover full/empty flags, ordered draining,
rejected overflow, low/high-word publication, and a consumer freeing space
between low-word staging and high-word publication.

Original XNU passed the JPEG reset banks, 64-bit PMGR bridge accesses and scaler0
reset/discovery banks. Run 38030307496 stops at PC 0xfffffff006451a5c with physical
fault address 0x208130004, resolved by stopped-AP QMP translation to the original
DT `/device-tree/arm-io/vxd` secondary bank. VXD control windows and a guest
read/modify/write check have been added; their follow-up is pending. Codec DMA,
video decoding and scaler pixel processing are not implemented.

61 Python tests pass locally. This is still the external QEMU research backend:
no restore launchd/EL0, normal iOS root mount, SpringBoard or usable emulator IPA
is confirmed. Native fixed 16-GiB sparse storage is not yet guest NVMe storage.

Evidence: https://github.com/agent-ios-dev/Podium7/actions/runs/38030307496

---

## Verified original PMP protocol exchanges in both directions

Run 38028974526 confirms AP reads the authentic firmware hello, responds with
version 12, and PMP consumes that response through its real ARM32 receive
handler. Further real messages advertise endpoints and negotiate buffers.
CPU#1 has no data abort. Main XNU no longer stops at the prior PMP status-4/5
20-second timeout in this run: the new fatal point is AppleJPEGDriver's reset
write at original PC 0xfffffff0060edc88 (STR W9,[X8,#8]).

The driver module was resolved from the original __PRELINK_INFO metadata and
its __TEXT_EXEC Mach-O segment, not inferred from an arbitrary register value.
The original n112ap DT maps JPEG0/JPEG1 at 0x207b00000/0x207b08000, each 0x4000.
Discovery/reset controls and a guest reset-sequence test have been added;
codec DMA and encode/decode results remain unsupported. Follow-up is pending.

All previous hardware tests and 59 Python tests pass. Both processors genuinely
execute original firmware/kernel instructions; no protocol responses are
fabricated. Restore EL0, launchd and graphical SpringBoard are still absent.
This remains an external research backend, not a usable iOS emulator IPA.

Evidence: https://github.com/agent-ios-dev/Podium7/actions/runs/38028974526

---

## Verified genuine RTKit hello delivered to XNU

Run 38028780454 confirms the corrected AP receive IRQ 170. The original PMP
sends 0x00100000000c000c; XNU reads it through +0x4038/+0x403c and sends the
version-12 HELLO_REPLY 0x00200000000c000c through +0x4010/+0x4014. These are
executed original firmware/kernel instructions, not hardcoded model replies.
RTBuddy's pending state advances from 4 to 5. Full handshake still stalls:
CPU#1 remains in scheduler WFI at 0x01007718 and has not consumed the AP reply.
The new private IOP receive-event/IRQ implementation is being tested next.

Original firmware IOP interrupt dispatcher at 0x0100bf94 reads bank +0x81c;
its validator at 0x0100c1fc accepts event type 4/source 0 for mailbox receive.
This controller is separate from the AP AIC. The original +0xb88 enable bit
and real inbox occupancy gate the new receive event and ARM32 IRQ.

QMP snapshots now correctly show CPU#1 ARM32 registers via per-request
cpu-index. All modeled-device checks and 59 Python tests pass. No launchd,
SpringBoard or usable iOS IPA is confirmed.

Evidence: https://github.com/agent-ios-dev/Podium7/actions/runs/38028780454
RTKit protocol reference: https://github.com/torvalds/linux/blob/master/drivers/soc/apple/rtkit.c

---

## Verified shared-memory PMP execution and bidirectional mailbox queues

Run 38028359295 verifies the original ARM32 firmware executing alongside ARM64
XNU in the same QEMU process. XNU copies firmware into its original SRAM window
and writes release +0x38; the generic Cortex-A7 research core then enters the
unaltered reset body through a private low SRAM alias. A second TCG context is
reserved without creating a second AP. PMP sends its original version-12 hello
at +0xbb0/+0xbb4. This is actual firmware execution, not an emulated RTKit reply.

Run 38028112335 also passes guest tests for both data directions, publication
only after the high word, occupied-slot protection, read consumption/refill,
and AIC receive assertion/deassertion. Receive registers +0xb98/+0xb9c and send
registers +0xbb0/+0xbb4 come from executed original firmware instructions.

Full handshake is not yet confirmed: run 38028359295 leaves the hello queued
and XNU still panics with RTBuddy(PMP) status 4 after 20 seconds. The trace shows
source 167 masked and original XNU enabling source 170 (DTS interrupt index 2).
The receive IRQ has now been corrected to 170; its follow-up is pending.
QMP snapshots were also corrected to select the peer through cpu-index on the
individual request, since a separate HMP cpu command did not persist selection.

59 Python tests pass locally. Launchd/EL0, SpringBoard, normal root storage,
and a usable iOS IPA remain unconfirmed. Fixed native 16-GiB backing is unchanged.

Evidence: https://github.com/agent-ios-dev/Podium7/actions/runs/38028359295

---

## Verified PMP milestone: original firmware reaches scheduler WFI

Run 37988746111 executes 1516 distinct authentic ARM32 blocks. The corrected
legacy status +0xb88 ends the zero-message drain. There is no data abort;
the stopped PC 0x01007718 follows THUMB DSB/WFI at 0x01007712/0x01007716
and returns via BX LR. Calling code at 0x01009b30 belongs to the scheduler.
Register patterns deadc0de/b0bed0ff alone are not evidence of a panic.
The original firmware is now waiting for a real interrupt/message. Reports
separately track scheduler-WFI and data-abort evidence, keeping full PMP
boot and iOS boot unconfirmed. Firmware-hash guarded instruction bytes
avoid treating arbitrary register patterns as completion.

All individual research hardware checks pass in this run: SPI controls,
I2C empty-bus NACK/W1C, GPIO pull-ups, genuine AIC IRQ/ERET, DART controls,
PCIe discovery, AOP timebase and firmware RAM boundaries. Main ARM64 XNU
still times out after 20 seconds waiting for PMP (_iopStatus=4), since the
ARM32 experiment is a separate process with no connected AP peer. Next
substantial implementation is shared or bridged AP/IOP message queues,
interrupts and memory ownership between the real firmware and ARM64 XNU.
Normal root storage, graphical SpringBoard and a usable iOS IPA are still
unconfirmed. Fixed native 16-GiB backing disk remains unchanged.

Evidence: https://github.com/agent-ios-dev/Podium7/actions/runs/37988746111

---

## Correct arithmetic of the captured legacy mailbox object

Run 37988260194 still drains zero messages. Re-read the captured structure:
0x01014540 = object+0x90 contains [4,8,0x10,0x18]. Therefore field +0x94
is 8, and +0x9c is 0x18, not 4/0x10. Combined with base 0xc0500b80, the
status is +0xb88 and 64-bit receive data is +0xb98. The stopped R02 confirms
0xc0500b98 at message load. Prior +0xb84 assignment was an analysis error;
move the derived empty bit to +0xb88, preserving all other controls. Real
firmware and regression verification pending. No ready response fabricated.

---

## Runtime firmware object resolves exact legacy receive status/data offsets

Run 37987733454 captures the actual PMP mailbox object at 0x010144b0.
Field +8 is 0xc0500b80; fields +0x94/+0x9c are offsets 4/0x10. The receive
helper adds those fields, so it reads status at 0xc0500b84 and message at
0xc0500b90. The prior +0xb80 alias applied to the base control address and
could not fix the drain loop. Move derived empty bit17 to exact +0xb84 and
remove its treatment at +0xb80. Regression checks target the observed status
address. No message or firmware-ready state is invented; next trace must
confirm leaving the drain loop. Main XNU still awaits a real PMP peer.

---

## Legacy queue empty check passes; firmware loop still requires exact object mapping

Run 37987144912 passes the +0xb80 empty-view regression, but firmware still
loops in its receive-drain helper. The stopped R02=0xc0500b80 is the message
address after the helper's pointer arithmetic, so it does not establish
that the control read is at +0xb80. Preserve evidence and capture only the
44-word firmware mailbox object at 0x010144b0; its +0x94/+0x9c pointers will
identify actual control/data apertures. Do not claim the previous alias
fixed real firmware execution. Main XNU still times out waiting for PMP.
Next stopped-object diagnostic pending; no firmware/iOS boot confirmed.

---

## PMP no longer data-aborts; legacy receive status caused endless zero-message draining

Run 37986404202 executes 1330 real PMP blocks with no post-relocation data
abort. It loops at 0x0100c432 calling 0x0100c6dc: reads legacy receive control
at virtual 0xc0500b80, tests bit17 for empty, and reads a 64-bit message if
clear. The passive model left bit17 clear, falsely reporting an endless
queue of zero words. Implement empty-bit17 on legacy +0xb80 just as the
modern +0x4020 view. Retain low control bits, but no AP message is fabricated.
ARM64 tests verify reset-empty and that writing zero or control 0x1100 cannot
clear derived emptiness. Next real firmware trace remains pending. A genuine
AP/IOP peer and shared execution are still required for PMP/iOS boot.

---

## PMP advances through AIC setup; next write is an existing PMGR aperture

Run 37985453138 executes 1111 authentic ARM32 firmware blocks (previously
755) after its AIC CPU view becomes accessible. Next fault is a store at
DFAR 0xc00d4004, translated physical 0x20e0d4004. Original DeviceTree PMGR
reg[1] covers 0x20e000000..0x20e100000; this is not an unverified UART.
The main research board already maps it in PMGR raw controls. Enable that
same discovery/control model in the explicit standalone PMP probe. No
additional success flags or firmware replies are supplied. Next firmware
trace will show whether further command semantics or register windows are
required. Main XNU/firmware integration is still absent; no iOS boot claim.

---

## PMP private CPU view maps to the real AIC region

Run 37984678914 confirms firmware DFAR 0xc0101028 translates to physical
0x20e101028. This is an AIC CPU register view, not a new timer or invented
mailbox. Extend the existing AIC CPU0 view with the observed +0x1000 alias,
preserving original +0x2000/+0x5000 views. ARM64 tests verify WHOAMI and
cross-view IPI set/ack behavior. The explicit standalone PMP probe realizes
AIC and routes its output alongside the normal GIC through the IRQ OR.
No software event is synthesized: authentic ARM32 firmware drives its own
AIC registers. Subsequent IRQ/controller initialization validation pending.
Main ARM64 still lacks a connected PMP firmware peer and does not boot iOS.

---

## PMP code advances with mapped control aperture; supply authentic boot descriptor shape

Run 37983815067 executes 755 distinct original firmware TBs (previously
483), passing the first high-address mailbox faults. The next data abort
has DFAR 0xc0101028; the snapshot's active page tables will now translate
all observed DFARs automatically. The probe's mailbox boot descriptor was
zero, while actual XNU writes load low/high at +8/+0x10, arguments at
+0x18/+0x20, reserved SRAM length 0x20000 at +0x28, and boot-enable at +0x38.
Mirror these inputs in the standalone probe using its real load 0x41000000;
keep all firmware response/status queues empty. This is boot input metadata,
not a synthesized PMP-ready reply. ARMv7 counter frequency is 24 MHz to match
the main research platform. Exact board and ARM64 integration remain absent.
Next genuine firmware execution validation pending.

---

## PMP firmware uses LPAE to address the same high physical mailbox

Run 37983124660 executes the same 483 authentic firmware TBs. Stopped QMP
gva2gpa resolves 0xc0500040 -> 0x20e300040 and 0xc0500008 -> 0x20e300008.
The ARMv7-A firmware uses LPAE physical addresses above 32 bits; dropping the
high bits would be wrong. An explicit guarded firmware backend now opts the
standalone Cortex-A7 probe into the existing high-address PMP mailbox and
system control apertures. This is still separate from ARM64 XNU: passive
controls do not supply an AP peer, fake replies or a completed PMP boot.
The next actual firmware execution trace must reveal subsequent hardware
access or mailbox operations. Original kernel still waits for PMP firmware.

---

## Actual ARM32 PMP code executes and relocates; next access needs private I/O map

Run 37982337383 confirms reset-body execution and 483 distinct actual TBs
from the authentic embedded firmware. It enables CP15/VFP and relocates
execution into virtual 0x01000000. It then data-aborts with DFSR 0x210,
DFAR 0xc0500040 (and subsequently 0xc0500008), and eventually enters the
abort-stack validation loop at 0x01000834. This is not firmware-ready or
PMP/iOS boot. Register r2=0x0e300008 suggests a private PMP control mapping,
but it is not the fault address; inspect the active page tables before
choosing a physical aperture. QMP snapshots now ask gva2gpa for the two
observed fault VAs and retain the actual last executed PCs/DFAR evidence.
Main XNU still waits for a genuine PMP response after 20 seconds.

---

## Standalone PMP probe reserves virt bootloader DTB memory

Run 37981854516 stops before ARM32 execution: generic virt loads its DTB at
0x40000000..0x40100000, overlapping the standalone firmware load address.
Move the synthetic probe to 0x41000000 (main XNU platform is unchanged).
The firmware is position-aware but its real PMP memory map is still absent.
Capture a stopped ARM32 QMP register snapshot before terminating, alongside
actual executed-TB trace. This distinguishes code execution from a loader
attempt and identifies the next unsupported instruction or memory access.
No standalone PMP boot is yet confirmed; validation pending.

---

## Initial device apertures pass; real kernel now waits for PMP firmware

Run 37980997607 passes all device checks including the monotonic AOP counter.
Original kernel gets past prior missing-register aborts, then RTBuddy(PMP)
asserts after 20 seconds without a firmware response (_iopStatus 4).
The passive mailbox/SRAM controls never realized a coprocessor; a fake
ready message would hide rather than implement the missing firmware.

The next bounded experiment extracts the actual 123296-byte embedded PMP
image at kernel VA 0xfffffff007b01000 (hash guarded) and executes it on a
generic Cortex-A7 ARMv7-A baseline in a separate QEMU virt process. Original
reset branches to offset 0x68 and uses CP15/VFP/translation registers.
Execution trace must show the reset body actually entering a TB, not just
being disassembled. This is not an exact PMP CPU/board or completed firmware
boot: peripherals, private memory map, mailbox peer and integration into
ARM64 XNU remain necessary. Reports explicitly keep PMP/iOS boot false.
No raw Apple firmware is uploaded in evidence. Prototype validation pending.

---

## Original AOP time synchronization reaches its missing free-running counter

Run 37980153266 passes PCIe controls and ECAM widths. Next kernel fault is
PC 0xfffffff005e1e3e8 reading physical 0x21000040c, AOP reg[3] high counter.
Original code reads high/low/high and retries on high rollover. Constructor
constants at 0xfffffff0055da960 give offsets 0/4; default conversion pair at
0xfffffff0055da970 is 15625/512 microseconds per tick (32768 Hz). Optional
aop-fr-timebase uses 1/24 microseconds (24 MHz), but original DT lacks it.

Provide the read-only 32768-Hz counter from QEMU virtual nanoseconds, with
split 32-bit access and monotonic progress. Add distinct AOP system control
reg[2] at 0x210000500/0x100, mailbox reg[0] at 0x210800000/0x1c000, and
640-KiB firmware SRAM reg[1] at 0x210e00000. Counter is not a success flag;
firmware execution and mailbox replies remain absent. ARM64 tests cover
stable reads, time progress, ignored writes, and system/SRAM bounds. Pending.

---

## DART discovery passes; next access is PCIe common control

Run 37979534877 passes DART programming tests and advances to original
PCIe register write at PC 0xfffffff00681d708, physical 0x600000004,
/devicetree/arm-io/apcie reg[9] (32-KiB common control). Provide the 11 exact
control/PHY apertures independently from existing DART regions, plus the
16-MiB configuration window at 0x610000000. No endpoint is attached:
configuration reads return all ones for byte/halfword/word accesses, writes
have no effect. No PHY-ready/link-up status or NVMe device is synthesized.
ARM64 tests check all control banks, widths and the ECAM end boundary.
Next kernel validation pending; restore root remains a real RAMDisk.

---

## I2C pull-up regression passes; original ISP DART is the next device

Run 37978974681 passes six-pin GPIO electrical tests. The original driver
sets each SCL/SDA pin to peripheral/input config 0x221 and now samples high,
advancing beyond the prior bad-bus assertion. The next data abort writes
0x0020fffc to physical 0x205b28024, original PC 0xfffffff0060d7ba4.
DeviceTree identifies dart-isp reg[0] within the encompassing ISP aperture.
Original routine writes a shifted table address at +0x24, stream control
at +0xc (with readback check), and configuration at +0x30/+0x20.

Add the 12 exact independent DART register windows in original DeviceTree,
including the 8-KiB scaler bank and the two PCIe DARTs. ARM64 checks cover
table/stream programming and each window's boundary. DMA address translation,
permission enforcement, faults and cache invalidation semantics remain absent;
no peripheral DMA is implemented or claimed. Next kernel validation pending.

---

## Real IRQ regression passes; investigate I2C electrical idle lines

Run 37978335556 confirms real EL1 IRQ vector entry and ERET for both AIC
software IRQ0 and external I2C IRQ232; W1C deasserts without duplicates.
The original kernel still reports an I2C bad-bus assertion with otherwise
idle TX-empty status 0x00010000. Original I2C recovery inspects GPIO helpers
for SCL/SDA; the existing GPIO model sampled all undriven pins low.

Original gpio-iic_scl/sda tuples map I2C0 to pins 197/196, I2C1 to 40/39,
and I2C2 to 132/133 on the main bank. Model external pull-ups on these six
lines when released/input; output mode 1 preserves actively driven low/high.
Unrelated GPIOs and AOP pins are unchanged. ARM64 checks exercise all six
pins' idle, driven-low/high and input-release transitions. Bound extra
logging for these pins exposes the actual driver's recovery operations.
Next kernel validation pending. Pin data/mode layout reference:
https://github.com/torvalds/linux/blob/master/drivers/pinctrl/pinctrl-apple-gpio.c

---

## I2C empty-bus semantics pass; next PMP bank and real IRQ routing

Run 37977641862 passes I2C START/STOP/NACK/W1C/reset tests and advances
beyond the fabricated busy-status regression. The next data abort is
original PC 0xfffffff005dc4bac, physical 0x20e400000, /arm-io/pmp reg[2]
(64-KiB system control bank). Add this independently from PMP mailbox and
firmware SRAM. The original 32-bit control writes are retained without
manufacturing coprocessor ready state or firmware execution.

Separately, AIC events previously existed only in MMIO and did not drive
CPU IRQ. The research AIC now combines software and external level events,
updates CPU0 IRQ on mask/target/event changes, and auto-masks on event read.
The CPU receives the OR of the normal GIC and Apple AIC lines. I2C NACK/STOP
events drive original IRQs 232/233/234 when their interrupt masks and global
enable permit it; W1C deasserts the level. A genuine EL1 ARM64 regression
checks software IRQ0 and external I2C IRQ232, vector entry, acknowledgment,
ERET and absence of duplicate events. Timers retain their independent FIQ
route. New kernel validation remains pending; no launchd/SpringBoard claim.

---

## Replace I2C status latch with real empty-bus packet semantics

Run 37976778224 advances beyond the missing PCIe tuning assertion, then
I2C0 fails its bus-status check for display-pmu with status 0x0aa00040.
That is the driver's acknowledgment mask, incorrectly retained as status by
the discovery-only model. Original code and Linux i2c-pasemi-core agree:
+0 is MTXFIFO, +4 MRXFIFO, +0x14 SMSTA (W1C), +0x18 IMASK, +0x1c CTL.
START/STOP/READ commands use bits 8/9/10; status includes XIP bit28,
XEN bit27, MTN (NACK) bit21, MTE (TX-empty) bit16.

Model an empty bus: START has no responding slave and produces NACK;
STOP ends active transfer and records completion. RX remains empty, TX
commands are consumed, and derived active/empty state cannot be set by
acknowledgment writes. CTL FIFO-reset commands self-clear. Genuine ARM64
tests cover NACK, START/STOP, W1C, RX emptiness and reset. No successful
slave transaction or interrupt delivery is claimed; next kernel probe pending.

Reference: https://github.com/torvalds/linux/blob/master/drivers/i2c/busses/i2c-pasemi-core.c

---

## I2C passes; original PCIe configure requires an iBoot tuning property

Run 37976146675 passes I2C ARM64 initialization and advances to
AppleT8010PCIe::configure. Its original assertion requires an OSData property
named apcie-phy-tunables, absent from the IPSW /arm-io/apcie node. Original
code at 0xfffffff00694ed04 looks it up and casts it before storing +0x1d8.
The opt-in research virtual PHY declares an empty tuning list: no analog
hardware needs programming. Existing supplied tables are preserved and the
original metadata baseline is unchanged. No kernel assertion is patched,
no PHY-ready or PCI link-up state is manufactured. A real controller model
and subsequent kernel validation remain necessary. Tests cover opt-in,
platform validation and preservation of authentic supplied data.

---

## SPI regression passes; next original access reaches I2C initialization

Run 37975568120 passes SPI controls and advances the kernel to I2C1.
Original PC 0xfffffff00613c824 writes divider 4 to physical 0x20a11101c,
then timing 0x0aa00040 at +0x14, zero at +0x18, and 0x80000000 at +0x10.
Original DeviceTree defines three 4-KiB banks at 0x20a110000, 0x20a111000,
0x20a112000 (IRQs 232/233/234), compatible i2c,t8010/i2c,s5l8940x.
Provide independent discovery/control storage and a genuine ARM64 probe of
that sequence and each bank's boundary. Slave acknowledgments, bus packets,
FIFO side effects and IRQ completion are not yet implemented or claimed.
The original initialization routine does not poll a reset-complete bit at
this point. This is not a synthetic hardware-ready signal. Probe pending.

---

## Original SPI driver discovery/control apertures

Run 37974713532 data-aborts in Samsung SPI register write at physical
0x20a084000, original PC 0xfffffff005d77b84. The calling routine disables
+0 and +0xc, then writes its configuration at +8. DeviceTree has two
spi-1,samsung banks: SPI1 at 0x20a084000/0x4000 and SPI2 at
0x20a088000/0x4000, with IRQs 215/216. Provide separate zero-initialized
32-bit discovery/control storage. No codec/touch packets, SPI transfer
completion, FIFO contents or interrupts are fabricated. Genuine ARM64
checks execute the observed disable/configure sequence and verify bank
independence and end-of-window storage before another real kernel probe.

---

## Verified checkpoint: run 37974713532, next missing device is SPI1

The genuine ARM64 SEP/SIO/PMP checks pass in one machine: independent queue
state, boot-parameter controls, 64-bit sends, immutable derived status, and
PMP SRAM word/byte-order/end-boundary storage. Timer regression also passes.
Actual kernel execution progresses beyond the previously fatal PMP control
access. AppleSEPManager registers and AppleCredentialManager matches it.

The next real data abort occurs at original PC 0xfffffff005d77b84, instruction
word 0xb8214902, physical 0x20a084000. Original DeviceTree identifies
/arm-io/spi1 reg[0], a 16-KiB SPI control aperture. This controller is not yet
modeled; do not interpret the successful component tests as an iOS boot.
The restore launchd/EL0 regression gate correctly fails in this single-CPU
configuration. No SpringBoard, normal root-volume boot, or usable iOS IPA
is confirmed. Passive mailbox and SRAM support does not execute coprocessor
firmware or synthesize authentication/security responses.

Evidence: https://github.com/agent-ios-dev/Podium7/actions/runs/37974713532

---

## PMP SRAM accepts firmware; next access is its control bank

Run 37974361788 passes timer and mailbox/SRAM checks. Original RTBuddy
writes its PMP firmware and advances to AppleA7IOP's boot-parameter helper
at PC 0xfffffff005dc3760. The next data abort at physical 0x20e300018 maps
to /arm-io/pmp reg[0], 128 KiB at 0x20e300000. Map this independently from
firmware SRAM at reg[1]; the same observed AppleA7IOP control helper is
already exercised for SIO. The ARM64 queue-isolation test now executes SEP,
SIO and PMP in one machine before its SRAM check. Firmware execution and
real IOP responses remain unimplemented. Next original kernel result pending.

---

## PMP SRAM allocation ownership regression caught before kernel execution

Run 37973912011 fails the first timer test before any guest executes. QEMU
memory_region_init_ram requires a NULL or DeviceState owner for RAM migration
naming, while the new region supplied MachineState. The assertion accurately
identifies this initialization bug. Use NULL with the unique board RAM name;
QEMU registers the region globally. The existing timer and SRAM tests must
both pass before the next genuine kernel probe. No iOS boot claimed.

---

## PMP firmware loading reaches previously missing SRAM: run 37973299612

Both SEP/SIO ARM64 tests pass, including queue independence in the same
machine. The actual kernel advances to RTBuddy(PMP) and finds t8010pmp
firmware. Its copy loop at original PC 0xfffffff005dd7da4 data-aborts on the
first word at physical 0x20e500000. Original DeviceTree /arm-io/pmp reg[1]
is a 128-KiB firmware aperture. The observed word is ARM32 branch ea000018.

Map this window as zero-initialized RAM suitable for loading firmware,
rather than a control-register bank. ARM64 checks exercise the observed
word, byte order, wide storage, and the final 64-bit boundary. This does
not implement the PMP coprocessor, RTKit responses or firmware execution.
No launchd recovery or normal iOS desktop has been confirmed; next kernel
probe pending.

---

## Next reached IOP instance is SIO: run 37972738221

The SEP mailbox ARM64 test passes, but the actual kernel reaches a separate
AppleA7IOP instance for SmartIO and aborts at original PC 0xfffffff005dc3760,
physical 0x20ae00018. DeviceTree identifies /arm-io/sio, reg index 0,
64 KiB at 0x20ae00000. Original code writes boot configuration at +0x18,
+0x20, +0x28, +0x30, +8, +0x10 and +0x38. Add this distinct aperture to
the passive mailbox model; each bank has separate controls and queue state.
ARM64 checks now exercise both apertures and their boot-parameter writes.
The mailbox report is explicitly retained in Actions evidence. No IOP
firmware execution or success responses are claimed. Next probe pending.

---

## SEP manager registers; next original fault reaches its IOP mailbox

Run 37972077876 passes chip-id initialization: AppleSEPManager reports
control endpoints created, PM init done, registered, and starts power state
0 -> 2. The next data abort is str w10 at original PC 0xfffffff005dc3544,
physical 0x20da04000, inside /arm-io/sep's 64-KiB aperture. The adjacent
original code writes 0x1111 at +0x4000/+0xc00. Original mailbox helpers use
empty/full bits 17/16 at +0x4008/+0x4020 and 64-bit words +0x4010/+0x4038.

The new research device models control storage and a bounded single-slot
AP-to-SEP queue. Without a SEP peer, one sent message remains pending/full;
the receive queue stays empty. Guest writes cannot manufacture responses
or clear derived queue status. No SEP firmware, keys, DMA or completion IRQs
are emulated. Genuine ARM64 checks exercise wide message transactions and
queue invariants before another kernel probe. Kernel validation is pending;
launchd has not recovered in the single-CPU configuration, no SpringBoard.

---

## Original error-handler startup passes; next fatal check is SEP chip type

Run 37971329013 passes the ARM64 status-acknowledgment regression and the
original error-handler no longer data-aborts. The kernel reaches
AppleSEPManager and panics in SEPROMPanicBuffer because /chosen/chip-id is
still the four-byte all-zero iBoot placeholder. Original code looks up
/chosen, requires four bytes, reads chip-id, and asserts it is nonzero.
The opt-in research handoff initializes exactly that placeholder to 0x8010,
verified against original arm-io,t8010 compatibility. Nonzero supplied
values and unique-chip-id remain untouched. No working SEP, ECID, nonce or
security state is fabricated. Next kernel validation remains pending.

Fault diagnostics now decode bounded file-backed instruction windows with
the existing Capstone dependency instead of unavailable Xcode llvm-mc.
Replaying run 37938836505's real panic decodes the original faulting
str w10, [x8, x9] at 0xfffffff006d0792c correctly.

---

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
