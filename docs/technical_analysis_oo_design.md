# Technical Analysis: First-Principles OO Design

## Executive Summary

The current architecture is appropriately simple for the MVP. It has clear domain slices: hardware control, servo safety, drawing geometry, calibration, and CLI applications. The strongest design choices are the `Arm` facade, per-servo limit enforcement, pluggable serial protocol encoders, mock-first execution, and explicit paper-mm drawing geometry.

The next technical risk is not lack of abstraction. It is the opposite: adding abstractions before real hardware teaches the project which forces are stable. The design should stay small through first physical drawing, then introduce a few focused objects around calibration sessions, hardware capabilities, execution planning, and diagnostics as soon as stateful workflows start to repeat.

## Current System Shape

Primary workflow:

```text
Shape/SVG
  -> Drawing in paper millimeters
  -> fit_to_paper
  -> StrokePlanner bilinear paper-to-pose mapping
  -> Arm interpolated joint motion
  -> Servo range validation and inversion
  -> SerialBackend protocol bytes
```

Important files:

- `src/painterbot/control/arm.py`: owns six servos, pose state, interpolated motion, stop/resume, hardware feedback calls.
- `src/painterbot/control/servo.py`: owns one joint's safe range, inversion, commanded angle, read/sync behavior.
- `src/painterbot/control/serial_controller.py`: owns mock/real serial transport and wire protocol registry.
- `src/painterbot/drawing/stroke_planner.py`: owns flat-paper calibration requirements, bilinear mapping, and stroke execution.
- `src/painterbot/drawing/path_sampler.py`: owns drawing geometry in paper millimeters.
- `src/painterbot/config.py`: owns typed YAML config for arm, workspace, paper, and drawing settings.
- `src/painterbot/apps/*.py`: own CLI parsing and user workflows.

## First Principles

Stable domain concepts:

- A joint has a logical angle, a safe range, a channel/ID, and optional inversion.
- An arm pose is an ordered list of six logical joint angles.
- A drawing is a list of strokes in paper millimeters.
- A workspace calibration maps paper coordinates to robot poses.
- A serial protocol can write position; some protocols can also read position and toggle torque.
- Mock execution is a real workflow, not just a test trick.

Invariants:

- Path execution must never silently clamp out-of-range poses.
- A stopped arm must refuse new motion until resumed.
- Motion should start from the software's best known current pose.
- Captured poses must have exactly the arm's joint count.
- Paper-space transforms must preserve known units and coordinate orientation.
- Feedback-dependent commands must fail loudly when the protocol does not support feedback.

Likely change scenarios:

- Real STS3215 hardware reveals protocol timing, ID, baud, ack, or torque behavior differences.
- Calibration becomes a guided session rather than ad hoc REPL commands.
- Flat bilinear mapping is replaced or supplemented by a better mapper.
- Drawing execution grows preflight, simulation, and diagnostics.
- Photo calibration adds image-to-paper state.
- 3D exploration adds mesh/object coordinates without immediately replacing flat drawing.

Failure modes:

- Servo commands sent to wrong ID or wrong baud.
- Out-of-range hand-guided pose causes a jump when torque is re-enabled.
- Stale serial status packets corrupt feedback reads.
- Calibration poses are incomplete or physically inconsistent.
- Bilinear interpolation produces usable small drawings but poor larger drawings.
- CLI code accumulates workflow state that belongs in domain services.

## Responsibility Review

### `Arm`

Current responsibility:

- Coordinate all six servos.
- Maintain commanded pose.
- Interpolate joint-space motion.
- Stop/resume motion.
- Delegate read/sync/torque to servos/backends.

Assessment:

- Good facade for the MVP.
- It should remain about arm motion and state, not drawing semantics.
- It currently has the right safety check before multi-joint pose writes: validate current pose before writing any joint.

Recommendation:

- Keep `Arm` focused on pose-level commands.
- Add a future `MotionExecutor` only when execution gains run plans, timing estimates, pause/resume semantics, or post-run reporting.

### `Servo`

Current responsibility:

- Validate and clamp logical joint angles.
- Translate logical angle through inversion before wire transmission.
- Track commanded angle.
- Read and sync actual encoder angle when supported.

Assessment:

- Cohesive and important. Safety belongs here.
- The class should not learn about paper, calibration, or drawing.

Recommendation:

- Add tests before changing inversion or sync behavior.
- Consider a small `JointState` value object only if commanded, actual, torque, and error flags all become visible state.

### `SerialBackend` and Protocol Registry

