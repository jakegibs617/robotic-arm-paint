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
* ``ascii_servo`` — ``S <channel> <angle>\\n`` per line. A human-readable
  **placeholder**; sniff the real board and replace/extend before trusting it.
* ``lx16a``       — LewanSoul / HiWonder LX-16A serial-bus servo binary protocol
  (``SERVO_MOVE_TIME_WRITE``). A concrete worked example of a real framing; only
  correct if the arm actually uses LX-16A servos.

Register your own with ``register_protocol(name, encoder)``.
"""

from __future__ import annotations

import logging
from typing import Callable, Optional, Protocol

logger = logging.getLogger("painterbot.serial")

#: A protocol encoder turns a servo command into the bytes to put on the wire.
ProtocolEncoder = Callable[[int, float], bytes]


class SerialBackend(Protocol):
    """Minimal transport interface used by the rest of the package."""

    def write_servo(self, channel: int, angle: float) -> None: ...

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


# -- protocol registry -------------------------------------------------------

# ``mock`` is handled by MockSerialBackend and has no real wire encoder, so it is
# deliberately absent here; ``open_backend`` short-circuits it.
_ENCODERS: dict[str, ProtocolEncoder] = {
    "ascii_servo": _encode_ascii_servo,
    "lx16a": _encode_lx16a,
}


def register_protocol(name: str, encoder: ProtocolEncoder) -> None:
    """Register (or override) a wire encoder under ``name``."""
    _ENCODERS[name] = encoder


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

    def write_servo(self, channel: int, angle: float) -> None:
        self.history.append((channel, angle))
        self.state[channel] = angle
        logger.info("MOCK %s", _encode_ascii_servo(channel, angle).decode().strip())

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
        serial_obj: object | None = None,
    ) -> None:
        self._encode: ProtocolEncoder = encoder or _encode_ascii_servo
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
    return PySerialBackend(port=port, baud=baud, timeout_s=timeout_s, encoder=encoder)
