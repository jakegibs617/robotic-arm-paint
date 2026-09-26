# Agent Handoff — painterbot (6DOF arm painter POC)

You are picking up a Mac-first Python project that controls a low-cost 6DOF servo
robot arm to draw on flat paper with a marker. The full roadmap is in
[initial_plan.md](initial_plan.md); this file is the current state + what to do next.

## TL;DR

The **entire software stack runs end-to-end today in mock mode** (no hardware).
You can plan a square/star/SVG, map it to servo poses, and "execute" it against an
in-memory mock serial backend that logs every command.

**Hardware has arrived and one servo is on the bench**: Feetech **STS3215**
serial bus servos (7.4V, 1:345, 19 kg·cm, 360° magnetic encoder with position
feedback) plus an **FE-URT-2** USB→TTL bus adapter — the Mac drives the servo bus
directly; there is no controller board. As of SW-017 the `sts3215` **read** path
is **verified against a physical servo** (ping, register reads, framing,
checksums, little-endian decode, 1 Mbps on macOS CDC-ACM). The **write** path —
torque, goal position, the counts-to-motion mapping — is **still unverified**,
blocked on getting 7.4V onto the adapter's screw terminal. What's missing is Phase 1
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
all have coverage, as do bus scan/identification (`tests/test_bus_scan.py`),
the bounded motion probe (`tests/test_motion_probe.py`), register-level probing
(`tests/test_register_bus.py`) and port discovery (`tests/test_serial_link.py`)
— 239 tests pass as of this writing (`.venv/bin/python -m pytest -q`).

## Latest completed milestone: SW-017 — bus scan, identification, motion probe

- **PR**: [#6](https://github.com/jakegibs617/robotic-arm-paint/pull/6) (merged
  into `main` at `97b8831`).
- **What it did**: gave the repo a way to ask the bus *what is on it* rather
  than only checking whether the six IDs the config expects reply. Added
  register-level access to the `sts3215` protocol (`RegisterAccess`,
  `ServoRegister`), two narrow role interfaces (`ServoProbe` is read-only, so
  "a scan cannot move a servo" is a property of the types), `control/bus_scan.py`
  (identify / scan / baud sweep / ID-spec parsing), `control/motion_probe.py`
  (a hard-capped nudge in raw encoder counts), `control/serial_link.py` (port
  discovery), and four `bringup` subcommands: `ports`, `scan`, `identify`,
  `nudge`.
