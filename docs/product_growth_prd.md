# Product Growth PRD

## Product Vision Statement

Painterbot helps hands-on makers, educators, and robotics learners move from "I have a low-cost servo arm and a drawing idea" to a repeatable physical drawing workflow by combining safe Mac-based arm control, guided calibration, artwork preparation, and hardware-aware execution, so they can turn simple digital paths into visible marks without learning ROS, inverse kinematics, or custom embedded systems first.

## One-Sentence Vision

Help makers get a low-cost robot arm drawing reliably without becoming robotics infrastructure experts.

## Current Implicit Vision

The current project vision is strong for an MVP but narrower than the long-term roadmap. The code and docs consistently point to one first proof: a Mac controls a 6DOF servo arm that draws a square, star, or SVG on flat paper. The repo already refuses major complexity for the MVP: no Raspberry Pi, no ROS, no RealSense, no custom iOS app, and no inverse kinematics before the flat drawing demo works.

The growth opportunity is to preserve that simplicity while turning the project from a working proof of concept into a guided robotics drawing system: hardware bring-up, calibration, preview, execution, diagnostics, and eventually camera/LiDAR-assisted surface painting.

## Strategic Narrative

Low-cost servo arms are now affordable, but the path from "kit on the desk" to "robot performs a precise creative task" is still fragmented. Users must identify hardware, wire power safely, discover serial protocols, assign servo IDs, calibrate workspace coordinates, prepare artwork, avoid crashes, and debug motion without much feedback. Generic robotics stacks are powerful but too heavy for this project's intended first experience.

Painterbot can win by being the opposite of a generic robotics platform. It should be a focused creative robotics workflow for one satisfying job: make the arm draw. The product should start with flat paper because flat drawing gives immediate feedback, clear acceptance tests, and a contained safety envelope. Once flat drawing is reliable, iPhone photo and LiDAR data can add guided positioning and eventually 3D surface awareness.

The future product should feel like a calm hardware assistant: connect the arm, verify servos, capture poses, preview a drawing, simulate motion, execute slowly, and help the user diagnose what changed when the physical result is wrong.

## Target Customer

Primary users:

- Makers and hobbyists building a low-cost robot arm project on a Mac.
- Educators or workshop leaders who need a repeatable robotics-art demo.
- Robotics learners who want practical motion-control intuition before heavier frameworks.

Secondary users:

- Digital artists experimenting with physical plotter-like output.
- Developers extending the system toward calibration, vision, or 3D surface workflows.

Buyer:

- Usually the builder themselves; in education, a teacher, lab, club, or workshop organizer.

Excluded users:

- Industrial automation users who need certified safety systems, production uptime, or high precision.
- Users who want a general robot programming environment.
- Users who want autonomous 3D painting before basic flat drawing is stable.

Early adopter profile:

- Comfortable with a terminal, Python environments, and light hardware assembly.
- Owns or is waiting on STS3215-class bus servos and a USB serial adapter.
- Values clear diagnostics and safe constraints more than a polished consumer UI.

## Jobs To Be Done

- When I receive robot arm parts, I want to verify power, serial, servo IDs, and encoder feedback, so I can know the hardware is safe before moving the full arm.
- When I mount the arm and marker, I want to capture home, pen-up, pen-down, and paper-corner poses, so the software can map paper coordinates to real motion.
- When I choose a shape or SVG, I want to preview and dry-run the plan, so I can catch scale, bounds, and calibration problems before moving hardware.
- When the arm draws poorly, I want diagnostics tied to calibration, servo limits, and drawing geometry, so I can fix the real cause instead of guessing.
- When I teach or demo the arm, I want a reliable square/star workflow, so the session succeeds even if the audience is new to robotics.
- When I outgrow flat paper, I want the same workflow to accept camera and scan context, so I can move toward object-aware drawing without starting over.

## Value Proposition

Functional value:

