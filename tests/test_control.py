import pytest

from painterbot.control.serial_controller import (
    MockSerialBackend,
    ServoRegister,
    PySerialBackend,
    available_protocols,
    get_encoder,
    get_feedback,
    open_backend,
    register_protocol,
)
from painterbot.control.servo import ServoLimitError


class FakeSerial:
    """Stand-in for ``serial.Serial`` that records writes and serves canned reads."""

    def __init__(self, to_read: bytes = b"") -> None:
        self.written: list[bytes] = []
        self.closed = False
        self.to_read = to_read
        self.input_resets = 0

    def write(self, payload: bytes) -> None:
        self.written.append(payload)

    def read(self, n: int) -> bytes:
        out, self.to_read = self.to_read[:n], self.to_read[n:]
        return out

    def reset_input_buffer(self) -> None:
        self.input_resets += 1

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
    assert "sts3215" in protos


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


def test_sts3215_encoder_packet():
    # 180 deg -> position 2048 (0x0800); WRITE Goal_Position (0x2A), little-endian.
    payload = get_encoder("sts3215")(3, 180.0)
    assert payload == bytes([0xFF, 0xFF, 0x03, 0x05, 0x03, 0x2A, 0x00, 0x08, 0xC2])
    # checksum = ~(id + length + instr + params), header excluded.
    assert payload[-1] == (~sum(payload[2:-1])) & 0xFF


def test_sts3215_encoder_clamps_to_encoder_range():
    # 4096 counts per rev, so valid positions are 0..4095.
    assert get_encoder("sts3215")(0, 400.0)[6:8] == bytes([0xFF, 0x0F])  # 4095
    assert get_encoder("sts3215")(0, -10.0)[6:8] == bytes([0x00, 0x00])  # 0


def test_sts3215_torque_and_read_packets():
    fb = get_feedback("sts3215")
    assert fb is not None
    # Torque_Enable (0x28) = 1 on servo 1.
    assert fb.encode_torque(1, True) == bytes(
        [0xFF, 0xFF, 0x01, 0x04, 0x03, 0x28, 0x01, 0xCE]
    )
    assert fb.encode_torque(1, False)[6] == 0x00
    # READ 2 bytes at Present_Position (0x38).
    assert fb.encode_read_position(1) == bytes(
        [0xFF, 0xFF, 0x01, 0x04, 0x02, 0x38, 0x02, 0xBE]
    )


def test_sts3215_set_id_and_lock_packets():
    fb = get_feedback("sts3215")
    assert fb.encode_set_id is not None
    assert fb.encode_lock is not None
    # WRITE ID (0x05) = 5 on current id 1.
    assert fb.encode_set_id(1, 5) == bytes([0xFF, 0xFF, 0x01, 0x04, 0x03, 0x05, 0x05, 0xED])
    # WRITE Lock (0x37): 0 = unlock (addressed to the old id)...
    assert fb.encode_lock(1, False) == bytes([0xFF, 0xFF, 0x01, 0x04, 0x03, 0x37, 0x00, 0xC0])
    # ...1 = re-lock, addressed to the *new* id since the servo already switched.
    assert fb.encode_lock(5, True) == bytes([0xFF, 0xFF, 0x05, 0x04, 0x03, 0x37, 0x01, 0xBB])


def test_sts3215_set_id_rejects_out_of_range():
    fb = get_feedback("sts3215")
    with pytest.raises(ValueError, match="out of range"):
        fb.encode_set_id(1, 254)
    with pytest.raises(ValueError, match="out of range"):
        fb.encode_set_id(1, -1)


def test_pyserial_backend_assign_servo_id_sequence():
    fb = get_feedback("sts3215")
    fake = FakeSerial()
    be = PySerialBackend(
        "/dev/fake", encoder=get_encoder("sts3215"), feedback=fb, serial_obj=fake
    )
    be.assign_servo_id(1, 5)

    assert fake.written == [
        fb.encode_lock(1, False),
        fb.encode_set_id(1, 5),
        fb.encode_lock(5, True),
    ]
    assert fake.input_resets == 3


