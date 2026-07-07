"""Servo ID (re)assignment tests: EEPROM unlock/write/lock sequence."""

from __future__ import annotations

from painterbot.control.id_assignment import assign_servo_id
from painterbot.control.serial_controller import (
    MockSerialBackend,
    PySerialBackend,
    get_encoder,
    get_feedback,
)
from painterbot.testing.fake_sts3215 import FakeSTS3215Serial


def _sts_backend(fake: FakeSTS3215Serial) -> PySerialBackend:
    return PySerialBackend(
        "/dev/fake",
        encoder=get_encoder("sts3215"),
        feedback=get_feedback("sts3215"),
        serial_obj=fake,
    )


def test_assign_servo_id_success_sequence():
    fake = FakeSTS3215Serial({1: 90.0})
    result = assign_servo_id(_sts_backend(fake), old_id=1, new_id=5)

    assert result.ok
    assert result.status == "success"
    fb = get_feedback("sts3215")
    assert fake.written == [
        fb.encode_lock(1, False),
        fb.encode_set_id(1, 5),
        fb.encode_lock(5, True),
    ]


def test_assign_servo_id_rejects_out_of_range_new_id():
    fake = FakeSTS3215Serial()
    result = assign_servo_id(_sts_backend(fake), old_id=1, new_id=300)

    assert not result.ok
    assert result.status == "invalid_id"
    assert fake.written == []


def test_assign_servo_id_reports_missing_capability_for_write_only_protocol():
    backend = PySerialBackend(
        "/dev/fake", encoder=get_encoder("ascii_servo"), serial_obj=FakeSTS3215Serial()
    )
    result = assign_servo_id(backend, old_id=1, new_id=5)

    assert not result.ok
    assert result.status == "missing_capability"


def test_assign_servo_id_via_mock_backend_remaps_state():
    backend = MockSerialBackend()
    backend.write_servo(1, 45.0)

    result = assign_servo_id(backend, old_id=1, new_id=5)

    assert result.ok
    assert backend.read_servo(5) == 45.0
