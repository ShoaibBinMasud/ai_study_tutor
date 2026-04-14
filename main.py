#!/usr/bin/env python3
"""
AI STEM Tutor — Main Entry Point

An adaptive AI tutoring system that:
- Auto-detects the subject from uploaded materials
- Builds a concept map and dependency graph on file upload
- Creates scope-aware teaching plans (section, chapter, exam prep)
- Teaches dynamically with merit-based adaptation
- Supports PDF, images, PPTX, DOCX, and plain text

Usage:
    python main.py <file1> [file2 ...]

Examples:
    python main.py physics_textbook.pdf
    python main.py textbook.pdf lecture_notes.pptx
    python main.py notes.pdf extra_slides.pdf

Type 'quit' or 'exit' to stop.
"""

import logging
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# Add src to Python path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from agents.tutor_agent import TutorAgent

logging.basicConfig(
    level=logging.INFO,
    format="%(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

BANNER = """
╔══════════════════════════════════════════════════════════════╗
║              AI ADAPTIVE STEM TUTOR                         ║
║  Fully agentic · Auto-detects subject · Merit-adaptive       ║
╚══════════════════════════════════════════════════════════════╝"""

HELP_TEXT = """
Just talk naturally:
  "teach me section 1-2"
  "I have a midterm on chapters 1-5 tomorrow"
  "I don't understand the Michelson interferometer"
  "what's in chapter 3?"
  "continue"
  load <file_path>   — add more study materials
  help               — show this message
  quit / exit        — end session
"""


def print_response(response: str):
    """Print the tutor's response with formatting."""
    print(f"\nTutor: {response}\n")


def main():
    if len(sys.argv) < 2:
        print(BANNER)
        print("\nUsage: python main.py <file1> [file2 ...]\n")
        print("Examples:")
        print("  python main.py textbook.pdf")
        print("  python main.py textbook.pdf slides.pptx notes.docx")
        sys.exit(1)

    file_paths = sys.argv[1:]

    # Validate files exist
    missing = [f for f in file_paths if not os.path.exists(f)]
    if missing:
        for m in missing:
            print(f"Error: File not found: {m}")
        sys.exit(1)

    # Load API key
    api_key = os.getenv("OPENAI_API_KEY") or os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        print("Error: No API key found.")
        print("Set OPENAI_API_KEY in your .env file or environment.")
        sys.exit(1)

    # Determine model
    model = os.getenv("TUTOR_MODEL", "gpt-4o-mini")

    print(BANNER)
    print(f"\nLoading {len(file_paths)} file(s)...\n")

    # Initialize agent
    try:
        tutor = TutorAgent(api_key=api_key, model=model)
    except Exception as e:
        print(f"Error initializing tutor: {e}")
        sys.exit(1)

    # Load files
    try:
        load_response = tutor.load_files(file_paths)
        print_response(load_response)
    except Exception as e:
        print(f"Error loading files: {e}")
        logger.error("File loading error", exc_info=True)
        sys.exit(1)

    print(HELP_TEXT)
    print("─" * 64)

    # Main loop
    while True:
        try:
            user_input = input("\nYou: ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\n\nGoodbye! Good luck with your studies.")
            break

        if not user_input:
            continue

        if user_input.lower() in ("quit", "exit", "q"):
            print("\nGoodbye! Good luck with your studies.")
            break

        if user_input.lower() == "help":
            print(HELP_TEXT)
            continue

        # Handle inline load command: "load /path/to/file.pdf"
        if user_input.lower().startswith("load "):
            extra_path = user_input[5:].strip()
            if not os.path.exists(extra_path):
                print(f"\nTutor: File not found: {extra_path}\n")
                continue
            try:
                response = tutor.load_files([extra_path])
                print_response(response)
            except Exception as e:
                print(f"\nTutor: Error loading {extra_path}: {e}\n")
            continue

        # Regular chat
        try:
            response = tutor.chat(user_input)
            print_response(response)
        except KeyboardInterrupt:
            print("\n\n[Interrupted]\n")
        except Exception as e:
            print(f"\nTutor: Something went wrong: {e}\n")
            logger.error("Chat error", exc_info=True)


if __name__ == "__main__":
    main()
