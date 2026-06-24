import pytest

from painterbot.control.serial_controller import (
    MockSerialBackend,
    PySerialBackend,
    available_protocols,
    get_encoder,
    open_backend,
    register_protocol,
)
from painterbot.control.servo import ServoLimitError


class FakeSerial:
    """Stand-in for ``serial.Serial`` that records written bytes."""

    def __init__(self) -> None:
        self.written: list[bytes] = []
        self.closed = False

    def write(self, payload: bytes) -> None:
        self.written.append(payload)

    def close(self) -> None:
        self.closed = True


def test_open_backend_defaults_to_mock():
    be = open_backend(mock=True)
    assert be.is_mock


def test_open_backend_real_needs_port():
    with pytest.raises(ValueError, match="no serial port"):
        open_backend(mock=False, protocol="ascii_servo", port=None)


def test_open_backend_rejects_unknown_protocol():
    with pytest.raises(ValueError, match="unknown serial protocol"):
        open_backend(mock=False, protocol="nope", port="/dev/null")


def test_available_protocols_lists_builtins():
    protos = available_protocols()
    assert "mock" in protos
    assert "ascii_servo" in protos
    assert "lx16a" in protos


def test_ascii_encoder_format():
    assert get_encoder("ascii_servo")(2, 90.0) == b"S 2 90.0\n"


def test_lx16a_encoder_packet():
    # 90 of 240 deg -> position 375 (0x0177); SERVO_MOVE_TIME_WRITE, time 0.
    payload = get_encoder("lx16a")(3, 90.0)
    assert payload[:2] == b"\x55\x55"  # header
    assert payload[2] == 3  # servo id / channel
    assert payload[3] == 7  # length = len(params) + 3
    assert payload[4] == 1  # SERVO_MOVE_TIME_WRITE
    assert payload[5:7] == bytes([375 & 0xFF, (375 >> 8) & 0xFF])
    # checksum = ~(id + length + cmd + params) over the body, header excluded.
    body = payload[2:-1]
    assert payload[-1] == (~sum(body)) & 0xFF


def test_pyserial_backend_writes_encoded_bytes():
    fake = FakeSerial()
    be = PySerialBackend(
        "/dev/fake", encoder=get_encoder("ascii_servo"), serial_obj=fake
    )
    be.write_servo(1, 45.0)
    be.write_servo(0, 90.0)
    assert fake.written == [b"S 1 45.0\n", b"S 0 90.0\n"]
    be.close()
    assert fake.closed


def test_register_protocol_roundtrips_through_backend():
    register_protocol("test_proto", lambda ch, ang: bytes([ch, int(ang)]))
    fake = FakeSerial()
    be = PySerialBackend(
        "/dev/fake", encoder=get_encoder("test_proto"), serial_obj=fake
    )
    be.write_servo(4, 120.0)
    assert fake.written == [bytes([4, 120])]


def test_servo_limit_enforced(mock_arm):
    base = mock_arm.servo("base")  # range 0..180
    with pytest.raises(ServoLimitError):
        base.move_to(200)


def test_servo_clamp_allows_out_of_range(mock_arm):
    base = mock_arm.servo("base")
    sent = base.move_to(200, clamp=True)
    assert sent == base.config.max_deg


def test_move_to_pose_sends_commands(arm_config):
    from painterbot.control.arm import Arm

    backend = MockSerialBackend()
    arm = Arm(arm_config, backend)
    arm.move_to_pose([90, 90, 90, 90, 90, 30])
    # Interpolation from home (already 90s) is short; final state should match.
    assert backend.state[0] == 90
    assert len(backend.history) >= 1


def test_stop_blocks_motion(mock_arm):
    mock_arm.stop()
    assert mock_arm.stopped
    with pytest.raises(RuntimeError):
        mock_arm.move_to_pose([90, 90, 90, 90, 90, 30])
    mock_arm.resume()
    assert not mock_arm.stopped


def test_pose_wrong_length_rejected(mock_arm):
    with pytest.raises(ValueError):
        mock_arm.move_to_pose([90, 90, 90])
