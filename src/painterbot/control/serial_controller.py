"""Serial transport for the arm controller.

Two backends share one interface:

* ``PySerialBackend`` — talks to a real controller over USB serial.
* ``MockSerialBackend`` — records commands in memory, no hardware needed.

The wire protocol is intentionally tiny and ASCII so it can be sniffed and
re-implemented on whatever controller firmware we end up with. One command per
line:

    ``S <channel> <angle>\\n``   set servo <channel> to <angle> degrees

The exact framing will be adapted in Phase 1 once the real controller board is
identified; until then the mock backend lets the whole stack run end to end.
"""

from __future__ import annotations

import logging
from typing import Optional, Protocol

logger = logging.getLogger("painterbot.serial")


class SerialBackend(Protocol):
    """Minimal transport interface used by the rest of the package."""

    def write_servo(self, channel: int, angle: float) -> None: ...

    def close(self) -> None: ...

    @property
    def is_mock(self) -> bool: ...


def _encode_servo(channel: int, angle: float) -> bytes:
    return f"S {channel} {angle:.1f}\n".encode("ascii")


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
        logger.info("MOCK %s", _encode_servo(channel, angle).decode().strip())

    def close(self) -> None:
        logger.info("MOCK serial closed (%d commands sent)", len(self.history))


class PySerialBackend:
    """Real USB-serial backend (lazy-imports pyserial so the mock path has no dep)."""

    is_mock = False

    def __init__(self, port: str, baud: int = 115200, timeout_s: float = 1.0) -> None:
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
        payload = _encode_servo(channel, angle)
        self._serial.write(payload)
        logger.info("TX %s", payload.decode().strip())

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
    protocol is ``"mock"``. A real connection requires an explicit ``port``.
    """
    if mock or protocol == "mock":
        return MockSerialBackend()
    if not port:
        raise ValueError(
            "no serial port given; pass --port /dev/tty.usbserial-XXXX or use --mock"
        )
    return PySerialBackend(port=port, baud=baud, timeout_s=timeout_s)
