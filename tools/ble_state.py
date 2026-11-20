#!/usr/bin/env python3
"""Report the CoreBluetooth central manager state (permission diagnostic)."""
import Foundation
from CoreBluetooth import CBCentralManager

NAMES = {
    0: "unknown",
    1: "resetting",
    2: "unsupported",
    3: "unauthorized",
    4: "poweredOff",
    5: "poweredOn",
}


class Delegate(Foundation.NSObject):
    def centralManagerDidUpdateState_(self, manager):  # noqa: N802
        print(f"delegate callback: state={NAMES.get(manager.state(), manager.state())}", flush=True)


def main() -> None:
    delegate = Delegate()
    central = CBCentralManager.alloc().initWithDelegate_queue_(delegate, None)
    for _ in range(16):
        Foundation.NSRunLoop.currentRunLoop().runUntilDate_(
            Foundation.NSDate.dateWithTimeIntervalSinceNow_(0.25)
        )
        if central.state() != 0:
            break
    print(f"FINAL state={NAMES.get(central.state(), central.state())}", flush=True)


if __name__ == "__main__":
    main()
