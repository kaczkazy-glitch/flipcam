#!/usr/bin/env python3
"""Connect to the Smooth 5S over CoreBluetooth and dump its GATT tree + notify bytes."""
import sys
import time

import Foundation
from CoreBluetooth import CBCentralManager

PROPS = [
    (0x01, "broadcast"), (0x02, "read"), (0x04, "write-without-response"),
    (0x08, "write"), (0x10, "notify"), (0x20, "indicate"),
    (0x40, "signed-write"), (0x80, "extended"), (0x100, "notify-enc"),
    (0x200, "indicate-enc"),
]

TARGET = "SMOOTH"
STATE = {"central": None, "peripheral": None, "connected": False,
         "services_done": False, "chars_done": set(), "notify": [], "start": 0.0}


def props(mask: int) -> str:
    return "|".join(n for bit, n in PROPS if mask & bit) or "-"


class Delegate(Foundation.NSObject):
    # ---- central ----
    def centralManagerDidUpdateState_(self, central):  # noqa: N802
        print(f"[state] {central.state()}", flush=True)
        if central.state() == 5:
            central.scanForPeripheralsWithServices_options_(None, None)

    def centralManager_didDiscoverPeripheral_advertisementData_RSSI_(  # noqa: N802
        self, central, peripheral, data, rssi
    ):
        name = data.get("kCBAdvDataLocalName") or peripheral.name() or ""
        if TARGET not in str(name).upper():
            return
        print(f"[found] {name} rssi={int(rssi)}", flush=True)
        STATE["peripheral"] = peripheral
        central.stopScan()
        central.connectPeripheral_options_(peripheral, None)

    def centralManager_didConnectPeripheral_(self, central, peripheral):  # noqa: N802
        print("[connected] discovering services", flush=True)
        STATE["connected"] = True
        STATE["start"] = time.time()
        peripheral.setDelegate_(self)
        peripheral.discoverServices_(None)

    def centralManager_didDisconnectPeripheral_error_(self, central, peripheral, err):  # noqa: N802
        print(f"[disconnected] {err}", flush=True)

    # ---- peripheral ----
    def peripheral_didDiscoverServices_(self, peripheral, error):  # noqa: N802
        if error:
            print(f"[services error] {error}", flush=True)
            return
        services = peripheral.services() or []
        print(f"[services] {len(services)} discovered", flush=True)
        if not services:
            STATE["services_done"] = True
            return
        for svc in services:
            peripheral.discoverCharacteristics_forService_(None, svc)

    def peripheral_didDiscoverCharacteristicsForService_error_(  # noqa: N802
        self, peripheral, service, error
    ):
        if error:
            print(f"[chars error] {error}", flush=True)
            return
        print(f"\nSERVICE {service.UUID()}  ({'primary' if service.isPrimary() else 'secondary'})",
              flush=True)
        chars = service.characteristics() or []
        if not chars:
            print("  (no characteristics)", flush=True)
        for ch in chars:
            print(f"  CHAR {ch.UUID()}  props=[{props(ch.properties())}]", flush=True)
            peripheral.discoverDescriptorsForCharacteristic_(ch)
            if ch.properties() & 0x10:
                print("    -> subscribing notify", flush=True)
                peripheral.setNotifyValue_forCharacteristic_(True, ch)
        STATE["chars_done"].add(str(service.UUID()))

    def peripheral_didDiscoverDescriptorsForCharacteristic_error_(  # noqa: N802
        self, peripheral, characteristic, error
    ):
        if error:
            return
        for desc in characteristic.descriptors() or []:
            print(f"    DESC {desc.UUID()}", flush=True)

    def peripheral_didUpdateValueForCharacteristic_error_(self, peripheral, ch, error):  # noqa: N802
        if error:
            print(f"    [notify error] {error}", flush=True)
            return
        raw = ch.value()
        data = bytes(raw) if raw is not None else b""
        STATE["notify"].append((str(ch.UUID()), data))
        print(f"    NOTIFY {ch.UUID()} {data.hex()}", flush=True)

    def peripheral_didWriteValueForCharacteristic_error_(self, peripheral, ch, error):  # noqa: N802
        pass


def main() -> int:
    delegate = Delegate.alloc().init()
    central = CBCentralManager.alloc().initWithDelegate_queue_(delegate, None)
    STATE["central"] = central
    loop = Foundation.NSRunLoop.currentRunLoop()

    # phase 1: scan + connect (20s max)
    end = time.time() + 20
    while time.time() < end and not STATE["connected"]:
        loop.runUntilDate_(Foundation.NSDate.dateWithTimeIntervalSinceNow_(0.1))

    if not STATE["connected"]:
        print("RESULT: could not connect", flush=True)
        return 2

    # phase 2: enumerate (12s)
    end = time.time() + 12
    while time.time() < end:
        loop.runUntilDate_(Foundation.NSDate.dateWithTimeIntervalSinceNow_(0.1))

    # phase 3: listen to notifications for 5s
    print("\n[listening 5s for notifications]", flush=True)
    end = time.time() + 5
    while time.time() < end:
        loop.runUntilDate_(Foundation.NSDate.dateWithTimeIntervalSinceNow_(0.1))

    n = len(STATE["notify"])
    print(f"\nRESULT: notifications received = {n}", flush=True)
    if STATE["peripheral"] is not None:
        STATE["central"].cancelPeripheralConnection_(STATE["peripheral"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
