import shutil
import time
from pathlib import Path

import pytest

from hil_pipeline.pipeline import run_all
from hil_pipeline.release import ReleaseError, load_release
from hil_pipeline.runner import evaluate
from hil_pipeline.testgen import generate_test_suite
from hil_pipeline.watcher import find_new_releases

ROOT = Path(__file__).resolve().parents[1]
GOOD = ROOT / "examples" / "ECU_DEMO_v1.0.0"
BAD = ROOT / "examples" / "ECU_DEMO_v1.1.0"


def test_release_loads():
    r = load_release(GOOD)
    assert r.release_id == "ECU_DEMO_v1.0.0"
    assert r.dbc_path.name == "ecu.dbc"


def test_incomplete_release_is_rejected(tmp_path):
    with pytest.raises(ReleaseError):
        load_release(tmp_path)


def test_suite_generated_from_dbc():
    suite = generate_test_suite(load_release(GOOD))
    types = [t["type"] for t in suite["tests"]]
    assert types.count("presence") == 3
    assert types.count("cycle_time") == 3
    assert types.count("signal_range") == 6


def test_cycle_time_evaluation_detects_slow_message():
    release = load_release(GOOD)
    suite = generate_test_suite(release)
    suite["tests"] = [t for t in suite["tests"] if t["id"] == "CYC_EEC1_Demo"]
    frame_id = 0x0CF00427
    payload = bytes(8)
    on_time = [(i * 0.100, frame_id, payload) for i in range(20)]
    too_slow = [(i * 0.150, frame_id, payload) for i in range(20)]
    assert evaluate(suite, release.dbc_path, on_time)[0]["passed"]
    assert not evaluate(suite, release.dbc_path, too_slow)[0]["passed"]


def test_healthy_release_passes(tmp_path):
    assert run_all(GOOD, tmp_path / "build")
    assert (tmp_path / "build" / "ECU_DEMO_v1.0.0" / "report.html").is_file()
    assert (tmp_path / "build" / "ECU_DEMO_v1.0.0" / "junit.xml").is_file()


def test_regression_is_caught(tmp_path):
    assert not run_all(BAD, tmp_path / "build")


def test_watcher_finds_only_complete_drops(tmp_path):
    incoming = tmp_path / "incoming"
    shutil.copytree(GOOD, incoming / "ECU_DEMO_v1.0.0")
    (incoming / "half_copied").mkdir()  # no manifest yet
    time.sleep(0.2)
    found = find_new_releases(incoming, settle_s=0.1)
    assert [p.name for p in found] == ["ECU_DEMO_v1.0.0"]
