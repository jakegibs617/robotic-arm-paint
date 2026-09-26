"""Hardware bring-up helpers.

``list-joints``, ``protocols``, ``ports``, and ``mock-session`` inspect
configuration, protocol capabilities, and the host's serial devices without
opening a port. ``scan``, ``identify``, ``ping``, ``nudge``, and ``assign-id``
open a connection -- a real one, or the in-memory fake with ``--mock``.

The intended order on a fresh build is ``ports`` -> ``scan`` -> ``identify`` ->
``nudge`` -> ``assign-id``: find the adapter, find out what is actually on the
bus before trusting the config's servo IDs, read the servo's own account of
itself, prove the write path with the smallest possible move, and only then
write to EEPROM.
"""

from __future__ import annotations

import argparse
import sys

from painterbot.apps._common import (
    add_connection_args,
    load_configs,
    resolve_serial,
    setup_logging,
)
from painterbot.control import serial_link
from painterbot.control.bus_scan import (
    DEFAULT_BAUDS,
    identify_servo,
    scan_bus,
    servo_ids_from_spec,
    sweep_bauds,
)
from painterbot.control.id_assignment import assign_servo_id
from painterbot.control.motion_probe import DEFAULT_NUDGE_COUNTS, nudge_servo
from painterbot.control.preflight import read_servo_preflight
from painterbot.control.serial_controller import (
    PySerialBackend,
    get_encoder,
    get_feedback,
    open_backend,
)


_PROBE_PROTOCOL = "sts3215"
#: Short per-probe timeout: a wide sweep at the config's 1.0s would be unusable
#: (an absent ID costs the full timeout, a real reply arrives in microseconds).
_PROBE_TIMEOUT_S = 0.05


def _feedback_text(protocol: str) -> str:
    return "yes" if get_feedback(protocol) is not None else "no"


def _open_raw_backend(args, arm_cfg, *, timeout_s=None):
    """A raw ``SerialBackend`` (not an ``Arm``) for protocol-level bring-up ops."""
    serial_cfg = resolve_serial(args, arm_cfg)
    return open_backend(
        mock=args.mock,
        port=serial_cfg.port,
        baud=serial_cfg.baud,
        timeout_s=timeout_s or serial_cfg.timeout_s,
        protocol=serial_cfg.protocol,
    )


def _simulated_bus(*, empty: bool):
    """A real ``PySerialBackend`` over the in-memory fake servo.

    ``--mock`` for the scan/identify/nudge subcommands deliberately does **not**
    use ``MockSerialBackend``: the point of these commands is the wire protocol,
    so the mock path runs the real sts3215 encoders and parsers against a fake
    port. A backend that invented a model number would prove nothing.
    """
    from painterbot.testing.fake_sts3215 import FakeSTS3215Serial, SimulatedServo

    servos = {} if empty else {1: SimulatedServo(position_counts=2048)}
    return PySerialBackend(
        "mock://fake-servo-bus",
        encoder=get_encoder(_PROBE_PROTOCOL),
        feedback=get_feedback(_PROBE_PROTOCOL),
        serial_obj=FakeSTS3215Serial(servos),
    )


def _open_probe_bus(args, arm_cfg, *, baud=None, timeout_s=None):
    """A register-level bus for the probing subcommands, plus what it connected to."""
    if args.mock:
        serial_cfg = resolve_serial(args, arm_cfg).model_copy(
            update={
                "protocol": _PROBE_PROTOCOL,
                "port": "mock://fake-servo-bus",
                "baud": baud or resolve_serial(args, arm_cfg).baud,
                "timeout_s": timeout_s or _PROBE_TIMEOUT_S,
            }
        )
        return _simulated_bus(empty=args.mock_empty_bus), serial_cfg

    serial_cfg = resolve_serial(args, arm_cfg).model_copy(
        update={
            "baud": baud or resolve_serial(args, arm_cfg).baud,
            "timeout_s": timeout_s or _PROBE_TIMEOUT_S,
        }
    )
    bus = open_backend(
        mock=False,
        port=serial_cfg.port,
        baud=serial_cfg.baud,
        timeout_s=serial_cfg.timeout_s,
        protocol=serial_cfg.protocol,
    )
    return bus, serial_cfg


def _print_connection(serial_cfg, *, mock: bool) -> None:
    note = " (mock: in-memory fake servo bus, nothing is sent to hardware)" if mock else ""
    print(
        f"connecting: port={serial_cfg.port} baud={serial_cfg.baud} "
        f"protocol={serial_cfg.protocol} timeout={serial_cfg.timeout_s}s{note}"
    )


def _resolve_ids(spec):
    try:
        return servo_ids_from_spec(spec), None
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return None, 2


def _print_ports(args) -> int:
    print(serial_link.describe_ports(serial_link.list_serial_ports()))
    return 0


