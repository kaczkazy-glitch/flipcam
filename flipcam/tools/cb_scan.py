#!/usr/bin/env python3
"""Direct CoreBluetooth BLE scan (bypasses bleak) with advertisement dump."""
import sys

import Foundation
from CoreBluetooth import CBCentralManager

DURATION = float(sys.argv[1]) if len(sys.argv) > 1 else 12.0


SEEN: dict[str, bool] = {}


class Delegate(Foundation.NSObject):
    def centralManagerDidUpdateState_(self, central):  # noqa: N802
        print(f"state={central.state()} (5 == poweredOn)", flush=True)
        if central.state() == 5:
            central.scanForPeripheralsWithServices_options_(None, None)
            print("scan started", flush=True)

    def centralManager_didDiscoverPeripheral_advertisementData_RSSI_(  # noqa: N802
        self, central, peripheral, data, rssi
    ):
        try:
            name = data.get("kCBAdvDataLocalName") or peripheral.name() or "<no-name>"
            ident = str(peripheral.identifier())
            if ident in SEEN:
                return
            SEEN[ident] = True
            services = data.get("kCBAdvDataServiceUUIDs") or []
            mfr = data.get("kCBAdvDataManufacturerData")
            mfr_hex = mfr.hex() if mfr is not None else "-"
            svc_txt = ",".join(str(s) for s in services) or "-"
            print(f"  {name:<30} {ident} rssi={int(rssi):<5} svc={svc_txt} mfr={mfr_hex}",
                  flush=True)
        except Exception as exc:  # noqa: BLE001
            print(f"  decode error: {exc}", flush=True)


def main() -> None:
    delegate = Delegate.alloc().init()
    central = CBCentralManager.alloc().initWithDelegate_queue_(delegate, None)
    loop = Foundation.NSRunLoop.currentRunLoop()
    deadline = Foundation.NSDate.dateWithTimeIntervalSinceNow_(DURATION)
    while Foundation.NSDate.date().compare_(deadline) == -1:
        loop.runUntilDate_(Foundation.NSDate.dateWithTimeIntervalSinceNow_(0.2))
    if central.state() == 5:
        central.stopScan()
    print(f"unique peripherals: {len(SEEN)}", flush=True)


if __name__ == "__main__":
    main()