Current responsibility:

- Separate transport from wire framing.
- Support mock, STS3215, ASCII, and LX16A protocol encoders.
- Expose optional feedback capabilities.

Assessment:

- This is the most mature extension point in the repo.
- The split between encoder and feedback protocol is useful, but feedback is capability-based only by convention.

Recommendation:

- After hardware verification, consider splitting interfaces into `PositionWriter`, `PositionReader`, and `TorqueController` protocols, or keep the current interface if it remains simple.
- Do not introduce a hardware plugin system until at least one additional real protocol is actively used.

### `StrokePlanner`

Current responsibility:

- Check required calibration poses.
- Convert paper-mm points to servo poses with bilinear interpolation.
- Execute strokes by raising/lowering the pen and moving the arm.

Assessment:

- It combines two responsibilities that are fine for the MVP but will diverge:
  mapping paper coordinates to poses, and executing drawing strokes.

Recommendation:

- Introduce a `WorkspaceMapper` or `PoseMapper` when another mapping strategy appears, such as photo-assisted calibration, local correction grids, or IK.
- Introduce a `DrawingExecutor` only when preflight, simulation, pause/resume, or result reporting becomes more complex.

### Config Models

Current responsibility:

- Validate YAML into typed models.
- Provide simple loading and saving.

Assessment:

- Good, practical boundary.
- `WorkspaceConfig.poses` is currently a loose dict, which is flexible but weak for calibration workflows.

Recommendation:

- Keep loose poses until hardware capture is proven.
- Then add a `CalibrationPoseSet` or stronger validation method to check required names, pose length, capture metadata, and session completeness.

### CLI Apps

Current responsibility:

- Parse arguments.
- Connect configs and arm.
- Run user workflows.

Assessment:

- The apps are thin enough today, except `manual_jog.py`, which is becoming a stateful workflow controller.

Recommendation:

- When adding guided bring-up or calibration, create workflow classes or command services instead of growing the REPL conditionals indefinitely.

## Design Forces and Recommended Shape

### Force: Hardware Capability Varies

Problem:

- Some protocols write only. STS3215 supports read and torque. Future hardware may support more status flags or less feedback.

Smallest useful pattern:

- Capability interfaces.

Consequence:

- Callers can ask for feedback capability explicitly rather than discovering failure at runtime.
- Adds names and a little indirection.

Exit criteria:

- If STS3215 remains the only supported real hardware, keep the current feedback registry and avoid ceremony.

### Force: Calibration Becomes a User Session

Problem:

- Calibration involves ordered steps, live hardware state, validation, saving, and retries. This is more than a config dict.

Smallest useful pattern:

- State object plus service: `CalibrationSession` operating on `WorkspaceConfig` and `Arm`.

Suggested responsibilities:

- Know required pose order.
- Capture current pose under a name.
- Validate pose length and safe ranges.
- Track completion.
- Save with metadata.

Consequence:

- `manual_jog.py` and future guided commands stop owning calibration rules.
- Adds a domain object that must stay small and testable.

Exit criteria:

- If calibration remains only a REPL convenience, keep using `pose_calibration.py` helpers.

### Force: Mapping Strategy Will Change

Problem:

- Bilinear interpolation is likely enough for the first square but not a durable abstraction for photo alignment, correction grids, or 3D planning.

Smallest useful pattern:

- Strategy pattern for `PoseMapper`.

Candidate API:

```python
class PoseMapper(Protocol):
    def paper_to_pose(self, point: Point, *, pen_down: bool = True) -> list[float]: ...
```

Implementations:

- `BilinearPoseMapper`
- Future `CorrectedPoseMapper`
- Future `IkPoseMapper`

Consequence:

- `StrokePlanner` can execute strokes without knowing mapping internals.
- Adds indirection before it is needed, so wait until a second mapper exists.

Exit criteria:

- If no second mapper emerges after flat drawing and photo calibration, collapse back into `StrokePlanner`.

### Force: Execution Needs Preflight and Diagnostics

Problem:

- Physical drawing needs checks before motion: calibration complete, drawing bounds valid, estimated commands reasonable, current pose safe, serial capability present, and maybe marker state verified.

Smallest useful pattern:

- Command object or plan object: `DrawingPlan`.

Suggested responsibilities:

- Hold resampled strokes and derived pose path.
- Report bounds, point count, command count, and required capabilities.
- Support preview/dry-run/execution using the same planned data.

Consequence:

- Dry-run and execution stop drifting apart.
- Planning can be tested without hardware.

Exit criteria:

