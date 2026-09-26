# Hardware identification (Phase 1)

Source of truth for the serial connection and safe servo ranges that the
configs depend on. Items marked _verify on arrival_ are from the order /
datasheets, not yet confirmed against the physical parts.

## Arm kit

- Model / kit name: custom build (frame TBD — servos + bus adapter ordered 2026-07)
- DOF: 6
- Servo type: **Feetech STS3215** serial bus servo ×6 (RCmall 6-pack, 7.4V,
  19 kg·cm, TTL bus, 360° magnetic encoder, position feedback, dual shaft)

## Controller board

There is no controller board: the Mac talks to the servo TTL bus directly
through a **FE-URT-2 USB serial bus servo adapter** (Feetech SMS/SCS/STS
family). The Python stack is the controller.

- USB-serial chip: **WCH CH343/CH9102** — VID `0x1A86`, PID `0x55D3`, product
  string "USB Single Serial". ✅ **measured 2026-09-26**. The earlier guess of
  "CH34x, expect `/dev/tty.usbserial-*`" was wrong: this is the CDC-ACM-class
  part, not a CH340.
- Driver needed on macOS? **No.** macOS drives it with its built-in CDC-ACM
  driver, which is why it enumerates as `usbmodem` rather than `usbserial`. No
  WCH vendor driver is installed on this machine.

Find it with `bringup ports`, which flags the candidate rather than making you
grep `/dev`:

```bash
.venv/bin/python -m painterbot.apps.bringup ports
#   /dev/cu.usbmodem5B790320481  1a86:55d3  USB Single Serial [WCH CH34x/CH343/CH9102] <- likely servo adapter
```

## Serial connection

- Device path: **`/dev/cu.usbmodem5B790320481`** ✅ measured 2026-09-26.
  (The trailing digits are this adapter's USB serial number, so the path is
  stable for this unit but will differ on another one — re-run `bringup ports`.)
- **Use the `/dev/cu.*` node, never `/dev/tty.*`.** The `tty` node blocks on
  open waiting for carrier detect, which a USB-serial bridge has no reason to
  assert.
- Baud rate: **1,000,000** ✅ confirmed working. On macOS this is not a POSIX
  rate, so pyserial applies it through the `IOSSIOSPEED` ioctl; that path works
  here. A rate the OS refuses is reported by `scan --baud-sweep` as a refused
  attempt rather than crashing the sweep.
- Wire protocol: `sts3215` (Feetech STS framing — `0xFF 0xFF` packets,
  little-endian registers, 4096 counts / 360°). Implemented in
  `src/painterbot/control/serial_controller.py`. ✅ **The read path is now
  verified against a physical servo** (PING, register reads, framing, checksums,
  little-endian decoding). The **write path is still unverified** — see below.
- Adapter echo: **none observed.** Some half-duplex adapters loop TX into RX,
  and an echoed request is itself a well-formed frame that decodes to a
  plausible fake angle, so `PySerialBackend` rejects a reply identical to its
  request (`ServoEchoError`). This adapter does not echo.

> `configs/arm.default.yaml` still ships `protocol: mock` on purpose, so no app
> goes looking for hardware by default. Pass `--protocol sts3215 --port …`
> explicitly. Giving a `--port` while the protocol is `mock` is now a hard
> error rather than a silent no-op.

## What one physical servo reported (2026-09-26)

Bench state: one STS3215 on the adapter, **USB power only — no 7.4 V on the
screw terminal.**

| Field | Value | Notes |
|---|---|---|
| Bus ID | **1** | factory default, as expected |
| Baud | 1,000,000 | factory default, as expected |
| Model number | **777** | `MODEL_L`=9, `MODEL_H`=3 → 9 + 3·256. Confirms STS3215 |
| Firmware | **3.10** | |
| Angle limits | **0..4095 counts** | factory default = full 360°, not a restricted range |
| Present position | 4093 counts (359.7°) | stable across repeated reads |
| Present voltage | **4.3 V** | ⚠️ below the 6–8.4 V spec — see below |
| Present temperature | 26 °C | |
| Error flags | 0x00 | notably *not* an under-voltage flag at 4.3 V |
| Torque enable (0x28) | **0** | limp at rest. Any stiffness by hand is the 1:345 gearbox, not holding force |
| Goal position (0x2a) | **0** | ⚠️ stale factory value while the servo sits at 4094 — see below |
| Response status level (0x08) | **1** | the servo **acks every write**; reads must flush first |
| Voltage protection (0x0f/0x0e) | **4.0 – 8.0 V** | why it boots on USB at all. ⚠️ **8.0 V, not 8.4** |
| Temperature limit (0x0d) | 70 °C | |
| Operating mode (0x21) | 0 | position mode, not wheel mode |
| Max torque limit (0x10) | 1000 | 100% |
| Speed / load / current | 0 / 0 / 0 | idle, consistent with torque off |

### ⚠️ A fully charged 2S LiPo exceeds this servo's own voltage limit

The servo's max-voltage protection register reads **8.0 V**. A 2S LiPo straight
off the charger is **8.4 V**. Use a bench supply set to 7.4 V, or a LiPo that has
been run down a little — and check `identify` reports a voltage inside 4.0–8.0 V
before doing anything else.

### ⚠️ Enabling torque with a stale goal is a full-turn slam

The bench servo sat at **4094 counts with `Goal_Position` still 0** — the factory
default, never overwritten. Enabling torque in that state tells the servo to
travel nearly a full turn to reach 0, immediately, at whatever speed it can
manage. On a mounted arm that is a collision.

