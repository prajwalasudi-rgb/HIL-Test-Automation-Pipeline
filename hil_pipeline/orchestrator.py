"""Multi-ECU orchestration over a shared folder: prepare -> queue -> execute.

Shared folder layout (a network share in production)::

    <share>/
      CT_in/<ECU>/<release>/           new software drops from the build server
      CT_in/<ECU>/Archive/<release>/   drops that have been prepared
      CT_out/<ECU>/<release_id>/
          prepared_workspace.zip       everything a bench needs to run the tests
          results/                     report.html, junit.xml, results.json, flash.log
      jobs.json                        job list: one entry per prepared release
      priority.json                    per-ECU priority and target HIL bench (0 = skip)

Stages
  prepare   for every ECU with a new drop: validate, generate the test suite,
            set up the tool projects, package the workspace to CT_out, add a
            job (PREPARATION_STATUS=OK, TESTING_STATUS=NT), archive the drop
  queue     sort the open jobs by priority and start one execution per job,
            either directly (local) or as a GitLab pipeline via the trigger API
  execute   unpack the workspace on the bench, flash the ECU, and only if the
            flash succeeded run the tests; publish results to CT_out
"""
from __future__ import annotations

import json
import os
import shutil
import tempfile
import time
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path

from .flash import flash_ecu
from .pipeline import run_stage
from .release import MANIFEST_NAME, ReleaseError, load_release

JOBS = "jobs.json"
PRIORITY = "priority.json"


# ---------------------------------------------------------------- job list --
def load_jobs(share: Path) -> list[dict]:
    f = share / JOBS
    return json.loads(f.read_text()) if f.is_file() else []


def save_jobs(share: Path, jobs: list[dict]) -> None:
    tmp = share / (JOBS + ".tmp")
    tmp.write_text(json.dumps(jobs, indent=2))
    tmp.replace(share / JOBS)  # atomic: other runners never see half a file


def load_priorities(share: Path) -> dict:
    f = share / PRIORITY
    return json.loads(f.read_text()) if f.is_file() else {}


def _update_job(share: Path, job_id: str, **fields) -> dict:
    jobs = load_jobs(share)
    for job in jobs:
        if job["job_id"] == job_id:
            job.update(fields)
            save_jobs(share, jobs)
            return job
    raise KeyError(job_id)


# ----------------------------------------------------------------- prepare --
def _new_drops(share: Path) -> list[Path]:
    drops = []
    for ecu_dir in sorted((share / "CT_in").glob("*")):
        if not ecu_dir.is_dir():
            continue
        for drop in sorted(ecu_dir.iterdir()):
            if drop.is_dir() and drop.name != "Archive" and (drop / MANIFEST_NAME).is_file():
                drops.append(drop)
    return drops


def prepare(share: Path, backend: str | None = None) -> list[dict]:
    """Prepare every new software drop; returns the jobs that were created."""
    created = []
    priorities = load_priorities(share)
    for drop in _new_drops(share):
        try:
            release = load_release(drop)
        except ReleaseError as exc:
            print(f"[prepare] {drop}: rejected ({exc})")
            continue
        print(f"[prepare] {release.ecu}: new software {release.release_id}")
        out_dir = share / "CT_out" / release.ecu / release.release_id
        out_dir.mkdir(parents=True, exist_ok=True)
        job = {
            "job_id": f"{release.release_id}_{int(time.time() * 1000) % 10**8}",
            "ECU": release.ecu,
            "SW_Name": release.release_id,
            "HIL": priorities.get(release.ecu, {}).get("hil", "HIL-1"),
            "Priority": int(priorities.get(release.ecu, {}).get("priority", 99)),
            "TestSuite": str(out_dir / "prepared_workspace.zip"),
            "PREPARATION_STATUS": "FAILED",
            "TESTING_STATUS": "NT",
        }
        with tempfile.TemporaryDirectory() as tmp:
            ws = Path(tmp)
            shutil.copytree(drop, ws / "release")
            ok = all(run_stage(s, ws / "release", ws / "build", backend)
                     for s in ("validate", "generate", "setup"))
            if ok:
                with zipfile.ZipFile(job["TestSuite"], "w", zipfile.ZIP_DEFLATED) as z:
                    for p in ws.rglob("*"):
                        z.write(p, p.relative_to(ws))
                job["PREPARATION_STATUS"] = "OK"
        archive = drop.parent / "Archive" / drop.name
        archive.parent.mkdir(exist_ok=True)
        if archive.exists():
            shutil.rmtree(archive)
        shutil.move(str(drop), str(archive))
        jobs = load_jobs(share)
        jobs.append(job)
        save_jobs(share, jobs)
        created.append(job)
        print(f"[prepare] {release.ecu}: workspace -> {job['TestSuite']} "
              f"(preparation {job['PREPARATION_STATUS']}), drop archived")
    if not created:
        print("[prepare] no new software drops")
    return created


