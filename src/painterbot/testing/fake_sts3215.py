"""Reusable fake serial port for STS3215 protocol tests.

Simulated behavior:
* STS position read requests queue status packets for any configured servo ID.
* Tests can inject short reads, checksum errors, wrong IDs, no reply, and stale
  packets.
* ``reset_input_buffer`` clears queued stale bytes, matching pyserial's API.

Still unknown until hardware arrives:
* Exact timing around servo status packets and write acknowledgements.
* Real error-flag combinations under low voltage, overload, or overheating.
* Whether factory configuration returns extra status bytes for some operations.
"""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass
from typing import Deque, Literal

FaultKind = Literal["short", "bad_checksum", "wrong_id", "no_reply"]

_HEADER = b"\xff\xff"
_INSTR_READ = 0x02
_REG_PRESENT_POSITION = 0x38
_COUNTS_PER_REV = 4096


@dataclass(frozen=True)
class QueuedFault:
    kind: FaultKind
    reply_id: int | None = None


def position_to_counts(angle: float) -> int:
    """Convert a servo angle in degrees to STS3215 encoder counts."""
    return max(0, min(_COUNTS_PER_REV - 1, round(angle * _COUNTS_PER_REV / 360.0)))


def sts_position_reply(servo_id: int, angle: float) -> bytes:
    """Build a valid STS3215 Present_Position status packet."""
    pos = position_to_counts(angle)
    body = [servo_id & 0xFF, 0x04, 0x00, pos & 0xFF, (pos >> 8) & 0xFF]
    return bytes([*_HEADER, *body, (~sum(body)) & 0xFF])


def corrupt_checksum(packet: bytes) -> bytes:
    """Return ``packet`` with a deliberately invalid checksum byte."""
    if not packet:
        return packet
    data = bytearray(packet)
    data[-1] ^= 0xFF
    return bytes(data)


class FakeSTS3215Serial:
    """Small pyserial-compatible fake for STS3215 read/write tests."""

    def __init__(self, positions: dict[int, float] | None = None) -> None:
        self.positions: dict[int, float] = dict(positions or {})
        self.written: list[bytes] = []
        self.closed = False
        self.input_resets = 0
        self._incoming = bytearray()
        self._faults: dict[int, Deque[QueuedFault]] = defaultdict(deque)

    def set_position(self, servo_id: int, angle: float) -> None:
        self.positions[servo_id] = angle

    def queue_fault(
        self,
        servo_id: int,
        kind: FaultKind,
        *,
        reply_id: int | None = None,
    ) -> None:
        self._faults[servo_id].append(QueuedFault(kind=kind, reply_id=reply_id))

    def queue_stale_packet(self, packet: bytes) -> None:
        self._incoming.extend(packet)

    def write(self, payload: bytes) -> None:
        self.written.append(payload)
        servo_id = self._read_request_servo_id(payload)
        if servo_id is None:
            return
        self._incoming.extend(self._next_reply(servo_id))

    def read(self, n: int) -> bytes:
        out = bytes(self._incoming[:n])
        del self._incoming[:n]
        return out

    def reset_input_buffer(self) -> None:
        self.input_resets += 1
        self._incoming.clear()

    def close(self) -> None:
        self.closed = True

    def _next_reply(self, servo_id: int) -> bytes:
        fault = self._faults[servo_id].popleft() if self._faults[servo_id] else None
        reply_id = servo_id if fault is None or fault.reply_id is None else fault.reply_id
        if fault is not None and fault.kind == "no_reply":
            return b""
        if fault is not None and fault.kind == "short":
            return sts_position_reply(reply_id, self.positions.get(servo_id, 0.0))[:4]
        if fault is not None and fault.kind == "wrong_id":
            wrong_id = reply_id if reply_id != servo_id else (servo_id + 1) & 0xFF
            return sts_position_reply(wrong_id, self.positions.get(servo_id, 0.0))
        packet = sts_position_reply(reply_id, self.positions.get(servo_id, 0.0))
        if fault is not None and fault.kind == "bad_checksum":
            return corrupt_checksum(packet)
        return packet

    @staticmethod
    def _read_request_servo_id(payload: bytes) -> int | None:
        if len(payload) < 8 or payload[:2] != _HEADER:
            return None
        if payload[4] != _INSTR_READ:
            return None
        if payload[5] != _REG_PRESENT_POSITION:
            return None
        return payload[2]
