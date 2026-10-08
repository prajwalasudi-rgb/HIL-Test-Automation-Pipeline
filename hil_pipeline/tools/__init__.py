"""Tool adapters and the factory that picks a backend."""
from __future__ import annotations

import os

from .base import ExperimentTool, TestAutomationTool


def get_tools(backend: str | None = None) -> tuple[ExperimentTool, TestAutomationTool]:
    """Return (experiment_tool, test_automation_tool) for the chosen backend.

    backend: "mock" (default) or "dspace"; can also be set with the
    HIL_TOOL_BACKEND environment variable (e.g. in the CI job definition).
    """
    backend = backend or os.environ.get("HIL_TOOL_BACKEND", "mock")
    if backend == "mock":
        from .mock import MockExperimentTool, MockTestAutomationTool
        return MockExperimentTool(), MockTestAutomationTool()
    if backend == "dspace":
        from .dspace_com import DspaceExperimentTool, DspaceTestAutomationTool
        return (DspaceExperimentTool(os.environ["HIL_EXPERIMENT_PROGID"]),
                DspaceTestAutomationTool(os.environ["HIL_AUTOMATION_PROGID"]))
    raise ValueError(f"unknown tool backend '{backend}'")
