#!/usr/bin/env python3
"""Scan for BLE peripherals that look like a Zhiyun gimbal."""
import asyncio
import sys

from bleak import BleakScanner


async def main() -> int:
    print("Scanning for BLE peripherals (12s)...", flush=True)
    seen = {}

    def on_detect(device, adv):
        addr = getattr(device, "address", "?")
        name = device.name or adv.local_name or ""
        rssi = adv.rssi
        key = (addr, name)
        if key in seen:
            return
        seen[key] = True
        uuids = ",".join(adv.service_uuids or []) or "-"
        mfr = adv.manufacturer_data or {}
        mfr_txt = ",".join(f"0x{k:04x}:{v.hex()}" for k, v in mfr.items()) or "-"
        print(f"  {name or '<no-name>':<28} {addr:<20} rssi={rssi:<5} services={uuids} mfr={mfr_txt}")

    scanner = BleakScanner(detection_callback=on_detect)
    await scanner.start()
    await asyncio.sleep(12.0)
    await scanner.stop()

    print(f"\nTotal unique peripherals: {len(seen)}")
    hits = [k for k in seen if "SMOOTH" in k[1].upper() or "ZHIYUN" in k[1].upper()]
    print(f"Zhiyun/Smooth candidates: {len(hits)}")
    for _, name in hits:
        print(f"  -> {name}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(asyncio.run(main()))
    except Exception as exc:  # noqa: BLE001
        print(f"SCAN FAILED: {type(exc).__name__}: {exc}", file=sys.stderr)
        sys.exit(1)
