import struct
import unittest
from qemu_probe import boot_args, elf_image, PHYSICAL_BASE, RAM_SIZE, virtual_base_for_kernel, panic_capture_complete


class QEMUProbeTests(unittest.TestCase):
    def test_system_probe_deadline_saves_snapshot_and_terminates_backend(self):
        import contextlib
        import io
        import json
        import pathlib
        import tempfile
        from types import SimpleNamespace
        from unittest.mock import patch, MagicMock
        from qemu_probe import run_probe
        with tempfile.TemporaryDirectory() as temporary:
            # macOS /var aliases /private/var; production resolves its disk path.
            # Canonicalize before matching the mocked fixture stat as well.
            root = pathlib.Path(temporary).resolve()
            disk = root / "disk.raw"
            disk.touch()
            (root / "KernelCache.macho").write_bytes(b"verified fixture")
            (root / "PreparedDeviceTree.bin").write_bytes(b"fixture tree")
            backend = MagicMock()
            backend.poll.return_value = None
            backend.returncode = 0
            def launch(*args, **kwargs):
                (root / "qemu-trace.txt").write_text("0x0000000042001000: nop\n")
                return backend
            original_stat = pathlib.Path.stat
            def stat(path, *args, **kwargs):
                if path == disk:
                    original = original_stat(path, *args, **kwargs)
                    return SimpleNamespace(st_size=16 << 30, st_mode=original.st_mode)
                return original_stat(path, *args, **kwargs)
            with contextlib.ExitStack() as stack:
                stack.enter_context(patch("qemu_probe.make_probe", return_value=(root / "fixture.elf", 0x42001000, (0, 0))))
                stack.enter_context(patch("qemu_probe.subprocess.check_output", return_value="QEMU fixture\n"))
                stack.enter_context(patch("qemu_probe.subprocess.Popen", side_effect=launch))
                stack.enter_context(patch("qemu_probe.time.monotonic", side_effect=[0, 301, 301]))
                stack.enter_context(patch("pathlib.Path.stat", stat))
                snapshot = stack.enter_context(patch("qemu_probe.capture_cpu", return_value={"registers": "PC=fixture", "stack": ""}))
                stack.enter_context(patch("inspect_pmgr_handoff.inspect_tree", return_value={}))
                stack.enter_context(contextlib.redirect_stdout(io.StringIO()))
                run_probe(root, cpu="podium7-research", research_system_root="disk0s1s1",
                          research_nvme=True, research_nvme_dart=True, research_nvme_msi=True,
                          research_nvme_image=disk, seconds=300)
            backend.terminate.assert_called_once()
            backend.wait.assert_called_once_with(timeout=3)
            self.assertFalse(snapshot.call_args.kwargs["kernel_process_metadata"])
            report = json.loads((root / "qemu-probe.json").read_text())
            self.assertEqual(report["stop"], "300-second execution deadline reached")
            self.assertEqual(report["cpu_snapshot"]["registers"], "PC=fixture")

    def test_keybag_diagnostics_require_no_sep_before_reading_files(self):
        from pathlib import Path
        from qemu_probe import make_probe
        with self.assertRaisesRegex(ValueError, 'keybag diagnostic'):
            make_probe(Path('nonexistent'), research_keybag_diagnostics=True)

    def test_debug_profile_is_explicit_and_keeps_default_boot_arguments(self):
        default = boot_args(0xfffffff004000000, 0xfffffff007d00000, 1234, 0x48000000, system_root='disk0s1s1')
        diagnostic = boot_args(0xfffffff004000000, 0xfffffff007d00000, 1234, 0x48000000, system_root='disk0s1s1', research_debug_diagnostics=True)
        self.assertIn(b'debug=0x8 ', default[108:716])
        self.assertIn(b'debug=0x14e ', diagnostic[108:716])
        self.assertEqual(default[:108], diagnostic[:108])
        self.assertEqual(default[716:], diagnostic[716:])
        with self.assertRaises(ValueError):
            boot_args(0xfffffff004000000, 0xfffffff007d00000, 1234, 0x48000000, research_debug_diagnostics=True)

    def test_fastsim_requires_explicit_unsealed_system_experiment_before_reading_files(self):
        from pathlib import Path
        from qemu_probe import make_probe
        for root, unsealed in ((None, False), ('disk0s1s1', False)):
            with self.assertRaisesRegex(ValueError, 'FastSim diagnostic'):
                make_probe(Path('nonexistent'), research_system_root=root,
                           research_unsealed_root=unsealed, research_fastsim=True)

    def test_trace_budget_rejects_unbounded_values_before_preparation(self):
        from unittest.mock import patch
        from qemu_probe import run_probe
        from pathlib import Path
        with patch("qemu_probe.make_probe") as prepare:
            for limit in (0, -1, 257, 1.5):
                with self.assertRaisesRegex(ValueError, "trace budget"):
                    run_probe(Path("unused"), trace_limit_mib=limit)
            prepare.assert_not_called()

    def test_panic_capture_waits_for_complete_first_saved_state(self):
        state = (b"pc: 0xfffffff005e45984 cpsr: 0x80400204 "
                 b"esr: 0x96000010 far: 0xffffffe0004ac020\n")
        header = b"panic(cpu 0 caller 0xfffffff00780f61c): Kernel data abort.\n"
        self.assertFalse(panic_capture_complete(header + b"x16: 0xfffffff007823ffc"))
        self.assertFalse(panic_capture_complete(state + header))
        self.assertFalse(panic_capture_complete(header + state[:-1]))
        self.assertTrue(panic_capture_complete(header + state))

    def test_assertion_panic_completes_without_watchdog_saved_state(self):
        header = b'panic(cpu 0 caller 0xfffffff006705ac8): "REQUIRE failed" @ApplePMGR.cpp:1148'
        self.assertFalse(panic_capture_complete(header))
        self.assertTrue(panic_capture_complete(header + b"\n"))

    def test_kernel_base_covers_lower_prelinked_and_upper_text_segments(self):
        base = virtual_base_for_kernel(0xfffffff0054e4000, 0xfffffff007dd0000)
        self.assertEqual(base, 0xfffffff004000000)
        for address in [0xfffffff005b0c500, 0xfffffff0071904e8]:
            physical = PHYSICAL_BASE + address - base
            self.assertEqual(physical & 0x1ffffff, address & 0x1ffffff)
            self.assertEqual(base + physical - PHYSICAL_BASE, address)
        with self.assertRaises(ValueError):
            virtual_base_for_kernel(0xfffffff0054e4000, 0xfffffff007dd0000, 0x42000000)
    def test_boot_args_ios15_layout(self):
        args = boot_args(0xfffffff0054e4000, 0xfffffff007d00000, 1234, 0x48000000)
        self.assertEqual(len(args), 736)
        self.assertEqual(struct.unpack_from("<HH", args), (2, 2))
        self.assertEqual(struct.unpack_from("<Q", args, 16)[0], PHYSICAL_BASE)
        self.assertEqual(struct.unpack_from("<Q", args, 24)[0], RAM_SIZE)
        self.assertEqual(struct.unpack_from("<QI", args, 96), (0xfffffff007d00000, 1234))
        self.assertEqual(args[108:716].split(b"\0", 1)[0], b"-v serial=3 debug=0x8 cpus=1")
        self.assertEqual(struct.unpack_from("<Q", args, 720)[0], 0)
        self.assertEqual(struct.unpack_from("<Q", args, 728)[0], RAM_SIZE)

    def test_elf_load_addresses_and_zero_fill(self):
        data = elf_image(0x40004000, [(0x40004000, 0x1000, b"test")])
        self.assertEqual(data[:4], b"\x7fELF")
        self.assertEqual(struct.unpack_from("<H", data, 18)[0], 183)
        self.assertEqual(struct.unpack_from("<Q", data, 24)[0], 0x40004000)
        self.assertEqual(struct.unpack_from("<II6Q", data, 64), (1, 7, 120, 0x40004000, 0x40004000, 4, 0x1000, 1))
        self.assertEqual(data[120:], b"test")
        with self.assertRaises(ValueError):
            elf_image(0, [(0, 1, b"test")])
