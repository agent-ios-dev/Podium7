"""Read a stopped QEMU CPU snapshot; no guest-success heuristics."""
import json
import re
import socket


def capture(path, virtual_addresses=(), memory_windows=(), physical_windows=()):
    family = getattr(socket, "AF_UNIX", None)
    if family is None:
        raise OSError("local QMP snapshots require Unix-domain sockets")
    with socket.socket(family, socket.SOCK_STREAM) as connection:
        connection.settimeout(3)
        connection.connect(str(path))
        with connection.makefile("rwb") as stream:
            def receive():
                line = stream.readline(1024 * 1024)
                if not line or not line.endswith(b"\n"):
                    raise ValueError("incomplete QMP message")
                return json.loads(line)
            if "QMP" not in receive():
                raise ValueError("missing QMP greeting")
            def request(command, arguments=None):
                message = {"execute": command, "id": command}
                if arguments is not None: message["arguments"] = arguments
                stream.write(json.dumps(message).encode() + b"\n")
                stream.flush()
                for _ in range(100):
                    reply = receive()
                    if reply.get("id") == command:
                        if "error" in reply: raise ValueError(str(reply["error"]))
                        return reply["return"]
                raise ValueError("QMP reply missing after 100 events")
            request("qmp_capabilities")
            request("stop")
            result = {"cpus": request("query-cpus-fast"),
                      "registers": request("human-monitor-command", {"command-line": "info registers"})}
            if virtual_addresses:
                result["translations"] = [
                    {"virtual_address": hex(address),
                     "backend_result": request("human-monitor-command", {
                         "command-line": f"gva2gpa {hex(address)}"})}
                    for address in virtual_addresses]
            if memory_windows:
                result["memory_windows"] = [
                    {"virtual_address": hex(address), "words": words,
                     "backend_result": request("human-monitor-command", {
                         "command-line": f"x/{words}wx {hex(address)}"})}
                    for address, words in memory_windows]
            if physical_windows:
                result["physical_windows"] = []
                for address, words in physical_windows:
                    if address < 0 or not 1 <= words <= 64:
                        raise ValueError("physical snapshot window must contain 1..64 words")
                    result["physical_windows"].append({
                        "physical_address": hex(address), "words": words,
                        "backend_result": request("human-monitor-command", {
                            "command-line": f"xp/{words}wx {hex(address)}"})})
            sp = re.search(r"\bSP=([0-9a-fA-F]{16})\b", result["registers"])
            result["stack"] = (request("human-monitor-command", {"command-line": f"x/256gx 0x{sp.group(1)}"})
                               if sp else "Stack capture unavailable: SP missing from CPU registers")
            # A stopped AP snapshot alone cannot distinguish a PMP stall from
            # a PMP reset/abort. Keep the original AP fields and capture peers.
            peers = [cpu["cpu-index"] for cpu in result["cpus"] if cpu["cpu-index"] != 0]
            if peers:
                result["peer_cpu_registers"] = []
                for index in peers:
                    # QMP creates a separate monitor context per HMP request;
                    # a previous `cpu N` command does not select the next request.
                    registers = request("human-monitor-command", {
                        "command-line": "info registers", "cpu-index": index})
                    result["peer_cpu_registers"].append({"cpu-index": index, "registers": registers})
            return result
