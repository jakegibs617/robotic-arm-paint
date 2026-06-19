"""painterbot — control a low-cost 6DOF servo arm to draw on paper.

See ``initial_plan.md`` for the phased roadmap. The MVP target is drawing a
square with a marker on flat paper, driven entirely from a Mac over USB serial.
"""

__version__ = "0.1.0"

# Fixed joint order used everywhere (servo channels, pose lists, configs).
JOINT_ORDER = (
    "base",
    "shoulder",
    "elbow",
    "wrist_pitch",
    "wrist_roll",
    "gripper",
)
