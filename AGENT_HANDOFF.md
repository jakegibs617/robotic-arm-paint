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

Tests should be run via **`.venv/bin/python -m pytest`**. Note:
`python` is shell-aliased to a pyenv interpreter that lacks this project's deps, so
always call the venv interpreter explicitly (see [docs/verification.md](docs/verification.md)
and Setup gotcha below). Homography (`tests/test_calibration.py`), preview
(`tests/test_preview.py`), the iphone stubs (`tests/test_iphone.py`), the
`--dry-run` summary (`tests/test_dry_run.py`), the sts3215 framing/feedback path
(`tests/test_control.py`), and servo-ID (re)assignment (`tests/test_id_assignment.py`)
all have coverage — 138 tests pass as of this writing (`.venv/bin/python -m pytest -q`).

## How to orient yourself (do this first)

```bash
cd /Users/jacobgiberson/Desktop/robotic-arm
source .venv/bin/activate
.venv/bin/python -m pytest -q             # confirm baseline
python -m painterbot.apps.draw_shape --shape square --dry-run   # counts + corner poses, no arm
python -m painterbot.apps.draw_shape --shape square --preview out/square.png --mock
python -m painterbot.apps.draw_shape --shape square --mock -v   # watch mock servo commands
```

Read in this order: [initial_plan.md](initial_plan.md) →
[src/painterbot/control/serial_controller.py](src/painterbot/control/serial_controller.py)
→ [src/painterbot/control/arm.py](src/painterbot/control/arm.py)
→ [src/painterbot/drawing/stroke_planner.py](src/painterbot/drawing/stroke_planner.py)
→ [docs/milestones.md](docs/milestones.md)
→ [docs/technical_analysis_oo_design.md](docs/technical_analysis_oo_design.md) (design forces + near-term refactor timing).

Two machine-trackable trackers are the source of truth for granular status — check
these before re-deriving status from prose: [docs/software_frontload_tasks.json](docs/software_frontload_tasks.json)
(completed/pending software tasks with acceptance criteria + evidence) and
[docs/hardware_bringup_checklist.json](docs/hardware_bringup_checklist.json) (the
first-hardware-session checklist, item-by-item). [docs/product_growth_prd.md](docs/product_growth_prd.md)
has the longer-term product framing if useful.

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
| Homography (img px → paper mm) | [calibration/homography.py](src/painterbot/calibration/homography.py) | ✅ implemented + tested (`test_calibration.py`) |
| Photo calibration UI | [apps/calibrate_workspace.py](src/painterbot/apps/calibrate_workspace.py) | ✅ OpenCV click UI; corner-order/homography/persistence logic split out and headlessly tested (`test_calibration_app_headless.py`); the click loop itself still needs a display |
| iPhone scan import | [iphone/import_scan.py](src/painterbot/iphone/import_scan.py) | ✅ safe mesh/scan summary (`MeshSummary`), lazy-loaded extras, error paths tested (`test_iphone.py`) |
| Marker holder | [hardware/mounts/marker_holder/](hardware/mounts/marker_holder/) | ☐ README only, no STL/STEP |
| Bring-up CLI | [apps/bringup.py](src/painterbot/apps/bringup.py) | ✅ `list-joints` / `protocols` / `mock-session` (mock-safe) plus `ping` / `assign-id`, which open a real connection when `--port` is given |
| Servo ping/read preflight | [control/preflight.py](src/painterbot/control/preflight.py) | ✅ `read_servo_preflight` classifies no-reply/wrong-ID/bad-checksum/success without writing; wired into `bringup ping` |
| Servo ID (re)assignment | [control/id_assignment.py](src/painterbot/control/id_assignment.py) | ✅ EEPROM unlock → write ID → re-lock sequence (`PySerialBackend.assign_servo_id`), wired into `bringup assign-id`; byte-level tests pass but **unverified on real hardware** |
| Calibration session | [calibration/pose_calibration.py](src/painterbot/calibration/pose_calibration.py) | ✅ `CalibrationSession` tracks required poses, captures, validates ranges |
| Drawing preflight plan | [drawing/plan.py](src/painterbot/drawing/plan.py) | ✅ `DrawingPlan` unifies dry-run/preview/execution bounds, counts, `validate_for_execution` |
| Fake STS3215 harness | [testing/fake_sts3215.py](src/painterbot/testing/fake_sts3215.py) | ✅ reusable fake serial: multi-ID replies, short/checksum/wrong-ID/stale-packet simulation |

## What is NOT done (the real gaps)

1. **Hardware verification of `sts3215`** — the framing (write Goal_Position 0x2A,
   read Present_Position 0x38, Torque_Enable 0x28; `0xFF 0xFF` header, little-endian,
   4096 counts/360°) is implemented from the Feetech memory map and unit-tested
   against expected byte frames, but has never touched a real servo. First hardware
   session: set `protocol: sts3215` + `serial.port` in
   [configs/arm.default.yaml](configs/arm.default.yaml) and verify against one servo.
2. **Phase 1 hardware bring-up** — parts ordered, not arrived. Serial port unknown;
   servo IDs must be assigned 0–5 (they ship as ID 1) — `bringup assign-id` now
   implements this, but it is **unverified against a real servo**; safe per-joint
   min/max in the config are **guesses for a 0–180 hobby servo** — STS3215 is 0–360
   with mid at 180, so expect to re-center. Checklist lives in
   [docs/hardware_identification.md](docs/hardware_identification.md).