def test_pyserial_backend_assign_servo_id_rejects_out_of_range_new_id():
    fake = FakeSerial()
    be = PySerialBackend(
        "/dev/fake",
        encoder=get_encoder("sts3215"),
        feedback=get_feedback("sts3215"),
        serial_obj=fake,
    )
    with pytest.raises(ValueError, match="out of range"):
        be.assign_servo_id(1, 300)
    assert fake.written == []  # nothing sent once the new id fails validation


def test_pyserial_backend_assign_servo_id_rejects_out_of_range_old_id():
    # old_id also needs validation: _sts_packet masks servo_id & 0xFF, so an
    # unchecked bad old_id would silently address a different bus servo.
    fake = FakeSerial()
    be = PySerialBackend(
        "/dev/fake",
        encoder=get_encoder("sts3215"),
        feedback=get_feedback("sts3215"),
        serial_obj=fake,
    )
    with pytest.raises(ValueError, match="out of range"):
        be.assign_servo_id(-1, 5)
    assert fake.written == []


def test_pyserial_backend_assign_servo_id_without_feedback_raises():
    be = PySerialBackend(
        "/dev/fake", encoder=get_encoder("ascii_servo"), serial_obj=FakeSerial()
    )
    with pytest.raises(RuntimeError, match="write-only"):
        be.assign_servo_id(1, 5)


def test_mock_backend_assign_servo_id_remaps_state():
    be = MockSerialBackend()
    be.write_servo(1, 45.0)
    be.set_torque(1, True)

    be.assign_servo_id(1, 5)

    assert be.read_servo(5) == 45.0
    assert be.torque == {5: True}
    assert 1 not in be.state
    assert 1 not in be.torque


def test_mock_backend_assign_servo_id_rejects_out_of_range():
    be = MockSerialBackend()
    with pytest.raises(ValueError, match="out of range"):
        be.assign_servo_id(1, 300)
    with pytest.raises(ValueError, match="out of range"):
        be.assign_servo_id(-1, 5)


def _sts_position_reply(servo_id: int, pos: int) -> bytes:
    body = [servo_id, 0x04, 0x00, pos & 0xFF, (pos >> 8) & 0xFF]
    return bytes([0xFF, 0xFF, *body, (~sum(body)) & 0xFF])


def test_sts3215_parse_position_reply():
    fb = get_feedback("sts3215")
    assert fb.parse_position_reply(_sts_position_reply(1, 1024), 1) == pytest.approx(90.0)
    assert fb.parse_position_reply(_sts_position_reply(5, 2048), 5) == pytest.approx(180.0)


def test_sts3215_parse_rejects_bad_replies():
    fb = get_feedback("sts3215")
    with pytest.raises(RuntimeError, match="no/short"):
        fb.parse_position_reply(b"", 1)
    with pytest.raises(RuntimeError, match="reply came from ID"):
        fb.parse_position_reply(_sts_position_reply(2, 1024), 1)
    corrupt = bytearray(_sts_position_reply(1, 1024))
    corrupt[5] ^= 0xFF
    with pytest.raises(RuntimeError, match="checksum"):
        fb.parse_position_reply(bytes(corrupt), 1)


def test_get_feedback_none_for_write_only_protocols():
    assert get_feedback("ascii_servo") is None
    assert get_feedback("lx16a") is None


def test_pyserial_backend_read_and_torque_roundtrip():
    fake = FakeSerial(to_read=_sts_position_reply(2, 1024))
    be = PySerialBackend(
        "/dev/fake",
        encoder=get_encoder("sts3215"),
        feedback=get_feedback("sts3215"),
        serial_obj=fake,
    )
    assert be.read_servo(2) == pytest.approx(90.0)
    assert fake.input_resets == 1  # stale write-acks must be flushed first
    assert fake.written[-1] == get_feedback("sts3215").encode_read_position(2)
    be.set_torque(2, False)
    assert fake.written[-1] == get_feedback("sts3215").encode_torque(2, False)


