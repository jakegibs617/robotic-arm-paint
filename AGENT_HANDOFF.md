# Agent Handoff — painterbot (6DOF arm painter POC)

You are picking up a Mac-first Python project that controls a low-cost 6DOF servo
robot arm to draw on flat paper with a marker. The full roadmap is in
[initial_plan.md](initial_plan.md); this file is the current state + what to do next.

## TL;DR

The **entire software stack runs end-to-end today in mock mode** (no hardware).
You can plan a square/star/SVG, map it to servo poses, and "execute" it against an
in-memory mock serial backend that logs every command.

**Hardware is ordered (July 2026) and identified**: 6× Feetech **STS3215** serial
bus servos (7.4V, 19 kg·cm, 360° magnetic encoder with position feedback) plus an
**FE-URT-2** USB→TTL bus adapter — the Mac drives the servo bus directly; there is
no controller board. The `sts3215` wire protocol (write position, read position,
torque on/off) is implemented and unit-tested against known byte frames, but
**unverified on real hardware** until the parts arrive. What's missing is Phase 1
bring-up (IDs, power, safe ranges), real calibration poses, the arm frame, and the
marker holder. The MVP milestone — *robot draws a square on paper* — is blocked on
hardware arrival, not on more software.

Tests: `63 passed, 0 skipped` **when run via `.venv/bin/python -m pytest`**. Note:
`python` is shell-aliased to a pyenv interpreter that lacks this project's deps, so
always call the venv interpreter explicitly (see Setup gotcha below). homography
(`tests/test_calibration.py`), preview (`tests/test_preview.py`), the iphone stubs
(`tests/test_iphone.py`), the `--dry-run` summary (`tests/test_dry_run.py`), and the
sts3215 framing/feedback path (`tests/test_control.py`) now have coverage.

## How to orient yourself (do this first)

```bash
cd /Users/jacobgiberson/Desktop/robotic-arm
source .venv/bin/activate
python -m pytest -q                       # confirm baseline (53 passed, 0 skipped)
python -m painterbot.apps.draw_shape --shape square --dry-run   # counts + corner poses, no arm
python -m painterbot.apps.draw_shape --shape square --preview out/square.png --mock
python -m painterbot.apps.draw_shape --shape square --mock -v   # watch mock servo commands
```

Read in this order: [initial_plan.md](initial_plan.md) →
[src/painterbot/control/serial_controller.py](src/painterbot/control/serial_controller.py)
→ [src/painterbot/control/arm.py](src/painterbot/control/arm.py)
→ [src/painterbot/drawing/stroke_planner.py](src/painterbot/drawing/stroke_planner.py)
→ [docs/milestones.md](docs/milestones.md).

## Architecture (what exists)

The coordinate pipeline is: `SVG/shape → paper-mm strokes → fit_to_paper → bilinear
pose interpolation → per-servo limit check → serial command`. **There is no inverse
kinematics by design** — the MVP uses manual pose calibration (jog the arm to 4
corners + pen_up/pen_down, save those poses, interpolate between them).

