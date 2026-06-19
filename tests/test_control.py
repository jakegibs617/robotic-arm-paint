import pytest

from painterbot.control.serial_controller import MockSerialBackend, open_backend
from painterbot.control.servo import ServoLimitError


def test_open_backend_defaults_to_mock():
    be = open_backend(mock=True)
    assert be.is_mock


def test_open_backend_real_needs_port():
    with pytest.raises(ValueError):
        open_backend(mock=False, protocol="arduino", port=None)


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
