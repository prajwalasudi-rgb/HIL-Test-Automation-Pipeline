"""A simulated ECU on a virtual CAN bus.

On a real HIL bench the ECU is physical hardware and the dSPACE simulator
provides the rest of the vehicle. For the demo, this thread plays the ECU:
it sends every message from the DBC at its cycle time with plausible,
changing signal values. Faults from the release manifest let a "buggy"
software version be simulated.
"""
from __future__ import annotations

import math
import threading
import time

import can
import cantools


def _signal_value(name: str, t: float) -> float:
    """Plausible, slowly varying physical values for the demo signals."""
    profiles = {
        "EngineSpeed": 1200 + 400 * math.sin(t * 0.8),
        "ActualEngineTorque": 30 + 20 * math.sin(t * 0.5),
        "WheelBasedVehicleSpeed": min(80.0, 12.0 * t),
        "ParkingBrakeSwitch": 0,
        "EngineCoolantTemp": 85 + 3 * math.sin(t * 0.2),
        "EngineOilTemp": 95 + 2 * math.sin(t * 0.3),
        "CabinTemp": 21 + 1.5 * math.sin(t * 0.4),
        "HeadlampLevel": 60,
    }
    return profiles.get(name, 0)


class EcuSimulator:
    def __init__(self, dbc_path, channel: str, faults: list | None = None,
                 interface: str = "virtual"):
        self.db = cantools.database.load_file(str(dbc_path))
        self.channel = channel
        self.interface = interface
        self.faults = faults or []
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    # -- fault handling ----------------------------------------------------
    def _cycle_s(self, msg) -> float:
        cycle = msg.cycle_time / 1000.0
        for f in self.faults:
            if f.get("type") == "slow_cycle" and f.get("message") == msg.name:
                cycle *= float(f.get("factor", 1.0))
        return cycle

    def _encode(self, msg, t: float) -> bytes:
        values = {s.name: _signal_value(s.name, t) for s in msg.signals}
        data = bytearray(msg.encode(values, strict=False))
        for f in self.faults:
            if f.get("type") == "out_of_range":
                sig = next((s for s in msg.signals if s.name == f.get("signal")), None)
                if sig is not None:
                    # write the raw value directly, bypassing range checks
                    raw = int(f["raw_value"])
                    start = sig.start // 8
                    nbytes = max(1, sig.length // 8)
                    data[start:start + nbytes] = raw.to_bytes(nbytes, "little")
        return bytes(data)

    # -- thread ------------------------------------------------------------
    def _run(self):
        bus = can.Bus(interface=self.interface, channel=self.channel,
                      receive_own_messages=False)
        try:
            schedule = [m for m in self.db.messages if m.cycle_time]
            t0 = time.perf_counter()
            next_due = {m.name: t0 for m in schedule}
            while not self._stop.is_set():
                now = time.perf_counter()
                for m in schedule:
                    if now >= next_due[m.name]:
                        bus.send(can.Message(arbitration_id=m.frame_id,
                                             is_extended_id=m.is_extended_frame,
                                             data=self._encode(m, now - t0)))
                        next_due[m.name] += self._cycle_s(m)
                sleep_for = min(next_due.values()) - time.perf_counter()
                if sleep_for > 0:
                    self._stop.wait(min(sleep_for, 0.05))
        finally:
            bus.shutdown()

    def start(self):
        self._thread = threading.Thread(target=self._run, name="ecu-sim", daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2)
