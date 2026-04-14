"""
Interactive CLI test for PlanDrivenTutor.

Usage:
    cd ai_study_tutor
    python test_plan_driven_tutor.py

Commands during session:
    start / yes / ready   — begin or continue
    go to N               — jump to unit N (1-based)
    skip                  — skip current unit
    quit / exit           — end session
"""

import logging
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from agents.plan_driven_tutor import PlanDrivenTutor
from utils.llm_client import LLMClient
from config import get_model

logging.basicConfig(
    level=logging.WARNING,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)

PLAN_PATH = os.path.join(os.path.dirname(__file__), "plan_output.json")


def main():
    if not os.path.exists(PLAN_PATH):
        print(f"ERROR: plan_output.json not found at {PLAN_PATH}")
        print("Run test_planner_agent.py first to generate it.")
        sys.exit(1)

    llm = LLMClient(model=get_model("teaching_agent"))
    tutor = PlanDrivenTutor(llm, PLAN_PATH)

    print("\n" + "=" * 60)
    print(tutor.start())
    print("=" * 60)

    while True:
        try:
            msg = input("\nYou: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nSession ended.")
            break

        if not msg:
            continue
        if msg.lower() in ("quit", "exit"):
            print("Session ended.")
            break

        response = tutor.chat(msg)
        print(f"\nTutor:\n{response}")


if __name__ == "__main__":
    main()
