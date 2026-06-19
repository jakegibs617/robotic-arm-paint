"""A single servo joint: enforces safe limits and tracks commanded angle."""

from __future__ import annotations

import logging

from painterbot.config import JointConfig
from painterbot.control.serial_controller import SerialBackend

logger = logging.getLogger("painterbot.servo")


class ServoLimitError(ValueError):
    """Raised when a requested angle falls outside the joint's safe range."""


class Servo:
    """Wraps one joint channel, clamping/validating against its config."""

    def __init__(self, config: JointConfig, backend: SerialBackend) -> None:
        self.config = config
        self._backend = backend
        # We don't know the real angle until commanded; assume home at startup.
        self.angle: float = config.home_deg

    @property
    def name(self) -> str:
        return self.config.name

    @property
    def channel(self) -> int:
        return self.config.channel

    def _to_wire(self, angle: float) -> float:
        """Apply inversion just before transmitting (config is in logical degrees)."""
        if self.config.invert:
            return self.config.min_deg + self.config.max_deg - angle
        return angle

    def move_to(self, angle: float, *, clamp: bool = False) -> float:
        """Command an absolute angle in degrees. Returns the angle actually sent.

        With ``clamp=False`` (default) an out-of-range angle raises
        ``ServoLimitError`` — the safe default for path execution. With
        ``clamp=True`` the angle is silently clamped, useful for manual jogging.
        """
        if not self.config.in_range(angle):
            if not clamp:
                raise ServoLimitError(
                    f"{self.name}: {angle:.1f}° outside safe range "
                    f"[{self.config.min_deg}, {self.config.max_deg}]"
                )
            angle = self.config.clamp(angle)
        self._backend.write_servo(self.channel, self._to_wire(angle))
        self.angle = angle
        return angle
