"""Read a stopped QEMU CPU snapshot; no guest-success heuristics."""
import json
import re
import socket


def capture(path):
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
            sp = re.search(r"\bSP=([0-9a-fA-F]{16})\b", result["registers"])
            result["stack"] = (request("human-monitor-command", {"command-line": f"x/256gx 0x{sp.group(1)}"})
                               if sp else "Stack capture unavailable: SP missing from CPU registers")
            return result
