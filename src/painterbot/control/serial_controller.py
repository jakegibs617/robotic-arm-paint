"""Serial transport for the arm controller.

Two backends share one interface:

* ``PySerialBackend`` — talks to a real controller over USB serial.
* ``MockSerialBackend`` — records commands in memory, no hardware needed.

The *wire format* is decoupled from the *transport* via a pluggable
``ProtocolEncoder`` — a callable ``(channel, angle) -> bytes``. Encoders are kept
in a small registry and selected by name (the ``serial.protocol`` config key), so
once the real controller board is identified in Phase 1 we can swap the framing
without touching the backend or the rest of the stack.

Built-in protocols:

* ``mock``        — no wire at all; runs fully in software (``MockSerialBackend``).
* ``sts3215``     — Feetech STS/SMS serial-bus servo framing (Dynamixel-1.0-style
  ``0xFF 0xFF`` packets, little-endian registers, 4096 counts per 360°). This is
  the arm's real protocol (STS3215 servos behind an FE-URT USB adapter). Servo
  bus IDs are assumed equal to the config ``channel`` (assign IDs 0..5 during
  bring-up). Framing is per the Feetech memory map but **unverified against
  hardware** until the servos arrive.
* ``ascii_servo`` — ``S <channel> <angle>\\n`` per line. Placeholder kept for the
  Arduino-PWM-bridge fallback path.
* ``lx16a``       — LewanSoul / HiWonder LX-16A serial-bus servo binary protocol
  (``SERVO_MOVE_TIME_WRITE``). Kept as a worked example of another real framing.

Register your own with ``register_protocol(name, encoder)``.

Protocols with servo feedback (position reads, torque on/off) additionally have a
``FeedbackProtocol`` registered; ``sts3215`` is the only built-in one. Feedback
enables hand-guided calibration: torque off, move the arm by hand, read the pose
back from the magnetic encoders.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Callable, Optional, Protocol

logger = logging.getLogger("painterbot.serial")

#: A protocol encoder turns a servo command into the bytes to put on the wire.
ProtocolEncoder = Callable[[int, float], bytes]


class SerialBackend(Protocol):
    """Minimal transport interface used by the rest of the package.

    ``read_servo`` and ``set_torque`` need a protocol with feedback support
    (e.g. ``sts3215``); backends without it raise ``RuntimeError``.
    ``assign_servo_id`` further needs ID-assignment support (``sts3215`` only)
    and writes persistent EEPROM state, unlike the other transient commands.
    """

    def write_servo(self, channel: int, angle: float) -> None: ...

    def read_servo(self, channel: int) -> Optional[float]: ...

    def set_torque(self, channel: int, enabled: bool) -> None: ...

    def assign_servo_id(self, old_id: int, new_id: int) -> None: ...

    def close(self) -> None: ...

    @property
    def is_mock(self) -> bool: ...


# -- wire encoders -----------------------------------------------------------


def _encode_ascii_servo(channel: int, angle: float) -> bytes:
    """``S <channel> <angle>\\n`` — the human-readable placeholder framing."""
    return f"S {channel} {angle:.1f}\n".encode("ascii")


def _encode_lx16a(channel: int, angle: float, *, move_time_ms: int = 0) -> bytes:
    """Encode one LX-16A ``SERVO_MOVE_TIME_WRITE`` packet.

    Frame layout (LewanSoul/HiWonder bus servo):

        0x55 0x55 ID LENGTH CMD PARAM... CHECKSUM

    where ``LENGTH = len(params) + 3``, ``CHECKSUM = ~(ID + LENGTH + CMD + params)``
    (header bytes excluded), and position ``0..1000`` maps linearly to ``0..240``
    degrees. ``move_time_ms`` is the servo-side interpolation time (0 = as fast as
    possible); the package does its own step interpolation so 0 is the default.
    """
    cmd = 1  # SERVO_MOVE_TIME_WRITE
    pos = max(0, min(1000, round(angle / 240.0 * 1000)))
    t = max(0, min(30000, int(move_time_ms)))
    params = [pos & 0xFF, (pos >> 8) & 0xFF, t & 0xFF, (t >> 8) & 0xFF]
    body = [channel & 0xFF, len(params) + 3, cmd, *params]
    checksum = (~sum(body)) & 0xFF
    return bytes([0x55, 0x55, *body, checksum])


# -- Feetech STS3215 (SCS/STS bus servo) --------------------------------------
#
# Frame layout (Dynamixel-protocol-1.0-style):
#
#     0xFF 0xFF ID LENGTH INSTRUCTION PARAM... CHECKSUM
#
# LENGTH = len(params) + 2, CHECKSUM = ~(ID + LENGTH + INSTR + params) & 0xFF
# (header excluded). STS-series registers are little-endian (low byte first).
# Position resolution: 4096 counts per 360° (mid position 2048 = 180°).

_STS_INSTR_READ = 0x02
_STS_INSTR_WRITE = 0x03
_STS_REG_ID = 0x05  # 5, 1 byte (EEPROM)
_STS_REG_LOCK = 0x37  # 55, 1 byte (EEPROM write-protect: 0=unlock, 1=lock)
_STS_REG_TORQUE_ENABLE = 0x28  # 40, 1 byte
_STS_REG_GOAL_POSITION = 0x2A  # 42, 2 bytes
_STS_REG_PRESENT_POSITION = 0x38  # 56, 2 bytes
_STS_COUNTS_PER_REV = 4096
_STS_POSITION_REPLY_LEN = 8  # FF FF ID LEN ERR POS_LO POS_HI CHK
_STS_MAX_ID = 253  # 254 is the broadcast ID; 0..253 are assignable


def _sts_packet(servo_id: int, instruction: int, params: list[int]) -> bytes:
    body = [servo_id & 0xFF, len(params) + 2, instruction, *params]
    checksum = (~sum(body)) & 0xFF
    return bytes([0xFF, 0xFF, *body, checksum])


def _encode_sts3215(channel: int, angle: float) -> bytes:
    """WRITE Goal_Position. The servo bus ID is the config channel (0..5)."""
    pos = max(0, min(_STS_COUNTS_PER_REV - 1, round(angle * _STS_COUNTS_PER_REV / 360.0)))
    params = [_STS_REG_GOAL_POSITION, pos & 0xFF, (pos >> 8) & 0xFF]
    return _sts_packet(channel, _STS_INSTR_WRITE, params)


def _encode_sts3215_torque(channel: int, enabled: bool) -> bytes:
    """WRITE Torque_Enable — 0 makes the servo limp (hand-guidable)."""
    return _sts_packet(
        channel, _STS_INSTR_WRITE, [_STS_REG_TORQUE_ENABLE, 1 if enabled else 0]
    )


def _encode_sts3215_read_position(channel: int) -> bytes:
    """READ 2 bytes at Present_Position."""
    return _sts_packet(channel, _STS_INSTR_READ, [_STS_REG_PRESENT_POSITION, 2])


def _encode_sts3215_lock(channel: int, locked: bool) -> bytes:
    """WRITE Lock — EEPROM (including ID) is write-protected while locked.

    Servos ship locked. Reassigning an ID means unlock -> write ID -> lock; see
    ``_encode_sts3215_set_id`` for why the *lock* packet must address the new ID.
    """
    return _sts_packet(channel, _STS_INSTR_WRITE, [_STS_REG_LOCK, 1 if locked else 0])


def _encode_sts3215_set_id(channel: int, new_id: int) -> bytes:
    """WRITE ID — reassigns the servo's bus ID (EEPROM; must be unlocked first).

    ``channel`` is the servo's *current* ID — the packet is still addressed to
    it, since the servo only switches to ``new_id`` after processing this
    write. Any packet sent *after* this one (e.g. the re-lock) must address
    ``new_id`` instead.
    """
    if not 0 <= new_id <= _STS_MAX_ID:
        raise ValueError(f"servo id {new_id} out of range 0..{_STS_MAX_ID}")
    return _sts_packet(channel, _STS_INSTR_WRITE, [_STS_REG_ID, new_id & 0xFF])


def _parse_sts3215_position_reply(data: bytes, channel: int) -> float:
    """Decode a Present_Position status packet into degrees.

    Raises ``RuntimeError`` on a missing/short/corrupt reply — during bring-up a
    loud, hex-dumped failure beats a silent wrong angle.
    """
    if len(data) < _STS_POSITION_REPLY_LEN:
        raise RuntimeError(
            f"servo {channel}: no/short position reply ({len(data)} bytes: "
            f"{data.hex(' ') or '<empty>'}); check power, wiring, ID and baud"
        )
    if data[0:2] != b"\xff\xff":
        raise RuntimeError(f"servo {channel}: bad reply header {data[:2].hex(' ')}")
    if data[2] != channel:
        raise RuntimeError(f"servo {channel}: reply came from ID {data[2]}")
    if (~sum(data[2:7])) & 0xFF != data[7]:
        raise RuntimeError(f"servo {channel}: reply checksum mismatch ({data.hex(' ')})")
    if data[4] != 0:
        # Error flags (voltage/overheat/overload...) — position is still valid.
        logger.warning("servo %d reports error flags 0x%02x", channel, data[4])
    pos = data[5] | (data[6] << 8)
    return pos * 360.0 / _STS_COUNTS_PER_REV


@dataclass(frozen=True)
class FeedbackProtocol:
    """Optional read/torque capability for bus servos with encoders.

    ``encode_set_id``/``encode_lock`` are further optional: only protocols that
    support reassigning a servo's bus ID (currently just ``sts3215``) set them.
    """

    encode_torque: Callable[[int, bool], bytes]
    encode_read_position: Callable[[int], bytes]
    parse_position_reply: Callable[[bytes, int], float]
    reply_length: int
    encode_set_id: Optional[Callable[[int, int], bytes]] = None
    encode_lock: Optional[Callable[[int, bool], bytes]] = None


# -- protocol registry -------------------------------------------------------

# ``mock`` is handled by MockSerialBackend and has no real wire encoder, so it is
# deliberately absent here; ``open_backend`` short-circuits it.
_ENCODERS: dict[str, ProtocolEncoder] = {
    "ascii_servo": _encode_ascii_servo,
    "lx16a": _encode_lx16a,
    "sts3215": _encode_sts3215,
}

# Protocols that can also read positions and toggle torque.
_FEEDBACK: dict[str, FeedbackProtocol] = {
    "sts3215": FeedbackProtocol(
        encode_torque=_encode_sts3215_torque,
        encode_read_position=_encode_sts3215_read_position,
        parse_position_reply=_parse_sts3215_position_reply,
        reply_length=_STS_POSITION_REPLY_LEN,
        encode_set_id=_encode_sts3215_set_id,
        encode_lock=_encode_sts3215_lock,
    ),
}


def register_protocol(
    name: str,
    encoder: ProtocolEncoder,
    feedback: Optional[FeedbackProtocol] = None,
) -> None:
    """Register (or override) a wire encoder (and optional feedback) under ``name``."""
    _ENCODERS[name] = encoder
    if feedback is not None:
        _FEEDBACK[name] = feedback


def available_protocols() -> list[str]:
    """All selectable protocol names, including the special ``mock``."""
    return ["mock", *sorted(_ENCODERS)]


def get_encoder(protocol: str) -> ProtocolEncoder:
    """Look up the encoder for ``protocol``; raise ``ValueError`` if unknown."""
    try:
        return _ENCODERS[protocol]
    except KeyError:
        raise ValueError(
            f"unknown serial protocol {protocol!r}; "
            f"available: {', '.join(available_protocols())}"
        ) from None


def get_feedback(protocol: str) -> Optional[FeedbackProtocol]:
    """Feedback capability for ``protocol``, or ``None`` if it is write-only."""
    return _FEEDBACK.get(protocol)


# -- backends ----------------------------------------------------------------


class MockSerialBackend:
    """In-memory backend that logs every command instead of sending it.

    Keeps a ``history`` of ``(channel, angle)`` tuples and the latest angle per
    channel in ``state`` — handy for tests and dry-run previews.
    """

    is_mock = True

    def __init__(self) -> None:
        self.history: list[tuple[int, float]] = []
        self.state: dict[int, float] = {}
        self.torque: dict[int, bool] = {}

    def write_servo(self, channel: int, angle: float) -> None:
        self.history.append((channel, angle))
        self.state[channel] = angle
        logger.info("MOCK %s", _encode_ascii_servo(channel, angle).decode().strip())

    def read_servo(self, channel: int) -> Optional[float]:
        """Mock feedback: the servo is exactly where it was last commanded
        (``None`` if never commanded)."""
        return self.state.get(channel)

    def set_torque(self, channel: int, enabled: bool) -> None:
        self.torque[channel] = enabled
        logger.info("MOCK torque ch=%d %s", channel, "on" if enabled else "off")

    def assign_servo_id(self, old_id: int, new_id: int) -> None:
        """Remap any recorded state from ``old_id`` to ``new_id``."""
        if not 0 <= old_id <= _STS_MAX_ID:
            raise ValueError(f"servo id {old_id} out of range 0..{_STS_MAX_ID}")
        if not 0 <= new_id <= _STS_MAX_ID:
            raise ValueError(f"servo id {new_id} out of range 0..{_STS_MAX_ID}")
        if old_id in self.state:
            self.state[new_id] = self.state.pop(old_id)
        if old_id in self.torque:
            self.torque[new_id] = self.torque.pop(old_id)
        logger.info("MOCK servo id %d -> %d", old_id, new_id)

    def close(self) -> None:
        logger.info("MOCK serial closed (%d commands sent)", len(self.history))


class PySerialBackend:
    """Real USB-serial backend (lazy-imports pyserial so the mock path has no dep).

    The wire format is supplied by ``encoder`` so the same transport can speak any
    registered protocol. ``serial_obj`` lets tests inject a fake serial port; when
    it is ``None`` a real ``pyserial`` port is opened.
    """

    is_mock = False

    def __init__(
        self,
        port: str,
        baud: int = 115200,
        timeout_s: float = 1.0,
        *,
        encoder: Optional[ProtocolEncoder] = None,
        feedback: Optional[FeedbackProtocol] = None,
        serial_obj: object | None = None,
    ) -> None:
        self._encode: ProtocolEncoder = encoder or _encode_ascii_servo
        self._feedback = feedback
        if serial_obj is not None:
            self._serial = serial_obj
            logger.info("Using injected serial object for %s", port)
            return
        try:
            import serial  # type: ignore
        except ImportError as exc:  # pragma: no cover - depends on env
            raise RuntimeError(
                "pyserial is required for real hardware; `pip install pyserial` "
                "or use the mock backend (--mock)"
            ) from exc
        self._serial = serial.Serial(port=port, baudrate=baud, timeout=timeout_s)
        logger.info("Opened serial port %s @ %d baud", port, baud)

    def write_servo(self, channel: int, angle: float) -> None:
        payload = self._encode(channel, angle)
        self._serial.write(payload)
        logger.debug("TX ch=%d angle=%.1f bytes=%s", channel, angle, payload.hex(" "))

    def _require_feedback(self, what: str) -> FeedbackProtocol:
        if self._feedback is None:
            raise RuntimeError(
                f"{what} needs a protocol with feedback support (e.g. sts3215); "
                "the current protocol is write-only"
            )
        return self._feedback

    def read_servo(self, channel: int) -> Optional[float]:
        fb = self._require_feedback("read_servo")
        # One retry: a write-ack still in transit at flush time can corrupt the
        # first reply (the parser catches it); the second attempt starts clean.
        last_exc: Optional[RuntimeError] = None
        for attempt in (1, 2):
            # STS servos ack every write by default, so stale status packets may
            # sit in the input buffer — drop them before pairing request/reply.
            reset = getattr(self._serial, "reset_input_buffer", None)
            if reset is not None:
                reset()
            self._serial.write(fb.encode_read_position(channel))
            raw = self._serial.read(fb.reply_length)
            try:
                angle = fb.parse_position_reply(raw, channel)
            except RuntimeError as exc:
                last_exc = exc
                logger.warning("read_servo ch=%d attempt %d failed: %s", channel, attempt, exc)
                continue
            logger.debug("RX ch=%d angle=%.2f bytes=%s", channel, angle, raw.hex(" "))
            return angle
        assert last_exc is not None
        raise last_exc

    def set_torque(self, channel: int, enabled: bool) -> None:
        fb = self._require_feedback("set_torque")
        self._serial.write(fb.encode_torque(channel, enabled))
        logger.info("torque ch=%d %s", channel, "on" if enabled else "off")

    def assign_servo_id(self, old_id: int, new_id: int) -> None:
        """Reassign a servo's bus ID: unlock EEPROM -> write ID -> re-lock.

        Connect exactly **one** servo at a time (see
        docs/hardware_identification.md) — this addresses raw bus IDs, not
        config channels, so a second servo already at ``new_id`` would answer
        too. Unverified against hardware: the register addresses and the
        unlock-before-write sequence are implemented from the Feetech memory
        map, not confirmed against a physical STS3215.
        """
        fb = self._require_feedback("assign_servo_id")
        if fb.encode_set_id is None or fb.encode_lock is None:
            raise RuntimeError(
                "assign_servo_id needs a protocol with ID-assignment support "
                "(e.g. sts3215); the current protocol does not support it"
            )
        # Both ids are validated up front (not just new_id): _sts_packet masks
        # servo_id & 0xFF, so an out-of-range old_id would otherwise silently
        # address a *different* servo on the shared bus instead of raising.
        if not 0 <= old_id <= _STS_MAX_ID:
            raise ValueError(f"servo id {old_id} out of range 0..{_STS_MAX_ID}")
        if not 0 <= new_id <= _STS_MAX_ID:
            raise ValueError(f"servo id {new_id} out of range 0..{_STS_MAX_ID}")
        reset = getattr(self._serial, "reset_input_buffer", None)
        # Each write may draw a status-packet ack; drop it before the next step
        # so it can't be mistaken for a reply to a later read (see read_servo).
        self._serial.write(fb.encode_lock(old_id, False))
        if reset is not None:
            reset()
        self._serial.write(fb.encode_set_id(old_id, new_id))
        if reset is not None:
            reset()
        # The servo has already switched IDs, so the re-lock must address
        # new_id, not old_id.
        self._serial.write(fb.encode_lock(new_id, True))
        if reset is not None:
            reset()
        logger.info("servo id %d -> %d (EEPROM unlock/write/lock)", old_id, new_id)

    def close(self) -> None:
        try:
            self._serial.close()
        finally:
            logger.info("Closed serial port")


def open_backend(
    *,
    mock: bool = False,
    port: Optional[str] = None,
    baud: int = 115200,
    timeout_s: float = 1.0,
    protocol: str = "mock",
) -> SerialBackend:
    """Construct the appropriate backend.

    Falls back to the mock backend when ``mock`` is requested or the config
    protocol is ``"mock"``. A real connection resolves ``protocol`` to a wire
    encoder (raising on an unknown name) and requires an explicit ``port``.
    """
    if mock or protocol == "mock":
        return MockSerialBackend()
    encoder = get_encoder(protocol)  # validates the protocol name up front
    if not port:
        raise ValueError(
            "no serial port given; pass --port /dev/tty.usbserial-XXXX or use --mock"
        )
    return PySerialBackend(
        port=port,
        baud=baud,
        timeout_s=timeout_s,
        encoder=encoder,
        feedback=get_feedback(protocol),
    )
