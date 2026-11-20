#!/usr/bin/env python3
"""Connect to the Smooth 5S and read every readable characteristic + descriptor."""
import sys
import time

import Foundation
from CoreBluetooth import CBCentralManager, CBUUID

TARGET = "SMOOTH"
KNOWN_ID = "907E7D75-E24D-4D62-529E-413D2A34CC46"
STATE = {"central": None, "peripheral": None, "connected": False, "pending": 0}


class Delegate(Foundation.NSObject):
    def centralManagerDidUpdateState_(self, central):  # noqa: N802
        if central.state() == 5:
            central.scanForPeripheralsWithServices_options_(None, None)

    def centralManager_didDiscoverPeripheral_advertisementData_RSSI_(  # noqa: N802
        self, central, peripheral, data, rssi
    ):
        name = data.get("kCBAdvDataLocalName") or peripheral.name() or ""
        if TARGET in str(name).upper():
            STATE["peripheral"] = peripheral
            central.stopScan()
            central.connectPeripheral_options_(peripheral, None)

    def centralManager_didConnectPeripheral_(self, central, peripheral):  # noqa: N802
        STATE["connected"] = True
        peripheral.setDelegate_(self)
        peripheral.discoverServices_(None)

    def peripheral_didDiscoverServices_(self, peripheral, error):  # noqa: N802
        for svc in peripheral.services() or []:
            peripheral.discoverCharacteristics_forService_(None, svc)

    def peripheral_didDiscoverCharacteristicsForService_error_(  # noqa: N802
        self, peripheral, service, error
    ):
        for ch in service.characteristics() or []:
            if ch.properties() & 0x02:
                peripheral.readValueForCharacteristic_(ch)
            if ch.properties() & 0x10:
                peripheral.setNotifyValue_forCharacteristic_(True, ch)
            peripheral.discoverDescriptorsForCharacteristic_(ch)

    def peripheral_didUpdateValueForCharacteristic_error_(self, peripheral, ch, error):  # noqa: N802
        raw = ch.value()
        if raw is None:
            return
        data = bytes(raw)
        text = data.decode("utf-8", "replace").strip("\x00")
        printable = text.isprintable() and len(text) > 0
        print(f"VALUE {ch.UUID()}  hex={data.hex()}  ascii={text if printable else repr(data)}",
              flush=True)

    def peripheral_didDiscoverDescriptorsForCharacteristic_error_(  # noqa: N802
        self, peripheral, ch, error
    ):
        for desc in ch.descriptors() or []:
            peripheral.readValueForDescriptor_(desc)

    def peripheral_didUpdateValueForDescriptor_error_(self, peripheral, desc, error):  # noqa: N802
        raw = desc.value()
        if raw is None:
            return
        print(f"DESC  {desc.UUID()} on {desc.characteristic().UUID()}  "
              f"hex={bytes(raw).hex()}  ascii={bytes(raw).decode('utf-8', 'replace')!r}", flush=True)


def main() -> int:
    delegate = Delegate.alloc().init()
    central = CBCentralManager.alloc().initWithDelegate_queue_(delegate, None)
    STATE["central"] = central
    loop = Foundation.NSRunLoop.currentRunLoop()

    # Prefer the cached peripheral: the gimbal stops advertising while bonded.
    uuid = CBUUID.UUIDWithString_(KNOWN_ID)
    known = central.retrievePeripheralsWithIdentifiers_([uuid]) or []
    if known:
        print("[cached] connecting to known peripheral", flush=True)
        STATE["peripheral"] = known[0]
        central.connectPeripheral_options_(known[0], None)

    end = time.time() + 20
    while time.time() < end and not STATE["connected"]:
        loop.runUntilDate_(Foundation.NSDate.dateWithTimeIntervalSinceNow_(0.1))
    if not STATE["connected"]:
        print("RESULT: connect failed", flush=True)
        return 2

    end = time.time() + 8
    while time.time() < end:
        loop.runUntilDate_(Foundation.NSDate.dateWithTimeIntervalSinceNow_(0.1))

    if STATE["peripheral"] is not None:
        central.cancelPeripheralConnection_(STATE["peripheral"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
