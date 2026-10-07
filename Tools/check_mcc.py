"""Exercise actual QEMU MMIO and RAM protection; no canned boot-success flag."""
import argparse
import json
import pathlib
import subprocess
import tempfile


def check(executable, report):
    with tempfile.TemporaryDirectory() as temporary:
        log = pathlib.Path(temporary) / "stderr.txt"
        with log.open("w") as errors:
            process = subprocess.Popen([executable, "-machine", "virt", "-cpu", "podium7-research",
                "-m", "128", "-display", "none", "-monitor", "none", "-serial", "none",
                "-qtest", "stdio", "-qtest-log", "/dev/null", "-S"],
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=errors, text=True)
            def command(text):
                process.stdin.write(text + "\n"); process.stdin.flush()
                result = process.stdout.readline().strip()
                if not result.startswith("OK"):
                    raise RuntimeError(f"qtest rejected {text}: {result}; {log.read_text()}")
                return result.split()[1:]
            try:
                command("writeb 0x44000000 0xa5")
                assert int(command("readb 0x44000000")[0], 16) == 0xa5
                command("writel 0x2000007e4 0x1000")
                command("writel 0x2000007e8 0x1000")
                command("writel 0x2000007ec 1")
                assert int(command("readl 0x2000007ec")[0], 16) == 1
                command("writel 0x2000007e4 0x1001")
                assert int(command("readl 0x2000007e4")[0], 16) == 0x1000
                command("writeb 0x44000000 0x5a")
                assert int(command("readb 0x44000000")[0], 16) == 0xa5
                command("writeb 0x44004000 0x5a")
                assert int(command("readb 0x44004000")[0], 16) == 0x5a
                report.write_text(json.dumps({"passed": True, "model": "minimal one-plane MCC",
                    "checks": ["range lock", "locked registers immutable", "protected RAM write rejected", "adjacent RAM writable"]}, indent=2))
            finally:
                process.terminate()
                try: process.wait(timeout=3)
                except subprocess.TimeoutExpired: process.kill(); process.wait()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--qemu", required=True)
    parser.add_argument("--report", type=pathlib.Path, default=pathlib.Path(".firmware/mcc-checks.json"))
    arguments = parser.parse_args()
    check(arguments.qemu, arguments.report)
