"""Generate a test suite from the release's CAN database.

Every message in the DBC gets:
  * a presence test      - the ECU must send the message at all
  * a cycle-time test    - if the DBC defines GenMsgCycleTime
and every signal with a defined physical range gets
  * a signal-range test  - all received values must stay inside [min, max]
"""
from __future__ import annotations

from pathlib import Path

import cantools
import yaml

from .release import Release


def generate_test_suite(release: Release) -> dict:
    db = cantools.database.load_file(str(release.dbc_path))
    tests = []
    for msg in sorted(db.messages, key=lambda m: m.name):
        frame = f"0x{msg.frame_id:08X}"
        tests.append({
            "id": f"PRES_{msg.name}",
            "type": "presence",
            "message": msg.name,
            "frame_id": frame,
        })
        if msg.cycle_time:
            tests.append({
                "id": f"CYC_{msg.name}",
                "type": "cycle_time",
                "message": msg.name,
                "frame_id": frame,
                "nominal_ms": msg.cycle_time,
                "tolerance": release.cycle_time_tolerance,
            })
        for sig in sorted(msg.signals, key=lambda s: s.name):
            if sig.minimum is None or sig.maximum is None:
                continue
            tests.append({
                "id": f"RNG_{sig.name}",
                "type": "signal_range",
                "message": msg.name,
                "signal": sig.name,
                "min": sig.minimum,
                "max": sig.maximum,
                "unit": sig.unit or "",
            })
    return {
        "suite": f"{release.release_id}_Regression",
        "ecu": release.ecu,
        "version": release.version,
        "dbc": release.dbc_path.name,
        "duration_s": release.duration_s,
        "tests": tests,
    }


def write_test_suite(suite: dict, out_file: Path) -> Path:
    out_file.parent.mkdir(parents=True, exist_ok=True)
    out_file.write_text(yaml.safe_dump(suite, sort_keys=False), encoding="utf-8")
    return out_file