def test_pyserial_backend_without_feedback_raises():
    be = PySerialBackend(
        "/dev/fake", encoder=get_encoder("ascii_servo"), serial_obj=FakeSerial()
    )
    with pytest.raises(RuntimeError, match="write-only"):
        be.read_servo(0)
    with pytest.raises(RuntimeError, match="write-only"):
        be.set_torque(0, False)


def test_mock_backend_feedback():
    be = MockSerialBackend()
    assert be.read_servo(0) is None  # never commanded
    be.write_servo(0, 45.0)
    assert be.read_servo(0) == 45.0
    be.set_torque(0, False)
    assert be.torque == {0: False}


def test_arm_feedback_via_mock(arm_config):
    from painterbot.control.arm import Arm

    backend = MockSerialBackend()
    arm = Arm(arm_config, backend)
    assert arm.read_pose() == [None] * 6
    arm.move_to_pose([90, 90, 90, 90, 90, 30])
    arm.set_torque(False)
    assert backend.torque == {ch: False for ch in range(6)}
    # Simulate hand-moving the base, then adopting encoder positions.
    backend.state[0] = 120.0
    synced = arm.sync_from_hardware()
    assert synced[0] == pytest.approx(120.0)
    assert arm.pose[0] == pytest.approx(120.0)


def test_motion_blocked_from_out_of_range_start(arm_config):
    from painterbot.control.arm import Arm

    backend = MockSerialBackend()
    arm = Arm(arm_config, backend)
    arm.move_to_pose([90, 90, 90, 90, 90, 30])
    # Hand-guided past the base's 180 limit (STS range is physically 0..360).
    backend.state[0] = 200.0
    arm.sync_from_hardware()
    history_before = list(backend.history)
    # Pose moves must refuse before writing anything (even with clamp=True,
    # which would otherwise command a full-speed jump to the boundary).
    with pytest.raises(RuntimeError, match="outside safe range"):
        arm.move_to_pose([90, 90, 90, 90, 90, 30], clamp=True)
    with pytest.raises(RuntimeError, match="outside safe range"):
        arm.home(clamp=True)
    # Single-joint moves refuse too.
    with pytest.raises(ServoLimitError, match="current position"):
        arm.set_joint("base", 90, clamp=True)
    assert backend.history == history_before  # nothing was commanded
    # Hand-moving back in range and re-syncing unblocks motion.
    backend.state[0] = 170.0
    arm.sync_from_hardware()
    arm.move_to_pose([90, 90, 90, 90, 90, 30], clamp=True)
    assert backend.state[0] == 90


def test_read_servo_retries_after_corrupt_reply():
    good = _sts_position_reply(1, 2048)
    corrupt = bytearray(good)
    corrupt[5] ^= 0xFF  # bad checksum on the first reply
    fake = FakeSerial(to_read=bytes(corrupt) + good)
    be = PySerialBackend(
        "/dev/fake",
        encoder=get_encoder("sts3215"),
        feedback=get_feedback("sts3215"),
        serial_obj=fake,
    )
    assert be.read_servo(1) == pytest.approx(180.0)
    assert fake.input_resets == 2  # flushed before each attempt


def test_read_servo_raises_after_two_bad_replies():
    fake = FakeSerial(to_read=b"\x00" * 16)
    be = PySerialBackend(
        "/dev/fake",
        encoder=get_encoder("sts3215"),
        feedback=get_feedback("sts3215"),
        serial_obj=fake,
    )
    with pytest.raises(RuntimeError, match="bad reply header"):
        be.read_servo(1)


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


# -- register-level access (bus scan / identification) ------------------------


def test_sts3215_register_access_encodes_ping_and_reads():
    fb = get_feedback("sts3215")
    regs = fb.registers
    assert regs is not None
    # PING (instruction 0x01) carries no params: FF FF ID LEN INSTR CHK.
    assert regs.encode_ping(1) == bytes([0xFF, 0xFF, 0x01, 0x02, 0x01, 0xFB])
    # A generic register read must reproduce the hand-written position read.
    assert regs.encode_read(1, ServoRegister.PRESENT_POSITION, 2) == bytes(
        [0xFF, 0xFF, 0x01, 0x04, 0x02, 0x38, 0x02, 0xBE]
    )
    # Model number lives at 0x03 and is 2 bytes wide.
    assert regs.encode_read(1, ServoRegister.MODEL, 2) == bytes(
        [0xFF, 0xFF, 0x01, 0x04, 0x02, 0x03, 0x02, 0xF3]
    )


