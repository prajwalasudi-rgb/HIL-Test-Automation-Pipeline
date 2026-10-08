"""Where real dSPACE tools plug in (Windows HIL PC only).

In a production setup these adapters run on a GitLab runner installed on the
Windows PC attached to the HIL simulator, and drive the dSPACE tools through
their COM automation interfaces (Python + pywin32):

  ExperimentTool       -> ControlDesk: open/create the experiment, add the
                          platform and variable description of the new
                          software, generate layouts, save the project
  TestAutomationTool   -> AutomationDesk: create the test project, import the
                          generated test suite, execute it, export the report

The exact COM object names, methods and their arguments depend on the
installed dSPACE release, so they are intentionally NOT reproduced here -
implement the methods below against the automation API documentation that
ships with your dSPACE installation. Everything else in this repository
(watching for releases, test generation, CI stages, reporting) stays the same.
"""
from __future__ import annotations

import sys
from pathlib import Path

from ..release import Release
from .base import ExperimentTool, TestAutomationTool


def _dispatch(prog_id: str):
    if sys.platform != "win32":
        raise RuntimeError("dSPACE COM automation is only available on Windows")
    import win32com.client  # pywin32, installed on the HIL PC only
    return win32com.client.Dispatch(prog_id)


class DspaceExperimentTool(ExperimentTool):
    name = "dspace-controldesk"

    def __init__(self, prog_id: str):
        self.prog_id = prog_id  # taken from configuration, see README

    def create_project(self, release: Release, suite: dict, out_dir: Path) -> Path:
        app = _dispatch(self.prog_id)
        raise NotImplementedError(
            "Implement with your ControlDesk version's automation API "
            f"(application object: {app!r})")


class DspaceTestAutomationTool(TestAutomationTool):
    name = "dspace-automationdesk"

    def __init__(self, prog_id: str):
        self.prog_id = prog_id

    def create_project(self, release: Release, out_dir: Path) -> Path:
        raise NotImplementedError("Implement with your AutomationDesk automation API")

    def import_test_suite(self, project: Path, suite_file: Path) -> None:
        raise NotImplementedError("Implement with your AutomationDesk automation API")

    def execute(self, project: Path, release: Release, suite: dict) -> list[dict]:
        raise NotImplementedError("Implement with your AutomationDesk automation API")
