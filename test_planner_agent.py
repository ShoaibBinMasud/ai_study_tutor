"""
Quick test for PlannerAgent.

Usage:
    cd ai_study_tutor
    python test_planner_agent.py

Reads content.json from the project root, runs the planner,
prints the result, and reports the trace file location.
"""

import json
import logging
import os
import sys

# Allow imports from src/
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from agents.planner_agent import PlannerAgent
from utils.gemini_client import GeminiLLMClient

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)

CONTENT_JSON = os.path.join(os.path.dirname(__file__), "content.json")
OUTPUT_FILE  = os.path.join(os.path.dirname(__file__), "plan_output.json")


def main():
    if not os.path.exists(CONTENT_JSON):
        print(f"ERROR: content.json not found at {CONTENT_JSON}")
        sys.exit(1)

    llm = GeminiLLMClient()               # reads GEMINI_API_KEY from .env
    agent = PlannerAgent(llm)

    print(f"\nRunning PlannerAgent on: {CONTENT_JSON}\n{'-'*60}")
    plan = agent.plan(CONTENT_JSON)

    # Save plan output
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(plan, f, indent=2, ensure_ascii=False)

    # Print summary
    if "error" in plan:
        print(f"\nPLAN FAILED: {plan['error']}")
    else:
        sources = plan.get("sources", [])
        path    = plan.get("final_learning_path", [])
        print(f"\nPlan complete:")
        print(f"  Sources   : {len(sources)}")
        print(f"  Total units: {sum(len(s.get('units', [])) for s in sources)}")
        print(f"  Learning path: {len(path)} steps")
        print(f"\nStudent overview:\n  {plan.get('student_overview', '(none)')}")
        print(f"\nFull plan saved → {OUTPUT_FILE}")

    # Print trace location
    traces = agent.trace_logger.list_traces()
    if traces:
        latest = traces[0]
        print(f"\nTrace saved → {latest['path']}")
        print(f"  Total time: {_load_total_ms(latest['path'])}")


def _load_total_ms(path: str) -> str:
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        ms = data.get("total_elapsed_ms", 0)
        steps = data.get("tool_calls", [])
        lines = [f"{ms/1000:.1f}s total, {len(steps)} LLM call(s)"]
        for s in steps:
            lines.append(f"    {s['tool_name']}({s['arguments'].get('source_id', '')}): {s['elapsed_ms']:.0f}ms")
        return "\n  ".join(lines)
    except Exception:
        return "(could not read trace)"


if __name__ == "__main__":
    main()
