"""Reusable fake serial port for STS3215 protocol tests.

This is a pyserial-shaped fake *port*, not a bus simulator: it parses the
requests the ``sts3215`` protocol writes and answers them from a small
``SimulatedServo`` record, so the whole bring-up stack (ping, register reads,
bus scan, bounded motion) is testable with no hardware and no servo power.

Simulated behavior:
* The ``positions`` keys are the set of servos that **exist**. An unconfigured
  ID gets silence, which is what an absent servo (or an unpowered bus) does.
* PING, register reads, and register writes are all parsed and served. A write
  to Goal_Position moves Present_Position unless the servo is ``stuck``.
* Tests can inject short reads, checksum errors, wrong IDs, no reply, garbage
  bytes, and stale packets.
* ``reset_input_buffer`` clears queued stale bytes, matching pyserial's API.

Two sibling fakes model failures that are about the *link* rather than a servo:
* ``FakeGarbledSerial`` -- a port open at the wrong baud: bytes arrive, none frame.
* ``FakeEchoingSerial`` -- a half-duplex adapter looping TX into RX. This one
  matters more than it looks: an echoed request can satisfy every validation
  check and decode as a plausible position (see ``PySerialBackend.exchange``).

Confirmed against a physical STS3215 on 2026-09-26 (bus powered from USB only,
4.3 V, so reads only -- see docs/hardware_identification.md):
* PING, register reads, framing, checksums and little-endian decoding all work.
* Model number is 777 (MODEL_L=9, MODEL_H=3), firmware 3.10, factory ID 1 at
  1,000,000 baud, angle limits 0..4095 counts. The defaults below match.
* No adapter echo on this FE-URT-2.
* **Response Status Level (0x08) is 1: the servo acks every write.** Those acks
  land in the input buffer between operations, which is why every read flushes
  before pairing request and reply. Tests that set ``ack_writes=True`` cover it.
* At rest the servo reports ``TORQUE_ENABLE=0`` and a **stale
  ``GOAL_POSITION`` of 0** while sitting at 4094 counts -- so enabling torque
  without first overwriting the goal commands a near-full-turn slam. See
  ``painterbot.control.motion_probe``.
* Its own voltage protection window is 4.0-8.0 V (0x0f/0x0e), which is why it
  boots at all on USB. Note 8.0 V, not 8.4: a freshly charged 2S LiPo is over
  the servo's own limit.
* Operating mode 0 (position), max torque limit 1000, max temperature limit
  70 C.

Still unknown:
* Everything about the write path: torque enable, goal position, and the sign
  and scale of the counts-to-motion mapping. The bench servo was under-voltage
  (4.3 V, against 6 V minimum for operation), so nothing has been commanded to
  move. ``ack_writes`` still defaults to ``False`` so existing tests keep their
  simpler expectations; the real servo acks.
* The meaning of register 0x02.
* Exact timing around servo status packets and write acknowledgements.
* Real error-flag combinations under low voltage, overload, or overheating --
  notably, 4.3 V produced error flags 0x00, not an under-voltage flag.
* Whether the EEPROM unlock/write-ID/re-lock sequence in
  ``PySerialBackend.assign_servo_id`` behaves as the memory map implies -- this
  fake does not simulate EEPROM persistence or ID remapping.
"""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Deque, Literal, Union

from painterbot.control.serial_controller import COUNTS_PER_REV, ServoRegister

FaultKind = Literal["short", "bad_checksum", "wrong_id", "no_reply", "garbage"]

_HEADER = b"\xff\xff"
_INSTR_PING = 0x01
_INSTR_READ = 0x02
_INSTR_WRITE = 0x03
_COUNTS_PER_REV = COUNTS_PER_REV
_GARBAGE = bytes([0x7F, 0x00, 0xFE, 0x81, 0x03, 0xC0, 0x55, 0xAA])


@dataclass(frozen=True)
class QueuedFault:
    kind: FaultKind
    reply_id: int | None = None


@dataclass(frozen=True)
class FakeRequest:
    """A request the fake parsed off the wire, so tests can assert on intent."""

    servo_id: int
    instruction: int
    address: int | None = None
    length: int | None = None
    payload: bytes = b""


