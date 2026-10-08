"""Watch the incoming folder for new software drops and trigger the pipeline.

A drop counts as complete when its manifest exists and no file in the folder
has changed for `settle_s` seconds (so half-copied releases are ignored).

Two trigger modes:
  * local  - run all pipeline stages right here (demo / single-PC setup)
  * gitlab - call the GitLab pipeline-trigger API, passing the release folder
             as a CI variable; runners on the HIL PCs then do the work
"""
from __future__ import annotations

import json
import os
import time
import urllib.parse
import urllib.request
from pathlib import Path

from .pipeline import run_all
from .release import MANIFEST_NAME

STATE_FILE = ".processed.json"


def _is_settled(folder: Path, settle_s: float) -> bool:
    newest = max((p.stat().st_mtime for p in folder.rglob("*") if p.is_file()), default=0)
    return (folder / MANIFEST_NAME).is_file() and time.time() - newest >= settle_s


def find_new_releases(incoming: Path, settle_s: float = 2.0) -> list[Path]:
    state = _load_state(incoming)
    return sorted(p for p in incoming.iterdir()
                  if p.is_dir() and p.name not in state and _is_settled(p, settle_s))


def _load_state(incoming: Path) -> dict:
    f = incoming / STATE_FILE
    return json.loads(f.read_text()) if f.is_file() else {}


def _mark_processed(incoming: Path, release: Path, result: str) -> None:
    state = _load_state(incoming)
    state[release.name] = {"result": result, "at": time.strftime("%Y-%m-%dT%H:%M:%S")}
    (incoming / STATE_FILE).write_text(json.dumps(state, indent=2))


def trigger_gitlab(release: Path) -> str:
    """Start a GitLab pipeline for this release (needs a pipeline trigger token)."""
    url = (f"{os.environ['GITLAB_URL'].rstrip('/')}/api/v4/projects/"
           f"{urllib.parse.quote(os.environ['GITLAB_PROJECT'], safe='')}/trigger/pipeline")
    data = urllib.parse.urlencode({
        "token": os.environ["GITLAB_TRIGGER_TOKEN"],
        "ref": os.environ.get("GITLAB_REF", "main"),
        "variables[RELEASE_DIR]": str(release),
    }).encode()
    with urllib.request.urlopen(urllib.request.Request(url, data=data), timeout=30) as resp:
        return json.loads(resp.read())["web_url"]


def watch(incoming: Path, build_root: Path, mode: str = "local",
          interval_s: float = 5.0, once: bool = False) -> None:
    incoming.mkdir(parents=True, exist_ok=True)
    print(f"[watch] watching {incoming} (mode: {mode})")
    while True:
        for release in find_new_releases(incoming):
            print(f"[watch] new software drop: {release.name}")
            if mode == "gitlab":
                result = trigger_gitlab(release)
                print(f"[watch] pipeline started: {result}")
            else:
                result = "passed" if run_all(release, build_root) else "failed"
                print(f"[watch] {release.name}: {result.upper()}")
            _mark_processed(incoming, release, result)
        if once:
            return
        time.sleep(interval_s)
