# Hardware identification (Phase 1)

Fill this in during hardware bring-up. It is the source of truth for the serial
connection and safe servo ranges that the configs depend on.

## Arm kit

- Model / kit name: _TODO_
- DOF: 6
- Servo type (e.g. MG996R, LX-16A serial bus servo): _TODO_

## Controller board

- Board: _TODO_ (e.g. Arduino Uno + servo shield, LeArm controller, ESP32)
- USB-serial chip: _TODO_ (FTDI / CH340 / CP210x / native USB)
- Driver needed on macOS? _TODO_

## Serial connection

- Device path: _TODO_ (`/dev/tty.usbserial-XXXX` or `/dev/tty.usbmodem-XXXX`)
- Baud rate: _TODO_ (config default 115200)
- Wire protocol: _TODO_

> Once known, update `configs/arm.default.yaml` (`serial.port`, `serial.baud`,
> `serial.protocol`).

## Safe servo ranges

Jog each joint slowly to its mechanical limits and record the safe software
range here, then copy into `configs/arm.default.yaml`.

| Joint        | Channel | Min° | Max° | Home° | Notes |
|--------------|---------|------|------|-------|-------|
| base         | 0       |      |      |       |       |
| shoulder     | 1       |      |      |       |       |
| elbow        | 2       |      |      |       |       |
| wrist_pitch  | 3       |      |      |       |       |
| wrist_roll   | 4       |      |      |       |       |
| gripper      | 5       |      |      |       |       |

## Emergency stop

- Power switch location: _TODO_
- See [setup_mac.md](setup_mac.md) for the full procedure.
