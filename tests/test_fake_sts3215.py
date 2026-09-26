"""Reusable fake STS3215 serial harness tests."""

from __future__ import annotations

import pytest

from painterbot.control.serial_controller import (
    PySerialBackend,
    ServoRegister,
    get_encoder,
    get_feedback,
)
from painterbot.testing.fake_sts3215 import (
    FakeEchoingSerial,
    FakeGarbledSerial,
    FakeSTS3215Serial,
    SimulatedServo,
    sts_position_reply,
)


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


# -- bus presence, ping, and arbitrary register access ------------------------


def _regs():
    return get_feedback("sts3215").registers


def test_fake_is_silent_for_unconfigured_ids():
    # A bus servo that is not on the wire says nothing at all -- the `positions`
    # keys are the set of servos that exist.
    fake = FakeSTS3215Serial({1: 90.0})
    regs = _regs()

    fake.write(regs.encode_read(7, ServoRegister.PRESENT_POSITION, 2))

    assert fake.read(8) == b""


def test_fake_answers_ping_with_a_bare_status_packet():
    fake = FakeSTS3215Serial({1: SimulatedServo(position_counts=2048, error_flags=0x04)})
    regs = _regs()

    fake.write(regs.encode_ping(1))
    reply = fake.read(regs.status_length)

    assert len(reply) == 6
    assert regs.parse_status(reply, 1) == 0x04


def test_fake_ignores_pings_to_absent_servos():
    fake = FakeSTS3215Serial({1: 90.0})
    regs = _regs()

    fake.write(regs.encode_ping(9))

    assert fake.read(6) == b""


def test_fake_serves_identity_and_telemetry_registers():
    fake = FakeSTS3215Serial(
        {
            1: SimulatedServo(
                position_counts=2043,
                model_number=777,
                firmware=(3, 10),
                voltage_dv=74,
                temperature_c=32,
            )
        }
    )
    regs = _regs()

    def read(address, length):
        fake.write(regs.encode_read(1, address, length))
        return regs.parse_read_reply(fake.read(regs.read_reply_length(length)), 1, length)

    assert read(ServoRegister.MODEL, 2) == 777
    assert read(ServoRegister.FIRMWARE, 1) == 3
    assert read(ServoRegister.ID, 1) == 1
    assert read(ServoRegister.PRESENT_POSITION, 2) == 2043
    assert read(ServoRegister.PRESENT_VOLTAGE, 1) == 74
    assert read(ServoRegister.PRESENT_TEMPERATURE, 1) == 32


def test_fake_goal_position_write_moves_the_simulated_servo():
    fake = FakeSTS3215Serial({1: SimulatedServo(position_counts=2000)})
    regs = _regs()

    fake.write(regs.encode_write(1, ServoRegister.GOAL_POSITION, 2, 2100))
    fake.write(regs.encode_read(1, ServoRegister.PRESENT_POSITION, 2))

    assert regs.parse_read_reply(fake.read(8), 1, 2) == 2100


def test_fake_stuck_servo_accepts_a_goal_without_moving():
    # The symptom of logic power but no motor power: the write lands, the
    # encoder never follows.
    fake = FakeSTS3215Serial({1: SimulatedServo(position_counts=2000, stuck=True)})
    regs = _regs()

    fake.write(regs.encode_write(1, ServoRegister.GOAL_POSITION, 2, 2100))
    fake.write(regs.encode_read(1, ServoRegister.PRESENT_POSITION, 2))

    assert regs.parse_read_reply(fake.read(8), 1, 2) == 2000


def test_fake_writes_are_silent_unless_acks_are_enabled():
    # Conservative default: the repo has never confirmed that a real STS3215
    # acks writes (Response Status Level), so the fake does not pretend it does.
    regs = _regs()
    silent = FakeSTS3215Serial({1: SimulatedServo()})
    silent.write(regs.encode_write(1, ServoRegister.TORQUE_ENABLE, 1, 1))
    assert silent.read(6) == b""

    acking = FakeSTS3215Serial({1: SimulatedServo()}, ack_writes=True)
    acking.write(regs.encode_write(1, ServoRegister.TORQUE_ENABLE, 1, 1))
    assert regs.parse_status(acking.read(6), 1) == 0


def test_fake_records_parsed_requests_not_just_bytes():
    fake = FakeSTS3215Serial({1: SimulatedServo()})
    regs = _regs()

    fake.write(regs.encode_ping(1))
    fake.write(regs.encode_read(1, ServoRegister.MODEL, 2))
    fake.write(regs.encode_write(1, ServoRegister.TORQUE_ENABLE, 1, 0))

    assert [(r.instruction, r.address) for r in fake.requests] == [
        (0x01, None),
        (0x02, int(ServoRegister.MODEL)),
        (0x03, int(ServoRegister.TORQUE_ENABLE)),
    ]


def test_fake_accepts_degrees_or_simulated_servo():
    fake = FakeSTS3215Serial({1: 180.0, 2: SimulatedServo(position_counts=1024)})
    regs = _regs()

    fake.write(regs.encode_read(1, ServoRegister.PRESENT_POSITION, 2))
    assert regs.parse_read_reply(fake.read(8), 1, 2) == 2048
    fake.write(regs.encode_read(2, ServoRegister.PRESENT_POSITION, 2))
    assert regs.parse_read_reply(fake.read(8), 2, 2) == 1024


def test_fake_garbage_fault_yields_non_frame_bytes():
    fake = FakeSTS3215Serial({1: SimulatedServo()})
    fake.queue_fault(1, "garbage")
    regs = _regs()

    fake.write(regs.encode_read(1, ServoRegister.PRESENT_POSITION, 2))
    reply = fake.read(8)

    assert reply[:2] != b"\xff\xff"
    with pytest.raises(RuntimeError):
        regs.parse_read_reply(reply, 1, 2)


def test_garbled_serial_answers_every_request_with_noise():
    # Models a port opened at the wrong baud: bytes arrive, none of them frame.
    fake = FakeGarbledSerial()
    regs = _regs()

    fake.write(regs.encode_ping(1))
    reply = fake.read(6)

    assert reply
    assert reply[:2] != b"\xff\xff"


def test_echoing_serial_returns_the_request_verbatim():
    # Models a half-duplex adapter looping TX into RX -- the case that makes an
    # echoed request parse as a valid reply.
    fake = FakeEchoingSerial()
    regs = _regs()
    request = regs.encode_read(1, ServoRegister.PRESENT_POSITION, 2)

    fake.write(request)

    assert fake.read(8) == request


def test_fake_models_implicit_torque_enable_on_a_differing_goal():
    """Confirmed on hardware 2026-09-26: writing a Goal_Position that differs
    from the present position implicitly enables torque, while writing a goal
    equal to the present position does not. A goal write is not inert."""
    fake = FakeSTS3215Serial({1: SimulatedServo(position_counts=2000, stuck=True)})
    regs = _regs()

    fake.write(regs.encode_write(1, ServoRegister.GOAL_POSITION, 2, 2000))
    assert fake.servos[1].torque_enabled is False

    fake.write(regs.encode_write(1, ServoRegister.GOAL_POSITION, 2, 2100))
    assert fake.servos[1].torque_enabled is True
