"""Shared CLI helpers: argument wiring, logging, and arm connection."""

from __future__ import annotations

import argparse
import logging
from pathlib import Path
from typing import Optional

from painterbot.config import (
    ArmConfig,
    WorkspaceConfig,
    load_arm_config,
    load_workspace_config,
)
from painterbot.control.arm import Arm


def add_connection_args(parser: argparse.ArgumentParser) -> None:
    """Add the serial/connection flags shared by every app."""
    parser.add_argument(
        "--mock",
        action="store_true",
        help="use the in-memory mock backend (no hardware)",
    )
    parser.add_argument(
        "--port",
        default=None,
        help=(
            "serial port, e.g. /dev/cu.usbmodem5B790320481 (omit with --mock); "
            "use the /dev/cu.* node, not /dev/tty.*"
        ),
    )
    parser.add_argument(
        "--baud",
        type=int,
        default=None,
        help="serial baud rate (default: serial.baud from the arm config)",
    )
    parser.add_argument(
        "--protocol",
        default=None,
        help=(
            "wire protocol, e.g. sts3215 (default: serial.protocol from the arm "
            "config, which ships as 'mock')"
        ),
    )
    parser.add_argument(
        "--arm-config",
        type=Path,
        default=None,
        help="path to arm config YAML (default: configs/arm.default.yaml)",
    )
    parser.add_argument(
        "--workspace-config",
        type=Path,
        default=None,
        help="path to workspace config YAML (default: calibrated, else default)",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="log every servo command",
    )


def resolve_serial(args, arm_cfg: ArmConfig):
    """The serial settings actually in force: CLI flags win over the config."""
    serial_cfg = arm_cfg.serial
    return serial_cfg.model_copy(
        update={
            "port": args.port or serial_cfg.port,
            "baud": getattr(args, "baud", None) or serial_cfg.baud,
            "protocol": getattr(args, "protocol", None) or serial_cfg.protocol,
        }
    )


def setup_logging(verbose: bool) -> None:
    logging.basicConfig(
        level=logging.INFO if verbose else logging.WARNING,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
        datefmt="%H:%M:%S",
    )


def load_configs(args) -> tuple[ArmConfig, WorkspaceConfig]:
    arm_cfg = load_arm_config(args.arm_config)
    ws_cfg = load_workspace_config(args.workspace_config)
    return arm_cfg, ws_cfg


def connect(args, arm_cfg: ArmConfig) -> Arm:
    return Arm.connect(arm_cfg, mock=args.mock, port=args.port)
