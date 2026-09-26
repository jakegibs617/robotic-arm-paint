"""Which serial device is the servo adapter.

Port discovery used to be a manual ``ls /dev/tty.*usb*`` step in
``docs/hardware_identification.md``, and that doc guessed wrong: the FE-URT-2 on
this build uses a WCH **CH343/CH9102**, which macOS drives with its built-in
CDC-ACM driver and exposes as ``/dev/cu.usbmodem*`` -- not the
``/dev/tty.usbserial-*`` a CH340 would give. Guessing the device name is exactly
the kind of thing a machine should do instead.

Always open the ``/dev/cu.*`` (callout) node rather than ``/dev/tty.*``: the
``tty`` node blocks on open waiting for carrier detect, which a USB-serial
bridge has no reason to assert.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional, Sequence

#: QinHeng/WCH -- CH340, CH343 and CH9102 all live here. The FE-URT-2 uses one.
WCH_VENDOR_ID = 0x1A86

#: USB-serial bridges worth pointing a user at, by vendor ID.
KNOWN_USB_SERIAL_CHIPS: dict[int, str] = {
    WCH_VENDOR_ID: "WCH CH34x/CH343/CH9102",
    0x0403: "FTDI",
    0x10C4: "Silicon Labs CP210x",
    0x067B: "Prolific PL2303",
    0x2341: "Arduino",
}


@dataclass(frozen=True)
class SerialPortInfo:
    """One candidate serial device, with just enough to identify it."""

    device: str
    description: str
    vid: Optional[int] = None
    pid: Optional[int] = None
    serial_number: Optional[str] = None

    @property
    def usb_id(self) -> Optional[str]:
        if self.vid is None or self.pid is None:
            return None
        return f"{self.vid:04x}:{self.pid:04x}"

    @property
    def chip_family(self) -> str:
        if self.vid is None:
            return "not USB"
        return KNOWN_USB_SERIAL_CHIPS.get(self.vid, "unknown USB-serial bridge")

    @property
    def likely_servo_adapter(self) -> bool:
        """A USB-serial bridge we recognise -- i.e. worth trying first."""
        return self.vid in KNOWN_USB_SERIAL_CHIPS


def list_serial_ports(
    comports: Optional[Callable[[], Sequence[object]]] = None,
) -> tuple[SerialPortInfo, ...]:
    """Enumerate serial ports, recognised USB-serial bridges first.

    ``comports`` is injected by tests; by default it is pyserial's, imported
    lazily so the mock path keeps its no-pyserial guarantee.
    """
    if comports is None:
        from serial.tools import list_ports  # type: ignore

        comports = list_ports.comports
    ports = [
        SerialPortInfo(
            device=str(getattr(port, "device", "")),
            description=str(getattr(port, "description", "") or "n/a"),
            vid=getattr(port, "vid", None),
            pid=getattr(port, "pid", None),
            serial_number=getattr(port, "serial_number", None),
        )
        for port in comports()
    ]
    return tuple(sorted(ports, key=lambda p: (not p.likely_servo_adapter, p.device)))


def describe_ports(ports: Sequence[SerialPortInfo]) -> str:
    """A human-readable listing that points at the likely adapter."""
    if not ports:
        return (
            "no serial ports found -- is the FE-URT-2 plugged in? On macOS the "
            "CH343/CH9102 needs no driver and appears as /dev/cu.usbmodem*"
        )
    lines = []
    for port in ports:
        marker = " <- likely servo adapter" if port.likely_servo_adapter else ""
        usb = port.usb_id or "-"
        lines.append(
            f"  {port.device}  {usb}  {port.description} [{port.chip_family}]{marker}"
        )
    lines.append(
        "open the /dev/cu.* node, never /dev/tty.* (tty blocks on carrier detect)"
    )
    return "\n".join(lines)
