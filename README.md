# robot-arm-painter

Mac-based software that controls a low-cost **6DOF servo robot arm** to draw simple
artwork on paper with a marker, with a roadmap toward iPhone camera/LiDAR-assisted
painting on 3D objects.

> **Primary milestone:** make the robot draw a square with a marker on paper.

See [initial_plan.md](initial_plan.md) for the full phased plan.

## Status

Scaffolding in place. The control stack runs today against a **mock serial backend**
(no hardware required), so you can exercise the jog CLI and drawing apps in simulation
before the arm is wired up.

## Quick start

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

# Manual jog CLI (mock backend, no hardware needed)
painterbot-jog --mock
# or: python -m painterbot.apps.manual_jog --mock

# Simulate drawing a square (writes a preview PNG, no hardware needed)
painterbot-draw-shape --shape square --mock --preview out/square.png
```

When real hardware is connected, drop `--mock` and pass the serial port:

```bash
painterbot-jog --port /dev/tty.usbserial-XXXX
```

## Layout

```text
configs/     YAML config (arm limits, workspace, iphone) — see *.default.yaml
src/painterbot/
  control/     serial + servo + arm kinematics
  drawing/     SVG loading, path sampling, stroke planning
  calibration/ workspace homography (Phase 7)
  iphone/      photo + LiDAR scan import (Phase 7-8)
  apps/        CLI entrypoints
docs/        setup, calibration, coordinate systems, milestones
hardware/    3D-printable marker holder mount
tests/
```

## Safety

- Servos never move outside the configured safe ranges in `configs/arm.default.yaml`.
- Every command is logged.
- Motion starts slow. `stop` (and Ctrl-C) halt the arm.
- See [docs/setup_mac.md](docs/setup_mac.md) for the emergency power-off procedure.
