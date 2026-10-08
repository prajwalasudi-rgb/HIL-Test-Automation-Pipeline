"""ECU flashing step (UDS-style), run before tests on the bench.

On a real bench this would drive a flash tool or a UDS stack over CAN:
diagnostic session control (0x10), security access (0x27), erase / request
download / transfer data / transfer exit (0x31, 0x34, 0x36, 0x37), checksum
routine and ECU reset (0x11). The demo simulates the same sequence and lets a
release fail it on purpose (sim_faults: [{type: flash_failure, step: ...}]),
which is how the execution stage's "no tests on a failed flash" gate is shown.
"""
from __future__ import annotations

from dataclasses import dataclass

from .release import Release

UDS_SEQUENCE = [
    ("0x10", "Diagnostic session control: programming session"),
    ("0x27", "Security access"),
    ("0x31", "Routine control: erase memory"),
    ("0x34", "Request download"),
    ("0x36", "Transfer data"),
    ("0x37", "Request transfer exit"),
    ("0x31", "Routine control: check memory / checksum"),
    ("0x11", "ECU reset"),
]


@dataclass
class FlashResult:
    ok: bool
    log: list[str]

    @property
    def verdict(self) -> str:
        return "passed" if self.ok else "failed"


def flash_ecu(release: Release) -> FlashResult:
    fail_at = next((f.get("step", "0x36") for f in release.sim_faults
                    if f.get("type") == "flash_failure"), None)
    log = [f"Flashing {release.release_id} onto {release.ecu}"]
    for sid, name in UDS_SEQUENCE:
        if sid == fail_at:
            log.append(f"  {sid} {name}: NEGATIVE RESPONSE (0x72 general programming failure)")
            return FlashResult(False, log)
        log.append(f"  {sid} {name}: OK")
    return FlashResult(True, log)
