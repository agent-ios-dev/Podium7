import io
import json
import unittest
from unittest.mock import patch, MagicMock
from qmp_diagnostics import capture


class Stream:
    def __init__(self, replies):
        self.reads = io.BytesIO(b"".join(json.dumps(reply).encode() + b"\n" for reply in replies))
        self.sent = []
    def __enter__(self): return self
    def __exit__(self, *args): pass
    def readline(self, size): return self.reads.readline(size)
    def write(self, data): self.sent.append(json.loads(data))
    def flush(self): pass


class QMPTests(unittest.TestCase):
    def test_live_snapshot_resumes_guest_even_when_register_capture_fails(self):
        stream = Stream([
            {'QMP': {}}, {'id': 'qmp_capabilities', 'return': {}},
            {'id': 'stop', 'return': {}},
            {'id': 'query-cpus-fast', 'error': {'desc': 'snapshot failed'}},
            {'id': 'cont', 'return': {}}])
        connection = MagicMock()
        connection.__enter__.return_value = connection
        connection.makefile.return_value = stream
        with patch('qmp_diagnostics.socket.AF_UNIX', 1, create=True), patch('qmp_diagnostics.socket.socket', return_value=connection):
            with self.assertRaisesRegex(ValueError, 'snapshot failed'):
                capture('local.sock', resume_after=True)
        self.assertEqual(stream.sent[-1]['execute'], 'cont')

    def test_stop_events_do_not_hide_cpu_register_reply(self):
        stream = Stream([
            {"QMP": {}}, {"id": "qmp_capabilities", "return": {}},
            {"event": "STOP"}, {"id": "stop", "return": {}},
            {"id": "query-cpus-fast", "return": [{"cpu-index": 0}]},
            {"id": "human-monitor-command", "return": "PC=fffffff0071904e8 SP=ffffffe000001000"},
            {"id": "human-monitor-command", "return": "ffffffe000001000: 0x1234"}])
        connection = MagicMock()
        connection.__enter__.return_value = connection
        connection.makefile.return_value = stream
        with patch("qmp_diagnostics.socket.AF_UNIX", 1, create=True), patch("qmp_diagnostics.socket.socket", return_value=connection):
            result = capture("local.sock")
        self.assertEqual(result["registers"], "PC=fffffff0071904e8 SP=ffffffe000001000")
        self.assertEqual(result["cpus"][0]["cpu-index"], 0)
        self.assertIn("0x1234", result["stack"])
        self.assertEqual(stream.sent[-1]["arguments"]["command-line"], "x/256gx 0xffffffe000001000")
        self.assertEqual([item["execute"] for item in stream.sent],
                         ["qmp_capabilities", "stop", "query-cpus-fast", "human-monitor-command", "human-monitor-command"])

    def test_secondary_arm32_core_is_selected_with_qmp_cpu_index(self):
        stream = Stream([
            {"QMP": {}}, {"id": "qmp_capabilities", "return": {}},
            {"id": "stop", "return": {}},
            {"id": "query-cpus-fast", "return": [{"cpu-index": 0}, {"cpu-index": 1}]},
            {"id": "human-monitor-command", "return": "PC=fffffff0071904e8"},
            {"id": "human-monitor-command", "return": "R15=01007718 PSR=600000ff"}])
        connection = MagicMock()
        connection.__enter__.return_value = connection
        connection.makefile.return_value = stream
        with patch("qmp_diagnostics.socket.AF_UNIX", 1, create=True), patch("qmp_diagnostics.socket.socket", return_value=connection):
            result = capture("local.sock")
        self.assertEqual(result["registers"], "PC=fffffff0071904e8")
        self.assertEqual(result["peer_cpu_registers"], [{"cpu-index": 1, "registers": "R15=01007718 PSR=600000ff"}])
        self.assertEqual(stream.sent[-1]["arguments"], {"command-line": "info registers", "cpu-index": 1})

    def test_server_error_is_not_reported_as_successful_snapshot(self):
        stream = Stream([{"QMP": {}}, {"id": "qmp_capabilities", "error": {"desc": "denied"}}])
        connection = MagicMock()
        connection.__enter__.return_value = connection
        connection.makefile.return_value = stream
        with patch("qmp_diagnostics.socket.AF_UNIX", 1, create=True), patch("qmp_diagnostics.socket.socket", return_value=connection):
            with self.assertRaisesRegex(ValueError, "denied"): capture("local.sock")

    def test_physical_control_snapshot_uses_xp_not_virtual_x(self):
        stream = Stream([
            {"QMP": {}}, {"id": "qmp_capabilities", "return": {}},
            {"id": "stop", "return": {}},
            {"id": "query-cpus-fast", "return": [{"cpu-index": 0}]},
            {"id": "human-monitor-command", "return": "PC=fffffff0071904e8"},
            {"id": "human-monitor-command", "return": "20e300b84: 0x0 0x1"}])
        connection = MagicMock()
        connection.__enter__.return_value = connection
        connection.makefile.return_value = stream
        with patch("qmp_diagnostics.socket.AF_UNIX", 1, create=True), patch("qmp_diagnostics.socket.socket", return_value=connection):
            result = capture("local.sock", physical_windows=((0x20e300b84, 2),))
        self.assertEqual(stream.sent[-1]["arguments"]["command-line"], "xp/2wx 0x20e300b84")
        self.assertEqual(result["physical_windows"][0]["physical_address"], "0x20e300b84")

    def test_process_metadata_rounds_short_reads_without_exporting_raw_words(self):
        node = 0xffffffe100001000
        name = b"SpringBoard\0".ljust(32, b"\0")
        name_words = [int.from_bytes(name[i:i+8], "little") for i in range(0, 32, 8)]
        def memory(address, values):
            return f"{address:016x}: " + " ".join(f"0x{value:016x}" for value in values)
        replies = [{"QMP": {}}, {"id": "qmp_capabilities", "return": {}},
            {"id": "stop", "return": {}},
            {"id": "query-cpus-fast", "return": [{"cpu-index": 0}]},
            {"id": "human-monitor-command", "return": "PC=fffffff0071904e8"}]
        for address, values in [(0xfffffff007137440, [0xffffffe100000000]),
            (0xfffffff007137448, [0]), (0xffffffe100000000, [node]),
            (node + 0x68, [23]), (node + 0x28, [1]),
            (node + 0x20, [node + 0x500]), (node + 0x500, [node]),
            (node + 0x520, [node + 0x600]), (node + 0x618, [501]),
            (node + 0x370, name_words), (node + 0xa8, [0])]:
            replies.append({"id": "human-monitor-command", "return": memory(address, values)})
        stream = Stream(replies)
        connection = MagicMock()
        connection.__enter__.return_value = connection
        connection.makefile.return_value = stream
        with patch("qmp_diagnostics.socket.AF_UNIX", 1, create=True), patch("qmp_diagnostics.socket.socket", return_value=connection):
            result = capture("local.sock", kernel_process_metadata=True)
        metadata = result["guest_process_metadata"]
        self.assertEqual(metadata["processes"], [{"pid": 23, "ppid": 1, "uid": 501, "name": "SpringBoard"}])
        self.assertTrue(metadata["springboard_process_seen"])
        self.assertFalse(metadata["visible_springboard_confirmed"])
        self.assertNotIn("backend_result", metadata)
        self.assertEqual(stream.sent[-8]["arguments"], {
            "command-line": f"x/1gx {hex(node + 0x68)}", "cpu-index": 0})
