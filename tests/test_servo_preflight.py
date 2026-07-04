"""Read-only servo preflight diagnostics."""

from __future__ import annotations

from painterbot.control.preflight import read_servo_preflight
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


def test_preflight_reports_success_for_fake_sts3215():
    fake = FakeSTS3215Serial({1: 90.0, 2: 180.0})
    results = read_servo_preflight(_sts_backend(fake), [1, 2])

    assert [r.status for r in results] == ["success", "success"]
    assert results[0].ok
    assert results[0].angle == 90.0
    assert len(fake.written) == 2


def test_preflight_reports_missing_feedback_for_write_only_protocol():
    backend = PySerialBackend(
        "/dev/fake",
        encoder=get_encoder("ascii_servo"),
        serial_obj=FakeSTS3215Serial(),
    )
    result = read_servo_preflight(backend, [1])[0]

    assert result.status == "missing_feedback"
    assert not result.ok
    assert result.angle is None
    assert "write-only" in result.detail


def test_preflight_distinguishes_serial_reply_failures():
    fake = FakeSTS3215Serial({1: 90.0, 2: 90.0, 3: 90.0})
    fake.queue_fault(1, "no_reply")
    fake.queue_fault(1, "no_reply")
    fake.queue_fault(2, "bad_checksum")
    fake.queue_fault(2, "bad_checksum")
    fake.queue_fault(3, "wrong_id", reply_id=4)
    fake.queue_fault(3, "wrong_id", reply_id=4)

    results = read_servo_preflight(_sts_backend(fake), [1, 2, 3])

    assert [r.status for r in results] == ["no_reply", "bad_checksum", "wrong_id"]


def test_preflight_does_not_move_servos():
    fake = FakeSTS3215Serial({1: 45.0})
    backend = _sts_backend(fake)

    read_servo_preflight(backend, [1])

    assert len(fake.written) == 1
    assert fake.written[0] == get_feedback("sts3215").encode_read_position(1)


def test_preflight_treats_mock_none_as_no_reply():
    result = read_servo_preflight(MockSerialBackend(), [0])[0]

    assert result.status == "no_reply"
    assert result.detail == "servo returned no position"