| Area | File | Status |
|------|------|--------|
| Serial transport | [control/serial_controller.py](src/painterbot/control/serial_controller.py) | ✅ mock + pyserial backends; protocol registry (`mock` / `sts3215` / `ascii_servo` / `lx16a`). `sts3215` matches the ordered hardware and adds feedback (position read, torque on/off); **unverified on real hardware** |
| Servo (limits, invert) | [control/servo.py](src/painterbot/control/servo.py) | ✅ done |
| Arm facade (interp motion, stop/resume) | [control/arm.py](src/painterbot/control/arm.py) | ✅ done |
| Config models | [config.py](src/painterbot/config.py) | ✅ pydantic, YAML load/save |
| Geometry / resample / fit | [drawing/path_sampler.py](src/painterbot/drawing/path_sampler.py) | ✅ done |
| Built-in shapes | [drawing/shapes.py](src/painterbot/drawing/shapes.py) | ✅ line/square/circle/spiral/star |
| SVG loader | [drawing/svg_loader.py](src/painterbot/drawing/svg_loader.py) | ✅ via svgpathtools |
| Stroke planner (paper→pose, execute) | [drawing/stroke_planner.py](src/painterbot/drawing/stroke_planner.py) | ✅ bilinear, needs real poses |
| PNG preview | [drawing/preview.py](src/painterbot/drawing/preview.py) | ✅ done |
| Manual jog CLI | [apps/manual_jog.py](src/painterbot/apps/manual_jog.py) | ✅ REPL, save/load poses |
| draw_shape / draw_svg apps | [apps/](src/painterbot/apps/) | ✅ done (with `--preview`, `--mock`) |
| Homography (img px → paper mm) | [calibration/homography.py](src/painterbot/calibration/homography.py) | ◐ implemented, untested |
| Photo calibration UI | [apps/calibrate_workspace.py](src/painterbot/apps/calibrate_workspace.py) | ◐ OpenCV click UI, needs display |
| iPhone scan import | [iphone/import_scan.py](src/painterbot/iphone/import_scan.py) | ◐ stub, needs `[scan]` extras |
| Marker holder | [hardware/mounts/marker_holder/](hardware/mounts/marker_holder/) | ☐ README only, no STL/STEP |

## What is NOT done (the real gaps)

1. **Hardware verification of `sts3215`** — the framing (write Goal_Position 0x2A,
   read Present_Position 0x38, Torque_Enable 0x28; `0xFF 0xFF` header, little-endian,
   4096 counts/360°) is implemented from the Feetech memory map and unit-tested
   against expected byte frames, but has never touched a real servo. First hardware
   session: set `protocol: sts3215` + `serial.port` in
   [configs/arm.default.yaml](configs/arm.default.yaml) and verify against one servo.
2. **Phase 1 hardware bring-up** — parts ordered, not arrived. Serial port unknown;
   servo IDs must be assigned 0–5 (they ship as ID 1); safe per-joint min/max in the
   config are **guesses for a 0–180 hobby servo** — STS3215 is 0–360 with mid at 180,
   so expect to re-center. Checklist lives in
   [docs/hardware_identification.md](docs/hardware_identification.md).
3. **Real calibration poses** — `home`, `pen_up`, `pen_down`, `corner_bl/br/tl/tr`
   are unset. The planner raises a clear error until they're captured and saved to
   `configs/workspace.calibrated.yaml`. With STS3215 feedback the fast path is
   hand-guided capture in the jog CLI: `torque off` → move by hand → `read` →
   `save <name>` (see [docs/calibration.md](docs/calibration.md)).
4. **Arm frame + marker holder** — no frame in the order yet (servos + adapter only);
   marker holder has no `.stl`/`.step`, only a README.
5. **Test coverage gaps** — no tests for `calibrate_workspace` (needs an OpenCV
   display/click UI). `homography`, `preview`, the `iphone/*` error paths, the
   `--dry-run` summary, and serial transport (encoders, sts3215 feedback round-trip,
   fake-serial) are covered. `test_svg_loader` skips only if svgpathtools is missing
   from the active interpreter.

## Recommended next task for you

Pick based on whether hardware is physically available:

### If NO hardware yet (software-only, do these now)
These harden the stack so the first hardware session goes smoothly:
- ✅ **DONE — serial protocol scaffold**: `open_backend` + `PySerialBackend` now
  select a wire encoder by name via a registry (`mock` / `ascii_servo` / `lx16a`),
  with `PySerialBackend` accepting an injectable `serial_obj` for testing. Covered by
  `tests/test_control.py`. Remaining work here is hardware-only: verify/replace the
  framing once the real board is identified (Phase 1).
