"""Read-only servo preflight diagnostics."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Sequence

from painterbot.control.serial_controller import SerialBackend

ServoPreflightStatus = Literal[
    "success",
    "missing_feedback",
    "no_reply",
    "wrong_id",
    "bad_checksum",
    "error",
]


@dataclass(frozen=True)
class ServoPreflightResult:
    servo_id: int
    status: ServoPreflightStatus
    detail: str
    angle: float | None = None

    @property
    def ok(self) -> bool:
        return self.status == "success"


def read_servo_preflight(
    backend: SerialBackend,
    servo_ids: Sequence[int],
) -> list[ServoPreflightResult]:
    """Read configured servos and classify bring-up failures.

    The function never writes goal positions or toggles torque; it only calls
    ``read_servo`` on the provided backend.
    """
    return [_read_one(backend, servo_id) for servo_id in servo_ids]


def _read_one(backend: SerialBackend, servo_id: int) -> ServoPreflightResult:
    try:
        angle = backend.read_servo(servo_id)
    except RuntimeError as exc:
        return _classify_runtime_error(servo_id, exc)
    if angle is None:
        return ServoPreflightResult(
            servo_id=servo_id,
            status="no_reply",
            detail="servo returned no position",
        )
    return ServoPreflightResult(
        servo_id=servo_id,
        status="success",
        angle=float(angle),
        detail=f"servo replied with position {float(angle):.2f} deg",
    )


def _classify_runtime_error(
    servo_id: int,
    exc: RuntimeError,
) -> ServoPreflightResult:
    detail = str(exc)
    lowered = detail.lower()
    if "write-only" in lowered or "feedback support" in lowered:
        status: ServoPreflightStatus = "missing_feedback"
    elif "no/short" in lowered or "short position reply" in lowered:
        status = "no_reply"
    elif "reply came from id" in lowered:
        status = "wrong_id"
    elif "checksum" in lowered:
        status = "bad_checksum"
    else:
        status = "error"
    return ServoPreflightResult(servo_id=servo_id, status=status, detail=detail)
