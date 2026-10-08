"""Software release drops: what the build server places in the incoming folder."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml

MANIFEST_NAME = "manifest.yaml"


class ReleaseError(Exception):
    """Raised when a release folder is incomplete or invalid."""


@dataclass
class Release:
    path: Path
    ecu: str
    version: str
    dbc_path: Path
    duration_s: float = 4.0
    cycle_time_tolerance: float = 0.10
    sim_faults: list = field(default_factory=list)

    @property
    def release_id(self) -> str:
        return f"{self.ecu}_v{self.version}"


def load_release(path: str | Path) -> Release:
    """Read and validate a release folder (manifest + CAN database)."""
    path = Path(path)
    manifest_file = path / MANIFEST_NAME
    if not manifest_file.is_file():
        raise ReleaseError(f"{path}: no {MANIFEST_NAME} found")

    manifest = yaml.safe_load(manifest_file.read_text(encoding="utf-8")) or {}
    for key in ("ecu", "version", "dbc"):
        if key not in manifest:
            raise ReleaseError(f"{manifest_file}: missing required key '{key}'")

    dbc_path = path / manifest["dbc"]
    if not dbc_path.is_file():
        raise ReleaseError(f"{path}: CAN database '{manifest['dbc']}' not found")

    cfg = manifest.get("test_config") or {}
    return Release(
        path=path,
        ecu=str(manifest["ecu"]),
        version=str(manifest["version"]),
        dbc_path=dbc_path,
        duration_s=float(cfg.get("duration_s", 4.0)),
        cycle_time_tolerance=float(cfg.get("cycle_time_tolerance", 0.10)),
        sim_faults=list(manifest.get("sim_faults") or []),
    )