`motion_probe.nudge_servo` therefore overwrites `Goal_Position` with the servo's
*current* position while it is still limp, and only then enables torque. Anything
else that enables torque — the jog CLI, `Arm.set_torque` — has the same hazard and
has **not** been audited for it yet.

### Surprise: this FE-URT-2 passes USB 5 V to the servo bus

This contradicts the assumption written into the earlier plan. It is an
observation about *this* adapter and servo, not a general truth about the
FE-URT-2 family — but the mechanism is clear enough: the servo's own
under-voltage protection is set to 4.0 V, so 4.3 V clears it. The logic runs and
answers fully at 4.3 V with USB alone — so a silent bus is **not** the expected result of a missing
supply, and "it answered" does **not** mean the supply is adequate. Always read
the voltage: 4.3 V means USB-only.

**Do not command motion at this voltage.** Under-voltage is the worst condition
in which to first exercise torque enable, goal position, or an EEPROM write: a
brownout mid-write is how a servo ends up with a corrupted ID. Wire 7.4 V
(≥5 A) into the screw terminal, confirm `identify` reports ~7.4 V, and only
then run `nudge`.

## Bring-up checklist (do in order, one servo at a time)

0. **Find the adapter**: `bringup ports`. Record the `/dev/cu.*` device.
1. **Scan before you trust the config**: `bringup scan` tells you which IDs are
   actually on the bus, which is not the same question as `bringup ping`
   ("are the six joints my config expects alive?"). Scan first.

   ```bash
   P=/dev/cu.usbmodem5B790320481
   .venv/bin/python -m painterbot.apps.bringup --port $P --protocol sts3215 --baud 1000000 scan --ids 0-11
   .venv/bin/python -m painterbot.apps.bringup --port $P --protocol sts3215 identify --id 1
   ```

   If nothing answers, add `--baud-sweep` before suspecting the wiring.
2. **Power**: the servos need an external supply into the FE-URT-2 power
   terminals for anything to *move* — USB drives the logic but not the motor.
   7.4 V nominal (STS3215 range ~6–8.4 V); budget ~1 A idle-per-servo headroom,
   stall is ~2.7 A each, so a 7.4 V supply rated ≥5 A is comfortable for
   drawing loads. Confirm with `identify` that the reported voltage is ~7.4 V,
   not 4.3 V.
3. **Prove the write path with the smallest possible move**, once powered.
   Start with a zero delta — it exercises torque enable and the read-back with
   nothing commanded to move — then a real one. The delta is hard-capped at 200
   counts (~17.6°) so a typo cannot swing a mounted arm.

   ```bash
   .venv/bin/python -m painterbot.apps.bringup --port $P --protocol sts3215 nudge --id 1 --counts 0
   .venv/bin/python -m painterbot.apps.bringup --port $P --protocol sts3215 nudge --id 1 --counts 57
   .venv/bin/python -m painterbot.apps.bringup --port $P --protocol sts3215 nudge --id 1 --counts -57
   ```

   Record the achieved delta and its **sign** — that is the counts-to-motion
   mapping, and nothing else in the repo knows it yet.
4. **Assign servo IDs**: servos ship as ID 1. Connect **one servo at a time**
   and assign IDs **0–5 matching the config `channel`** (0=base … 5=gripper)
   with:

   ```bash
   .venv/bin/python -m painterbot.apps.bringup --port $P --protocol sts3215 assign-id --old-id 1 --new-id 0
   ```

   This does the EEPROM unlock → write ID → re-lock sequence
   (`control/id_assignment.py`, `PySerialBackend.assign_servo_id`) —
   **unverified against hardware** until the first session; Feetech's FD
   software (Windows) is the fallback if it doesn't work as expected. Always
   confirm with `bringup scan --ids 0-11` afterwards, since the assignment does
   not read itself back. **Never do this under-voltage.**

## Bring-up checklist (do in order, one servo at a time)

5. **Ping the configured joints** once IDs are assigned:

   ```bash
   .venv/bin/python -m painterbot.apps.bringup --port $P --protocol sts3215 ping
   ```

   (or `read` in the jog CLI for one servo at a time).
6. **Centering**: the STS3215 mid position is count 2048 = **180°** — the
   encoder range is 0–360°, so mount horns/brackets with the joint's neutral
   near 180°, and expect to re-center `home_deg` values around 180 rather
   than the placeholder 90.
7. Record safe ranges below, then copy into `configs/arm.default.yaml`.

Because the STS3215 has position feedback, calibration poses can be captured
hands-on: in the jog CLI run `torque off`, move the arm by hand, `read`, then
`save <pose>` (see `docs/calibration.md`).

## Safe servo ranges

Jog each joint slowly to its mechanical limits and record the safe software
range here, then copy into `configs/arm.default.yaml`.

| Joint        | Channel/ID | Min° | Max° | Home° | Notes |
|--------------|------------|------|------|-------|-------|
| base         | 0          |      |      |       |       |
| shoulder     | 1          |      |      |       |       |
| elbow        | 2          |      |      |       |       |
| wrist_pitch  | 3          |      |      |       |       |
| wrist_roll   | 4          |      |      |       |       |
| gripper      | 5          |      |      |       |       |

## Emergency stop

- Power switch location: _TODO_ (put a switch on the 7.4V supply line)
- See [setup_mac.md](setup_mac.md) for the full procedure.

## Fallback path (not the plan)

The repo keeps an Arduino PWM-servo bridge sketch
(`hardware/firmware/arduino_ascii_servo_bridge/`, `ascii_servo` protocol) from
before the hardware was chosen. It only applies if the build ever switches to
hobby PWM servos; with STS3215 bus servos it is unused.
