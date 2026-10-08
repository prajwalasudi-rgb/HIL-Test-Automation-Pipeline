import json
from pathlib import Path

from hil_pipeline import orchestrator as orch
from hil_pipeline.flash import flash_ecu
from hil_pipeline.release import load_release

ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / "examples"


def test_flash_gate_simulation():
    assert flash_ecu(load_release(EXAMPLES / "BODY_DEMO_v2.0.0")).ok
    failed = flash_ecu(load_release(EXAMPLES / "GATEWAY_DEMO_v3.0.0"))
    assert not failed.ok and "NEGATIVE RESPONSE" in failed.log[-1]


def test_prepare_creates_jobs_and_archives_drops(tmp_path):
    share = tmp_path / "share"
    orch.create_demo_share(share, EXAMPLES)
    jobs = orch.prepare(share)
    assert {j["ECU"] for j in jobs} == {"ECU_DEMO", "BODY_DEMO", "GATEWAY_DEMO"}
    assert all(j["PREPARATION_STATUS"] == "OK" and j["TESTING_STATUS"] == "NT" for j in jobs)
    for j in jobs:
        assert Path(j["TestSuite"]).is_file()
        assert (share / "CT_in" / j["ECU"] / "Archive" / j["SW_Name"]).is_dir()
    assert orch.prepare(share) == []  # nothing new on a second run


def test_queue_order_and_priority_zero(tmp_path):
    share = tmp_path / "share"
    orch.create_demo_share(share, EXAMPLES)
    prio = json.loads((share / "priority.json").read_text())
    prio["ECU_DEMO"]["priority"] = 0            # 0 = disabled
    (share / "priority.json").write_text(json.dumps(prio))
    orch.prepare(share)
    assert [j["ECU"] for j in orch.open_jobs(share)] == ["BODY_DEMO", "GATEWAY_DEMO"]


def test_end_to_end_demo(tmp_path):
    share = tmp_path / "share"
    orch.create_demo_share(share, EXAMPLES)
    orch.prepare(share)
    orch.queue(share, "local")
    status = {j["ECU"]: j["TESTING_STATUS"] for j in orch.load_jobs(share)}
    assert status == {"BODY_DEMO": "PASSED", "ECU_DEMO": "FAILED", "GATEWAY_DEMO": "FLASH_FAILED"}
    body = share / "CT_out" / "BODY_DEMO" / "BODY_DEMO_v2.0.0" / "results"
    assert (body / "report.html").is_file() and (body / "junit.xml").is_file()
    gateway = share / "CT_out" / "GATEWAY_DEMO" / "GATEWAY_DEMO_v3.0.0" / "results"
    assert (gateway / "flash.log").is_file() and not (gateway / "report.html").exists()
