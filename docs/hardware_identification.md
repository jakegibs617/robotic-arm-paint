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

- USB-serial chip: CH34x family — _verify on arrival_ with
  `system_profiler SPUSBDataType`
- Driver needed on macOS? Recent macOS ships a built-in CH34x driver; install
  the WCH vendor driver only if no `/dev/tty.*` device appears when plugged in.

## Serial connection

- Device path: _verify on arrival_ — expect `/dev/tty.usbserial-*` or
  `/dev/tty.wchusbserial*` (`ls /dev/tty.*usb*`)
- Baud rate: **1,000,000** (STS3215 factory default; config is set to match)
- Wire protocol: `sts3215` (Feetech STS framing — `0xFF 0xFF` packets,
  little-endian registers, 4096 counts / 360°). Implemented in
  `src/painterbot/control/serial_controller.py`, **unverified against hardware**.

> Once the port is known, set `serial.port` in `configs/arm.default.yaml`
> (protocol and baud are already set).

## Bring-up checklist (do in order, one servo at a time)

1. **Power**: the servos need an external supply into the FE-URT-2 power
   terminals — USB alone cannot drive them. 7.4V nominal (STS3215 range
   ~6–8.4V); budget ~1A idle-per-servo headroom, stall is ~2.7A each, so a
   7.4V supply rated ≥5A is comfortable for drawing loads.
2. **Assign servo IDs**: servos ship as ID 1. Connect **one servo at a time**
   and assign IDs **0–5 matching the config `channel`** (0=base … 5=gripper)
   with:

   ```bash
   .venv/bin/python -m painterbot.apps.bringup assign-id --port /dev/tty.usbserial-XXXX --old-id 1 --new-id 0
   ```

   This does the EEPROM unlock → write ID → re-lock sequence
   (`control/id_assignment.py`, `PySerialBackend.assign_servo_id`) —
   **unverified against hardware** until the first session; Feetech's FD
   software (Windows) is the fallback if it doesn't work as expected.
3. **Ping each servo** at 1 Mbps and confirm position reads work:

   ```bash
   .venv/bin/python -m painterbot.apps.bringup ping --port /dev/tty.usbserial-XXXX
   ```

   (or `read` in the jog CLI for one servo at a time).
4. **Centering**: the STS3215 mid position is count 2048 = **180°** — the
   encoder range is 0–360°, so mount horns/brackets with the joint's neutral
   near 180°, and expect to re-center `home_deg` values around 180 rather
   than the placeholder 90.
5. Record safe ranges below, then copy into `configs/arm.default.yaml`.

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
