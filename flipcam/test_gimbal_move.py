#!/usr/bin/env python3
"""Gentle, safety-gated pan/tilt step for the Zhiyun Smooth 5S.

Envelope reverse-engineered from the Zhiyun Crane 2S / Weebill-S BLE protocol, which
uses the identical FEE9 UART characteristics. NOT yet confirmed against Smooth 5S
firmware, so every actuating mode prints a warning and requires typed confirmation.

Usage:
  .venv/bin/python tools/test_gimbal_move.py --selftest   # offline frame check, no radio
  .venv/bin/python tools/test_gimbal_move.py --probe      # writes only a STOP frame
  .venv/bin/python tools/test_gimbal_move.py --live       # prompts, then a gentle step
"""
import argparse
import sys
import time

import Foundation
from CoreBluetooth import CBCentralManager, CBUUID

SERVICE = "0000FEE9-0000-1000-8000-00805F9B34FB"
TX_CHAR = "D44BC439-ABFD-45A2-B575-925416129600"
RX_CHAR = "D44BC439-ABFD-45A2-B575-925416129601"

MAGIC_OUT = b"\x24\x3c"     # host -> gimbal
FORMAT_ID = b"\x18\x12"     # app -> gimbal
DIR_HOST_TO_GIMBAL = 0x01
PAYLOAD_LEN = 0x0008        # format-id .. payload inclusive

AXIS_CMD = {"pan": 0x01, "tilt": 0x02, "roll": 0x03}
CENTER = 2048               # 2048 == hold, <2048 / >2048 == opposite directions
MAX_SPEED = 30              # never exceed this from this script

# Captured live from this Smooth 5S while idle (~2 Hz). Its CRC is authoritative:
# XMODEM over bytes [4 : 4+len]. The "pan right" example published for the Crane 2S
# (243c08001812010102100008a4f1) does NOT verify under any standard CRC variant, so
# it is treated as illustrative only and is not asserted on.
TELEMETRY = bytes.fromhex("243e0c0018150820008000000000000085b6")
CRANE2S_EXAMPLE = bytes.fromhex("243c08001812010102100008a4f1")


def crc16_xmodem(data: bytes) -> int:
    crc = 0x0000
    for byte in data:
        crc ^= byte << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) & 0xFFFF if crc & 0x8000 else (crc << 1) & 0xFFFF
    return crc


def build_frame(cmd: int, value: int, speed: int, seq: int) -> bytes:
    """value 0..4095 (2048 = stop); speed 1..255."""
    value = max(0, min(4095, int(value)))
    speed = max(1, min(255, int(speed)))
    body = FORMAT_ID + bytes([seq & 0xFF, DIR_HOST_TO_GIMBAL, cmd & 0xFF])
    body += value.to_bytes(2, "little") + bytes([speed])
    crc = crc16_xmodem(body)
    return MAGIC_OUT + PAYLOAD_LEN.to_bytes(2, "little") + body + crc.to_bytes(2, "little")


def stop_frame(seq: int, axis: str = "pan") -> bytes:
    return build_frame(AXIS_CMD[axis], CENTER, 1, seq)


def verify(frame: bytes) -> bool:
    """Envelope + CRC check using the framing observed on live telemetry."""
    if len(frame) < 6 or frame[0] != 0x24:
        return False
    length = int.from_bytes(frame[2:4], "little")
    if length != len(frame) - 6:
        return False
    body = frame[4:4 + length]
    return crc16_xmodem(body) == int.from_bytes(frame[-2:], "little")


def selftest() -> int:
    ok = True
    expect = int.from_bytes(TELEMETRY[-2:], "little")
    got = crc16_xmodem(TELEMETRY[4:-2])
    print(f"captured telemetry {TELEMETRY.hex()}")
    print(f"  crc recomputed 0x{got:04x} == wire 0x{expect:04x} -> "
          f"{'PASS' if got == expect else 'FAIL'}")
    ok &= got == expect and verify(TELEMETRY)

    for axis, cmd in AXIS_CMD.items():
        frame = stop_frame(7, axis)
        good = (len(frame) == 14 and frame[8] == cmd and verify(frame))
        ok &= good
        print(f"  stop {axis:<5} {frame.hex()} {'PASS' if good else 'FAIL'}")

    for value in (0, 1024, 2048, 4095):
        frame = build_frame(0x01, value, 10, 200)
        good = verify(frame) and frame[9:11] == value.to_bytes(2, "little")
        ok &= good
    print(f"  pan sweep 0/1024/2048/4095 -> {'PASS' if ok else 'FAIL'}")

    print(f"  Crane2S example {CRANE2S_EXAMPLE.hex()} verify={verify(CRANE2S_EXAMPLE)}"
          " (expected False; illustrative only)")
    return 0 if ok else 1


