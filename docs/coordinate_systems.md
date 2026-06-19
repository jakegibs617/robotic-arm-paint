# Coordinate systems

Tracked explicitly so every transform in the code has a named source and target.

| Space            | Units / form                                   | Where it lives |
|------------------|------------------------------------------------|----------------|
| Servo space      | raw servo angles (per channel)                 | `serial_controller`, on the wire |
| Robot joint space| `base, shoulder, elbow, wrist_pitch, wrist_roll, gripper` in degrees | `config.JointConfig`, `Servo`, `Arm.pose` |
| Robot base space | X/Y/Z millimeters (not used by MVP — no IK)    | future (Phase 9) |
| Paper space      | 2D millimeters, origin bottom-left, +x right, +y up | `drawing.path_sampler`, `Stroke` |
| Image space      | iPhone photo pixels                            | `calibration.homography` |
| Mesh space       | 3D millimeters/meters from LiDAR scan          | `iphone.import_scan` (Phase 8) |

## MVP mapping

```text
SVG / shape
   -> paper coordinates      (drawing/svg_loader, shapes, fit_to_paper)
   -> robot joint angles      (drawing/stroke_planner, bilinear interp of corners)
   -> servo commands          (control/servo, control/serial_controller)
```

The MVP skips robot base space (no inverse kinematics). Paper coordinates map
straight to joint angles by bilinearly interpolating the four manually-captured
corner poses.

## Later mapping (Phase 9)

```text
iPhone LiDAR mesh
   -> robot base coordinates  (robot-to-object calibration)
   -> surface-following paths (normals, brush angle, pressure)
```