- If dry-run remains just a summary string, avoid adding the plan object.

## Anti-Patterns to Avoid

### God CLI

How it would show up:

- `manual_jog.py` owns servo ID assignment, calibration validation, config mutation, hardware diagnostics, and drawing execution.

Why it matters:

- Hard to test and easy to break during hardware sessions.

Avoidance:

- Move repeated workflow rules into small services once a second command needs them.

### Leaky Hardware Protocol

How it would show up:

- STS3215 register names and packet assumptions spread into `Arm`, `Servo`, apps, or tests outside serial-specific boundaries.

Why it matters:

- Harder to change protocol timing, retries, or packet parsing after hardware verification.

Avoidance:

- Keep register details in `serial_controller.py` or a future protocol module.

### Premature Robot Abstraction

How it would show up:

- Generic robot-arm classes, plugin systems, full kinematic models, or ROS-like concepts before the first square.

Why it matters:

- The project's advantage is focused simplicity.

Avoidance:

- Add abstractions only when a real second implementation or repeated workflow appears.

### Hidden Safety Override

How it would show up:

- `clamp=True` used in path execution, or broad exception handling that continues after safety failures.

Why it matters:

- Clamping is appropriate for interactive jogging, not autonomous execution.

Avoidance:

- Keep path execution strict. Treat any automatic clamp in drawing execution as a bug.

### Coordinate Soup

How it would show up:

- Image pixels, paper millimeters, joint angles, and future mesh coordinates passed around as unlabelled tuples.

Why it matters:

- Coordinate mistakes are hard to diagnose and can cause unsafe motion.

Avoidance:

- Keep module boundaries explicit. Consider small value types if photo/3D code increases tuple ambiguity.

## Near-Term Refactor Recommendations

These are ordered by timing, not by abstract elegance.

### 1. Before Hardware Arrival

- Add a servo ping/read/ID bring-up CLI or command module.
- Add tests for error messages around feedback absence and calibration incompleteness.
- Add headless tests for calibration UI logic if possible without depending on a display.
- Add richer SVG fixtures for path loading and preview bounds.

### 2. During Hardware Bring-Up

- Keep protocol changes tightly scoped to serial code.
- Record real behavior in tests: baud, reply length, ack behavior, retry needs, torque behavior.
- Do not refactor the planner while hardware protocol assumptions are still unstable.

### 3. After First Physical Square

- Extract `CalibrationSession` if pose capture remains a repeated manual process.
- Extract `BilinearPoseMapper` if photo alignment or correction-grid mapping begins.
- Consider `DrawingPlan` if dry-run, preview, and execution need shared preflight data.
- Strengthen workspace pose validation around required pose names and pose lengths.

### 4. Before 3D Surface Work

- Define explicit coordinate value types or named dataclasses for paper, image, mesh, robot base, and joint spaces.
- Keep 3D import and analysis non-executing until object-to-robot calibration is validated.
- Introduce surface planning as a separate planner rather than expanding `StrokePlanner` until it handles two unrelated domains.

## Testing Strategy

Current tests already cover a healthy slice of config, drawing, preview, dry-run, homography, iPhone stubs, control, protocol framing, feedback, and safety behavior.

Recommended additions:

- Hardware protocol golden tests from real captures after first STS3215 session.
- Calibration session tests for missing, partial, and complete pose sets.
- Preflight tests that fail before any serial writes when calibration or current pose is unsafe.
- Drawing plan tests that compare dry-run counts, preview data, and execution path source.
- CLI tests for bring-up commands using fake serial objects.

## Decision Rules

- If a change affects physical motion, add tests before or alongside it.
- If a concept has only one implementation, keep it concrete unless it is already hiding clear complexity.
- If a CLI branch repeats domain logic from another CLI, move that logic into a small service.
- If a coordinate crosses a module boundary, its units and source space must be obvious from naming or type.
- If a new feature bypasses mock mode, it is not ready.
- If a new feature makes the first square harder, defer it.

## Proposed Next Technical Milestone

Build a hardware bring-up workflow with minimal new architecture:

- `painterbot.apps.bringup` for CLI entry.
- Reuse `open_backend`, STS3215 feedback, and fake serial tests.
- Add a small service only if needed, such as `ServoBusBringup`, with methods for `ping/read`, `set_torque`, and later `assign_id`.
- Keep ID assignment conservative and one-servo-at-a-time.
- Record observed hardware behavior back into tests and docs.

This milestone validates the riskiest dependency while preserving the current clean MVP architecture.

