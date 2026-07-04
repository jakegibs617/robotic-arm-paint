# Calibration

## MVP: manual pose calibration (Phase 5)

The flat-drawing pipeline needs seven poses captured with the jog CLI. No camera
or inverse kinematics involved — you physically jog the arm and save each pose.

1. Start the jog CLI: `painterbot-jog --port /dev/tty.usbserial-XXXX`
2. Tape your paper down inside the arm's reach.
3. Capture the reference poses:

   ```text
   home              -> jog to a safe neutral pose,  then: save home
   pen_up            -> jog so the marker clears paper, then: save pen_up
   pen_down          -> lower until the marker just touches, then: save pen_down
   corner_bl         -> at pen-down height, move to bottom-left corner:  save corner_bl
   corner_br         -> bottom-right corner:  save corner_br
   corner_tl         -> top-left corner:      save corner_tl
   corner_tr         -> top-right corner:     save corner_tr
   ```

4. Persist them: `save-config` (writes `configs/workspace.calibrated.yaml`).

**Hand-guided capture (recommended with STS3215 servos):** instead of jogging
joint-by-joint, run `torque off`, physically move the arm to each target while
supporting it, then `read` (adopts the encoder positions as the current pose)
and `save <name>`. Finish with `torque on` — it re-syncs from the encoders
first, so the arm won't jump. This is faster and more precise than numeric
jogging because the magnetic encoders report the true pose.

`pen_up` / `pen_down` should be captured at the same XY location so their
difference is a pure pen-lift delta. The four corners define the drawing plane;
any paper coordinate is mapped by bilinear interpolation between them (see
`drawing/stroke_planner.py`).

The drawing apps automatically load `workspace.calibrated.yaml` if it exists.

## Phase 7: iPhone-photo calibration

Maps overhead-photo pixels to paper millimeters via a four-corner homography:

```bash
painterbot-calibrate --image ./iphone_photo.jpg
```

Click the four paper corners in order (bottom-left, bottom-right, top-right,
top-left). See `calibration/homography.py`.
