"""The smallest safe commanded move, for verifying the write path on a bench servo.

Why raw encoder counts instead of the :class:`~painterbot.control.servo.Servo`
layer: the per-joint safe ranges in ``configs/arm.default.yaml`` are still
placeholders for a 0..180 hobby servo, while an STS3215 spans 0..360 with its
centre at 2048 counts = 180 degrees. A bench servo therefore sits in the region
those limits would reject, and `Servo`'s degree conversion and `invert` flag
would obscure the one thing this probe exists to measure -- the sign and scale of
the counts-to-motion mapping. So this talks to the register directly and says so.

Safety properties, in order of how much they matter:

* The delta is capped before any byte reaches the bus, so a bring-up typo cannot
  swing a mounted arm.
* The start position must be readable, so a servo is never commanded blind.
* The stale goal is neutralised *before* torque is enabled. This one is not
  theoretical: the bench STS3215 was found sitting at 4094 counts with
  Goal_Position still at its factory 0. Enabling torque in that state commands a
  near-full-turn slam to 0 before any deliberate goal is sent, which on a
  mounted arm is a collision. So the goal register is overwritten with the
  servo's current position while it is still limp.
* The goal is clamped into the encoder range.
* Torque is released in a ``finally``, so a failure cannot leave the servo
  energised.
* Only ``servo_id`` is ever addressed -- no broadcast, no sync write.
* Nothing raises: every outcome comes back as a status a human can read.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Callable, Literal, Optional

from painterbot.control.serial_controller import RegisterBus, ServoRegister

logger = logging.getLogger("painterbot.motion_probe")

COUNTS_PER_REV = 4096
MAX_POSITION_COUNTS = COUNTS_PER_REV - 1

#: ~5 degrees: visible by eye, small enough to be harmless on an unmounted horn.
DEFAULT_NUDGE_COUNTS = 57

#: Hard ceiling, ~17.6 degrees. Not a default and not overridable: the point is
#: that no argument to this function can produce a large swing.
MAX_NUDGE_COUNTS = 200

MotionProbeStatus = Literal[
    "success",
    "refused",
    "no_start_position",
    "no_end_position",
    "did_not_move",
    "error",
]


@dataclass(frozen=True)
class NudgeResult:
    """What one bounded move actually did, alongside what was asked for."""

    servo_id: int
    status: MotionProbeStatus
    detail: str
    requested_delta_counts: int
    start_counts: Optional[int] = None
    goal_counts: Optional[int] = None
    end_counts: Optional[int] = None
    torque_released: bool = False

    @property
    def ok(self) -> bool:
        return self.status == "success"

    @property
    def moved_counts(self) -> Optional[int]:
        if self.start_counts is None or self.end_counts is None:
            return None
        return self.end_counts - self.start_counts

    @property
    def moved_deg(self) -> Optional[float]:
        moved = self.moved_counts
        return None if moved is None else moved * 360.0 / COUNTS_PER_REV

    def summary(self) -> str:
        if self.moved_counts is None:
            return f"servo {self.servo_id}: [{self.status}] {self.detail}"
        return (
            f"servo {self.servo_id}: [{self.status}] "
            f"{self.start_counts} -> {self.end_counts} counts "
            f"(asked {self.requested_delta_counts:+d}, moved "
            f"{self.moved_counts:+d} = {self.moved_deg:+.1f}deg) -- {self.detail}"
        )


def nudge_servo(
    bus: RegisterBus,
    servo_id: int,
    *,
    delta_counts: int = DEFAULT_NUDGE_COUNTS,
    settle_s: float = 0.5,
    sleep: Callable[[float], None] = time.sleep,
) -> NudgeResult:
    """Move ``servo_id`` by ``delta_counts`` from wherever it currently sits.

    ``sleep`` is injectable so tests do not wait. A ``delta_counts`` of 0 is
    useful in its own right: it exercises torque-enable framing and the read
    path with nothing commanded to move, which is the right first command to
    send to a servo nobody has ever talked to.
    """
    if abs(delta_counts) > MAX_NUDGE_COUNTS:
        return NudgeResult(
            servo_id=servo_id,
            status="refused",
            detail=(
                f"delta {delta_counts:+d} counts exceeds the {MAX_NUDGE_COUNTS}-count "
                f"({MAX_NUDGE_COUNTS * 360.0 / COUNTS_PER_REV:.1f} degree) cap; "
                "nothing was sent to the bus"
            ),
            requested_delta_counts=delta_counts,
        )

    start = bus.read_register(servo_id, ServoRegister.PRESENT_POSITION, 2)
    if start is None:
        return NudgeResult(
            servo_id=servo_id,
            status="no_start_position",
            detail=(
                "could not read Present_Position, so the servo was not commanded "
                "-- run a bus scan first; check power, wiring, ID and baud"
            ),
            requested_delta_counts=delta_counts,
        )

    goal = max(0, min(MAX_POSITION_COUNTS, start + delta_counts))
    end: Optional[int] = None
    failure: Optional[str] = None
    released = False
    try:
        # Neutralise whatever goal the servo is still holding before giving it
        # the power to chase it (see the module docstring).
        bus.write_register(servo_id, ServoRegister.GOAL_POSITION, 2, start)
        bus.set_torque(servo_id, True)
        bus.write_register(servo_id, ServoRegister.GOAL_POSITION, 2, goal)
        sleep(settle_s)
        end = bus.read_register(servo_id, ServoRegister.PRESENT_POSITION, 2)
    except Exception as exc:  # noqa: BLE001 - a probe reports, it does not raise
        failure = str(exc)
        logger.warning("servo %d: motion probe failed: %s", servo_id, exc)
    finally:
        try:
            bus.set_torque(servo_id, False)
            released = True
        except Exception:  # noqa: BLE001
            logger.exception("servo %d: could not release torque", servo_id)

    return NudgeResult(
        servo_id=servo_id,
        status=_classify(start, goal, end, failure),
        detail=_detail(start, goal, end, failure),
        requested_delta_counts=delta_counts,
        start_counts=start,
        goal_counts=goal,
        end_counts=end,
        torque_released=released,
    )


def _classify(
    start: int, goal: int, end: Optional[int], failure: Optional[str]
) -> MotionProbeStatus:
    if failure is not None:
        return "error"
    if end is None:
        return "no_end_position"
    if goal != start and end == start:
        return "did_not_move"
    return "success"


def _detail(start: int, goal: int, end: Optional[int], failure: Optional[str]) -> str:
    if failure is not None:
        return f"bus error during the move: {failure}"
    if end is None:
        return (
            f"commanded {start} -> {goal} counts but could not read the result back; "
            "torque was released"
        )
    if goal != start and end == start:
        return (
            f"the servo accepted goal {goal} but the encoder never left {start}: "
            "the usual cause is no motor power -- connect 7.4V (>=5A) to the "
            "FE-URT-2 screw terminal, USB alone cannot drive a servo"
        )
    if goal == start:
        return "no motion commanded; torque and the read path were exercised"
    return "commanded move completed"
