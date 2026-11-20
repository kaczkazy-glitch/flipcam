#!/usr/bin/env python3
"""Adopt the Smooth 5S's existing system BLE connection and dump GATT + notify bytes.

A bonded gimbal stays connected at the macOS level and stops advertising, so a fresh
scan never sees it. CoreBluetooth exposes those already-connected peripherals through
retrieveConnectedPeripheralsWithServices_(); this tool attaches to that link read-only.
"""
import sys
import time

import Foundation
from CoreBluetooth import CBCentralManager, CBUUID

SERVICE_UUIDS = [
    "0000FEE9-0000-1000-8000-00805F9B34FB",
    "0000180A-0000-1000-8000-00805F9B34FB",
    "0000180F-0000-1000-8000-00805F9B34FB",
]
PROPS = [
    (0x01, "broadcast"), (0x02, "read"), (0x04, "write-no-rsp"),
    (0x08, "write"), (0x10, "notify"), (0x20, "indicate"),
    (0x40, "signed-write"), (0x80, "extended"), (0x100, "notify-enc"),
    (0x200, "indicate-enc"),
]

STATE = {"central": None, "peripheral": None, "found": False, "connected": False,
         "notify": [], "chars": 0, "services": 0}


def props(mask: int) -> str:
    return "|".join(n for bit, n in PROPS if mask & bit) or "-"


class Delegate(Foundation.NSObject):
    def centralManagerDidUpdateState_(self, central):  # noqa: N802
        if central.state() != 5:
            return
        uuids = [CBUUID.UUIDWithString_(u) for u in SERVICE_UUIDS]
        found = central.retrieveConnectedPeripheralsWithServices_(uuids) or []
        print(f"[connected peripherals] {len(found)}", flush=True)
        for p in found:
            print(f"  {p.name()!r} {p.identifier()}", flush=True)
        target = next((p for p in found if "SMOOTH" in str(p.name() or "").upper()), None)
        if target is None and found:
            target = found[0]
        if target is None:
            print("RESULT: no system-connected gimbal; wake it and retry", flush=True)
            return
        STATE["found"] = True
        STATE["peripheral"] = target
        central.connectPeripheral_options_(target, None)

    def centralManager_didConnectPeripheral_(self, central, peripheral):  # noqa: N802
        print(f"[connected] {peripheral.name()}", flush=True)
        STATE["connected"] = True
        peripheral.setDelegate_(self)
        peripheral.discoverServices_(None)

    def centralManager_didDisconnectPeripheral_error_(self, central, peripheral, err):  # noqa: N802
        print(f"[disconnected] {err}", flush=True)

    def peripheral_didDiscoverServices_(self, peripheral, error):  # noqa: N802
        print(f"[services] {len(peripheral.services() or [])}", flush=True)
        for svc in peripheral.services() or []:
            STATE["services"] += 1
            print(f"\nSERVICE {svc.UUID()}", flush=True)
            peripheral.discoverCharacteristics_forService_(None, svc)

    def peripheral_didDiscoverCharacteristicsForService_error_(self, peripheral, svc, error):  # noqa: N802
        for ch in (svc.characteristics() or []):
            STATE["chars"] += 1
            print(f"  CHAR {ch.UUID()} [{props(ch.properties())}]", flush=True)
            peripheral.discoverDescriptorsForCharacteristic_(ch)
            if ch.properties() & 0x02:
                peripheral.readValueForCharacteristic_(ch)
            if ch.properties() & 0x10:
                peripheral.setNotifyValue_forCharacteristic_(True, ch)

    def peripheral_didDiscoverDescriptorsForCharacteristic_error_(self, peripheral, ch, error):  # noqa: N802
        for desc in (ch.descriptors() or []):
            print(f"    DESC {desc.UUID()}", flush=True)
            peripheral.readValueForDescriptor_(desc)

    def peripheral_didUpdateValueForDescriptor_error_(self, peripheral, desc, error):  # noqa: N802
        raw = desc.value()
        if raw is None:
            return
        if isinstance(raw, str):
            print(f"    DESC VALUE {desc.UUID()} text={raw!r}", flush=True)
            return
        try:
            hexed = bytes(raw).hex()
        except TypeError:
            print(f"    DESC VALUE {desc.UUID()} {raw!r}", flush=True)
            return
        print(f"    DESC VALUE {desc.UUID()} hex={hexed}", flush=True)

    def peripheral_didUpdateValueForCharacteristic_error_(self, peripheral, ch, error):  # noqa: N802
        raw = ch.value()
        if raw is None:
            return
        data = bytes(raw) if not isinstance(raw, str) else raw.encode("utf-8", "replace")
        STATE["notify"].append((str(ch.UUID()), data))
        text = data.decode("utf-8", "replace")
        printable = text.isprintable() and text.strip("\x00") != ""
        tail = f" ascii={text.strip(chr(0))!r}" if printable else ""
        print(f"    VALUE {ch.UUID()} hex={data.hex()}{tail}", flush=True)


def main() -> int:
    delegate = Delegate.alloc().init()
    central = CBCentralManager.alloc().initWithDelegate_queue_(delegate, None)
    STATE["central"] = central
    loop = Foundation.NSRunLoop.currentRunLoop()

    end = time.time() + 15
    while time.time() < end and not STATE["connected"]:
        loop.runUntilDate_(Foundation.NSDate.dateWithTimeIntervalSinceNow_(0.1))
    if not STATE["connected"]:
        print("RESULT: connect callback never arrived", flush=True)
        return 2

    for _ in range(40):
        loop.runUntilDate_(Foundation.NSDate.dateWithTimeIntervalSinceNow_(0.1))

    print("\n[listening 6s for notifications]", flush=True)
    start = time.time()
    while time.time() - start < 6:
        loop.runUntilDate_(Foundation.NSDate.dateWithTimeIntervalSinceNow_(0.1))

    print(f"\nRESULT: services={STATE['services']} chars={STATE['chars']} "
          f"notify_frames={len(STATE['notify'])}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