def _print_scan(args) -> int:
    servo_ids, failure = _resolve_ids(args.ids)
    if failure is not None:
        return failure
    arm_cfg, _ = load_configs(args)

    if args.baud_sweep:
        base = resolve_serial(args, arm_cfg)
        print(f"sweeping bauds on {base.port or '<no port>'} for IDs {args.ids}")

        def open_bus_at(baud):
            bus, serial_cfg = _open_probe_bus(
                args, arm_cfg, baud=baud, timeout_s=args.probe_timeout
            )
            _print_connection(serial_cfg, mock=args.mock)
            return bus

        sweep = sweep_bauds(
            open_bus_at, servo_ids=servo_ids, bauds=DEFAULT_BAUDS
        )
        print(sweep.describe())
        return 0 if sweep.answered_at is not None else 1

    bus, serial_cfg = _open_probe_bus(args, arm_cfg, timeout_s=args.probe_timeout)
    _print_connection(serial_cfg, mock=args.mock)
    try:
        scan = scan_bus(bus, servo_ids, baud=serial_cfg.baud)
    finally:
        bus.close()
    print(scan.describe())
    return 0 if not scan.is_empty else 1


def _print_identify(args) -> int:
    arm_cfg, _ = load_configs(args)
    bus, serial_cfg = _open_probe_bus(args, arm_cfg, timeout_s=args.probe_timeout)
    _print_connection(serial_cfg, mock=args.mock)
    try:
        identity = identify_servo(bus, args.id)
    finally:
        bus.close()
    if identity is None:
        print(f"servo {args.id} did not answer at {serial_cfg.baud} baud")
        return 1
    print(f"  {identity.summary()}")
    if identity.angle_limits_counts is not None:
        low, high = identity.angle_limits_counts
        print(f"  angle limits: {low}..{high} counts")
    return 0


def _print_nudge(args) -> int:
    arm_cfg, _ = load_configs(args)
    bus, serial_cfg = _open_probe_bus(args, arm_cfg, timeout_s=args.probe_timeout)
    _print_connection(serial_cfg, mock=args.mock)
    print(
        f"keep the horn clear: commanding servo {args.id} by "
        f"{args.counts:+d} counts from wherever it sits"
    )
    try:
        result = nudge_servo(
            bus, args.id, delta_counts=args.counts, settle_s=args.settle
        )
    finally:
        bus.close()
    print(f"  {result.summary()}")
    if not result.torque_released and result.start_counts is not None:
        print("  WARNING: torque may still be enabled")
    return 0 if result.ok else 1


def _print_joint_table(args) -> None:
    arm_cfg, _ = load_configs(args)
    protocol = arm_cfg.serial.protocol
    print(f"protocol: {protocol}")
    print(f"feedback: {_feedback_text(protocol)}")
    print("configured servo IDs:")
    for joint in arm_cfg.joints:
        print(
            f"  {joint.channel}: {joint.name} "
            f"home={joint.home_deg:g}deg "
            f"safe={joint.min_deg:g}..{joint.max_deg:g}deg"
        )


def _print_protocols() -> None:
    from painterbot.control.serial_controller import available_protocols

    print("protocols:")
    for protocol in available_protocols():
        print(f"  {protocol} feedback={_feedback_text(protocol)}")


def _print_ping(args) -> None:
    arm_cfg, _ = load_configs(args)
    backend = _open_raw_backend(args, arm_cfg)
    try:
        results = read_servo_preflight(backend, [j.channel for j in arm_cfg.joints])
        for joint, result in zip(arm_cfg.joints, results):
            marker = "OK" if result.ok else "FAIL"
            print(f"  {result.servo_id}: {joint.name:12s} [{marker}] {result.detail}")
        ok_count = sum(r.ok for r in results)
        print(f"{ok_count}/{len(results)} servos responded")
    finally:
        backend.close()


def _print_assign_id(args) -> None:
    arm_cfg, _ = load_configs(args)
    print("connect exactly ONE servo before running this (docs/hardware_identification.md)")
    backend = _open_raw_backend(args, arm_cfg)
    try:
        result = assign_servo_id(backend, args.old_id, args.new_id)
        marker = "OK" if result.ok else "FAIL"
        print(f"[{marker}] {result.detail}")
    finally:
        backend.close()