@dataclass
class SimulatedServo:
    """One servo's worth of control table, in the units the registers use.

    Defaults describe a healthy 7.4 V STS3215 sitting at its centre count.
    ``model_number`` and ``firmware`` are the values a physical STS3215 actually
    reported (see the module docstring); ``voltage_dv`` is the nominal powered
    value rather than an observed one.
    """

    position_counts: int = 2048
    model_number: int = 777  # MODEL_L=9, MODEL_H=3 -- confirmed on hardware
    firmware: tuple[int, int] = (3, 10)  # confirmed on hardware
    voltage_dv: int = 74  # register units: 0.1 V
    temperature_c: int = 32
    error_flags: int = 0
    min_angle_counts: int = 0
    max_angle_counts: int = _COUNTS_PER_REV - 1
    baud_code: int = 0
    #: Accepts a goal but never moves -- the symptom of logic power with no
    #: motor power, which is exactly the bench state before 7.4V is wired.
    stuck: bool = False
    torque_enabled: bool = False
    locked: bool = True
    goal_counts: int | None = None
    #: Every write the fake could not model, as {address: payload}.
    unmodelled_writes: dict[int, bytes] = field(default_factory=dict)


ServoSpec = Union[float, int, SimulatedServo]


def position_to_counts(angle: float) -> int:
    """Convert a servo angle in degrees to STS3215 encoder counts."""
    return max(0, min(_COUNTS_PER_REV - 1, round(angle * _COUNTS_PER_REV / 360.0)))


def _status_frame(servo_id: int, error: int, payload: bytes) -> bytes:
    body = [servo_id & 0xFF, len(payload) + 2, error & 0xFF, *payload]
    return bytes([*_HEADER, *body, (~sum(body)) & 0xFF])


def sts_status_reply(servo_id: int, error: int = 0) -> bytes:
    """Build a bare STS3215 acknowledgement (the reply to a PING or a write)."""
    return _status_frame(servo_id, error, b"")


def sts_register_reply(servo_id: int, values: bytes, error: int = 0) -> bytes:
    """Build an STS3215 status packet carrying ``values`` as its payload."""
    return _status_frame(servo_id, error, values)


def sts_position_reply(servo_id: int, angle: float) -> bytes:
    """Build a valid STS3215 Present_Position status packet."""
    counts = position_to_counts(angle)
    return sts_register_reply(servo_id, counts.to_bytes(2, "little"))


def corrupt_checksum(packet: bytes) -> bytes:
    """Return ``packet`` with a deliberately invalid checksum byte."""
    if not packet:
        return packet
    data = bytearray(packet)
    data[-1] ^= 0xFF
    return bytes(data)


def _readdress(packet: bytes, servo_id: int) -> bytes:
    """Re-issue ``packet`` as if it came from ``servo_id`` (checksum fixed up)."""
    if len(packet) < 6:
        return packet
    return _status_frame(servo_id, packet[4], packet[5:-1])


def _register_bytes(servo: SimulatedServo, servo_id: int) -> dict[int, int]:
    """The servo's control table as {address: byte}, rebuilt per read.

    Only the registers bring-up actually touches are modelled; anything else
    reads back as zero, which is honest -- the fake does not know the rest of the
    memory map either.
    """
    table: dict[int, int] = {}

    def put_byte(address: int, value: int) -> None:
        table[int(address)] = value & 0xFF

    def put_word(address: int, value: int) -> None:
        put_byte(address, value & 0xFF)
        put_byte(int(address) + 1, (value >> 8) & 0xFF)

    put_byte(ServoRegister.FIRMWARE, servo.firmware[0])
    put_byte(int(ServoRegister.FIRMWARE) + 1, servo.firmware[1])
    put_word(ServoRegister.MODEL, servo.model_number)
    put_byte(ServoRegister.ID, servo_id)
    put_byte(ServoRegister.BAUD_CODE, servo.baud_code)
    put_word(ServoRegister.MIN_ANGLE_LIMIT, servo.min_angle_counts)
    put_word(ServoRegister.MAX_ANGLE_LIMIT, servo.max_angle_counts)
    put_byte(ServoRegister.TORQUE_ENABLE, int(servo.torque_enabled))
    put_word(
        ServoRegister.GOAL_POSITION,
        servo.position_counts if servo.goal_counts is None else servo.goal_counts,
    )
    put_byte(ServoRegister.LOCK, int(servo.locked))
    put_word(ServoRegister.PRESENT_POSITION, servo.position_counts)
    put_byte(ServoRegister.PRESENT_VOLTAGE, servo.voltage_dv)
    put_byte(ServoRegister.PRESENT_TEMPERATURE, servo.temperature_c)
    return table


