# Agent Handoff — painterbot (6DOF arm painter POC)

You are picking up a Mac-first Python project that controls a low-cost 6DOF servo
robot arm to draw on flat paper with a marker. The full roadmap is in
[initial_plan.md](initial_plan.md); this file is the current state + what to do next.

## TL;DR

The **entire software stack runs end-to-end today in mock mode** (no hardware).
You can plan a square/star/SVG, map it to servo poses, and "execute" it against an
in-memory mock serial backend that logs every command. What's missing is
everything that touches **real hardware**: the actual serial wire protocol, real
calibration poses, and the marker holder. The MVP milestone — *robot draws a
square on paper* — is blocked on Phase 1 hardware bring-up, not on more software.

Tests: `53 passed, 0 skipped` **when run via `.venv/bin/python -m pytest`**. Note:
`python` is shell-aliased to a pyenv interpreter that lacks this project's deps, so
always call the venv interpreter explicitly (see Setup gotcha below). homography
(`tests/test_calibration.py`), preview (`tests/test_preview.py`), the iphone stubs
(`tests/test_iphone.py`), and the `--dry-run` summary (`tests/test_dry_run.py`) now
have coverage.

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
| Serial transport | [control/serial_controller.py](src/painterbot/control/serial_controller.py) | ✅ mock + pyserial backends; pluggable protocol registry (`mock` / `ascii_servo` placeholder / `lx16a`). Real wire framing still **unverified** until the board is identified |
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

1. **Real serial protocol** — the transport now has a pluggable encoder registry
   (`register_protocol` / `get_encoder` in `serial_controller.py`) with `mock`,
   `ascii_servo` (placeholder `S <ch> <angle>\n`), and `lx16a` (LX-16A bus-servo
   binary framing) built in. **None of the real framings are verified against
   hardware** — baud/handshake and whether the board even speaks LX-16A are unknown
   until it's identified. Once known, register the board-specific encoder (a
   one-liner) and set `protocol:` in [configs/arm.default.yaml](configs/arm.default.yaml).
2. **Phase 1 hardware bring-up** — board not identified, serial port unknown, safe
   per-joint min/max angles are **guesses** in the config. [docs/hardware_identification.md](docs/hardware_identification.md)
   is an empty template to fill in.
3. **Real calibration poses** — `home`, `pen_up`, `pen_down`, `corner_bl/br/tl/tr`
   are unset. The planner raises a clear error until they're captured via the jog CLI
   on real hardware and saved to `configs/workspace.calibrated.yaml`.
4. **Marker holder** — no `.stl`/`.step`, only a README.
5. **Test coverage gaps** — no tests for `calibrate_workspace` (needs an OpenCV
   display/click UI). `homography`, `preview`, the `iphone/*` error paths, the
   `--dry-run` summary, and serial transport (encoders + fake-serial round-trip) are
   now covered. `test_svg_loader` skips only if svgpathtools is missing from the
   active interpreter.

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
- Remaining software-only ideas: a test for `apps/calibrate_workspace` (needs a
  headless way to drive the OpenCV click UI), and richer SVG fixtures.

### If hardware IS available (the MVP critical path)
Follow [initial_plan.md](initial_plan.md) Phases 1→5 in order:
1. Identify the controller board; find the serial device
   (`ls /dev/tty.usb*`); fill in [docs/hardware_identification.md](docs/hardware_identification.md).
2. Pick/register the **real serial protocol** (try `lx16a` if the arm uses LX-16A
   bus servos, else `register_protocol` the board's framing); set `protocol:` in the
   config, then move one servo, then all servos.
3. Tighten safe min/max in [configs/arm.default.yaml](configs/arm.default.yaml) to
   measured values.
4. Jog to and `save` the 7 calibration poses; `save-config` to
   `configs/workspace.calibrated.yaml`.
5. Run `draw_shape --shape square` (no `--mock`) and iterate until the square is clean.

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
