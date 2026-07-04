"""Typed configuration models and loaders.

Configs live in ``configs/*.yaml``. These pydantic models validate them and give
the rest of the package a typed, autocompleting view of the settings.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import yaml
from pydantic import BaseModel, Field, field_validator

# Repo root is three parents up from this file: src/painterbot/config.py
REPO_ROOT = Path(__file__).resolve().parents[2]
CONFIGS_DIR = REPO_ROOT / "configs"


class SerialConfig(BaseModel):
    baud: int = 115200
    port: Optional[str] = None
    timeout_s: float = 1.0
    protocol: str = "mock"


class MotionConfig(BaseModel):
    max_step_deg: float = 2.0
    step_delay_s: float = 0.02


class JointConfig(BaseModel):
    name: str
    channel: int
    min_deg: float
    max_deg: float
    home_deg: float
    invert: bool = False

    @field_validator("max_deg")
    @classmethod
    def _max_above_min(cls, v: float, info) -> float:
        min_deg = info.data.get("min_deg")
        if min_deg is not None and v <= min_deg:
            raise ValueError(f"max_deg ({v}) must exceed min_deg ({min_deg})")
        return v

    def clamp(self, deg: float) -> float:
        """Clamp a requested angle into this joint's safe range."""
        return max(self.min_deg, min(self.max_deg, deg))

    def in_range(self, deg: float) -> bool:
        return self.min_deg <= deg <= self.max_deg


class ArmConfig(BaseModel):
    serial: SerialConfig = Field(default_factory=SerialConfig)
    motion: MotionConfig = Field(default_factory=MotionConfig)
    joints: list[JointConfig]

    @field_validator("joints")
    @classmethod
    def _exactly_six(cls, v: list[JointConfig]) -> list[JointConfig]:
        if len(v) != 6:
            raise ValueError(f"expected 6 joints, got {len(v)}")
        return v

    @property
    def home_pose(self) -> list[float]:
        return [j.home_deg for j in self.joints]

    def joint(self, name: str) -> JointConfig:
        for j in self.joints:
            if j.name == name:
                return j
        raise KeyError(f"no joint named {name!r}")


class PaperConfig(BaseModel):
    width_mm: float = 150.0
    height_mm: float = 150.0
    margin_mm: float = 10.0


class DrawingConfig(BaseModel):
    point_spacing_mm: float = 1.5
    pen_settle_s: float = 0.3


class WorkspaceConfig(BaseModel):
    paper: PaperConfig = Field(default_factory=PaperConfig)
    # Named poses; each is a list of 6 servo angles or None if not yet captured.
    poses: dict[str, Optional[list[float]]] = Field(default_factory=dict)
    drawing: DrawingConfig = Field(default_factory=DrawingConfig)

    @field_validator("poses", mode="before")
    @classmethod
    def _pose_shapes(cls, v):
        if v is None:
            return {}
        if not isinstance(v, dict):
            raise ValueError("poses must be a mapping of pose name to 6 angles or null")
        for name, pose in v.items():
            if pose is None:
                continue
            if not isinstance(pose, (list, tuple)):
                raise ValueError(f"pose {name!r}: expected 6 numeric angles or null")
            if len(pose) != 6:
                raise ValueError(
                    f"pose {name!r}: expected 6 numeric angles, got {len(pose)}"
                )
            for idx, angle in enumerate(pose):
                if isinstance(angle, bool) or not isinstance(angle, (int, float)):
                    raise ValueError(
                        f"pose {name!r}: angle {idx} is not numeric"
                    )
        return v

    def pose(self, name: str) -> list[float]:
        p = self.poses.get(name)
        if p is None:
            raise KeyError(
                f"pose {name!r} is not set; capture it with the jog CLI "
                f"(`save {name}`) before drawing"
            )
        return list(p)

    def has_pose(self, name: str) -> bool:
        return self.poses.get(name) is not None


def _load_yaml(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def load_arm_config(path: Optional[Path] = None) -> ArmConfig:
    path = path or CONFIGS_DIR / "arm.default.yaml"
    return ArmConfig.model_validate(_load_yaml(path))


def resolve_workspace_config_path(path: Optional[Path] = None) -> Path:
    """Resolve the workspace config path that ``load_workspace_config`` will read."""
    if path is not None:
        return path
    calibrated = CONFIGS_DIR / "workspace.calibrated.yaml"
    return calibrated if calibrated.exists() else CONFIGS_DIR / "workspace.default.yaml"


def default_workspace_save_path(path: Optional[Path] = None) -> Path:
    """Resolve where captured calibration poses should be saved."""
    return path or CONFIGS_DIR / "workspace.calibrated.yaml"


def load_workspace_config(path: Optional[Path] = None) -> WorkspaceConfig:
    """Load workspace config, preferring the calibrated file if it exists."""
    return WorkspaceConfig.model_validate(_load_yaml(resolve_workspace_config_path(path)))


def save_workspace_config(cfg: WorkspaceConfig, path: Optional[Path] = None) -> Path:
    """Persist a workspace config (used to store captured poses)."""
    path = default_workspace_save_path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        yaml.safe_dump(cfg.model_dump(), f, sort_keys=False)
    return path
