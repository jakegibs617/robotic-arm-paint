"""Servo bus-ID (re)assignment (Phase 1 bring-up).

Writes an STS3215 servo's ID over the bus: unlock EEPROM, write the new ID,
re-lock EEPROM (see ``PySerialBackend.assign_servo_id``). This is the one
bring-up operation in this package that writes persistent (EEPROM) servo
state rather than a transient goal position or torque flag, so it is kept out
of ``control/preflight.py`` (read-only) and given its own explicit result type
rather than silently succeeding or raising.

Do this **one servo at a time** on the bus (see
docs/hardware_identification.md) — addressing is by raw bus ID, so a second
servo already at ``new_id`` would answer too. Unverified against hardware:
implemented from the Feetech memory map only.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from painterbot.control.serial_controller import SerialBackend

IdAssignmentStatus = Literal["success", "missing_capability", "invalid_id", "error"]


@dataclass(frozen=True)
class IdAssignmentResult:
    old_id: int
    new_id: int
    status: IdAssignmentStatus
    detail: str

    @property
    def ok(self) -> bool:
        return self.status == "success"


def assign_servo_id(
    backend: SerialBackend,
    old_id: int,
    new_id: int,
) -> IdAssignmentResult:
    """Reassign one servo's bus ID and classify the outcome.

    Connect exactly one servo before calling this — see the module docstring.
    Never raises: hardware/config problems come back as a non-``ok`` result.
    ``"success"`` means the three writes were sent without error — none of them
    are read back, so it is not proof the servo actually applied them. Follow
    up with a ``ping`` at the new ID before trusting it.
    """
    try:
        backend.assign_servo_id(old_id, new_id)
    except ValueError as exc:
        return IdAssignmentResult(old_id, new_id, "invalid_id", str(exc))
    except RuntimeError as exc:
        detail = str(exc)
        status: IdAssignmentStatus = (
            "missing_capability" if "support" in detail.lower() else "error"
        )
        return IdAssignmentResult(old_id, new_id, status, detail)
    return IdAssignmentResult(
        old_id,
        new_id,
        "success",
        f"sent unlock/write-id/lock for servo {old_id} -> {new_id} "
        "(not read back; verify with `bringup ping` before trusting it)",
    )
