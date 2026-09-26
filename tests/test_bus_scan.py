"""Bus discovery: what is physically on the wire, at what ID, and what is it."""

from __future__ import annotations

import pytest

from painterbot.control.bus_scan import (
    DEFAULT_BAUDS,
    BusScan,
    identify_servo,
    scan_bus,
    servo_ids_from_spec,
    sweep_bauds,
)
from painterbot.control.serial_controller import (
    PySerialBackend,
    ServoEchoError,
    get_encoder,
    get_feedback,
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


def _bench_servo() -> SimulatedServo:
    return SimulatedServo(
        position_counts=2043,
        model_number=777,
        firmware=(3, 6),
        voltage_dv=74,
        temperature_c=32,
        min_angle_counts=0,
        max_angle_counts=4095,
    )


# -- identification ----------------------------------------------------------


def test_identify_reports_what_the_servo_says_about_itself():
    identity = identify_servo(_bus(FakeSTS3215Serial({1: _bench_servo()})), 1)

    assert identity is not None
    assert identity.servo_id == 1
    assert identity.model_number == 777
    assert identity.firmware == (3, 6)
    assert identity.position_counts == 2043
    assert identity.voltage_v == pytest.approx(7.4)
    assert identity.temperature_c == 32
    assert identity.angle_limits_counts == (0, 4095)
    assert identity.error_flags == 0


def test_identify_converts_counts_to_degrees_on_the_sts_scale():
    # 4096 counts per 360 deg, so the centre count 2048 is 180 deg -- not the 90
    # deg a 0..180 hobby servo would sit at.
    identity = identify_servo(
        _bus(FakeSTS3215Serial({1: SimulatedServo(position_counts=2048)})), 1
    )

    assert identity.position_deg == pytest.approx(180.0)


def test_identify_returns_none_for_an_absent_servo_after_one_packet():
    fake = FakeSTS3215Serial({1: _bench_servo()})

    assert identify_servo(_bus(fake), 9) is None
    # A ping and nothing else: an absent ID must not cost eight register reads.
    assert len(fake.written) == 1


def test_identify_records_a_partial_reply_when_a_servo_answers_then_goes_quiet():
    # Marginal voltage or a flaky connector: the cheap ping gets through, the
    # register reads do not. A partial identity is more useful during bring-up
    # than throwing the evidence away.
    fake = FakeSTS3215Serial({1: _bench_servo()})
    for _ in range(8):
        fake.queue_fault(1, "no_reply", instruction=0x02)

    identity = identify_servo(_bus(fake), 1)

    assert identity is not None
    assert identity.error_flags == 0
    assert identity.model_number is None
    assert identity.position_counts is None
    assert identity.partial
    assert "partial reply" in identity.summary()


def test_identify_propagates_adapter_echo_instead_of_inventing_a_servo():
    with pytest.raises(ServoEchoError):
        identify_servo(_bus(FakeEchoingSerial()), 1)


# -- scanning ----------------------------------------------------------------


def test_scan_finds_only_the_servos_that_are_present():
    fake = FakeSTS3215Serial({1: _bench_servo(), 4: SimulatedServo()})

    scan = scan_bus(_bus(fake), range(0, 8), baud=1_000_000)

    assert [s.servo_id for s in scan.found] == [1, 4]
    assert scan.silent_ids == (0, 2, 3, 5, 6, 7)
    assert not scan.is_empty
    assert scan.baud == 1_000_000


def test_scan_of_an_unpowered_bus_is_empty_and_says_so():
    # FakeSTS3215Serial({}) *is* the unpowered bus: every ID silent.
    scan = scan_bus(_bus(FakeSTS3215Serial({})), range(0, 6), baud=1_000_000)

    assert scan.is_empty
    assert scan.found == ()
    assert "no servo answered" in scan.describe()
    assert "7.4" in scan.describe()


def test_scan_describe_names_each_servo_it_found():
    scan = scan_bus(_bus(FakeSTS3215Serial({1: _bench_servo()})), [0, 1], baud=1_000_000)
    text = scan.describe()

    assert "777" in text
    assert "1/2" in text


def test_scan_streams_each_result_as_it_arrives():
    seen = []
    scan_bus(
        _bus(FakeSTS3215Serial({1: _bench_servo()})),
        range(0, 4),
        baud=1_000_000,
        on_probe=lambda servo_id, identity: seen.append((servo_id, identity is not None)),
    )

    assert seen == [(0, False), (1, True), (2, False), (3, False)]


# -- baud sweep --------------------------------------------------------------


def test_sweep_stops_at_the_baud_that_answers():
    opened = []

    def open_at(baud):
        fake = (
            FakeSTS3215Serial({1: _bench_servo()})
            if baud == 500_000
            else FakeGarbledSerial()
        )
        opened.append((baud, fake))
        return _bus(fake)

    sweep = sweep_bauds(open_at, bauds=(1_000_000, 500_000, 115_200), servo_ids=[1])

    assert sweep.answered_at == 500_000
    assert [baud for baud, _ in opened] == [1_000_000, 500_000]
    assert all(fake.closed for _, fake in opened)


def test_sweep_records_every_attempt_when_nothing_answers():
    fakes = []

    def open_at(baud):
        fake = FakeSTS3215Serial({})
        fakes.append(fake)
        return _bus(fake)

    sweep = sweep_bauds(open_at, bauds=(1_000_000, 115_200), servo_ids=[1])

    assert sweep.answered_at is None
    assert len(sweep.attempts) == 2
    assert all(attempt.scan.is_empty for attempt in sweep.attempts)
    assert all(fake.closed for fake in fakes)


def test_sweep_records_a_refused_baud_instead_of_raising():
    # Non-POSIX rates (250000, 128000) can be refused by the OS or the driver;
    # that is data about the link, not a crash.
    def open_at(baud):
        if baud == 250_000:
            raise OSError("termios: invalid argument")
        return _bus(FakeSTS3215Serial({}))

    sweep = sweep_bauds(open_at, bauds=(250_000, 115_200), servo_ids=[1])

    assert sweep.attempts[0].scan is None
    assert "invalid argument" in sweep.attempts[0].open_error
    assert sweep.attempts[1].scan is not None


def test_sweep_can_be_asked_to_try_every_baud():
    sweep = sweep_bauds(
        lambda baud: _bus(FakeSTS3215Serial({1: _bench_servo()})),
        bauds=(1_000_000, 115_200),
        servo_ids=[1],
        stop_on_first_reply=False,
    )

    assert len(sweep.attempts) == 2
    assert sweep.answered_at == 1_000_000


def test_default_bauds_lead_with_the_sts3215_factory_rate():
    assert DEFAULT_BAUDS[0] == 1_000_000


# -- id specs ----------------------------------------------------------------


def test_servo_ids_from_spec_accepts_ranges_and_lists():
    assert servo_ids_from_spec("0-5") == (0, 1, 2, 3, 4, 5)
    assert servo_ids_from_spec("1") == (1,)
    assert servo_ids_from_spec("0,4,2") == (0, 2, 4)
    assert servo_ids_from_spec("0-2,7") == (0, 1, 2, 7)


def test_servo_ids_from_spec_rejects_broadcast_and_out_of_range():
    # 254 is the broadcast ID: every servo answers at once and the replies
    # collide on a half-duplex line, so a "scan" of it teaches us nothing.
    with pytest.raises(ValueError, match="broadcast"):
        servo_ids_from_spec("254")
    with pytest.raises(ValueError, match="0..253"):
        servo_ids_from_spec("300")
    with pytest.raises(ValueError, match="0..253"):
        servo_ids_from_spec("-1")
    with pytest.raises(ValueError, match="empty|invalid"):
        servo_ids_from_spec("")
