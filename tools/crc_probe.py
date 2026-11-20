#!/usr/bin/env python3
"""Identify the CRC16 variant and covered byte range for a captured Zhiyun frame."""


def crc_ccitt(data: bytes, init: int = 0xFFFF, poly: int = 0x1021, xorout: int = 0) -> int:
    crc = init
    for b in data:
        crc ^= b << 8
        for _ in range(8):
            crc = ((crc << 1) ^ poly) & 0xFFFF if crc & 0x8000 else (crc << 1) & 0xFFFF
    return crc ^ xorout


def crc_reflected(data: bytes, init: int, poly: int, xorout: int = 0) -> int:
    crc = init
    for b in data:
        crc ^= b
        for _ in range(8):
            crc = (crc >> 1) ^ poly if crc & 1 else crc >> 1
    return crc ^ xorout


VARIANTS = {
    "CCITT-FALSE": lambda d: crc_ccitt(d, 0xFFFF, 0x1021, 0),
    "XMODEM": lambda d: crc_ccitt(d, 0x0000, 0x1021, 0),
    "AUG-CCITT": lambda d: crc_ccitt(d, 0x1D0F, 0x1021, 0),
    "X25": lambda d: crc_reflected(d, 0xFFFF, 0x8408, 0xFFFF),
    "KERMIT": lambda d: crc_reflected(d, 0x0000, 0x8408, 0),
    "MODBUS": lambda d: crc_reflected(d, 0xFFFF, 0xA001, 0),
    "IBM/ARC": lambda d: crc_reflected(d, 0x0000, 0xA001, 0),
}

FRAMES = [
    bytes.fromhex("243e0c0018150820008000000000000085b6"),
]


def main() -> None:
    for frame in FRAMES:
        print(f"frame ({len(frame)} bytes): {frame.hex()}")
        want_le = int.from_bytes(frame[-2:], "little")
        want_be = int.from_bytes(frame[-2:], "big")
        for name, fn in VARIANTS.items():
            for start in range(0, 5):
                for end in range(start + 2, len(frame) - 1):
                    calc = fn(frame[start:end])
                    if calc in (want_le, want_be):
                        order = "little" if calc == want_le else "big"
                        print(f"  MATCH {name:<12} bytes[{start}:{end}] -> 0x{calc:04x} "
                              f"({order}-endian trailer)")
        print("  trailer le=0x%04x be=0x%04x" % (want_le, want_be))


if __name__ == "__main__":
    main()
