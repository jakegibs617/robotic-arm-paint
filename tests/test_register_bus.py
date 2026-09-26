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
    sts_register_reply,
    sts_status_reply,
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


def test_write_register_rejects_a_missing_value_with_a_clear_message():
    """A failed read returns None. Passing that straight into a write used to
    blow up as `TypeError: unsupported operand type(s) for >>: 'NoneType'`
    from inside the encoder -- three frames from the actual mistake."""
    bus = _bus(FakeSTS3215Serial({1: SimulatedServo()}))

    with pytest.raises(ValueError, match="no value to write"):
        bus.write_register(1, ServoRegister.GOAL_POSITION, 2, None)


def test_write_register_rejects_a_value_too_wide_for_the_register():
    bus = _bus(FakeSTS3215Serial({1: SimulatedServo()}))

    with pytest.raises(ValueError, match="does not fit"):
        bus.write_register(1, ServoRegister.TORQUE_ENABLE, 1, 256)
    with pytest.raises(ValueError, match="does not fit"):
        bus.write_register(1, ServoRegister.GOAL_POSITION, 2, -1)


# -- echo disambiguation ------------------------------------------------------


def test_under_volted_servo_is_not_mistaken_for_an_echo():
    """A PING reply carrying error flag 0x01 is byte-identical to the PING
    request -- and bit 0 of the STS error byte is UNDER-VOLTAGE, the exact
    condition a bench servo on marginal power reports. Treating that frame as
    an echo would blame the adapter for the one thing that is fine."""
    fake = FakeSTS3215Serial({1: SimulatedServo(position_counts=2048, error_flags=0x01)})
    regs = get_feedback("sts3215").registers
    assert regs.encode_ping(1) == sts_status_reply(1, 0x01)  # the ambiguity is real

    assert _bus(fake).ping(1) == 0x01


def test_ambiguous_position_read_from_a_real_servo_is_not_an_echo():
    # The 2-byte read collision: error flag 0x02 with value 568 counts.
    fake = FakeSTS3215Serial({1: SimulatedServo(position_counts=568, error_flags=0x02)})
    regs = get_feedback("sts3215").registers
    assert regs.encode_read(1, ServoRegister.PRESENT_POSITION, 2) == sts_register_reply(
        1, (568).to_bytes(2, "little"), error=0x02
    )

    assert _bus(fake).read_register(1, ServoRegister.PRESENT_POSITION, 2) == 568


def test_a_genuinely_echoing_link_is_still_caught():
    bus = _bus(FakeEchoingSerial())

    with pytest.raises(ServoEchoError, match="echo"):
        bus.ping(1)


def test_echo_is_decided_once_per_link_not_per_packet():
    """Echo is a property of the wiring, constant for the session. Deciding it
    per packet means re-running the disambiguation on every ambiguous frame."""
    fake = FakeSTS3215Serial({1: SimulatedServo(error_flags=0x01)})
    bus = _bus(fake)

    bus.ping(1)
    after_first = len(fake.written)
    bus.ping(1)
    bus.ping(1)

    # The first ping pays for one disambiguating exchange; later ones do not.
    assert after_first == 2
    assert len(fake.written) == after_first + 2
