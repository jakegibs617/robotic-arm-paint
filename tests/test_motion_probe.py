"""Bounded motion probe: the smallest safe commanded move, in raw counts."""

from __future__ import annotations

import pytest

from painterbot.control.motion_probe import (
    MAX_NUDGE_COUNTS,
    nudge_servo,
)
from painterbot.control.serial_controller import (
    PySerialBackend,
    ServoRegister,
    get_encoder,
    get_feedback,
)
from painterbot.testing.fake_sts3215 import FakeSTS3215Serial, SimulatedServo


def _bus(fake) -> PySerialBackend:
    return PySerialBackend(
        "/dev/fake",
        encoder=get_encoder("sts3215"),
        feedback=get_feedback("sts3215"),
        serial_obj=fake,
    )


def _never_sleep(_seconds: float) -> None:
    return None


def _steps(fake) -> list[tuple[int, int | None]]:
    return [(r.instruction, r.address) for r in fake.requests]


READ = 0x02
WRITE = 0x03
POSITION = int(ServoRegister.PRESENT_POSITION)
GOAL = int(ServoRegister.GOAL_POSITION)
TORQUE = int(ServoRegister.TORQUE_ENABLE)


def test_nudge_reads_energises_commands_reads_back_then_releases():
    fake = FakeSTS3215Serial({1: SimulatedServo(position_counts=2000)})

    result = nudge_servo(_bus(fake), 1, delta_counts=100, sleep=_never_sleep)

    assert result.status == "success"
    assert result.start_counts == 2000
    assert result.goal_counts == 2100
    assert result.end_counts == 2100
    assert result.moved_counts == 100
    assert result.moved_deg == pytest.approx(100 * 360.0 / 4096)
    assert result.torque_released
    # Order matters: never command a servo whose position is unknown, and always
    # release torque afterwards.
    assert _steps(fake) == [
        (READ, POSITION),
        (WRITE, GOAL),  # neutralise the stale goal BEFORE energising
        (WRITE, TORQUE),
        (WRITE, GOAL),
        (READ, POSITION),
        (WRITE, TORQUE),
    ]


def test_nudge_waits_for_the_servo_to_settle_before_reading_back():
    slept = []
    nudge_servo(
        _bus(FakeSTS3215Serial({1: SimulatedServo()})),
        1,
        delta_counts=20,
        settle_s=0.25,
        sleep=slept.append,
    )

    assert slept == [0.25]


def test_nudge_refuses_an_over_cap_delta_without_touching_the_bus():
    fake = FakeSTS3215Serial({1: SimulatedServo()})

    result = nudge_servo(_bus(fake), 1, delta_counts=9999, sleep=_never_sleep)

    assert result.status == "refused"
    assert str(MAX_NUDGE_COUNTS) in result.detail
    assert fake.written == []
    assert result.start_counts is None


def test_nudge_cap_applies_in_both_directions():
    fake = FakeSTS3215Serial({1: SimulatedServo()})

    result = nudge_servo(_bus(fake), 1, delta_counts=-MAX_NUDGE_COUNTS - 1, sleep=_never_sleep)

    assert result.status == "refused"
    assert fake.written == []


def test_nudge_clamps_the_goal_into_the_encoder_range():
    fake = FakeSTS3215Serial({1: SimulatedServo(position_counts=4090)})

    result = nudge_servo(_bus(fake), 1, delta_counts=100, sleep=_never_sleep)

    assert result.goal_counts == 4095
    assert result.status == "success"


def test_zero_delta_still_energises_reads_and_releases():
    # The first thing to run on a live servo: proves torque framing and the read
    # path with nothing commanded to move.
    fake = FakeSTS3215Serial({1: SimulatedServo(position_counts=2048)})

    result = nudge_servo(_bus(fake), 1, delta_counts=0, sleep=_never_sleep)

    assert result.status == "success"
    assert result.moved_counts == 0
    assert result.torque_released
    assert _steps(fake).count((WRITE, TORQUE)) == 2


