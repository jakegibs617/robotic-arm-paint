"""Mock-safe hardware bring-up helpers.

The commands in this module are intended for pre-hardware and first-power-on
sessions. They inspect configuration and protocol capabilities without opening a
serial port unless a future subcommand explicitly opts into that behavior.
"""

from __future__ import annotations

import argparse

from painterbot.apps._common import add_connection_args, load_configs, setup_logging
from painterbot.control.serial_controller import get_feedback


def _feedback_text(protocol: str) -> str:
    return "yes" if get_feedback(protocol) is not None else "no"


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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Mock-safe servo bus bring-up inspection tools."
    )
    add_connection_args(parser)
    sub = parser.add_subparsers(dest="command")

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
    return parser


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    setup_logging(args.verbose)
    if args.command is None:
        args.command = "list-joints"
        args.func = _print_joint_table
    args.func(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
