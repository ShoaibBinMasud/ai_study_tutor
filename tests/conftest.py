"""
Shared fixtures for DocumentAgent tests.

- Initialises the agent once per session (expensive LLM client).
- Suppresses individual per-trace JSON files during tests.
- Collects every trace and writes one combined report at the end.
"""

import json
import os
import sys
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import pytest

# Make src importable
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from agents.document_agent import DocumentAgent
from utils.llm_client import LLMClient

# ── Paths ─────────────────────────────────────────────────────────────────────

BOOK      = "sample_pdfs/physics_book.pdf"
LEC_3     = "sample_pdfs/physic_lecture/lecture_3.pdf"
LEC_4     = "sample_pdfs/physic_lecture/lecture_4.pdf"
ALL_FILES = [BOOK, LEC_3, LEC_4]
FOLDER    = "sample_pdfs/test_folder"

TRACES_OUT = ".traces/test_suite_results.json"

# ── Session-scoped agent ───────────────────────────────────────────────────────

@pytest.fixture(scope="session")
def agent():
    """One DocumentAgent instance shared across all tests."""
    return DocumentAgent(LLMClient())


# ── Trace collector ───────────────────────────────────────────────────────────

_all_traces: list = []


@pytest.fixture(autouse=True)
def suppress_individual_traces(monkeypatch):
    """
    Replace TraceLogger.save with a no-op so individual JSON files are not
    written during tests. Traces are instead collected in _all_traces and
    written as one combined JSON at session end.
    """
    def _collect(self, trace):
        _all_traces.append(asdict(trace))
        return ""   # no file path

    monkeypatch.setattr(
        "utils.trace_logger.TraceLogger.save",
        _collect,
    )


def pytest_sessionfinish(session, exitstatus):
    """Write every collected trace to a single JSON after all tests finish."""
    if not _all_traces:
        return

    os.makedirs(".traces", exist_ok=True)
    report = {
        "generated_at": datetime.now().isoformat(),
        "total_scenarios": len(_all_traces),
        "passed": sum(1 for t in _all_traces if not t.get("error")),
        "traces": _all_traces,
    }
    with open(TRACES_OUT, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
    print(f"\n\nTest traces written → {TRACES_OUT}")