def test_nudge_reports_a_servo_that_accepts_the_goal_but_does_not_move():
    # Exactly the symptom of logic power with no motor power: this must read as a
    # diagnosis, not a crash.
    fake = FakeSTS3215Serial({1: SimulatedServo(position_counts=2000, stuck=True)})

    result = nudge_servo(_bus(fake), 1, delta_counts=100, sleep=_never_sleep)

    assert result.status == "did_not_move"
    assert result.moved_counts == 0
    assert "power" in result.detail


def test_nudge_refuses_to_move_a_servo_it_cannot_read():
    fake = FakeSTS3215Serial({})

    result = nudge_servo(_bus(fake), 1, delta_counts=100, sleep=_never_sleep)

    assert result.status == "no_start_position"
    # One read attempt and nothing else -- never move blind.
    assert _steps(fake) == [(READ, POSITION)]


def test_nudge_never_commands_when_the_start_read_fails():
    fake = FakeSTS3215Serial({1: SimulatedServo(position_counts=2000)})
    fake.queue_fault(1, "no_reply", instruction=READ)

    result = nudge_servo(_bus(fake), 1, delta_counts=50, sleep=_never_sleep)

    assert result.status == "no_start_position"
    assert (WRITE, GOAL) not in _steps(fake)
    assert (WRITE, TORQUE) not in _steps(fake)


def test_nudge_releases_torque_when_the_end_read_fails():
    fake = FakeSTS3215Serial({1: SimulatedServo(position_counts=2000)})

    class SilentAfterGoal:
        """Answers the first position read, then nothing."""

        def __init__(self, inner):
            self.inner = inner
            self.reads = 0

        def ping(self, servo_id):
            return self.inner.ping(servo_id)

        def read_register(self, servo_id, address, length):
            if int(address) == POSITION:
                self.reads += 1
                if self.reads > 1:
                    return None
            return self.inner.read_register(servo_id, address, length)

        def write_register(self, servo_id, address, length, value):
            self.inner.write_register(servo_id, address, length, value)

        def set_torque(self, channel, enabled):
            self.inner.set_torque(channel, enabled)

    result = nudge_servo(
        SilentAfterGoal(_bus(fake)), 1, delta_counts=50, sleep=_never_sleep
    )

    assert result.status == "no_end_position"
    assert result.torque_released
    assert _steps(fake)[-1] == (WRITE, TORQUE)
    assert fake.servos[1].torque_enabled is False


def test_max_nudge_counts_is_a_small_fraction_of_a_turn():
    # The cap exists so a bring-up typo cannot swing a mounted arm.
    assert 0 < MAX_NUDGE_COUNTS <= 256


def test_nudge_neutralises_a_stale_goal_before_energising():
    """A servo at rest still holds whatever Goal_Position was last written.

    The bench STS3215 was found sitting at 4094 counts with Goal_Position 0 --
    the factory default, never overwritten. Enabling torque in that state
    commands a near-full-turn slam to 0 before any deliberate goal is sent. So
    the goal is overwritten with the *current* position while the servo is
    still limp, and only then is torque enabled.
    """
    fake = FakeSTS3215Serial({1: SimulatedServo(position_counts=4094, goal_counts=0)})

    result = nudge_servo(_bus(fake), 1, delta_counts=-57, sleep=_never_sleep)

    writes = [r for r in fake.requests if r.instruction == WRITE]
    first_goal_write = next(r for r in writes if r.address == GOAL)
    # The first thing written to the goal register is where the servo already is.
    assert int.from_bytes(first_goal_write.payload, "little") == 4094
    # And it happens before torque is ever enabled.
    assert writes.index(first_goal_write) < next(
        i for i, r in enumerate(writes) if r.address == TORQUE
    )
    assert result.status == "success"
    assert result.end_counts == 4094 - 57


def test_nudge_tolerates_a_servo_that_acks_every_write():
    """The bench servo reports Response Status Level 1: it acks writes.

    Those acks land in the input buffer between operations, so every read must
    flush before pairing request and reply or it would read an ack as a value.
    """
    fake = FakeSTS3215Serial(
        {1: SimulatedServo(position_counts=2000)}, ack_writes=True
    )

    result = nudge_servo(_bus(fake), 1, delta_counts=100, sleep=_never_sleep)

    assert result.status == "success"
    assert result.start_counts == 2000
    assert result.end_counts == 2100
