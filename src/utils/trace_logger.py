"""
TraceLogger — persists agent traces to JSON for later analysis.

Saves each trace to a timestamped JSON file in .traces/ directory.
Allows listing and loading previous traces for debugging.

Usage:
    logger = TraceLogger()
    logger.save(trace)              # saves to .traces/trace_YYYYMMDD_HHMMSS.json
    traces = logger.list_traces()   # get list of all traces
    trace = logger.load_trace(path) # load a specific trace
"""

import json
import logging
import os
from pathlib import Path
from typing import List, Dict, Optional
from datetime import datetime
from dataclasses import asdict

from utils.agent_tracer import AgentTrace

logger = logging.getLogger(__name__)

TRACES_DIR = ".traces"


class TraceLogger:
    """Persist and retrieve agent execution traces."""

    def __init__(self, traces_dir: str = TRACES_DIR):
        self.traces_dir = traces_dir
        os.makedirs(traces_dir, exist_ok=True)

    def save(self, trace: AgentTrace) -> str:
        """
        Save a trace to JSON file.

        Returns: path to saved file
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        # Sanitize request for filename — strip chars invalid on Windows
        req = trace.request.replace(" ", "_")[:30]
        req = "".join(c for c in req if c.isalnum() or c in ("_", "-"))
        filename = f"trace_{timestamp}_{req}.json"
        filepath = os.path.join(self.traces_dir, filename)

        try:
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(asdict(trace), f, indent=2)
            logger.info(f"Trace saved: {filepath}")
            return filepath
        except Exception as e:
            logger.error(f"Failed to save trace: {e}")
            return ""

    def list_traces(self) -> List[Dict]:
        """
        List all saved traces with metadata.

        Returns list of dicts: {filename, path, timestamp, request, tool_count}
        """
        traces = []
        try:
            for fname in sorted(os.listdir(self.traces_dir), reverse=True):
                if fname.endswith(".json"):
                    fpath = os.path.join(self.traces_dir, fname)
                    try:
                        with open(fpath, encoding="utf-8") as f:
                            data = json.load(f)
                        traces.append({
                            "filename": fname,
                            "path": fpath,
                            "timestamp": data.get("timestamp", "?"),
                            "request": data.get("request", "?")[:60],
                            "tool_count": len(data.get("tool_calls", [])),
                        })
                    except Exception as e:
                        logger.debug(f"Failed to read {fname}: {e}")
        except Exception as e:
            logger.error(f"Failed to list traces: {e}")

        return traces

    def load_trace(self, filepath: str) -> Optional[AgentTrace]:
        """Load and parse a trace from JSON file."""
        try:
            with open(filepath, encoding="utf-8") as f:
                data = json.load(f)
            # Reconstruct AgentTrace
            trace = AgentTrace(
                request=data.get("request", ""),
                timestamp=data.get("timestamp", ""),
                reasoning=data.get("reasoning", ""),
                final_response=data.get("final_response", ""),
                total_elapsed_ms=data.get("total_elapsed_ms", 0),
                tool_calls=[],
            )
            return trace
        except Exception as e:
            logger.error(f"Failed to load trace: {e}")
            return None

    def format_trace_file(self, filepath: str) -> str:
        """Load and format a trace file as markdown."""
        trace = self.load_trace(filepath)
        if trace is None:
            return f"Failed to load: {filepath}"

        from utils.agent_tracer import AgentTracer
        return AgentTracer.format_trace(trace)