def _apply_write(servo: SimulatedServo, address: int, payload: bytes) -> None:
    value = int.from_bytes(payload, "little") if payload else 0
    if address == ServoRegister.GOAL_POSITION:
        servo.goal_counts = value
        if value != servo.position_counts:
            # Confirmed on hardware: a goal that differs from the present
            # position implicitly enables torque, while a goal equal to it does
            # not. So a goal write is never inert -- it is the act of
            # energising, which is why nothing can "pre-stage" a goal.
            servo.torque_enabled = True
        if not servo.stuck:
            servo.position_counts = value
    elif address == ServoRegister.TORQUE_ENABLE:
        servo.torque_enabled = bool(value)
    elif address == ServoRegister.LOCK:
        servo.locked = bool(value)
    else:
        servo.unmodelled_writes[address] = payload


def _parse_request(payload: bytes) -> FakeRequest | None:
    if len(payload) < 6 or payload[:2] != _HEADER:
        return None
    servo_id, length, instruction = payload[2], payload[3], payload[4]
    params = payload[5 : 3 + length]
    if instruction == _INSTR_PING:
        return FakeRequest(servo_id=servo_id, instruction=instruction)
    if instruction == _INSTR_READ and len(params) >= 2:
        return FakeRequest(
            servo_id=servo_id,
            instruction=instruction,
            address=params[0],
            length=params[1],
        )
    if instruction == _INSTR_WRITE and len(params) >= 1:
        return FakeRequest(
            servo_id=servo_id,
            instruction=instruction,
            address=params[0],
            payload=bytes(params[1:]),
        )
    return None