- ✅ **DONE — test coverage**: `calibration/homography.py` (`test_calibration.py`),
  `drawing/preview.py` (`test_preview.py`), and the iphone stubs' error paths
  (`test_iphone.py`) are covered. svgpathtools tests no longer skip (deps installed).
- ✅ **DONE — `--dry-run` summary**: both `draw_shape` and `draw_svg` accept
  `--dry-run`, printing stroke/point counts, drawing bounds, and the corner poses
  (or a "not calibrated" notice) with no arm connection. Helper:
  `summarize_drawing` in `stroke_planner.py`; covered by `test_dry_run.py`.
- ✅ **DONE — sts3215 protocol + feedback**: `sts3215` encoder in the registry,
  plus a `FeedbackProtocol` layer (position read / torque on-off) surfaced as
  `Arm.read_pose` / `sync_from_hardware` / `set_torque` and jog-CLI `read` /
  `torque on|off` for hand-guided calibration. Byte-level tests in
  `tests/test_control.py`.
- Remaining software-only ideas: a small servo-ID assignment/ping CLI for
  bring-up day (scan the bus, set IDs 0–5, verify), a test for
  `apps/calibrate_workspace` (needs a headless way to drive the OpenCV click
  UI), and richer SVG fixtures.

### If hardware IS available (the MVP critical path)
Hardware is STS3215 servos + FE-URT-2 adapter; follow the bring-up checklist in
[docs/hardware_identification.md](docs/hardware_identification.md):
1. Wire external 7.4V power into the FE-URT-2; find the serial device
   (`ls /dev/tty.*usb*`); record it in the doc and config.
2. Assign servo IDs 0–5 (= config channels) **one servo at a time** — they ship
   as ID 1.
3. Set `protocol: sts3215` and `serial.port` in
   [configs/arm.default.yaml](configs/arm.default.yaml); verify a position `read`
   and a small move on one servo, then all six.
4. Tighten safe min/max to measured values (STS range is 0–360, mid 2048 = 180°).
5. Capture the 7 calibration poses hands-on: `torque off` → move by hand → `read`
   → `save <name>`; then `save-config` to `configs/workspace.calibrated.yaml`.
6. Run `draw_shape --shape square` (no `--mock`) and iterate until the square is clean.

## Setup gotchas

- **Use `.venv/bin/python`, not `python`.** In this shell `python` is aliased to a
  pyenv interpreter (`~/.pyenv/.../3.11.6`) that lacks the project deps, so plain
  `python -m pytest` silently skips svgpathtools/cv2/pyserial tests. Run the suite as
  `.venv/bin/python -m pytest -q`.
- The `.venv` now has the core deps installed (`opencv-python`, `svgpathtools`,
  `pyserial`, `matplotlib`, etc.). For iPhone LiDAR work also run
  `.venv/bin/pip install -e ".[scan]"`. Optional deps are lazy-imported, so missing
  ones only fail at the relevant call site.
- `configs/workspace.calibrated.yaml` is auto-preferred over `workspace.default.yaml`
  when present (see `load_workspace_config`). Captured poses + photo calibration land there.
- `out/` already contains `square.png` / `star.png` preview renders.
- Everything is mock-safe: pass `--mock` to any app to run without hardware.

## Constraints (from the plan — do not violate)

- No Raspberry Pi, no RealSense, no ROS, no custom iOS app for the MVP.
- Never command a servo outside its configured safe range (the `Servo` class enforces
  this; keep it that way — `clamp=True` only for interactive jogging, never path exec).
- Prefer manual pose calibration over inverse kinematics for the MVP.
- Start motion slow; keep `stop()`/emergency-stop working.
- First demo is flat 2D drawing. Do **not** start 3D object painting (Phase 9).

## Verify your work

```bash
python -m pytest -q                                    # keep green
python -m painterbot.apps.draw_svg examples/star.svg --preview out/star.png --mock
python -m painterbot.apps.manual_jog --mock            # exercise the REPL
```