def test_sts3215_register_access_encodes_writes_little_endian():
    regs = get_feedback("sts3215").registers
    # 1-byte write reproduces the hand-written torque packet.
    assert regs.encode_write(1, ServoRegister.TORQUE_ENABLE, 1, 1) == bytes(
        [0xFF, 0xFF, 0x01, 0x04, 0x03, 0x28, 0x01, 0xCE]
    )
    # 2-byte write is low byte first: 2048 -> 00 08.
    assert regs.encode_write(1, ServoRegister.GOAL_POSITION, 2, 2048) == bytes(
        [0xFF, 0xFF, 0x01, 0x05, 0x03, 0x2A, 0x00, 0x08, 0xC4]
    )


def test_sts3215_register_access_parses_replies():
    regs = get_feedback("sts3215").registers
    assert regs.status_length == 6
    assert regs.read_reply_length(1) == 7
    assert regs.read_reply_length(2) == 8
    # Bare ack to a ping: error flags come back as an int.
    assert regs.parse_status(bytes([0xFF, 0xFF, 0x01, 0x02, 0x00, 0xFC]), 1) == 0
    # 2-byte read reply, little-endian.
    assert (
        regs.parse_read_reply(bytes([0xFF, 0xFF, 0x01, 0x04, 0x00, 0x00, 0x08, 0xF2]), 1, 2)
        == 2048
    )
    # 1-byte read reply (e.g. present temperature = 74 C).
    assert regs.parse_read_reply(bytes([0xFF, 0xFF, 0x01, 0x03, 0x00, 0x4A, 0xB1]), 1, 1) == 74


def test_sts3215_register_replies_reject_corrupt_frames():
    regs = get_feedback("sts3215").registers
    with pytest.raises(RuntimeError, match="no/short"):
        regs.parse_read_reply(b"\xff\xff\x01", 1, 2)
    with pytest.raises(RuntimeError, match="checksum"):
        regs.parse_read_reply(bytes([0xFF, 0xFF, 0x01, 0x04, 0x00, 0x00, 0x08, 0x00]), 1, 2)
    with pytest.raises(RuntimeError, match="came from ID"):
        regs.parse_read_reply(bytes([0xFF, 0xFF, 0x02, 0x04, 0x00, 0x00, 0x08, 0xF1]), 1, 2)


def test_servo_register_addresses_match_feetech_memory_map():
    # Datasheet-derived; the names are what callers outside the serial module use.
    assert ServoRegister.FIRMWARE == 0x00
    assert ServoRegister.MODEL == 0x03
    assert ServoRegister.ID == 0x05
    assert ServoRegister.BAUD_CODE == 0x06
    assert ServoRegister.MIN_ANGLE_LIMIT == 0x09
    assert ServoRegister.MAX_ANGLE_LIMIT == 0x0B
    assert ServoRegister.TORQUE_ENABLE == 0x28
    assert ServoRegister.GOAL_POSITION == 0x2A
    assert ServoRegister.LOCK == 0x37
    assert ServoRegister.PRESENT_POSITION == 0x38
    assert ServoRegister.PRESENT_VOLTAGE == 0x3E
    assert ServoRegister.PRESENT_TEMPERATURE == 0x3F


def test_open_backend_refuses_a_real_port_when_the_protocol_is_mock():
    # The trap this closes: configs/arm.default.yaml still ships protocol: mock,
    # so `bringup ping --port /dev/cu.X` used to talk to the mock backend and
    # report healthy servos without sending a single byte.
    with pytest.raises(ValueError, match="protocol is 'mock'"):
        open_backend(port="/dev/cu.usbmodem1", protocol="mock")


def test_open_backend_still_mocks_when_no_port_is_given():
    assert open_backend(protocol="mock").is_mock
    assert open_backend(mock=True, port="/dev/cu.usbmodem1").is_mock
