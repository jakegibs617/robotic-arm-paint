"""The Arm facade: coordinates all six servos and interpolated motion.

This is the main object apps use. It owns the serial backend, enforces per-joint
limits via :class:`Servo`, and moves smoothly between poses by interpolating in
joint space (no inverse kinematics — the MVP uses manual pose calibration).
"""

from __future__ import annotations

import logging
import time
from contextlib import contextmanager
from typing import Optional, Sequence

from painterbot.config import ArmConfig
from painterbot.control.serial_controller import SerialBackend, open_backend
from painterbot.control.servo import Servo

logger = logging.getLogger("painterbot.arm")

Pose = Sequence[float]


class Arm:
    """Six-servo arm controller with safe, interpolated motion."""

    def __init__(self, config: ArmConfig, backend: SerialBackend) -> None:
        self.config = config
        self.backend = backend
        self.servos: list[Servo] = [Servo(j, backend) for j in config.joints]
        self._stopped = False

    # -- construction --------------------------------------------------------

    @classmethod
    def connect(
        cls,
        config: ArmConfig,
        *,
        mock: bool = False,
        port: Optional[str] = None,
    ) -> "Arm":
        backend = open_backend(
            mock=mock,
            port=port or config.serial.port,
            baud=config.serial.baud,
            timeout_s=config.serial.timeout_s,
            protocol=config.serial.protocol,
        )
        logger.info("Arm connected (mock=%s)", backend.is_mock)
        return cls(config, backend)

    # -- state ---------------------------------------------------------------

    @property
    def pose(self) -> list[float]:
        """Current commanded angles in joint order."""
        return [s.angle for s in self.servos]

    def servo(self, name: str) -> Servo:
        for s in self.servos:
            if s.name == name:
                return s
        raise KeyError(f"no joint named {name!r}")

    # -- motion --------------------------------------------------------------

    def set_joint(self, name: str, angle: float, *, clamp: bool = False) -> float:
        """Immediately move one joint (no interpolation). Returns angle sent."""
        return self.servo(name).move_to(angle, clamp=clamp)

    def _write_pose(self, pose: Pose, *, clamp: bool) -> None:
        if len(pose) != len(self.servos):
            raise ValueError(f"pose needs {len(self.servos)} angles, got {len(pose)}")
        for servo, angle in zip(self.servos, pose):
            servo.move_to(angle, clamp=clamp)

    def move_to_pose(
        self,
        target: Pose,
        *,
        clamp: bool = False,
        interpolate: bool = True,
    ) -> None:
        """Move all joints to ``target``, interpolating for smooth, slow motion.

        Honors ``stop()``: a stopped arm refuses to move until ``resume()``.
        """
        if self._stopped:
            raise RuntimeError("arm is stopped; call resume() before moving")
        if len(target) != len(self.servos):
            raise ValueError(f"pose needs {len(self.servos)} angles, got {len(target)}")

        if not interpolate:
            self._write_pose(target, clamp=clamp)
            return

        start = self.pose
        steps = self._step_count(start, target)
        for i in range(1, steps + 1):
            if self._stopped:
                logger.warning("Motion interrupted by stop()")
                return
            frac = i / steps
            intermediate = [s + (t - s) * frac for s, t in zip(start, target)]
            self._write_pose(intermediate, clamp=clamp)
            time.sleep(self.config.motion.step_delay_s)

    def _step_count(self, start: Pose, target: Pose) -> int:
        max_delta = max((abs(t - s) for s, t in zip(start, target)), default=0.0)
        return max(1, int(max_delta / self.config.motion.max_step_deg + 0.5))

    def home(self, **kwargs) -> None:
        """Move to the configured home pose."""
        self.move_to_pose(self.config.home_pose, **kwargs)

    # -- feedback (STS-class bus servos) --------------------------------------

    def read_pose(self) -> list[Optional[float]]:
        """Read actual encoder positions (does not change commanded state)."""
        return [s.read_actual() for s in self.servos]

    def sync_from_hardware(self) -> list[Optional[float]]:
        """Adopt encoder positions as the commanded pose (after hand-guiding)."""
        return [s.sync() for s in self.servos]

    def set_torque(self, enabled: bool) -> None:
        """Torque all servos on/off. Off makes the arm limp — support it!

        Re-enable via the jog CLI's ``torque on``, which syncs from the encoders
        first so the next move starts from the arm's true pose.
        """
        for s in self.servos:
            self.backend.set_torque(s.channel, enabled)

    # -- safety / lifecycle --------------------------------------------------

    def stop(self) -> None:
        """Emergency stop: freeze at the current pose and block further motion."""
        self._stopped = True
        logger.warning("STOP — arm halted at pose %s", self.pose)

    def resume(self) -> None:
        self._stopped = False
        logger.info("Arm resumed")

    @property
    def stopped(self) -> bool:
        return self._stopped

    def close(self) -> None:
        self.backend.close()

    def __enter__(self) -> "Arm":
        return self

    def __exit__(self, *exc) -> None:
        self.close()


@contextmanager
def connect_arm(config: ArmConfig, *, mock: bool = False, port: Optional[str] = None):
    """Context manager that connects an arm and guarantees the port is closed."""
    arm = Arm.connect(config, mock=mock, port=port)
    try:
        yield arm
    finally:
        arm.close()