class FakeSTS3215Serial:
    """Small pyserial-compatible fake for STS3215 read/write tests."""

    def __init__(
        self,
        positions: dict[int, ServoSpec] | None = None,
        *,
        ack_writes: bool = False,
    ) -> None:
        self.servos: dict[int, SimulatedServo] = {
            servo_id: _coerce_servo(spec) for servo_id, spec in (positions or {}).items()
        }
        self.ack_writes = ack_writes
        self.written: list[bytes] = []
        self.requests: list[FakeRequest] = []
        self.closed = False
        self.input_resets = 0
        self._incoming = bytearray()
        self._faults: dict[tuple[int, int | None], Deque[QueuedFault]] = defaultdict(
            deque
        )

    # -- test-facing state ---------------------------------------------------

    def set_position(self, servo_id: int, angle: float) -> None:
        counts = position_to_counts(angle)
        servo = self.servos.get(servo_id)
        if servo is None:
            self.servos[servo_id] = SimulatedServo(position_counts=counts)
        else:
            servo.position_counts = counts

    def queue_fault(
        self,
        servo_id: int,
        kind: FaultKind,
        *,
        reply_id: int | None = None,
        instruction: int | None = None,
    ) -> None:
        """Queue one fault for ``servo_id``'s next reply.

        ``instruction`` narrows it to replies to that instruction (0x01 ping,
        0x02 read, 0x03 write), so a test can say "answers the ping, then goes
        quiet on the register reads" -- a real marginal-voltage symptom.
        """
        self._faults[(servo_id, instruction)].append(
            QueuedFault(kind=kind, reply_id=reply_id)
        )

    def queue_stale_packet(self, packet: bytes) -> None:
        self._incoming.extend(packet)

    # -- pyserial surface ----------------------------------------------------

    def write(self, payload: bytes) -> None:
        self.written.append(payload)
        request = _parse_request(payload)
        if request is None:
            return
        self.requests.append(request)
        servo = self.servos.get(request.servo_id)
        if servo is None:
            return  # absent servo: silence, not a zeroed reply
        reply = self._ideal_reply(servo, request)
        if reply is None:
            return
        self._incoming.extend(
            self._apply_faults(request.servo_id, request.instruction, reply)
        )

    def read(self, n: int) -> bytes:
        out = bytes(self._incoming[:n])
        del self._incoming[:n]
        return out

    def reset_input_buffer(self) -> None:
        self.input_resets += 1
        self._incoming.clear()

    def close(self) -> None:
        self.closed = True

    # -- internals -----------------------------------------------------------

    def _ideal_reply(self, servo: SimulatedServo, request: FakeRequest) -> bytes | None:
        if request.instruction == _INSTR_PING:
            return sts_status_reply(request.servo_id, servo.error_flags)
        if request.instruction == _INSTR_READ:
            table = _register_bytes(servo, request.servo_id)
            values = bytes(
                table.get(int(request.address) + offset, 0)
                for offset in range(request.length or 0)
            )
            return sts_register_reply(request.servo_id, values, servo.error_flags)
        if request.instruction == _INSTR_WRITE:
            _apply_write(servo, int(request.address), request.payload)
            if self.ack_writes:
                return sts_status_reply(request.servo_id, servo.error_flags)
            return None
        return None

    def _apply_faults(self, servo_id: int, instruction: int, packet: bytes) -> bytes:
        fault = None
        for key in ((servo_id, instruction), (servo_id, None)):
            queued = self._faults.get(key)  # .get, so a scan does not insert
            if queued:                       # an empty deque per ID probed
                fault = queued.popleft()
                break
        if fault is None:
            return packet
        if fault.kind == "no_reply":
            return b""
        if fault.kind == "garbage":
            return _GARBAGE[: max(len(packet), 4)]
        if fault.kind == "short":
            return packet[:4]
        if fault.kind == "wrong_id":
            wrong_id = (
                fault.reply_id
                if fault.reply_id is not None and fault.reply_id != servo_id
                else (servo_id + 1) & 0xFF
            )
            return _readdress(packet, wrong_id)
        if fault.kind == "bad_checksum":
            return corrupt_checksum(packet)
        return packet


def _coerce_servo(spec: ServoSpec) -> SimulatedServo:
    if isinstance(spec, SimulatedServo):
        return spec
    return SimulatedServo(position_counts=position_to_counts(float(spec)))


class FakeGarbledSerial:
    """A port open at the wrong baud: every request draws non-frame noise."""

    def __init__(self, pattern: bytes = _GARBAGE) -> None:
        self.pattern = pattern
        self.written: list[bytes] = []
        self.closed = False
        self.input_resets = 0
        self._incoming = bytearray()

    def write(self, payload: bytes) -> None:
        self.written.append(payload)
        self._incoming.extend(self.pattern)

    def read(self, n: int) -> bytes:
        out = bytes(self._incoming[:n])
        del self._incoming[:n]
        return out

    def reset_input_buffer(self) -> None:
        self.input_resets += 1
        self._incoming.clear()

    def close(self) -> None:
        self.closed = True


class FakeEchoingSerial:
    """A half-duplex adapter looping TX into RX: the reply *is* the request.

    Kept as its own fake because the failure is electrical, not protocol-level,
    and because an echoed request passes header, ID, and checksum validation --
    it must be caught by comparing the reply to the request, nothing else.
    """

    def __init__(self) -> None:
        self.written: list[bytes] = []
        self.closed = False
        self.input_resets = 0
        self._incoming = bytearray()

    def write(self, payload: bytes) -> None:
        self.written.append(payload)
        self._incoming.extend(payload)

    def read(self, n: int) -> bytes:
        out = bytes(self._incoming[:n])
        del self._incoming[:n]
        return out

    def reset_input_buffer(self) -> None:
        self.input_resets += 1
        self._incoming.clear()

    def close(self) -> None:
        self.closed = True
