"""Command line: python -m hil_pipeline <command> ...

  run    <release_dir>              all stages for one release
  stage  <name> <release_dir>       a single stage (used by the CI jobs)
  watch  <incoming_dir>             wait for new software drops
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .pipeline import STAGES, run_all, run_stage
from .watcher import watch


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

    a = p.parse_args(argv)
    if a.cmd == "run":
        return 0 if run_all(a.release_dir, a.build, a.backend) else 1
    if a.cmd == "stage":
        return 0 if run_stage(a.name, a.release_dir, a.build, a.backend) else 1
    watch(a.incoming, a.build, a.mode, a.interval, a.once)
    return 0


if __name__ == "__main__":
    sys.exit(main())
