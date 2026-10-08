"""Command line: python -m hil_pipeline <command> ...

Single release
  run     <release_dir>             all stages for one release
  stage   <name> <release_dir>      a single stage (used by CI jobs)
  watch   <incoming_dir>            wait for new software drops (single folder)

Multi-ECU orchestration over a shared folder (CT_in / CT_out)
  prepare <share>                   prepare every new software drop, create jobs
  queue   <share>                   start open jobs in priority order
  execute <share> --job <JOB_ID>    flash + test one prepared job (execution pipeline)
  status  <share>                   print the job table
  demo    [<share>]                 three ECUs end to end: prepare -> queue -> execute
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from . import orchestrator as orch
from .pipeline import STAGES, run_all, run_stage
from .watcher import watch

EXAMPLES = Path(__file__).resolve().parents[1] / "examples"


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="hil_pipeline", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--build", default="build", type=Path, help="build/output folder")
    p.add_argument("--backend", choices=["mock", "dspace"], default=None,
                   help="tool backend (default: mock, or $HIL_TOOL_BACKEND)")
    sub = p.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("run", help="run all stages for one release")
    r.add_argument("release_dir", type=Path)

    s = sub.add_parser("stage", help="run one stage")
    s.add_argument("name", choices=STAGES)
    s.add_argument("release_dir", type=Path)

    w = sub.add_parser("watch", help="watch a folder for new software drops")
    w.add_argument("incoming", type=Path)
    w.add_argument("--mode", choices=["local", "gitlab"], default="local")
    w.add_argument("--interval", type=float, default=5.0)
    w.add_argument("--once", action="store_true", help="check once and exit")

    pr = sub.add_parser("prepare", help="prepare all new drops in <share>/CT_in")
    pr.add_argument("share", type=Path)

    q = sub.add_parser("queue", help="start open jobs in priority order")
    q.add_argument("share", type=Path)
    q.add_argument("--mode", choices=["local", "gitlab"], default="local",
                   help="local: execute here; gitlab: trigger one execution pipeline per job")

    e = sub.add_parser("execute", help="flash + test one prepared job")
    e.add_argument("share", type=Path)
    e.add_argument("--job", default=os.environ.get("JOB_ID"), help="job id (or $JOB_ID)")

    st = sub.add_parser("status", help="print the job table")
    st.add_argument("share", type=Path)

    d = sub.add_parser("demo", help="three ECUs end to end")
    d.add_argument("share", type=Path, nargs="?", default=Path("build/demo_share"))

    a = p.parse_args(argv)
    if a.cmd == "run":
        return 0 if run_all(a.release_dir, a.build, a.backend) else 1
    if a.cmd == "stage":
        return 0 if run_stage(a.name, a.release_dir, a.build, a.backend) else 1
    if a.cmd == "watch":
        watch(a.incoming, a.build, a.mode, a.interval, a.once)
        return 0
    if a.cmd == "prepare":
        jobs = orch.prepare(a.share, a.backend)
        return 0 if all(j["PREPARATION_STATUS"] == "OK" for j in jobs) else 1
    if a.cmd == "queue":
        orch.queue(a.share, a.mode, a.backend)
        return 0
    if a.cmd == "execute":
        if not a.job:
            p.error("execute needs --job or $JOB_ID")
        return 0 if orch.execute(a.share, a.job, a.backend) else 1
    if a.cmd == "status":
        print(orch.summary(a.share))
        return 0
    # demo
    orch.create_demo_share(a.share, EXAMPLES)
    print(f"Demo share: {a.share}\n")
    orch.prepare(a.share, a.backend)
    print()
    orch.queue(a.share, "local", a.backend)
    print("\n" + orch.summary(a.share))
    return 0


if __name__ == "__main__":
    sys.exit(main())
