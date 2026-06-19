# Robotic Arm Painter POC — Refined Technical Plan

## Core Assumptions

* Development machine: Mac
* Robot arm: low-cost 6DOF servo robot arm kit
* Robot connection: Mac → USB/serial → robot controller
* First drawing tool: Sharpie or paint marker
* First surface: flat paper/cardboard
* Camera/depth device: iPhone with LiDAR
* No Raspberry Pi for MVP
* No RealSense for MVP
* No ROS for MVP
* Main software language: Python 3.11+

## Project Goal

Build a Mac-based software system that controls a low-cost 6DOF robot arm to draw simple artwork on paper, then expand it to use iPhone camera/LiDAR data for calibration and eventually painting on 3D objects.

The first successful demo is:

> Robot draws a square, star, or simple SVG on paper with a marker.

## MVP Architecture

```text
Mac Python App
   ↓ USB serial
Robot Arm Controller
   ↓
6DOF Servo Arm
   ↓
Marker / Brush Tool
```

Later:

```text
iPhone LiDAR / Camera
   ↓ export image, mesh, or scan
Mac Python App
   ↓ path planning
Robot Arm
   ↓
Drawing / painting
```

## Phase 1 — Hardware Bring-Up

Goal: prove the Mac can control the arm.

Tasks:

1. Assemble the robot arm.
2. Identify the controller board.
3. Confirm USB connection type.
4. Determine whether it appears as:

   * `/dev/tty.usbserial-*`
   * `/dev/tty.usbmodem-*`
   * Bluetooth serial
   * vendor-specific driver
5. Move one servo from the Mac.
6. Move all servos individually.
7. Record safe min/max angles for every joint.

Deliverables:

* `docs/hardware_identification.md`
* working serial connection
* basic servo test script

Acceptance criteria:

* One servo moves from a Python script on Mac.
* All servos can be moved safely.
* Emergency stop/power-off procedure is documented.

## Phase 2 — Python Control Package

Create a Python package called `painterbot`.

Repo structure:

```text
robot-arm-painter/
  README.md
  pyproject.toml
  requirements.txt

  configs/
    arm.default.yaml
    workspace.default.yaml
    iphone.default.yaml

  src/
    painterbot/
      control/
        serial_controller.py
        servo.py
        arm.py
      drawing/
        svg_loader.py
        path_sampler.py
        stroke_planner.py
      calibration/
        pose_calibration.py
        homography.py
      iphone/
        import_scan.py
        import_image.py
      apps/
        manual_jog.py
        draw_shape.py
        draw_svg.py
        calibrate_workspace.py

  hardware/
    mounts/
      marker_holder/

  docs/
    setup_mac.md
    calibration.md
    coordinate_systems.md
    milestones.md

  tests/
```

Required Python dependencies:

```text
pyserial
numpy
opencv-python
svgpathtools
pydantic
pyyaml
pytest
matplotlib
```

Optional later:

```text
open3d
trimesh
scipy
```

## Phase 3 — Manual Jog CLI

Build:

```bash
python -m painterbot.apps.manual_jog
```

Required commands:

```text
connect
home
servo 1 90
servo 2 110
pose 90 100 80 90 90 30
save home
save pen_up
save pen_down
goto home
goto pen_up
goto pen_down
stop
```

Acceptance criteria:

* User can manually move every joint.
* User can save and reload named poses.
* Servo limits are enforced.
* Commands are logged.

## Phase 4 — Marker Holder

Remove or ignore the gripper.

Design a 3D printed marker holder that attaches to the wrist.

Requirements:

* Holds Sharpie or Posca marker.
* Mounts to wrist plate.
* Allows tip height adjustment.
* Keeps marker rigid.
* Does not collide with the arm.
* Prefer slight compliance using foam, spring, or flexible clamp.

Deliverables:

```text
hardware/mounts/marker_holder/marker_holder.stl
hardware/mounts/marker_holder/marker_holder.step
hardware/mounts/marker_holder/README.md
```

Acceptance criteria:

* Marker touches paper consistently.
* Marker can be lifted off paper.
* Holder survives repeated drawing motions.

## Phase 5 — Flat Drawing Without Camera

First drawing system should not use LiDAR.

Coordinate flow:

```text
SVG/image path
   ↓
2D drawing coordinates
   ↓
manual workspace calibration
   ↓
robot servo poses
   ↓
servo commands
```

Build:

```bash
python -m painterbot.apps.draw_shape --shape square
python -m painterbot.apps.draw_shape --shape circle
python -m painterbot.apps.draw_shape --shape spiral
```

Drawing behavior:

```text
move to start at pen_up
lower to pen_down
draw stroke
raise to pen_up
move to next stroke
```

Acceptance criteria:

* Robot draws a line.
* Robot draws a square.
* Robot draws a circle approximation.
* Robot returns home after drawing.

