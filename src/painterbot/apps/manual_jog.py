"""Interactive manual jog CLI (Phase 3).

Run:

    python -m painterbot.apps.manual_jog --mock
    python -m painterbot.apps.manual_jog --port /dev/tty.usbserial-XXXX

Commands::

    connect                 (re)connect the arm
    home                    move to home pose
    servo <name|idx> <deg>  move one joint (clamped to safe range)
    pose a b c d e f        move all six joints at once
    save <name>             save current pose to the workspace config
    goto <name>             move to a saved pose
    list                    list saved poses
    where                   print the current pose
    stop                    emergency stop (freeze)
    resume                  clear stop
    save-config [path]      write the workspace config (with poses) to disk
    help                    show this help
    quit / exit             leave (closes the serial port)

Jogging clamps to safe limits so you can't drive a servo past its configured
range. Every command is logged.
"""

from __future__ import annotations

import argparse
import logging

from painterbot import JOINT_ORDER
from painterbot.apps._common import (
    add_connection_args,
    connect,
    load_configs,
    setup_logging,
)
from painterbot.config import save_workspace_config
from painterbot.control.arm import Arm
from painterbot.control.servo import ServoLimitError

logger = logging.getLogger("painterbot.jog")

HELP = __doc__


def _resolve_joint(arm: Arm, token: str) -> str:
    """Accept a joint name or numeric index, return the joint name."""
    if token.isdigit():
        idx = int(token)
        if not 0 <= idx < len(arm.servos):
            raise ValueError(f"joint index {idx} out of range 0..{len(arm.servos) - 1}")
        return arm.servos[idx].name
    if token not in JOINT_ORDER:
        raise ValueError(f"unknown joint {token!r}; one of {', '.join(JOINT_ORDER)}")
    return token


def run_repl(arm: Arm, ws_cfg, args) -> Arm:
    """Run the interactive loop. Returns the live arm (may differ after `connect`)."""
    print("painterbot manual jog. Type 'help' for commands, 'quit' to exit.")
    print(f"connected (mock={arm.backend.is_mock}); pose = {_fmt(arm.pose)}")

    while True:
        try:
            line = input("jog> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not line:
            continue
        parts = line.split()
        cmd, rest = parts[0].lower(), parts[1:]

        try:
            if cmd in ("quit", "exit"):
                break
            elif cmd == "help":
                print(HELP)
            elif cmd == "connect":
                arm.close()
                arm = connect(args, arm.config)
                print(f"reconnected (mock={arm.backend.is_mock})")
            elif cmd == "home":
                arm.home(clamp=True)
                print(f"home -> {_fmt(arm.pose)}")
            elif cmd == "servo":
                name = _resolve_joint(arm, rest[0])
                sent = arm.set_joint(name, float(rest[1]), clamp=True)
                print(f"{name} -> {sent:.1f}")
            elif cmd == "pose":
                angles = [float(x) for x in rest]
                arm.move_to_pose(angles, clamp=True)
                print(f"pose -> {_fmt(arm.pose)}")
            elif cmd == "save":
                name = rest[0]
                ws_cfg.poses[name] = list(arm.pose)
                print(f"saved pose {name!r} = {_fmt(arm.pose)}")
            elif cmd == "goto":
                name = rest[0]
                arm.move_to_pose(ws_cfg.pose(name), clamp=True)
                print(f"goto {name} -> {_fmt(arm.pose)}")
            elif cmd == "list":
                _list_poses(ws_cfg)
            elif cmd == "where":
                print(_fmt(arm.pose))
            elif cmd == "stop":
                arm.stop()
                print("STOPPED — type 'resume' to continue")
            elif cmd == "resume":
                arm.resume()
                print("resumed")
            elif cmd == "save-config":
                path = save_workspace_config(ws_cfg, rest[0] if rest else None)
                print(f"workspace config written to {path}")
            else:
                print(f"unknown command {cmd!r}; type 'help'")
        except ServoLimitError as exc:
            print(f"limit: {exc}")
        except (IndexError, ValueError, KeyError, RuntimeError) as exc:
            print(f"error: {exc}")

    return arm


def _fmt(pose) -> str:
    return "[" + ", ".join(f"{a:.1f}" for a in pose) + "]"


def _list_poses(ws_cfg) -> None:
    if not ws_cfg.poses:
        print("(no saved poses)")
        return
    for name, pose in ws_cfg.poses.items():
        print(f"  {name:12s} {_fmt(pose) if pose else '(unset)'}")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Manual jog CLI for the arm.")
    add_connection_args(parser)
    args = parser.parse_args(argv)
    setup_logging(args.verbose)

    arm_cfg, ws_cfg = load_configs(args)
    arm = connect(args, arm_cfg)
    try:
        # run_repl may reconnect (the `connect` command), so close what it returns.
        arm = run_repl(arm, ws_cfg, args)
    finally:
        arm.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