- End-to-end flat drawing flow from shape/SVG to servo commands.
- Mock mode for development without hardware.
- Safe joint-limit enforcement and slow interpolated motion.
- Manual and hand-guided calibration using servo feedback.
- Preview and dry-run output before execution.

Emotional value:

- Reduces the feeling that robotics work is opaque and brittle.
- Gives the user confidence that hardware will not jump unexpectedly.
- Makes the first visible result feel achievable instead of theoretical.

Economic value:

- Uses low-cost STS3215 servos and a Mac instead of a full robotics stack.
- Avoids extra onboard computers and depth cameras for the MVP.
- Lets builders validate the system before investing in custom mounts or 3D workflows.

Strategic value:

- Establishes a focused foundation for creative robotics experiments.
- Builds a reusable path from flat calibration to photo alignment and later surface planning.

## Differentiation

Versus manual hardware scripts:

- Painterbot packages serial control, safety limits, calibration, drawing geometry, preview, and execution into one coherent workflow.

Versus generic robotics frameworks:

- It solves a narrower problem with far less setup. The user does not need ROS, a URDF, inverse kinematics, or a robot controller board for the first milestone.

Versus plotters or CNC machines:

- It teaches and exercises articulated-arm control rather than hiding motion behind a rigid gantry.

Versus doing nothing or waiting for perfect hardware:

- Mock mode lets software, tests, drawing prep, and user workflow mature before the physical arm arrives.

Versus jumping directly to 3D painting:

- Flat drawing provides measurable success criteria and safer iteration before adding scan, mesh, normals, and surface-following complexity.

## Product Principles

- Make the first physical success obvious: line, square, star, then SVG.
- Keep safety in the domain model, not just in CLI instructions.
- Prefer guided calibration over hidden math until the hardware proves it needs more.
- Treat mock mode as a first-class product surface.
- Show the user what will happen before the arm moves.
- Add complexity only when it improves the drawing workflow.
- Preserve clear coordinate-system boundaries.

## Anti-Goals

- Do not become a generic robotics IDE.
- Do not add ROS, Raspberry Pi control, RealSense, or a custom iOS app before the flat-paper workflow is reliable.
- Do not build 3D object painting before hardware bring-up, marker mounting, and flat calibration are validated.
- Do not hide unsafe motion behind convenience flags.
- Do not optimize for arbitrary robot arms before the STS3215 build is proven.
- Do not turn the CLI into a pile of unrelated scripts without shared workflow state.

## Product Requirements

### PRD-1: Hardware Bring-Up Assistant

Goal:

Guide the first hardware session from "parts arrived" to "all six servos are identified, readable, and safe to move."

Core capabilities:

- Detect and show available serial ports.
- Ping one connected servo at a time.
- Read present position from STS3215 servos.
- Toggle torque safely.
- Assign or verify servo IDs 0 through 5.
- Record measured min, max, and home angles.
- Write validated updates to arm config.

Acceptance criteria:

- User can verify one servo without connecting the full arm.
- User can detect wrong baud, wrong ID, missing power, or short replies with actionable messages.
- No command moves a servo outside the configured or measured safe range.

### PRD-2: Calibration Session Workflow

Goal:

Turn manual pose capture into a guided, repeatable session instead of an expert-only REPL sequence.

Core capabilities:

- Step through home, pen_up, pen_down, and four paper corners.
- Support torque-off, hand-guided capture, read, save, and validate.
- Warn when pen_up and pen_down are not captured at a compatible XY location.
- Save `workspace.calibrated.yaml` with a session summary.
- Let users reload, inspect, and recapture individual poses.

Acceptance criteria:

- A new user can capture all required poses by following prompts.
- The drawing apps can detect incomplete calibration and tell the user exactly what remains.
- Calibration is not silently overwritten without user intent.

### PRD-3: First Drawing Reliability

Goal:

Make "draw a square on paper" repeatable enough to be the project's true MVP.