# ------------------------------------------------------------------- queue --
def open_jobs(share: Path) -> list[dict]:
    """Prepared, not yet tested jobs in execution order (priority 0 = disabled)."""
    jobs = [j for j in load_jobs(share)
            if j["PREPARATION_STATUS"] == "OK" and j["TESTING_STATUS"] == "NT"
            and j["Priority"] != 0]
    return sorted(jobs, key=lambda j: (j["Priority"], j["job_id"]))


def trigger_gitlab_execution(job: dict) -> str:
    """Start an execution pipeline for one job via the GitLab trigger API."""
    url = (f"{os.environ['GITLAB_URL'].rstrip('/')}/api/v4/projects/"
           f"{urllib.parse.quote(os.environ['GITLAB_PROJECT'], safe='')}/trigger/pipeline")
    variables = {"TEST_TASK": "Execution", "JOB_ID": job["job_id"], "ECU": job["ECU"],
                 "HIL": job["HIL"], "SW_NAME": job["SW_Name"], "PRIORITY": str(job["Priority"])}
    data = urllib.parse.urlencode({
        "token": os.environ["GITLAB_TRIGGER_TOKEN"],
        "ref": os.environ.get("GITLAB_REF", "main"),
        **{f"variables[{k}]": v for k, v in variables.items()},
    }).encode()
    with urllib.request.urlopen(urllib.request.Request(url, data=data), timeout=30) as resp:
        return json.loads(resp.read())["web_url"]


def queue(share: Path, mode: str = "local", backend: str | None = None) -> list[dict]:
    started = []
    for job in open_jobs(share):
        print(f"[queue] priority {job['Priority']}: {job['SW_Name']} on {job['HIL']}")
        if mode == "gitlab":
            url = trigger_gitlab_execution(job)
            _update_job(share, job["job_id"], TESTING_STATUS="QUEUED", pipeline=url)
            print(f"[queue]   pipeline started: {url}")
        else:
            execute(share, job["job_id"], backend)
        started.append(job)
    if not started:
        print("[queue] nothing to run")
    return started


# ----------------------------------------------------------------- execute --
def execute(share: Path, job_id: str, backend: str | None = None) -> bool:
    job = next(j for j in load_jobs(share) if j["job_id"] == job_id)
    _update_job(share, job_id, TESTING_STATUS="RUNNING")
    results = Path(job["TestSuite"]).parent / "results"
    results.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory() as tmp:
        ws = Path(tmp)
        with zipfile.ZipFile(job["TestSuite"]) as z:
            z.extractall(ws)
        release = load_release(ws / "release")
        print(f"[execute] {job['SW_Name']} on {job['HIL']}")

        flash = flash_ecu(release)
        (results / "flash.log").write_text("\n".join(flash.log) + "\n")
        for line in flash.log:
            print(f"[execute]   {line}")
        if not flash.ok:
            _update_job(share, job_id, TESTING_STATUS="FLASH_FAILED", Flash_verdict="failed")
            print(f"[execute] {job['SW_Name']}: flashing failed - tests not started")
            return False

        tests_ok = run_stage("test", ws / "release", ws / "build", backend)
        run_stage("report", ws / "release", ws / "build", backend)
        for name in ("report.html", "junit.xml", "results.json", "test_suite.yaml"):
            src = ws / "build" / release.release_id / name
            if src.is_file():
                shutil.copy(src, results / name)

    status = "PASSED" if tests_ok else "FAILED"
    _update_job(share, job_id, TESTING_STATUS=status, Flash_verdict="passed")
    print(f"[execute] {job['SW_Name']}: {status} -> {results}")
    return tests_ok


# -------------------------------------------------------------------- demo --
def summary(share: Path) -> str:
    rows = ["| ECU | Software | Priority | HIL | Preparation | Testing |",
            "|---|---|---|---|---|---|"]
    for j in sorted(load_jobs(share), key=lambda j: j["Priority"]):
        rows.append(f"| {j['ECU']} | {j['SW_Name']} | {j['Priority']} | {j['HIL']} | "
                    f"{j['PREPARATION_STATUS']} | {j['TESTING_STATUS']} |")
    return "\n".join(rows)


def create_demo_share(share: Path, examples: Path) -> None:
    """A share with three software drops for three ECUs and a priority list."""
    if share.exists():
        shutil.rmtree(share)
    drops = {"ECU_DEMO": "ECU_DEMO_v1.1.0", "BODY_DEMO": "BODY_DEMO_v2.0.0",
             "GATEWAY_DEMO": "GATEWAY_DEMO_v3.0.0"}
    for ecu, rel in drops.items():
        shutil.copytree(examples / rel, share / "CT_in" / ecu / rel)
    (share / "CT_out").mkdir(parents=True)
    (share / PRIORITY).write_text(json.dumps({
        "BODY_DEMO": {"priority": 1, "hil": "HIL-2"},
        "ECU_DEMO": {"priority": 2, "hil": "HIL-1"},
        "GATEWAY_DEMO": {"priority": 3, "hil": "HIL-3"},
    }, indent=2))
