# Verification

Use the project virtualenv explicitly. In this workspace, plain `python` may
resolve to a pyenv interpreter without the project dependencies.

## Local Test Suite

```bash
.venv/bin/python -m pytest -q
```

## No-Hardware Smoke Checks

```bash
.venv/bin/python -m painterbot.apps.bringup list-joints
.venv/bin/python -m painterbot.apps.bringup mock-session
.venv/bin/python -m painterbot.apps.bringup ports
.venv/bin/python -m painterbot.apps.bringup --mock scan --ids 0-5
.venv/bin/python -m painterbot.apps.bringup --mock --mock-empty-bus scan --ids 0-5
.venv/bin/python -m painterbot.apps.bringup --mock identify --id 1
.venv/bin/python -m painterbot.apps.bringup --mock nudge --id 1 --counts 57
.venv/bin/python -m painterbot.apps.calibrate_workspace --dry-run
.venv/bin/python -m painterbot.apps.draw_shape --shape square --dry-run
.venv/bin/python -m painterbot.apps.draw_shape --shape square --preview out/square.png
.venv/bin/python -m painterbot.apps.draw_svg examples/star.svg --dry-run
.venv/bin/python -m painterbot.apps.draw_svg examples/star.svg --preview out/star.png
```

`ports` only enumerates devices; it opens nothing. The `--mock` probing commands
run the real `sts3215` encoders and parsers against an in-memory fake port, so
they exercise the wire protocol end to end without hardware. `--mock-empty-bus`
simulates a bus where nothing answers and exits 1.

## Hardware (powered)

Needs 7.4 V (>=5 A) on the FE-URT-2 screw terminal. Confirm `identify` reports
~7.4 V, not 4.3 V, before commanding any motion — USB alone powers the servo's
logic but not its motor.

```bash
P=/dev/cu.usbmodem5B790320481          # from `bringup ports`
B=".venv/bin/python -m painterbot.apps.bringup --port $P --protocol sts3215"
$B scan --ids 0-11                     # expect one servo at factory ID 1
$B identify --id 1                     # model 777, firmware 3.10, ~7.4V
$B nudge --id 1 --counts 0             # torque + read path, nothing moves
$B nudge --id 1 --counts 57            # ~5 deg; record the achieved delta and sign
```

All commands in the first block are hardware-safe. They do not require a serial port and do
not modify real calibration configs.

## Optional Scan Extras

iPhone LiDAR / mesh import work is optional and uses the `scan` extra:

```bash
.venv/bin/python -m pip install -e ".[scan]"
```

Run scan-specific checks only after those extras are installed.
