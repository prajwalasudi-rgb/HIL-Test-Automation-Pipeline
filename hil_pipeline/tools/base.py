"""Tool-adapter interfaces.

The pipeline never talks to a test tool directly. It talks to these two
interfaces, so the same pipeline can drive

  * the mock adapters (``tools/mock.py``) - run anywhere, used in CI and demos
  * real dSPACE tools via COM on a Windows HIL PC (``tools/dspace_com.py``)

ExperimentTool       ~ the role of ControlDesk: experiment / instrumentation
                       project with layouts for the release's signals
TestAutomationTool   ~ the role of AutomationDesk: test project, test-suite
                       import and execution
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from ..release import Release


class ExperimentTool(ABC):
    name = "experiment-tool"

    @abstractmethod
    def create_project(self, release: Release, suite: dict, out_dir: Path) -> Path:
        """Create the experiment project for this release and return its path."""


class TestAutomationTool(ABC):
    name = "test-automation-tool"

    @abstractmethod
    def create_project(self, release: Release, out_dir: Path) -> Path:
        """Create an empty test project for this release."""

    @abstractmethod
    def import_test_suite(self, project: Path, suite_file: Path) -> None:
        """Import the generated test suite into the project."""

    @abstractmethod
    def execute(self, project: Path, release: Release, suite: dict) -> list[dict]:
        """Run the test suite and return one result dict per test."""