- **🔌 FIRST HARDWARE SESSION — the `sts3215` read path is now verified against
  a physical servo.** See the measured table in
  [docs/hardware_identification.md](docs/hardware_identification.md#what-one-physical-servo-reported-2026-09-26).
  Headlines: adapter is a **WCH CH343/CH9102** (`1a86:55d3`) at
  `/dev/cu.usbmodem5B790320481`, macOS built-in CDC-ACM, no driver — the docs'
  `CH34x` / `/dev/tty.usbserial-*` expectation was wrong on both counts.
  Servo answers at **factory ID 1 / 1,000,000 baud**, **model 777**, firmware
  **3.10**, angle limits **0..4095**, no adapter echo. 1 Mbps applies correctly
  on macOS CDC-ACM.
- **Three hardware facts that changed the design**, all recorded in
  `docs/hardware_bringup_checklist.json`:
  1. **This FE-URT-2 passes USB 5V to the servo bus.** The servo runs and
     answers reads fully at 4.3V, so a silent bus is *not* the symptom of a
     missing supply, and "it answered" does *not* mean the supply is adequate.
     Read the voltage.
  2. **A goal write is not inert — it implicitly enables torque.** Writing a
     `Goal_Position` that *differs* from the present position energises the
     servo (0 → 1); writing one *equal* to it does not. Nothing can pre-stage a
     goal without committing to motion. `Servo.move_to` / `Arm.move_to_pose`
     therefore leave the servo energised regardless of `set_torque` — documented,
     **not yet fixed**.
  3. **The servo sits with a stale `Goal_Position` of 0** while parked at 4094
     counts. Enabling torque in that state is a near-full-turn slam. `nudge_servo`
     clears it by writing `goal = present` (the one goal write that cannot
     energise or move) before enabling torque.
  Also: the servo's own voltage protection window is **4.0–8.0 V** — note 8.0,
  not 8.4, so **a freshly charged 2S LiPo exceeds the servo's own limit**. Use a
  bench supply at 7.4 V.
- **Two latent bugs fixed**: the silent-mock trap (`--port` with `protocol: mock`
  quietly used the mock backend and reported six healthy servos), and adapter
  echo — an echoed 2-byte position read is a well-formed frame that decodes to
  568 counts = 49.9°, which `read_servo` would have handed to `Arm` as a real
  joint angle.
- **Tests run**: `.venv/bin/python -m pytest -q` — **239 passed** (up from 139).
  New: `test_bus_scan.py`, `test_motion_probe.py`, `test_register_bus.py`,
  `test_serial_link.py`.
- **Review**: a subagent reviewed PR #6 and posted findings on GitHub
  ([review](https://github.com/jakegibs617/robotic-arm-paint/pull/6#issuecomment-5848274028),
  [response](https://github.com/jakegibs617/robotic-arm-paint/pull/6#issuecomment-5848356843)).
  It caught a **serious false positive in the echo guard**: request and status
  frames share a shape, so a PING reply carrying error flag `0x01` is
  byte-identical to the PING request — and bit 0 of the STS error byte is
  **under-voltage**, exactly what this bench servo reports. The guard would have
  blamed the adapter for the one thing that was working, and aborted the whole
  scan. Echo is now decided once per link, by a 4-byte read whose 10-byte reply
  an 8-byte echo provably cannot fill. Also fixed: a raw `AttributeError` under
  the shipped default config, `nudge` exiting 0 with torque possibly enabled,
  `nudge_servo` raising despite documenting that it does not, and `nudge`
  leaving a live goal behind (the same hazard it was written to prevent).
- **Known limitations**: **the write path is entirely unverified.** The bench
  servo reads 4.3 V against a 6–8.4 V spec, so torque, goal position, and the
  sign/scale of the counts-to-motion mapping have never been exercised.
  `HW-MOTION-001` is `blocked` on 7.4 V. Deferred from the review, all agreed
  as real: collapse `FeedbackProtocol` into `RegisterAccess` (they describe one
  protocol twice); replace `preflight`'s substring-matching error classifier
  with typed exceptions and give it an `echo` status; propagate the
  implicit-torque finding into `Servo`/`Arm`; extract `_simulated_bus` into a
  factory.
- **Copy/paste prompt for the next session**:

  ```text
  Read AGENT_HANDOFF.md first. The sts3215 READ path is verified on hardware;
  the WRITE path is not, and is blocked on 7.4V (>=5A, bench supply -- NOT a
  freshly charged 2S LiPo, which at 8.4V exceeds the servo's own 8.0V limit)
  into the FE-URT-2's blue screw terminal.

  If 7.4V IS connected: `bringup ports`, then `bringup --port <dev> --protocol
  sts3215 identify --id 1` and CHECK IT REPORTS ~7.4V NOT 4.3V. Then
  `nudge --id 1 --counts 0` (torque + read-back, no motion), then
  `--counts 57` and `--counts -57` with the horn unloaded. Record the achieved
  delta and its SIGN into docs/hardware_bringup_checklist.json HW-MOTION-001 --
  nothing in the repo knows the counts-to-motion mapping yet. Only then
  `assign-id`, one servo at a time, confirming each with `scan`.

  If 7.4V is NOT connected: do not command motion. Pick up the deferred
  software work listed under SW-017's known limitations instead -- the
  FeedbackProtocol/RegisterAccess merge and preflight's typed exceptions are
  both well understood and hardware-independent.
  ```

## Previous milestone: SW-016 — servo-ID assignment + bringup wiring

- **PR**: [#5](https://github.com/jakegibs617/robotic-arm-paint/pull/5) (merged
  into `main` at `650cd5d`).
- **What it did**: implemented the STS3215 EEPROM unlock/write-ID/re-lock wire
  protocol for reassigning a servo's bus ID (`control/serial_controller.py`,
  `control/id_assignment.py`), and wired both that and the already-existing
  `read_servo_preflight` into two new `apps/bringup.py` subcommands (`ping`,
  `assign-id`) — previously `bringup.py` had no subcommand that opened a real
  serial connection at all. This closed out the last two software-only,
  hardware-independent gaps identified before the project needs a physical
  servo to make further progress (see the hill chart below).
- **Tests run**: `.venv/bin/python -m pytest -q` — 139 passed (up from 124
  before this milestone). Focused: `tests/test_control.py`,
  `tests/test_id_assignment.py`, `tests/test_bringup_cli.py`. Manual smoke:
  `bringup --mock ping` and `bringup --mock assign-id --old-id 1 --new-id 0`.
- **Review**: a subagent reviewed PR #5 and posted findings on GitHub
  ([review comment](https://github.com/jakegibs617/robotic-arm-paint/pull/5),
  [fix-up comment](https://github.com/jakegibs617/robotic-arm-paint/pull/5#issuecomment-4899358744)).
  Fixed: `old_id` wasn't range-validated (only `new_id` was) — since
  `_sts_packet` masks `servo_id & 0xFF`, a bad `old_id` would have silently
  addressed a different bus servo instead of raising; the CLI's success message
  overclaimed (none of the three writes are read back, so it now says "sent
  ... not read back; verify with `bringup ping`" instead of asserting success);
  a stale docstring in `bringup.py` was corrected.
- **Known limitations**: the entire ID-assignment sequence is **unverified
  against real hardware** — implemented from the Feetech memory map only, same
  caveat as the rest of the `sts3215` protocol. `assign_servo_id` does not read
  back any of its three writes, so a CLI "success" only means the writes were
  sent without a Python exception, not that the servo applied them — always
  follow it with `bringup ping` before trusting a new ID.
- **Copy/paste prompt for the next session**:

  ```text
  Read AGENT_HANDOFF.md first. Software-only work is exhausted for now (see
  the hill chart's "Downhill — known" / "software-only" sections) except
  optional richer SVG fixtures. The real next milestone is the first physical
  hardware session per docs/hardware_identification.md: find the serial port,
  run `bringup assign-id` one servo at a time (unverified — watch for it not
  working as expected and be ready to fall back to Feetech's FD software),
  confirm with `bringup ping`, then measure safe ranges and capture the 7
  calibration poses per docs/calibration.md. If hardware still isn't
  available, treat the software backlog as done and say so rather than
  inventing new speculative work — check docs/software_frontload_tasks.json
  first.
  ```

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
