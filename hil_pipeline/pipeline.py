"""The pipeline stages. Each stage reads/writes files in the build folder, so
CI can run them as separate jobs and pass the folder on as an artifact.

    validate -> generate -> setup -> test -> report
"""
from __future__ import annotations

import json
from pathlib import Path

import yaml

from .release import load_release
from .report import write_html, write_junit
from .testgen import generate_test_suite, write_test_suite
from .tools import get_tools

STAGES = ["validate", "generate", "setup", "test", "report"]


def _build_dir(build_root: Path, release_id: str) -> Path:
    d = build_root / release_id
    d.mkdir(parents=True, exist_ok=True)
    return d


def run_stage(stage: str, release_dir: Path, build_root: Path, backend: str | None = None) -> bool:
    release = load_release(release_dir)
    out = _build_dir(build_root, release.release_id)
    suite_file = out / "test_suite.yaml"
    experiment_tool, automation_tool = get_tools(backend)

    if stage == "validate":
        print(f"[validate] {release.release_id}: manifest and CAN database OK "
              f"({release.dbc_path.name})")
        return True

    if stage == "generate":
        suite = generate_test_suite(release)
        write_test_suite(suite, suite_file)
        counts: dict[str, int] = {}
        for t in suite["tests"]:
            counts[t["type"]] = counts.get(t["type"], 0) + 1
        print(f"[generate] {len(suite['tests'])} tests -> {suite_file} {counts}")
        return True

    suite = yaml.safe_load(suite_file.read_text(encoding="utf-8"))

    if stage == "setup":
        exp = experiment_tool.create_project(release, suite, out / "projects")
        proj = automation_tool.create_project(release, out / "projects")
        automation_tool.import_test_suite(proj, suite_file)
        print(f"[setup] {experiment_tool.name}: {exp}")
        print(f"[setup] {automation_tool.name}: {proj} (suite imported)")
        return True

    if stage == "test":
        proj = out / "projects" / f"{release.release_id}_TestProject"
        results = automation_tool.execute(proj, release, suite)
        (out / "results.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
        write_junit(results, suite, out / "junit.xml")
        failed = [r for r in results if not r["passed"]]
        print(f"[test] {len(results) - len(failed)}/{len(results)} passed")
        for r in failed:
            print(f"[test]   FAIL {r['id']}: {r['detail']}")
        return not failed

    if stage == "report":
        results = json.loads((out / "results.json").read_text(encoding="utf-8"))
        path = write_html(results, suite, out / "report.html")
        print(f"[report] {path}")
        return all(r["passed"] for r in results)

    raise ValueError(f"unknown stage '{stage}'")


def run_all(release_dir: Path, build_root: Path, backend: str | None = None) -> bool:
    ok = True
    for stage in STAGES:
        stage_ok = run_stage(stage, release_dir, build_root, backend)
        ok = ok and stage_ok
    return ok