def _print_mock_session(args) -> None:
    preview = args.preview
    workspace = args.workspace
    print("mock hardware session transcript:")
    print("# setup")
    print(".venv/bin/python -m pip install -e '.[dev]'")
    print("# inspect calibration state")
    print("painterbot-calibrate --dry-run")
    print("# dry-run artwork without connecting to an arm")
    print(f"painterbot-draw-shape --shape {args.shape} --dry-run")
    print("# render a preview PNG without moving hardware")
    print(f"painterbot-draw-shape --shape {args.shape} --preview {preview}")
    print("# mock execution with a synthetic calibrated workspace")
    print(
        f"painterbot-draw-shape --shape {args.shape} --mock "
        f"--workspace-config {workspace}"
    )
    print("expected output:")
    print("  dry run: stroke and point counts plus estimated servo commands")
    print(f"  wrote preview to {preview}")
    print(f"  drew {args.shape}: N stroke(s)")
    print("notes:")
    print("  No real serial port is opened when --mock is used.")
    print("  Use a temp/synthetic workspace file; real configs are not modified.")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Mock-safe servo bus bring-up inspection tools."
    )
    add_connection_args(parser)
    parser.add_argument(
        "--mock-empty-bus",
        action="store_true",
        help="with --mock, simulate a bus where nothing answers (an unpowered bus)",
    )
    sub = parser.add_subparsers(dest="command")

    ports_parser = sub.add_parser(
        "ports",
        help="list the host's serial devices and flag the likely servo adapter",
    )
    ports_parser.set_defaults(func=_print_ports)

    list_parser = sub.add_parser(
        "list-joints",
        help="list configured joints and intended servo IDs without connecting",
    )
    list_parser.set_defaults(func=_print_joint_table)

    protocols_parser = sub.add_parser(
        "protocols",
        help="list known serial protocols and whether they support feedback",
    )
    protocols_parser.set_defaults(func=lambda args: _print_protocols())

    ping_parser = sub.add_parser(
        "ping",
        help="open a connection and read each configured servo's position",
    )
    ping_parser.set_defaults(func=_print_ping)

    assign_id_parser = sub.add_parser(
        "assign-id",
        help="reassign one servo's bus ID (EEPROM write) -- one servo at a time",
    )
    assign_id_parser.add_argument(
        "--old-id", type=int, required=True, help="the servo's current bus ID"
    )
    assign_id_parser.add_argument(
        "--new-id", type=int, required=True, help="the bus ID to assign (0..253)"
    )
    assign_id_parser.set_defaults(func=_print_assign_id)

    scan_parser = sub.add_parser(
        "scan",
        help="probe a range of bus IDs and report every servo that answers",
    )
    scan_parser.add_argument(
        "--ids",
        default="0-11",
        help="IDs to probe, e.g. '1', '0-5' or '0-2,7' (default: 0-11)",
    )
    scan_parser.add_argument(
        "--baud-sweep",
        action="store_true",
        help="retry the scan at each candidate baud until something answers",
    )
    scan_parser.add_argument(
        "--probe-timeout",
        type=float,
        default=_PROBE_TIMEOUT_S,
        help=(
            "seconds to wait per probe (default: %(default)s); an absent ID costs "
            "the full timeout, so 254 IDs takes about 254x this"
        ),
    )
    scan_parser.set_defaults(func=_print_scan)

    identify_parser = sub.add_parser(
        "identify",
        help="read one servo's model, firmware, position, voltage and temperature",
    )
    identify_parser.add_argument("--id", type=int, required=True, help="the servo's bus ID")
    identify_parser.add_argument(
        "--probe-timeout", type=float, default=_PROBE_TIMEOUT_S, help=argparse.SUPPRESS
    )
    identify_parser.set_defaults(func=_print_identify)

    nudge_parser = sub.add_parser(
        "nudge",
        help="move one servo a small, capped number of encoder counts and read it back",
    )
    nudge_parser.add_argument("--id", type=int, required=True, help="the servo's bus ID")
    nudge_parser.add_argument(
        "--counts",
        type=int,
        default=DEFAULT_NUDGE_COUNTS,
        help=(
            "encoder counts to move from the current position (default: "
            "%(default)s, about 5 degrees; 4096 counts = 360 degrees). 0 is "
            "useful on its own: it exercises torque and the read path without "
            "commanding motion"
        ),
    )
    nudge_parser.add_argument(
        "--settle",
        type=float,
        default=0.5,
        help="seconds to wait before reading the position back (default: %(default)s)",
    )
    nudge_parser.add_argument(
        "--probe-timeout", type=float, default=_PROBE_TIMEOUT_S, help=argparse.SUPPRESS
    )
    nudge_parser.set_defaults(func=_print_nudge)

    session_parser = sub.add_parser(
        "mock-session",
        help="print a repeatable no-hardware workflow transcript",
    )
    session_parser.add_argument(
        "--shape",
        default="line",
        choices=("line", "square", "circle", "spiral", "star"),
    )
    session_parser.add_argument("--preview", default="out/mock-session.png")
    session_parser.add_argument(
        "--workspace",
        default="out/mock-calibrated-workspace.yaml",
        help="synthetic calibrated workspace path shown in the transcript",
    )
    session_parser.set_defaults(func=_print_mock_session)
    return parser


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    setup_logging(args.verbose)
    if args.command is None:
        args.command = "list-joints"
        args.func = _print_joint_table
    # Handlers that diagnose hardware return an exit code so the powered
    # bring-up checklist can be scripted; the inspection ones return None -> 0.
    return int(args.func(args) or 0)


if __name__ == "__main__":
    raise SystemExit(main())
