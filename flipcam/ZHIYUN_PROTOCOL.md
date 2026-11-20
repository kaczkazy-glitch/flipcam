# Zhiyun Smooth 5S — Local Discovery Report

Captured on macOS 14.8.7 (Darwin 23.6.0), Python 3.13.15, via CoreBluetooth + `system_profiler`.
Device: **SMOOTH 5S_4460-7**, powered on, on the desk, battery 100%.

Status legend: **verified** = observed on this unit; **unverified** = inferred from open-source
Zhiyun protocol work and not yet confirmed against this firmware.

---

## 1. USB interface — not a control path

| Check | Result |
|---|---|
| `ioreg -p IOUSB -l -w 0` | Only the two `AppleT8103USBXHCI` controllers, **zero downstream devices** |
| `system_profiler SPUSBDataType` | Two `USB 3.1 Bus` entries with no children |
| `ls /dev/cu.* /dev/tty.*` | `wlan-debug`, `Bluetooth-Incoming-Port`, Soundcore headsets. **No `usbmodem*` / `usbserial*`** |

**Conclusion (verified):** the USB-C port does not enumerate as CDC-ACM, HID, or any USB
device on this Mac. It is charge-only / firmware-service only, so there is nothing to listen
to at 9600/38400/57600/115200 and no framing to sniff. All control goes over BLE.

---

## 2. BLE peripheral

| Field | Value |
|---|---|
| Advertising name | `SMOOTH 5S_4460-7` |
| BLE MAC (visible to `system_profiler`) | `DA:3F:AC:F1:FC:ED` |
| CoreBluetooth identifier (this Mac) | `907E7D75-E24D-4D62-529E-413D2A34CC46` |
| USB-style VID / PID | `0x0905` / `0x0250` (Zhiyun) |
| Manufacturer data | `09 05 42 02 01` (company `0x0509` LE, then `0x42 0x02 0x01`) |
| Advertised service UUIDs | none |

**Bonding behaviour (verified):** once macOS holds a connection the gimbal stops
advertising entirely. A fresh `scanForPeripherals` returns nothing for it; a new
`CBCentralManager` must adopt the existing link via
`retrieveConnectedPeripheralsWithServices_([FEE9, 180A])`. On Android this is not an issue —
scan and connect normally, or use `autoConnect = true` for wake-from-sleep.

---

## 3. GATT tree (enumerated live)

```
Service 0000180A  Device Information
  Char 0x2A29 Manufacturer Name String  [read]        -> "ZHIYUN"
  Char 0x2A50 PnP ID                    [read]        -> 02 05 09 50 02 01 00
Service 0000180F  Battery
  Char 0x2A19 Battery Level             [read|notify] -> 0x64 (100%)
      Desc 0x2902 Client Characteristic Configuration
Service 0000FEE9-0000-1000-8000-00805F9B34FB   (Zhiyun UART)
  Char D44BC439-ABFD-45A2-B575-925416129600  [write-without-response]  <- TX to gimbal
  Char D44BC439-ABFD-45A2-B575-925416129601  [notify]                  <- RX from gimbal
      Desc 0x2902 Client Characteristic Configuration
      Desc 0x2901 Characteristic User Description -> base64 "CQVCAgE=" = 09 05 42 02 01
```

All values above were read from the device, not assumed. There is no readable or
write-with-response control characteristic; **everything goes through `…9600`**.

---

## 4. Framing — verified on live traffic

Idle telemetry arrives on `…9601` at ~2 Hz, always the same 18 bytes:

```
24 3E 0C 00 18 15 08 20 00 80 00 00 00 00 00 00 85 B6
```

| Offset | Size | Field | Notes |
|---|---|---|---|
| 0 | 1 | `0x24` | magic `$` |
| 1 | 1 | `0x3E` gimbal→host / `0x3C` host→gimbal | direction magic |
| 2–3 | 2 | length, LE | **count of bytes from offset 4 to the CRC**, not total length |
| 4–5 | 2 | format ID | `18 15` = heartbeat/telemetry, `18 12` = app→gimbal |
| 6 | 1 | sequence | increments per command; gimbal echoes it in ACKs |
| 7 | 1 | direction | `01` host→gimbal, `10` on gimbal replies |
| 8 | 1 | command ID | `0x00` = status, `0x01/02/03` = pan/tilt/roll |
| 9… | n | payload | command-specific |
| end−2 | 2 | CRC-16/XMODEM, LE | over bytes `[4 : 4+len]` |

Total length = `6 + len`. For the frame above `len = 0x000C = 12`, CRC covers `[4:16]`.

### Checksum — verified

`CRC-16/XMODEM`: poly `0x1021`, init `0x0000`, no reflection, xorout `0x0000`, over
`bytes[4 : 4+len]`, transmitted low byte first. Recomputing the captured frame gives
`0xB685` -> wire `85 B6`. **PASS.**

Accuracy note: the "pan right" example published for the Crane 2S
(`243c08001812010102100008a4f1`) does **not** verify under XMODEM or any other standard
CRC variant over any subrange, so that example is illustrative only. The rule above is
anchored on the live Smooth 5S frame, and on gimbal **ACKs** captured in §6 — three
independent frames now agree.

### Telemetry payload

`00 80 00 00 00 00 00 00` after command `0x00` is byte-identical on every frame while the
gimbal is idle, so it is a static status/version block, **not** live IMU or quaternion data.
Do not build motion prediction on it.

---

## 5. Motor commands

