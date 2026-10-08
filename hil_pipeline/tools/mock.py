"""Mock tool adapters: same interface as the real tools, no licences needed.

They write plain JSON/YAML "projects" so every pipeline stage produces a
visible artifact, and execution runs against the simulated ECU on a virtual
CAN bus.
"""
from __future__ import annotations

import json
import shutil
import time
from pathlib import Path

from ..release import Release
from ..runner import evaluate, new_channel_name, record_traffic
from ..sim.ecu_sim import EcuSimulator
from .base import ExperimentTool, TestAutomationTool


class MockExperimentTool(ExperimentTool):
    name = "mock-experiment-tool"

    def create_project(self, release: Release, suite: dict, out_dir: Path) -> Path:
        out_dir.mkdir(parents=True, exist_ok=True)
        layouts: dict[str, list[str]] = {}
        for test in suite["tests"]:
            if test["type"] == "signal_range":
                layouts.setdefault(test["message"], []).append(test["signal"])
        project = {
            "project": f"{release.release_id}_Experiment",
            "platform": "virtual-can",
            "variable_description": release.dbc_path.name,
            "layouts": [{"name": msg, "instruments": [{"type": "plotter", "signals": sigs}]}
                        for msg, sigs in sorted(layouts.items())],
            "created": time.strftime("%Y-%m-%dT%H:%M:%S"),
        }
        path = out_dir / f"{release.release_id}_Experiment.json"
        path.write_text(json.dumps(project, indent=2), encoding="utf-8")
        return path


class MockTestAutomationTool(TestAutomationTool):
    name = "mock-test-automation-tool"

    def create_project(self, release: Release, out_dir: Path) -> Path:
        project = out_dir / f"{release.release_id}_TestProject"
        project.mkdir(parents=True, exist_ok=True)
        (project / "project.json").write_text(json.dumps({
            "project": project.name,
            "ecu": release.ecu,
            "version": release.version,
            "created": time.strftime("%Y-%m-%dT%H:%M:%S"),
        }, indent=2), encoding="utf-8")
        return project

    def import_test_suite(self, project: Path, suite_file: Path) -> None:
        shutil.copy(suite_file, project / suite_file.name)

    def execute(self, project: Path, release: Release, suite: dict) -> list[dict]:
        channel = new_channel_name()
        ecu = EcuSimulator(release.dbc_path, channel=channel, faults=release.sim_faults)
        ecu.start()
        try:
            time.sleep(0.05)  # let the ECU come up before recording
            frames = record_traffic(channel, suite["duration_s"])
        finally:
            ecu.stop()
        return evaluate(suite, release.dbc_path, frames)