class Link(Foundation.NSObject):
    """Adopts the gimbal's existing macOS BLE link and writes control frames."""

    def centralManagerDidUpdateState_(self, central):  # noqa: N802
        if central.state() != 5:
            return
        uuids = [CBUUID.UUIDWithString_(u) for u in (SERVICE,
                 "0000180A-0000-1000-8000-00805F9B34FB")]
        found = central.retrieveConnectedPeripheralsWithServices_(uuids) or []
        target = next((p for p in found if "SMOOTH" in str(p.name() or "").upper()), None)
        if target is None:
            print("gimbal not in a system-connected state; wake it and retry")
            return
        self.peripheral = target
        central.connectPeripheral_options_(target, None)

    def centralManager_didConnectPeripheral_(self, central, peripheral):  # noqa: N802
        self.connected = True
        peripheral.setDelegate_(self)
        peripheral.discoverServices_([CBUUID.UUIDWithString_(SERVICE)])

    def centralManager_didDisconnectPeripheral_error_(self, central, peripheral, err):  # noqa: N802
        self.connected = False
        print(f"[disconnected] {err}")

    def peripheral_didDiscoverServices_(self, peripheral, error):  # noqa: N802
        for svc in peripheral.services() or []:
            peripheral.discoverCharacteristics_forService_(None, svc)

    def peripheral_didDiscoverCharacteristicsForService_error_(self, peripheral, svc, error):  # noqa: N802
        for ch in svc.characteristics() or []:
            uuid = str(ch.UUID()).upper()
            if TX_CHAR in uuid:
                self.tx = ch
                print(f"[tx ready] {uuid}")
            elif RX_CHAR in uuid:
                peripheral.setNotifyValue_forCharacteristic_(True, ch)
                print(f"[rx subscribed] {uuid}")

    def peripheral_didUpdateValueForCharacteristic_error_(self, peripheral, ch, error):  # noqa: N802
        raw = ch.value()
        if raw is None:
            return
        self.notifies += 1
        self.last_notify = time.time()
        self.rx_log.append(bytes(raw))
        if self.notifies <= 5:
            print(f"  rx {bytes(raw).hex()}")

    def send_frame(self, central, frame: bytes) -> None:
        if self.tx is None:
            raise RuntimeError("TX characteristic not discovered")
        data = Foundation.NSData.dataWithBytes_length_(frame, len(frame))
        # CBCharacteristicWriteWithoutResponse == 1
        self.peripheral.writeValue_forCharacteristic_type_(data, self.tx, 1)


def connect(timeout: float = 15.0):
    link = Link.alloc().init()
    link.tx = None
    link.connected = False
    link.peripheral = None
    link.rx_log = []
    link.notifies = 0
    link.last_notify = 0.0
    central = CBCentralManager.alloc().initWithDelegate_queue_(link, None)
    loop = Foundation.NSRunLoop.currentRunLoop()
    end = time.time() + timeout
    while time.time() < end and not (link.connected and link.tx is not None):
        loop.runUntilDate_(Foundation.NSDate.dateWithTimeIntervalSinceNow_(0.1))
    return central, link, loop


def main() -> int:
    ap = argparse.ArgumentParser(description="Gentle Smooth 5S pan/tilt test")
    ap.add_argument("--selftest", action="store_true", help="offline frame check only")
    ap.add_argument("--probe", action="store_true", help="write only STOP frames")
    ap.add_argument("--live", action="store_true", help="gentle step + immediate stop")
    ap.add_argument("--axis", default="pan", choices=sorted(AXIS_CMD))
    ap.add_argument("--amount", type=int, default=180, help="offset from 2048 (default 180)")
    ap.add_argument("--speed", type=int, default=15, help="1..30 (default 15)")
    ap.add_argument("--yes", action="store_true", help="skip the typed confirmation")
    args = ap.parse_args()

    if args.selftest or not (args.probe or args.live):
        return selftest()

    speed = max(1, min(MAX_SPEED, args.speed))
    amount = max(30, min(400, abs(args.amount)))
    value = CENTER + (amount if args.amount >= 0 else -amount)
    axis = args.axis

    print(f"axis={axis} value={value} (center {CENTER}) speed={speed}")
    if args.live:
        print("This will command PHYSICAL MOTOR MOVEMENT. Clear the gimbal's swing path.")
        if not args.yes:
            answer = input("Type MOVE to proceed: ").strip()
            if answer != "MOVE":
                print("aborted")
                return 3

    central, link, loop = connect()
    if link.tx is None:
        print("RESULT: could not attach to gimbal")
        return 2
    print("attached; sending in 1s")
    time.sleep(1.0)

    seq = 1
    try:
        print(f"-> stop        {stop_frame(seq, axis).hex()}")
        link.send_frame(central, stop_frame(seq, axis))
        seq += 1
        time.sleep(0.6)

        if args.live:
            move = build_frame(AXIS_CMD[axis], value, speed, seq)
            seq += 1
            print(f"-> step        {move.hex()}")
            link.send_frame(central, move)
            time.sleep(1.0)
        print(f"-> stop        {stop_frame(seq, axis).hex()}")
        link.send_frame(central, stop_frame(seq, axis))
        seq += 1

        # Drain notifications so any reply is printed.
        end = time.time() + 2.0
        while time.time() < end:
            loop.runUntilDate_(Foundation.NSDate.dateWithTimeIntervalSinceNow_(0.1))
    except KeyboardInterrupt:
        print("\ninterrupted -> stop")
        try:
            link.send_frame(central, stop_frame(seq, axis))
        except Exception:  # noqa: BLE001
            pass
        return 130
    finally:
        try:
            link.send_frame(central, stop_frame(seq, axis))
        except Exception:  # noqa: BLE001
            pass

    print(f"RESULT: notifies={link.notifies}")
    if link.notifies == 0:
        print("no reply frames: either this firmware ignores the envelope or it needs the")
        print("active format ID; record the outcome in ZHIYUN_PROTOCOL.md before app use.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