Per-axis command IDs (from Zhiyun Crane 2S / Weebill-S work, same characteristic pair):

| Command | Axis |
|---|---|
| `0x01` | pan (yaw) |
| `0x02` | tilt (pitch) |
| `0x03` | roll |

Payload for a motion command is 3 bytes:

| Offset in payload | Field | Range |
|---|---|---|
| 0–1 | target value, LE | `0..4095`; `2048` = hold/centred, below/above = opposite directions |
| 2 | speed | `1..255`, higher = faster |

So a motion frame is always 14 bytes: `24 3C | 08 00 | 18 12 | seq | 01 | cmd | val_lo val_hi | speed | crc_lo crc_hi`.

```python
def build_frame(cmd: int, value: int, speed: int, seq: int) -> bytes:
    body = b"\x18\x12" + bytes([seq & 0xFF, 0x01, cmd]) \
         + (value & 0x0FFF).to_bytes(2, "little") + bytes([speed])
    crc = crc16_xmodem(body)                      # over [4 : 4+len]
    return b"\x24\x3c" + (len(body)).to_bytes(2, "little") + body \
         + crc.to_bytes(2, "little")
```

> **`value` is a scaled target, not a velocity.** Centre is 2048; `2048 + n` and `2048 - n`
> drive opposite directions. There is no documented "zero velocity" opcode on this
> firmware, so the safe stop is a hold frame at `value = 2048, speed = 1`. The test tool
> sends that in a `finally` block.

---

## 6. Firmware acceptance — verified (non-actuating probe)

`test_gimbal_move.py --probe` writes **only** hold/stop frames and logs replies:

```
-> 24 3c 08 00 18 12 01 01 01 00 08 01 3b 74     (seq 1, pan, hold, speed 1)
rx 24 3e 0c 00 18 15 08 20 00 80 00 00 00 00 00 00 85 b6   (telemetry)
rx 24 3e 08 00 18 12 01 10 01 00 00 00 b8 43               (ACK: seq 1, dir 0x10, cmd 0x01)
-> 24 3c 08 00 18 12 02 01 01 00 08 01 db ba     (seq 2)
rx 24 3e 08 00 18 12 02 10 01 00 00 00 58 8d               (ACK: seq 2)
```

**The gimbal parses our envelope and acknowledges it.** This confirms magic bytes, length
field, CRC coverage and byte order, sequence handling, and that `0x01` is a valid pan
command on this firmware. What is still **unverified** is whether a non-centre `value`
produces the expected direction and magnitude of physical motion — that needs the gated
`--live` run on a clear desk.

ACK frame shape: `24 3E | 08 00 | 18 12 | seq | 10 | cmd | 00 00 00 | crc`.
The reply uses format `18 12` (not `18 15`), direction `0x10`, echoes `seq` and `cmd`, and
carries a 3-byte zero payload. Treat direction `0x10` as the "response" bit.

---

## 7. Safety-gated test tool

```bash
cd flipcam
.venv/bin/python test_gimbal_move.py --selftest   # offline: CRC + envelope checks, no radio
.venv/bin/python test_gimbal_move.py --probe      # hold frames only, logs ACKs
.venv/bin/python test_gimbal_move.py --live --axis pan --amount 180 --speed 15
```

`--live` prints a warning, requires typing `MOVE` (unless `--yes`), limits `speed` to 30 and
`amount` to 400 (≈ ±10 % of the axis range), sends one step, then a hold frame — and repeats
the hold in `finally` and on `Ctrl+C`. It never writes firmware-update or calibration
opcodes.

Expected result: a slow, small pan to the right (positive `amount`) and an immediate stop.

---

## 8. Android integration (`Smooth5sBleClient.kt`)

```
SERVICE  = 0000fee9-0000-1000-8000-00805f9b34fb
TX_CHAR  = d44bc439-abfd-45a2-b575-925416129600   WRITE_NO_RESPONSE
RX_CHAR  = d44bc439-abfd-45a2-b575-925416129601   NOTIFY
SCAN_NAME_PREFIX = "SMOOTH"
MFR_ID   = 0x0509
```

- Request `BLUETOOTH_SCAN` (`neverForLocation`) + `BLUETOOTH_CONNECT` at runtime.
- Subscribe to `RX_CHAR` before writing; telemetry starts immediately.
- Frames are 14–18 bytes, so they fit a default 23-byte MTU — no negotiation needed.
- Send at most ~10 Hz, and with `speed <= 30` for anything driven by tracking output.
- Always follow a movement frame with a hold frame (`value = 2048`) when tracking releases
  the subject; never leave the last step latched.
- Keep the gimbal module optional: if no `SMOOTH` peripheral is found, the camera and
  skeleton tracker must run exactly as before.

---

## 9. Artifacts

| File | Purpose |
|---|---|
| `tools/ble_scan.py` | bleak scan (parity with what Android will see) |
| `tools/cb_scan.py` | CoreBluetooth scan with advertisement dump |
| `tools/ble_state.py` | central-manager permission/state diagnostic |
| `tools/gatt_dump.py` | scan → connect → GATT tree + 5 s notify capture |
| `tools/gatt_connected.py` | **adopts the bonded system connection** and dumps GATT + notify |
| `tools/gatt_read.py` | reads all readable characteristics/descriptors |
| `tools/crc_probe.py` | brute-forces CRC variant/range against a frame |
| `test_gimbal_move.py` | offline self-test, hold-only probe, gated pan/tilt step |