Core capabilities:

- Dry-run summary for shape and SVG drawings.
- Preview PNG with paper bounds and drawing bounds.
- Slow first execution mode.
- Stroke count, point count, and estimated command count before motion.
- Post-run summary of executed strokes and final pose.

Acceptance criteria:

- The robot draws a line, square, circle approximation, and star on paper.
- User can rerun a drawing without recalibrating unless hardware moved.
- Errors identify whether the failure is config, calibration, serial, servo limit, or drawing geometry.

### PRD-4: Photo-Assisted Paper Alignment

Goal:

Use an iPhone photo to position artwork relative to the actual paper sheet.

Core capabilities:

- Import photo.
- Click or detect paper corners.
- Compute image-pixel to paper-mm homography.
- Preview artwork over the photo.
- Save alignment metadata with the workspace.

Acceptance criteria:

- User can place a drawing relative to a photographed sheet.
- The transformed bounds match the configured paper size.
- The system still works without a camera.

### PRD-5: Surface Exploration, Not Full 3D Painting Yet

Goal:

Prepare for object-aware painting without promising a complete 3D painting product too early.

Core capabilities:

- Import iPhone LiDAR scan files through optional extras.
- Inspect scale, orientation, and mesh bounds.
- Mark candidate flat or gently curved regions.
- Generate non-executing surface path previews.

Acceptance criteria:

- The app can load and summarize a scan.
- The team can validate coordinate and calibration assumptions before commanding 3D motion.
- No 3D execution path bypasses flat-drawing safety lessons.

## Roadmap

### Milestone 0: Maintain Mock-Complete Baseline

- Keep tests green.
- Keep dry-run and preview working without hardware.
- Add richer SVG fixtures and regression previews.

### Milestone 1: Hardware Bring-Up

- Build servo ping/read/ID tooling.
- Verify STS3215 protocol against real hardware.
- Record safe joint ranges.
- Update config with measured baud, port, ranges, and homes.

### Milestone 2: Physical Flat-Drawing MVP

- Finish marker holder.
- Capture calibration poses.
- Draw line, square, circle approximation, and star.
- Document common physical failures and fixes.

### Milestone 3: Guided Workflow

- Convert bring-up and calibration into guided commands.
- Add preflight validation before execution.
- Add clearer run summaries and diagnostics.

### Milestone 4: Camera-Assisted Flat Drawing

- Complete photo calibration workflow.
- Overlay previews on photos.
- Support repeatable paper repositioning.

### Milestone 5: 3D Readiness

- Import scans.
- Validate mesh scale and object-to-robot calibration concepts.
- Prototype non-executing surface paths before moving hardware in 3D.

## Success Metrics

- Time from fresh checkout to mock square preview.
- Time from hardware arrival to first safe one-servo read.
- Time from assembled arm to first physical square.
- Number of commands or prompts needed to complete calibration.
- Percentage of drawing failures with actionable error messages.
- Repeatability of square dimensions and corner closure across runs.
- Test coverage around serial protocol, safety limits, calibration, and planner behavior.

## Key Risks

- STS3215 protocol assumptions may differ from the real hardware behavior.
- Servo IDs, baud, power, or stale status packets may make bring-up confusing.
- Bilinear interpolation may be insufficient for larger paper areas or nonlinear arm geometry.
- Marker holder compliance and tip pressure may dominate drawing quality.
- Users may want to jump to 3D before flat calibration is mechanically reliable.
- The CLI workflow may become hard to operate as stateful sessions grow.

## Validation Needed

- Verify actual servo reads, torque toggles, and writes on hardware.
- Measure safe ranges after the arm is assembled.
- Confirm that hand-guided pose capture is precise enough for the first square.
- Test marker holder designs with real pens and paper.
- Compare physical drawing error against preview and calibration assumptions.
- Validate whether photo homography improves placement enough to justify UX investment.

