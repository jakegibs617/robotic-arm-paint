"""Reusable fake STS3215 serial harness tests."""

from __future__ import annotations

import pytest

from painterbot.control.serial_controller import (
    PySerialBackend,
    get_encoder,
    get_feedback,
)
from painterbot.testing.fake_sts3215 import FakeSTS3215Serial, sts_position_reply


def _backend(fake: FakeSTS3215Serial) -> PySerialBackend:
    return PySerialBackend(
        "/dev/fake",
        encoder=get_encoder("sts3215"),
        feedback=get_feedback("sts3215"),
        serial_obj=fake,
    )


def test_fake_serves_position_replies_for_multiple_ids():
    fake = FakeSTS3215Serial({1: 90.0, 4: 180.0})
    be = _backend(fake)

    assert be.read_servo(1) == pytest.approx(90.0)
    assert be.read_servo(4) == pytest.approx(180.0)
    assert len(fake.written) == 2


def test_fake_can_simulate_short_read_then_success():
    fake = FakeSTS3215Serial({2: 45.0})
    fake.queue_fault(2, "short")
    be = _backend(fake)

    assert be.read_servo(2) == pytest.approx(45.0)
    assert fake.input_resets == 2


def test_fake_can_simulate_checksum_and_wrong_id_failures():
    fake = FakeSTS3215Serial({3: 120.0})
    fake.queue_fault(3, "bad_checksum")
    fake.queue_fault(3, "wrong_id", reply_id=5)
    be = _backend(fake)

    with pytest.raises(RuntimeError, match="reply came from ID"):
        be.read_servo(3)


def test_fake_can_simulate_missing_reply():
    fake = FakeSTS3215Serial({1: 30.0})
    fake.queue_fault(1, "no_reply")
    fake.queue_fault(1, "no_reply")
    be = _backend(fake)

    with pytest.raises(RuntimeError, match="no/short position reply"):
        be.read_servo(1)


def test_fake_clears_stale_packets_on_input_reset():
    fake = FakeSTS3215Serial({1: 60.0})
    fake.queue_stale_packet(sts_position_reply(5, 180.0))
    be = _backend(fake)

    assert be.read_servo(1) == pytest.approx(60.0, abs=0.05)
    assert fake.input_resets == 1
