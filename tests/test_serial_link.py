"""Serial port discovery -- which device is the servo adapter."""

from __future__ import annotations

from dataclasses import dataclass

from painterbot.control.serial_link import (
    WCH_VENDOR_ID,
    describe_ports,
    list_serial_ports,
)


@dataclass
class _Port:
    """Shaped like pyserial's ListPortInfo."""

    device: str
    description: str = "n/a"
    vid: int | None = None
    pid: int | None = None
    serial_number: str | None = None


def _comports():
    return [
        _Port("/dev/cu.Bluetooth-Incoming-Port"),
        _Port(
            "/dev/cu.usbmodem5B790320481",
            "USB Single Serial",
            vid=0x1A86,
            pid=0x55D3,
            serial_number="5B79032048",
        ),
        _Port("/dev/cu.debug-console"),
    ]


def test_lists_ports_with_usb_identifiers():
    ports = list_serial_ports(comports=_comports)

    adapter = next(p for p in ports if "usbmodem" in p.device)
    assert adapter.usb_id == "1a86:55d3"
    assert adapter.description == "USB Single Serial"
    assert adapter.serial_number == "5B79032048"


def test_recognises_the_wch_bridge_used_by_the_fe_urt_2():
    ports = list_serial_ports(comports=_comports)
    by_device = {p.device: p for p in ports}

    adapter = by_device["/dev/cu.usbmodem5B790320481"]
    assert adapter.likely_servo_adapter
    assert "WCH" in adapter.chip_family
    assert WCH_VENDOR_ID == 0x1A86
    # A Bluetooth serial port is not a candidate.
    assert not by_device["/dev/cu.Bluetooth-Incoming-Port"].likely_servo_adapter
    assert by_device["/dev/cu.Bluetooth-Incoming-Port"].usb_id is None


def test_likely_adapters_are_listed_first():
    assert list_serial_ports(comports=_comports)[0].likely_servo_adapter


def test_describe_ports_marks_the_candidate_and_warns_off_tty_nodes():
    text = describe_ports(list_serial_ports(comports=_comports))

    assert "/dev/cu.usbmodem5B790320481" in text
    assert "1a86:55d3" in text
    assert "<-" in text  # the candidate is pointed at
    assert "/dev/cu." in text


def test_describe_ports_says_so_when_nothing_is_plugged_in():
    text = describe_ports(list_serial_ports(comports=lambda: []))

    assert "no serial ports" in text
