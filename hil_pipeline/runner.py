"""Execute a generated test suite against the bus and evaluate the results."""
from __future__ import annotations

import statistics
import time
import uuid

import can
import cantools


def record_traffic(channel: str, duration_s: float, interface: str = "virtual"):
    """Record (timestamp, frame_id, data) tuples for `duration_s` seconds."""
    frames = []
    with can.Bus(interface=interface, channel=channel) as bus:
        end = time.perf_counter() + duration_s
        while True:
            remaining = end - time.perf_counter()
            if remaining <= 0:
                break
            msg = bus.recv(timeout=min(remaining, 0.1))
            if msg is not None:
                frames.append((time.perf_counter(), msg.arbitration_id, bytes(msg.data)))
    return frames


def evaluate(suite: dict, dbc_path, frames) -> list[dict]:
    """Evaluate every test of the suite on the recorded frames."""
    db = cantools.database.load_file(str(dbc_path))
    by_msg: dict[str, list] = {}
    for ts, fid, data in frames:
        try:
            msg = db.get_message_by_frame_id(fid)
        except KeyError:
            continue
        by_msg.setdefault(msg.name, []).append((ts, data))

    results = []
    for test in suite["tests"]:
        received = by_msg.get(test["message"], [])
        res = {"id": test["id"], "type": test["type"], "message": test["message"]}

        if test["type"] == "presence":
            res["passed"] = len(received) > 0
            res["detail"] = f"{len(received)} frames received"

        elif test["type"] == "cycle_time":
            nominal = test["nominal_ms"]
            tol = test["tolerance"]
            stamps = [ts for ts, _ in received]
            gaps_ms = [(b - a) * 1000.0 for a, b in zip(stamps, stamps[1:])]
            res["nominal_ms"] = nominal
            res["tolerance"] = tol
            res["gaps_ms"] = [round(g, 3) for g in gaps_ms]
            if len(gaps_ms) < 2:
                res["passed"] = False
                res["detail"] = "too few frames to measure the cycle time"
            else:
                mean = statistics.fmean(gaps_ms)
                lo, hi = nominal * (1 - tol), nominal * (1 + tol)
                res["mean_ms"] = round(mean, 2)
                res["passed"] = lo <= mean <= hi
                res["detail"] = (f"mean {mean:.1f} ms, expected {nominal} ms "
                                 f"+/-{tol:.0%} ({lo:.0f}-{hi:.0f} ms)")

        elif test["type"] == "signal_range":
            msg = db.get_message_by_name(test["message"])
            values = []
            for _, data in received:
                decoded = msg.decode(data, decode_choices=False, scaling=True)
                values.append(float(decoded[test["signal"]]))
            res["signal"] = test["signal"]
            if not values:
                res["passed"] = False
                res["detail"] = "signal never received"
            else:
                vmin, vmax = min(values), max(values)
                res["passed"] = test["min"] <= vmin and vmax <= test["max"]
                res["detail"] = (f"observed {vmin:g} to {vmax:g} {test['unit']}, "
                                 f"allowed {test['min']:g} to {test['max']:g}")
        else:
            res["passed"] = False
            res["detail"] = f"unknown test type {test['type']}"
        results.append(res)
    return results


def new_channel_name() -> str:
    """A unique virtual-bus channel so parallel runs don't see each other."""
    return f"hil-{uuid.uuid4().hex[:8]}"
