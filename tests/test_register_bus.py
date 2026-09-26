"""Register-level bus access: single-exchange, non-retrying servo probing."""

from __future__ import annotations

import pytest

from painterbot.control.serial_controller import (
    FeedbackProtocol,
    PySerialBackend,
    ServoEchoError,
    ServoRegister,
    get_encoder,
    get_feedback,
    register_protocol,
)
from painterbot.testing.fake_sts3215 import (
    FakeEchoingSerial,
    FakeGarbledSerial,
    FakeSTS3215Serial,
    SimulatedServo,
)


def _bus(fake) -> PySerialBackend:
    return PySerialBackend(
        "/dev/fake",
        encoder=get_encoder("sts3215"),
        feedback=get_feedback("sts3215"),
        serial_obj=fake,
    )


def test_ping_returns_error_flags_and_flushes_stale_input():
    fake = FakeSTS3215Serial({1: SimulatedServo(error_flags=0x04)})
    fake.queue_stale_packet(b"\xff\xff\x09\x02\x00\xf4")
    bus = _bus(fake)

    assert bus.ping(1) == 0x04
    assert fake.input_resets == 1
    assert len(fake.written) == 1


def test_ping_absent_servo_returns_none_without_retrying():
    # Deliberately unlike read_servo, which retries once (two writes). A scan of
    # 254 IDs cannot afford a hidden second attempt per absent ID.
    fake = FakeSTS3215Serial({1: SimulatedServo()})
    bus = _bus(fake)

    assert bus.ping(9) is None
    assert len(fake.written) == 1


def test_read_servo_still_retries_once():
    fake = FakeSTS3215Serial({})
    bus = _bus(fake)

    with pytest.raises(RuntimeError):
        bus.read_servo(1)
    assert len(fake.written) == 2


def test_read_register_returns_the_window_value():
    fake = FakeSTS3215Serial(
        {1: SimulatedServo(position_counts=2043, model_number=777, temperature_c=32)}
    )
    bus = _bus(fake)

    assert bus.read_register(1, ServoRegister.MODEL, 2) == 777
    assert bus.read_register(1, ServoRegister.PRESENT_POSITION, 2) == 2043
    assert bus.read_register(1, ServoRegister.PRESENT_TEMPERATURE, 1) == 32


def test_read_register_returns_none_on_silence_and_on_noise():
    assert _bus(FakeSTS3215Serial({})).read_register(1, ServoRegister.MODEL, 2) is None
    assert _bus(FakeGarbledSerial()).read_register(1, ServoRegister.MODEL, 2) is None


def test_write_register_sends_a_little_endian_write_frame():
    fake = FakeSTS3215Serial({1: SimulatedServo(position_counts=2000)})
    bus = _bus(fake)

    bus.write_register(1, ServoRegister.GOAL_POSITION, 2, 2100)

    assert fake.written[-1] == bytes([0xFF, 0xFF, 0x01, 0x05, 0x03, 0x2A, 0x34, 0x08, 0x90])
    assert fake.servos[1].position_counts == 2100


def test_echoed_request_is_reported_not_decoded_as_a_position():
    # A half-duplex adapter looping TX into RX echoes our request. The echo of a
    # 2-byte position read is a structurally valid status packet: right header,
    # right ID, correct checksum -- and it decodes to 0x0238 = 568 counts =
    # 49.9 deg. Every other validation layer passes it, so the only defence is
    # comparing the reply against the request.
    bus = _bus(FakeEchoingSerial())

    with pytest.raises(ServoEchoError, match="echo"):
        bus.read_register(1, ServoRegister.PRESENT_POSITION, 2)
    with pytest.raises(ServoEchoError, match="echo"):
        bus.ping(1)


def test_read_servo_also_refuses_an_echoed_reply():
    # The same phantom would otherwise reach Arm/Servo as a real joint angle.
    bus = _bus(FakeEchoingSerial())

    with pytest.raises(ServoEchoError, match="echo"):
        bus.read_servo(1)


def test_echo_error_is_a_runtime_error():
    # Callers that already catch RuntimeError (preflight, the apps) keep working.
    assert issubclass(ServoEchoError, RuntimeError)


def test_register_access_refuses_a_write_only_protocol():
    bus = PySerialBackend(
        "/dev/fake", encoder=get_encoder("ascii_servo"), serial_obj=FakeSTS3215Serial({})
    )

    with pytest.raises(RuntimeError, match="write-only"):
        bus.ping(1)


def test_register_access_refuses_a_feedback_protocol_without_a_memory_map():
    sts = get_feedback("sts3215")
    register_protocol(
        "mapless_test_protocol",
        get_encoder("sts3215"),
        feedback=FeedbackProtocol(
            encode_torque=sts.encode_torque,
            encode_read_position=sts.encode_read_position,
            parse_position_reply=sts.parse_position_reply,
            reply_length=sts.reply_length,
        ),
    )
    bus = PySerialBackend(
        "/dev/fake",
        encoder=get_encoder("mapless_test_protocol"),
        feedback=get_feedback("mapless_test_protocol"),
        serial_obj=FakeSTS3215Serial({1: SimulatedServo()}),
    )

    with pytest.raises(RuntimeError, match="register-level access"):
        bus.read_register(1, ServoRegister.MODEL, 2)
