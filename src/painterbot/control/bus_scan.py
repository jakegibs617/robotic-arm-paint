"""Bus discovery: what is physically on the servo bus, and what is it.

This answers a different question from :mod:`painterbot.control.preflight`.
Preflight asks "are the six joints my config expects alive, and where are they?"
-- it trusts the config and reports per-joint health. A scan asks "what is on
this wire at all, at which IDs, at which baud, and what does it say it is?" That
question comes *first*, before the config can be trusted: servos ship at ID 1,
the baud may not be the factory default, and on a fresh build nobody has yet
confirmed a single byte crosses the adapter.

Everything here depends on :class:`ServoProbe`, which cannot write. A scan
therefore cannot move a servo -- that is a property of the types, not a promise.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Callable, Iterable, Optional, Sequence

from painterbot.control.serial_controller import (
    SerialBackend,
    ServoProbe,
    ServoRegister,
)

logger = logging.getLogger("painterbot.bus_scan")

#: Encoder resolution: 4096 counts per full turn, so the centre count 2048 is
#: 180 degrees -- not the 90 degrees a 0..180 hobby servo would sit at.
COUNTS_PER_REV = 4096

#: The broadcast ID. Never probed: every servo answers at once and the replies
#: collide on a half-duplex line, so a "scan" of it teaches us nothing.
BROADCAST_ID = 254
MAX_SERVO_ID = 253

#: Rates an STS3215 can be configured for, factory default first.
DEFAULT_BAUDS: tuple[int, ...] = (
    1_000_000,
    500_000,
    250_000,
    128_000,
    115_200,
    76_800,
    57_600,
    38_400,
)


@dataclass(frozen=True)
class ServoIdentity:
    """What one servo reported about itself.

    Every field past ``error_flags`` is optional because a servo can answer the
    ping and then fall silent mid-interrogation (marginal voltage, a flaky
    connector). Recording that as a partial identity is more useful during
    bring-up than discarding it.
    """

    servo_id: int
    error_flags: int
    model_number: Optional[int] = None
    firmware: Optional[tuple[int, int]] = None
    position_counts: Optional[int] = None
    voltage_dv: Optional[int] = None  # register units: 0.1 V
    temperature_c: Optional[int] = None
    angle_limits_counts: Optional[tuple[int, int]] = None
    baud_code: Optional[int] = None

    @property
    def voltage_v(self) -> Optional[float]:
        return None if self.voltage_dv is None else self.voltage_dv / 10.0

    @property
    def position_deg(self) -> Optional[float]:
        if self.position_counts is None:
            return None
        return self.position_counts * 360.0 / COUNTS_PER_REV

    @property
    def partial(self) -> bool:
        """True when the servo answered the ping but not every register."""
        return any(
            value is None
            for value in (
                self.model_number,
                self.firmware,
                self.position_counts,
                self.voltage_dv,
                self.temperature_c,
                self.angle_limits_counts,
                self.baud_code,
            )
        )

    def summary(self) -> str:
        model = "?" if self.model_number is None else str(self.model_number)
        firmware = "?" if self.firmware is None else f"{self.firmware[0]}.{self.firmware[1]}"
        counts = "?" if self.position_counts is None else str(self.position_counts)
        degrees = "?" if self.position_deg is None else f"{self.position_deg:.1f}deg"
        volts = "?" if self.voltage_v is None else f"{self.voltage_v:.1f}V"
        temp = "?" if self.temperature_c is None else f"{self.temperature_c}C"
        note = " (partial reply)" if self.partial else ""
        return (
            f"id {self.servo_id}: model={model} fw={firmware} pos={counts} "
            f"({degrees}) {volts} {temp} err=0x{self.error_flags:02x}{note}"
        )


def identify_servo(probe: ServoProbe, servo_id: int) -> Optional[ServoIdentity]:
    """Ping ``servo_id`` and, if it answers, read what it says about itself.

    Returns ``None`` when nothing replied. The ping comes first so an absent ID
    costs one packet rather than eight -- which is what makes a wide sweep
    affordable.
    """
    error_flags = probe.ping(servo_id)
    if error_flags is None:
        return None

    def read(register: ServoRegister, length: int) -> Optional[int]:
        return probe.read_register(servo_id, register, length)

    firmware_word = read(ServoRegister.FIRMWARE, 2)
    minimum = read(ServoRegister.MIN_ANGLE_LIMIT, 2)
    maximum = read(ServoRegister.MAX_ANGLE_LIMIT, 2)
    return ServoIdentity(
        servo_id=servo_id,
        error_flags=error_flags,
        model_number=read(ServoRegister.MODEL, 2),
        firmware=(
            None if firmware_word is None else (firmware_word & 0xFF, firmware_word >> 8)
        ),
        position_counts=read(ServoRegister.PRESENT_POSITION, 2),
        voltage_dv=read(ServoRegister.PRESENT_VOLTAGE, 1),
        temperature_c=read(ServoRegister.PRESENT_TEMPERATURE, 1),
        angle_limits_counts=(
            None if minimum is None or maximum is None else (minimum, maximum)
        ),
        baud_code=read(ServoRegister.BAUD_CODE, 1),
    )


@dataclass(frozen=True)
class BusScan:
    """One pass over a set of IDs at one baud."""

    baud: int
    probed_ids: tuple[int, ...]
    found: tuple[ServoIdentity, ...]

    @property
    def is_empty(self) -> bool:
        return not self.found

    @property
    def silent_ids(self) -> tuple[int, ...]:
        answered = {identity.servo_id for identity in self.found}
        return tuple(servo_id for servo_id in self.probed_ids if servo_id not in answered)

    def describe(self) -> str:
        header = (
            f"{len(self.found)}/{len(self.probed_ids)} IDs answered at {self.baud} baud"
        )
        if self.is_empty:
            return (
                f"{header}\n"
                "  no servo answered -- if the bus is not powered this is the "
                "expected result, not a fault: connect 7.4V (>=5A) to the "
                "FE-URT-2 screw terminal, USB alone cannot power a servo"
            )
        lines = [f"  {identity.summary()}" for identity in self.found]
        return "\n".join([header, *lines])


def scan_bus(
    probe: ServoProbe,
    servo_ids: Iterable[int],
    *,
    baud: int,
    on_probe: Optional[Callable[[int, Optional[ServoIdentity]], None]] = None,
) -> BusScan:
    """Probe each ID in turn. Owns nothing -- the caller opened the port.

    ``on_probe`` is called after every ID so a long sweep can report progress
    rather than going quiet for the duration.
    """
    probed: list[int] = []
    found: list[ServoIdentity] = []
    for servo_id in servo_ids:
        identity = identify_servo(probe, servo_id)
        probed.append(servo_id)
        if identity is not None:
            found.append(identity)
        if on_probe is not None:
            on_probe(servo_id, identity)
    return BusScan(baud=baud, probed_ids=tuple(probed), found=tuple(found))


@dataclass(frozen=True)
class BaudAttempt:
    """One baud tried. Exactly one of ``scan``/``open_error`` is set."""

    baud: int
    scan: Optional[BusScan] = None
    open_error: Optional[str] = None


@dataclass(frozen=True)
class BaudSweep:
    attempts: tuple[BaudAttempt, ...]

    @property
    def answered_at(self) -> Optional[int]:
        for attempt in self.attempts:
            if attempt.scan is not None and not attempt.scan.is_empty:
                return attempt.baud
        return None

    def describe(self) -> str:
        lines = []
        for attempt in self.attempts:
            if attempt.open_error is not None:
                lines.append(f"{attempt.baud:>8}: port refused ({attempt.open_error})")
            else:
                lines.append(f"{attempt.baud:>8}: {attempt.scan.describe()}")
        return "\n".join(lines)


def sweep_bauds(
    open_bus_at: Callable[[int], SerialBackend],
    *,
    servo_ids: Sequence[int],
    bauds: Sequence[int] = DEFAULT_BAUDS,
    stop_on_first_reply: bool = True,
    on_attempt: Optional[Callable[[BaudAttempt], None]] = None,
) -> BaudSweep:
    """Scan ``servo_ids`` at each baud until something answers.

    A ``PySerialBackend`` binds its baud when it opens the port, so changing baud
    means a new backend. ``open_bus_at`` is that factory -- injected so the sweep
    is testable without a real port -- and this function owns every backend the
    factory hands it, closing each one before trying the next rate (macOS will
    refuse to reopen a port that is still held).

    A baud the OS or driver refuses outright (250000 and 128000 are not POSIX
    rates) is recorded as an attempt with ``open_error``, not raised: which rates
    the link supports is information about the link.
    """
    attempts: list[BaudAttempt] = []
    for baud in bauds:
        try:
            bus = open_bus_at(baud)
        except Exception as exc:  # noqa: BLE001 - any open failure is data
            logger.warning("baud %d refused: %s", baud, exc)
            attempt = BaudAttempt(baud=baud, open_error=str(exc))
        else:
            try:
                attempt = BaudAttempt(
                    baud=baud, scan=scan_bus(bus, servo_ids, baud=baud)
                )
            finally:
                bus.close()
        attempts.append(attempt)
        if on_attempt is not None:
            on_attempt(attempt)
        if (
            stop_on_first_reply
            and attempt.scan is not None
            and not attempt.scan.is_empty
        ):
            break
    return BaudSweep(attempts=tuple(attempts))


_RANGE_SPEC = re.compile(r"^(-?\d+)\s*-\s*(-?\d+)$")
_SINGLE_SPEC = re.compile(r"^-?\d+$")


def servo_ids_from_spec(spec: str) -> tuple[int, ...]:
    """Parse an ID spec like ``"0-5"``, ``"1"`` or ``"0-2,7"`` into sorted IDs."""
    text = spec.strip()
    if not text:
        raise ValueError("empty servo id spec; try '1', '0-5' or '0-2,7'")
    ids: set[int] = set()
    for part in text.split(","):
        chunk = part.strip()
        span = _RANGE_SPEC.match(chunk)
        if span is not None:
            low, high = int(span.group(1)), int(span.group(2))
            if low > high:
                raise ValueError(f"invalid servo id range {chunk!r}: {low} > {high}")
            ids.update(range(low, high + 1))
        elif _SINGLE_SPEC.match(chunk):
            ids.add(int(chunk))
        else:
            raise ValueError(f"invalid servo id spec {spec!r} at {chunk!r}")
    for servo_id in sorted(ids):
        if servo_id == BROADCAST_ID:
            raise ValueError(
                f"servo id {BROADCAST_ID} is the broadcast address: every servo "
                "would answer at once and the replies would collide on the "
                "half-duplex bus"
            )
        if not 0 <= servo_id <= MAX_SERVO_ID:
            raise ValueError(f"servo id {servo_id} out of range 0..{MAX_SERVO_ID}")
    return tuple(sorted(ids))
