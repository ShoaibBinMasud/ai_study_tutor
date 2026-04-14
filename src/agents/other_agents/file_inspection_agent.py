"""
FileInspectionAgent — Simple agent for inspecting uploaded files.

Takes file paths, inspects them, and generates a natural language
summary of what we're working with. Used by other agents to inform decisions.

Usage:
    from agents.file_inspection_agent import FileInspectionAgent
    from utils.llm_client import LLMClient

    agent = FileInspectionAgent(LLMClient())
    summary = agent.inspect(["physics.pdf", "lecture_notes.pptx"])
    print(summary)
    # Output: Natural language description of files
"""

import json
import logging
from pathlib import Path
from typing import List, Optional

from ..content.file_inspection_tool import inspect
from ..utils.llm_client import LLMClient

logger = logging.getLogger(__name__)


class FileInspectionAgent:
    """Simple agent that inspects files and describes them in natural language."""

    def __init__(self, llm_client: LLMClient):
        self.llm = llm_client

    def inspect(self, path_input) -> dict:
        """
        Inspect files and return structured data + natural language summary.

        Args:
            path_input: Can be:
                - Single file path (str)
                - List of file paths
                - Folder path (will scan all supported files)

        Returns:
            {
                "summary": "Natural language description",
                "files": [
                    {
                        "file_name": "...",
                        "file_type": "...",
                        "total_pages": ...,
                        "is_scanned": bool,
                        "has_toc": bool,
                        "toc_entry_count": int,
                        "avg_chars_per_page": float
                    },
                    ...
                ]
            }
        """
        if not path_input:
            return {
                "summary": "No files provided.",
                "files": []
            }

        # Inspect using the flexible inspect function
        inspections = inspect(path_input)

        if not inspections:
            return {
                "summary": "Could not inspect any files.",
                "files": []
            }

        # Generate natural language summary
        summary = self._summarize(inspections)

        return {
            "summary": summary,
            "files": inspections
        }

    def _summarize(self, inspections: list) -> str:
        """Use LLM to generate a natural language summary of the files."""
        prompt = f"""You are a file inspection summarizer. Look at these file inspections and generate a brief, natural language summary of what we have.

File inspections:
{json.dumps(inspections, indent=2)}

Generate a summary that includes:
1. Number of files and their types
2. Total pages across all documents
3. Whether any are scanned/handwritten
4. Whether any have usable table of contents
5. Key observations (e.g., "mostly PDFs", "mixed scanned and digital", etc.)

Keep it concise — 2-3 sentences max. Markdown format."""

        try:
            response = self.llm.chat(
                messages=[{"role": "user", "content": prompt}],
                max_tokens=500,
                temperature=0.1,
            )
            summary = response["choices"][0]["message"]["content"]
            logger.info(f"Generated file inspection summary")
            return summary
        except Exception as e:
            logger.error(f"Failed to generate summary: {e}")
            # Fallback to basic summary
            return self._basic_summary(inspections)

    @staticmethod
    def _basic_summary(inspections: list) -> str:
        """Fallback: basic summary if LLM fails."""
        file_count = len(inspections)
        total_pages = sum(f.get("total_pages", 0) for f in inspections if "total_pages" in f)
        has_scanned = any(f.get("is_scanned", False) for f in inspections)
        has_toc = any(f.get("has_toc", False) for f in inspections)

        lines = [f"**Files:** {file_count} document(s), {total_pages} total pages"]
        if has_scanned:
            lines.append("— includes scanned/image content")
        if has_toc:
            lines.append("— has table of contents")

        return " ".join(lines)


# ── Test ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 70)
    print("FileInspectionAgent Test")
    print("=" * 70)

    # Initialize agent
    llm = LLMClient()
    agent = FileInspectionAgent(llm)

    # Test 1: Single file
    print("\n[Test 1] Single file:")
    test_file = "sample_pdfs/physics_book.pdf"  # adjust path as needed
    if Path(test_file).exists():
        result = agent.inspect(test_file)
        print(f"Summary: {result['summary']}")
        print(f"Files found: {len(result['files'])}")
        for f in result['files']:
            print(f"  - {f['file_name']} ({f['file_type']}) "
                  f"{f['total_pages']} pages, scanned={f['is_scanned']}, "
                  f"toc={f['has_toc']}")
    else:
        print(f"  File not found: {test_file}")

    # Test 2: Multiple files
    print("\n[Test 2] Multiple files:")
    test_files = ["sample_pdfs/physic_lecture/lecture_1.pdf", "sample_pdfs/physic_lecture/lecture_2.pdf"]
    existing_files = [f for f in test_files if Path(f).exists()]
    if existing_files:
        result = agent.inspect(existing_files)
        print(f"Summary: {result['summary']}")
        print(f"Files found: {len(result['files'])}")
        for f in result['files']:
            print(f"  - {f['file_name']} ({f['file_type']}) "
                  f"{f['total_pages']} pages, scanned={f['is_scanned']}")
    else:
        print(f"  No files found. Adjust paths in test.")

    # Test 3: Folder
    print("\n[Test 3] Folder scan:")
    test_folder = "sample_pdfs/physic_lecture/"
    if Path(test_folder).exists():
        result = agent.inspect(test_folder)
        print(f"Summary: {result['summary']}")
        print(f"Files found: {len(result['files'])}")
        for f in result['files'][:5]:  # show first 5
            print(f"  - {f['file_name']} ({f['file_type']}) "
                  f"{f['total_pages']} pages")
        if len(result['files']) > 5:
            print(f"  ... and {len(result['files']) - 5} more")
    else:
        print(f"  Folder not found: {test_folder}")

    print("\n" + "=" * 70)
    print("Test complete. Update paths as needed for your test files.")
    print("=" * 70)