## Phase 6 — SVG Drawing

Build:

```bash
python -m painterbot.apps.draw_svg ./examples/star.svg
```

Required SVG support:

* line
* polyline
* polygon
* rect
* circle
* path

Path handling:

* Convert curves into sampled points.
* Scale artwork into drawing area.
* Preserve aspect ratio.
* Support multi-stroke drawings.
* Lift marker between strokes.

Acceptance criteria:

* Robot draws a simple star SVG.
* Robot draws a single-line logo or signature SVG.
* Drawing fits inside configured workspace.

## Phase 7 — iPhone Camera Calibration

Use iPhone as the camera source before using LiDAR.

Simplest workflow:

1. Take overhead photo of paper with iPhone.
2. Transfer image to Mac.
3. Run calibration script.
4. Click four paper corners manually.
5. Software computes paper coordinate system.
6. SVG drawing is aligned to paper.

Build:

```bash
python -m painterbot.apps.calibrate_workspace --image ./iphone_photo.jpg
```

This should produce:

```text
configs/workspace.calibrated.yaml
```

Acceptance criteria:

* Image pixels map to paper coordinates.
* Drawing can be positioned relative to detected paper.
* Manual four-corner click calibration works.

## Phase 8 — iPhone LiDAR Scan Import

Do not build a custom iPhone app first.

Use existing iPhone LiDAR apps:

* Polycam
* Scaniverse
* Apple Reality Composer / ARKit export if available

Initial scan workflow:

```text
iPhone LiDAR scan
   ↓
export OBJ / GLB / USDZ / STL
   ↓
import into Mac software
   ↓
inspect mesh
   ↓
plan future painting paths
```

Build later:

```bash
python -m painterbot.iphone.import_scan ./scan.obj
```

Useful later libraries:

```text
open3d
trimesh
numpy
opencv-python
```

Acceptance criteria:

* Mac software can load exported iPhone scan.
* Mesh can be displayed or inspected.
* Surface coordinates can be sampled.

## Phase 9 — Vision/LiDAR-Assisted Painting

Only after flat drawing works.

Future flow:

```text
iPhone LiDAR scan object
   ↓
export mesh to Mac
   ↓
align robot coordinate system to mesh
   ↓
project image/artwork onto mesh
   ↓
generate surface-following strokes
   ↓
robot paints object
```

This requires:

* robot-to-object calibration
* mesh scaling
* surface normal calculation
* collision avoidance
* brush angle planning
* pressure compensation

This is not MVP.

## Coordinate Systems

Track these explicitly:

```text
Servo space:
raw servo angles

Robot joint space:
base, shoulder, elbow, wrist_pitch, wrist_roll, gripper

Robot base space:
X/Y/Z in millimeters

Paper space:
2D coordinates on paper

Image space:
iPhone photo pixels

Mesh space:
3D coordinates from iPhone LiDAR scan
```

Important mapping:

```text
SVG → paper coordinates → robot coordinates → joint angles → servo commands
```

Later:

```text
iPhone LiDAR mesh → robot coordinates → surface painting paths
```

## Recommended Implementation Order

1. Assemble arm.
2. Identify controller board.
3. Connect Mac to arm.
4. Move one servo from Python.
5. Move all servos safely.
6. Build manual jog CLI.
7. Save/load poses.
8. Design and print marker holder.
9. Define home, pen_up, pen_down.
10. Draw a line.
11. Draw a square.
12. Draw SVG star.
13. Add iPhone photo calibration.
14. Import iPhone LiDAR scan.
15. Plan 3D painting.

## Agent Starting Prompt

You are implementing a Mac-first robotic arm painter POC.

Hardware:

* Low-cost 6DOF servo robot arm kit.
* Mac development machine.
* iPhone with LiDAR for future camera/depth workflows.
* First tool is a Sharpie or paint marker.
* First surface is flat paper.

Do not use Raspberry Pi, RealSense, ROS, or custom iOS app for MVP.

Build a Python 3.11+ package called `painterbot`.

Primary milestone:
Make the robot draw a square with a marker on paper.

Implementation order:

1. Identify serial connection from Mac.
2. Implement serial servo control.
3. Enforce servo min/max limits.
4. Implement manual jog CLI.
5. Implement save/load poses.
6. Implement pen_up and pen_down.
7. Implement basic shape drawing.
8. Implement SVG parsing and path sampling.
9. Implement iPhone photo-based workspace calibration using manual four-corner clicking.
10. Later, implement iPhone LiDAR scan import from OBJ/GLB/USDZ/STL exports.

Safety:

* Never move servos outside configured safe ranges.
* Include emergency stop.
* Log every command.
* Start with slow motion.
* Prefer manual pose calibration before inverse kinematics.

Do not begin with 3D object painting. The first working demo is flat 2D drawing.
