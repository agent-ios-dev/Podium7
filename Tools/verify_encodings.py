"""Check bootstrap opcode fixtures against Apple's actual AArch64 assembler."""
import pathlib
import struct
import subprocess
import tempfile

instructions = [
    ("msr OSLAR_EL1, xzr", 0xd510109f),
    ("msr DAIFSet, #15", 0xd5034fdf),
    ("msr DAIFClr, #3", 0xd50343ff),
    ("mov x0, #4096", 0xd2820000),
    ("msr VBAR_EL1, x0", 0xd518c000),
    ("mov x20, x0", 0xaa0003f4),
    ("ldr x22, [x20, #256]", 0xf9408296),
    ("ret", 0xd65f03c0),
    ("cmp x2, x3", 0xeb03005f),
    ("subs x0, x0, #1", 0xf1000400),
]

with tempfile.TemporaryDirectory() as temporary:
    path = pathlib.Path(temporary)
    (path / "fixture.s").write_text(".text\n" + "\n".join(x[0] for x in instructions) + "\n")
    subprocess.run(["xcrun", "clang", "-arch", "arm64", "-c", str(path / "fixture.s"), "-o", str(path / "fixture.o")], check=True)
    data = (path / "fixture.o").read_bytes()
    commands = struct.unpack_from("<I", data, 16)[0]
    cursor, text = 32, None
    for _ in range(commands):
        kind, size = struct.unpack_from("<II", data, cursor)
        if kind == 0x19:
            count = struct.unpack_from("<I", data, cursor + 64)[0]
            for index in range(count):
                section = cursor + 72 + index * 80
                if data[section:section + 16].rstrip(b"\0") == b"__text":
                    length = struct.unpack_from("<Q", data, section + 40)[0]
                    offset = struct.unpack_from("<I", data, section + 48)[0]
                    text = data[offset:offset + length]
        cursor += size
    expected = b"".join(struct.pack("<I", word) for _, word in instructions)
    if text != expected:
        raise RuntimeError(f"Assembler mismatch: {text.hex() if text else 'missing __text'} != {expected.hex()}")
    print(f"Verified {len(instructions)} opcode fixtures using Apple's AArch64 assembler")