3. **Real calibration poses** — `home`, `pen_up`, `pen_down`, `corner_bl/br/tl/tr`
   are unset. The planner raises a clear error until they're captured and saved to
   `configs/workspace.calibrated.yaml`. With STS3215 feedback the fast path is
   hand-guided capture in the jog CLI: `torque off` → move by hand → `read` →
   `save <name>` (see [docs/calibration.md](docs/calibration.md)).
4. **Arm frame + marker holder** — no frame in the order yet (servos + adapter only);
   marker holder has no `.stl`/`.step`, only a README.
5. **Test coverage** — `homography`, `preview`, the `iphone/*` error paths, the
   `--dry-run` summary, `calibrate_workspace`'s corner/homography/persistence logic
   (headlessly), calibration sessions, drawing preflight, and serial transport
   (encoders, sts3215 feedback round-trip, fake-serial) are all covered — see
   `docs/software_frontload_tasks.json` (SW-001..SW-015, all done) for the itemized
   list. `test_svg_loader` skips only if svgpathtools is missing from the active
   interpreter. What's still genuinely untested is real-hardware behavior, since
   nothing here has touched a physical servo.

## Hill chart — known vs. unknown

Basecamp's hill chart convention: **uphill = unknown** (we haven't figured out the
approach yet, real chance of surprises) vs. **downhill = known** (the approach is
settled — what's left is just doing the work). This re-sorts every open item above
and in "Recommended next task" by that lens instead of by file/area, so the next
agent can tell "well-understood backlog" apart from "actual risk" at a glance.

### Uphill — unknown (approach unproven, could surprise us)

- **STS3215 wire protocol on real hardware** — framing is implemented from the
  datasheet only; ack/timing/retry/torque behavior has never touched a real servo
  (gap 1 above).
- **Servo-ID assignment over the bus** — `bringup assign-id` implements the
  unlock/write-ID/re-lock sequence and it's byte-level tested, but whether that
  EEPROM sequence actually works against a real STS3215 (register addresses,
  timing, ack handling) is unresolved until the first hardware session
  (`docs/hardware_identification.md` step 2). Feetech's Windows FD tool is the
  fallback if it doesn't.
- **Marker holder design** — README only, no STL/STEP; the compliance mechanism
  (foam/spring/flexible clamp) and tip-height adjustment haven't been designed,
  only specified as requirements (gap 4 above).
- **Arm frame** — not even ordered; no mount/frame design exists yet (gap 4 above).
- **First-square drawing quality** — depends on two unproven things at once: marker
  holder compliance/tip pressure, and whether bilinear pose interpolation holds up
  outside small test areas. Both are named as key risks in
  `docs/product_growth_prd.md` ("Marker holder compliance and tip pressure may
  dominate drawing quality"; "Bilinear interpolation may be insufficient for larger
  paper areas or nonlinear arm geometry").

### Downhill — known (approach settled, just execution)

- **Serial port / driver discovery** — standard `ls /dev/tty.*usb*` + CH34x driver
  check, fully documented in `docs/hardware_identification.md`.
- **Safe per-joint range measurement** — the *how* is fully specified (jog to
  mechanical limit, record, copy into config); only the numbers are pending
  hardware (gap 2 above).
- **Real calibration pose capture** — hand-guided procedure is fully documented
  end-to-end (`torque off` → move → `read` → `save`) in `docs/calibration.md`
  (gap 3 above).
- **Richer SVG fixtures** — mechanical addition of more test fixtures, no open
  questions.

(Wiring `control/preflight.py` into `apps/bringup.py` was in this list — done as
of SW-016, see below.)

## Recommended next task for you

Pick based on whether hardware is physically available:

### If NO hardware yet (software-only, do these now)
`docs/software_frontload_tasks.json` (SW-001..SW-015) plus SW-016 (this session)
cover the full backlog that was frontloaded here: serial protocol scaffold,
sts3215 protocol + feedback, `--dry-run` summary, fake STS3215 harness, servo
ping/read preflight (now wired into `bringup ping`), servo-ID assignment (`bringup
assign-id`, `control/id_assignment.py`), `CalibrationSession`, `DrawingPlan` +
preflight safety checks, expanded SVG fixtures, preview regression tests, headless
calibration UI tests, workspace pose validation, mock-session transcript, the
hardware checklist JSON, verification docs, and safe scan-import summaries. Check
that file for acceptance criteria and evidence per task before assuming something
is still open.

What's genuinely still open, software-only:
- Richer SVG fixtures beyond what SW-008 added, if new artwork patterns show gaps.
- Everything else remaining is hardware-bound (see the hill chart above) — the
  next real milestone is the first physical hardware session, not more software.

### If hardware IS available (the MVP critical path)
Hardware is STS3215 servos + FE-URT-2 adapter; follow the bring-up checklist in
[docs/hardware_identification.md](docs/hardware_identification.md):
1. Wire external 7.4V power into the FE-URT-2; find the serial device
   (`ls /dev/tty.*usb*`); record it in the doc and config.
2. Assign servo IDs 0–5 (= config channels) **one servo at a time** — they ship
   as ID 1. Try `bringup assign-id --port ... --old-id 1 --new-id 0` (unverified
   on hardware; fall back to Feetech's FD software if it doesn't work).
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
.venv/bin/python -m pytest -q
.venv/bin/python -m painterbot.apps.draw_svg examples/star.svg --preview out/star.png
.venv/bin/python -m painterbot.apps.bringup mock-session
```

See [docs/verification.md](docs/verification.md) for the full local checklist,
including no-hardware dry-run and preview commands plus optional scan extras.
